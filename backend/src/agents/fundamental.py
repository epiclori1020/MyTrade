"""Fundamental Analyst Agent — LLM-based stock analysis.

Uses direct Anthropic SDK (not Agno) for Step 5. Reasons:
1. Single agent — no multi-agent coordination needed (Agno coordinate mode = Step 8+)
2. messages.parse() gives native Pydantic structured output
3. Clear token tracking via response.usage
4. Better testability (mock one client call vs Agno internals)

Agno stays in dependencies for Step 8+ (Team coordinate mode).
"""

import logging
from functools import lru_cache

import anthropic
from pydantic import BaseModel, Field

from src.config import get_settings
from src.services.exceptions import AgentError

logger = logging.getLogger(__name__)

MODEL_ID = "claude-sonnet-4-6"

# 4096 output tokens for ~1500-3000 token JSON response.
# 30K budget from agents.md is input+output total, not output only.
MAX_OUTPUT_TOKENS = 4096

# Deterministic mapping from DB source field to API endpoint
SOURCE_ENDPOINTS = {
    "finnhub": "/stock/metric",
    "alpha_vantage": "OVERVIEW",
}


# --- Pydantic Output Schema ---
# Compatible with claim-schema.json source_primary format


class DataPoint(BaseModel):
    value: float | None = None
    unit: str  # "USD", "USD_B", "pct", "ratio"
    source: str  # "finnhub", "alpha_vantage", "calculated"
    period: str  # "TTM", "2026-Q1"
    retrieved_at: str  # ISO-8601


class BusinessModel(BaseModel):
    description: str
    moat_assessment: str  # reasoning about competitive advantage
    revenue_segments: str


class Financials(BaseModel):
    revenue: DataPoint | None = None
    net_income: DataPoint | None = None
    free_cash_flow: DataPoint | None = None
    eps: DataPoint | None = None
    roe: DataPoint | None = None
    roic: DataPoint | None = None


class Valuation(BaseModel):
    pe_ratio: DataPoint | None = None
    pb_ratio: DataPoint | None = None
    ev_ebitda: DataPoint | None = None
    fcf_yield: DataPoint | None = None
    assessment: str  # "undervalued|fairly_valued|overvalued" + reasoning


class Quality(BaseModel):
    f_score: DataPoint | None = None
    z_score: DataPoint | None = None
    assessment: str


class SourceEntry(BaseModel):
    provider: str  # "finnhub", "alpha_vantage", "calculated"
    endpoint: str  # "/stock/metric", "OVERVIEW"
    retrieved_at: str  # ISO-8601


class FundamentalAnalysis(BaseModel):
    business_model: BusinessModel
    financials: Financials
    valuation: Valuation
    quality: Quality
    moat_rating: str = Field(description="none, narrow, or wide")
    score: int = Field(ge=0, le=100, description="Overall fundamental score 0-100")
    risks: list[str]
    sources: list[SourceEntry]


# --- System Prompt (German, per agents.md Agent 3) ---

SYSTEM_PROMPT = """Du bist ein leitender Equity-Research-Analyst. Führe eine Fundamentalanalyse durch:

1) **Geschäftsmodell:** Beschreibe das Geschäftsmodell, Umsatzsegmente und bewerte den Moat (none/narrow/wide).

2) **Finanzen:** Analysiere die bereitgestellten TTM-Daten:
   - Revenue, Net Income, Free Cash Flow, EPS
   - ROE, ROIC (falls verfügbar)

3) **Bewertung:** Bewerte anhand verfügbarer Kennzahlen:
   - P/E Ratio, P/B Ratio, EV/EBITDA (falls verfügbar)
   - FCF Yield (berechne aus FCF / Marktkapitalisierung falls Kurs verfügbar)
   - Gesamtbewertung: undervalued, fairly_valued, oder overvalued mit Begründung

4) **Qualität:** Bewerte anhand von F-Score und Z-Score (falls verfügbar).

**KRITISCHE REGELN:**
- Wenn Daten NULL oder nicht verfügbar sind → setze value: null. Erfinde KEINE Zahlen.
- Nur TTM-Daten verfügbar, keine historische Zeitreihe — beziehe dich darauf.
- Keine Peer-Daten verfügbar — keine Peer-Vergleiche.
- Jede Zahl MUSS im Format {value, unit, source, period, retrieved_at} sein.
- Die source und retrieved_at Felder MÜSSEN exakt die Werte aus den bereitgestellten Daten übernehmen.
- Der score (0-100) bewertet die Gesamtattraktivität der Aktie als Fundamentalinvestment.
- Alle Risiken müssen konkret und spezifisch für das Unternehmen sein.
- In der sources-Liste alle verwendeten Datenquellen mit {provider, endpoint, retrieved_at} angeben."""


@lru_cache(maxsize=1)
def _get_client() -> anthropic.Anthropic:
    """Lazy singleton — created on first LLM call, not at import time."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")
    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=120.0,  # LLM calls can take 30-60s
        max_retries=2,  # SDK auto-retries on HTTP 429/500
    )


def _format_number(value, label: str) -> str:
    """Format a number for the prompt, or mark as unavailable."""
    if value is None:
        return f"{label}: NICHT VERFÜGBAR"
    if isinstance(value, (int, float)) and abs(value) >= 1_000_000_000:
        return f"{label}: {value:,.0f} USD"
    return f"{label}: {value}"


def _format_ratio_pct(value, label: str) -> str:
    """Format a ratio as value with percentage (e.g. ROE 1.45 → '1.45 (145%)')."""
    if value is None:
        return f"{label}: NICHT VERFÜGBAR"
    return f"{label}: {value} ({value * 100:.0f}%)"


def _build_user_prompt(
    ticker: str, fundamentals: dict, current_price: dict | None
) -> str:
    """Build the user prompt from DB data."""
    source = fundamentals.get("source", "unknown")
    endpoint = SOURCE_ENDPOINTS.get(source, "unknown")
    fetched_at = fundamentals.get("fetched_at", "unknown")
    period = fundamentals.get("period", "TTM")

    lines = [
        f"Analysiere die Fundamentaldaten von {ticker}.",
        "",
        "=== FUNDAMENTALDATEN ===",
        f"Ticker: {ticker}",
        f"Periode: {period}",
        f"Quelle: {source}",
        f"Endpoint: {endpoint}",
        f"Abgerufen: {fetched_at}",
        "",
        _format_number(fundamentals.get("revenue"), "Revenue"),
        _format_number(fundamentals.get("net_income"), "Net Income"),
        _format_number(fundamentals.get("free_cash_flow"), "Free Cash Flow"),
        _format_number(fundamentals.get("eps"), "EPS"),
        _format_number(fundamentals.get("pe_ratio"), "P/E Ratio (TTM)"),
        _format_number(fundamentals.get("pb_ratio"), "P/B Ratio"),
        _format_number(fundamentals.get("ev_ebitda"), "EV/EBITDA"),
        _format_ratio_pct(fundamentals.get("roe"), "ROE"),
        _format_ratio_pct(fundamentals.get("roic"), "ROIC"),
        _format_number(fundamentals.get("f_score"), "F-Score"),
        _format_number(fundamentals.get("z_score"), "Z-Score"),
    ]

    lines.append("")
    if current_price:
        price_val = current_price.get("close")
        price_date = current_price.get("date", "unknown")
        price_source = current_price.get("source", "unknown")
        lines.append("=== AKTUELLER KURS ===")
        lines.append(f"Kurs: {price_val} USD (Datum: {price_date})")
        lines.append(f"Quelle: {price_source}")
    else:
        lines.append("=== AKTUELLER KURS ===")
        lines.append(
            "NICHT VERFÜGBAR — Bewertungskennzahlen (FCF Yield, etc.) ggf. eingeschränkt."
        )

    lines.extend([
        "",
        "=== HINWEISE ===",
        '- Felder mit "NICHT VERFÜGBAR" dürfen NICHT geschätzt oder erfunden werden → setze value: null',
        "- Nur TTM-Daten verfügbar, keine historische Zeitreihe",
        "- Keine Peer-Daten verfügbar",
    ])

    return "\n".join(lines)


def call_fundamental_agent(
    ticker: str, fundamentals: dict, current_price: dict | None
) -> tuple[dict, dict]:
    """Call the Fundamental Analyst LLM and return structured analysis.

    Returns:
        (analysis_dict, usage_dict) where usage_dict has input_tokens and output_tokens.

    Raises:
        AgentError: On API errors, timeouts, or parse failures after retry.
    """
    client = _get_client()
    user_prompt = _build_user_prompt(ticker, fundamentals, current_price)
    total_usage = {"input_tokens": 0, "output_tokens": 0}

    try:
        response = client.messages.parse(
            model=MODEL_ID,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            output_format=FundamentalAnalysis,
        )

        total_usage["input_tokens"] = response.usage.input_tokens
        total_usage["output_tokens"] = response.usage.output_tokens

        if response.parsed_output is None:
            raise AgentError(
                agent_name="fundamental_analyst",
                message=f"LLM returned no parsed output (stop_reason: {response.stop_reason})",
                error_type="parse_failed",
                usage=total_usage,
            )

        return response.parsed_output.model_dump(), total_usage

    except AgentError:
        raise

    except anthropic.APITimeoutError as exc:
        raise AgentError(
            agent_name="fundamental_analyst",
            message=f"API timeout: {exc}",
            error_type="timeout",
            usage=total_usage,
        ) from exc

    except anthropic.APIError as exc:
        raise AgentError(
            agent_name="fundamental_analyst",
            message=f"API error ({exc.status_code}): {exc.message}",
            error_type="api_error",
            usage=total_usage,
        ) from exc

    except Exception as exc:
        raise AgentError(
            agent_name="fundamental_analyst",
            message=f"Unexpected error: {exc}",
            error_type="unexpected",
            usage=total_usage,
        ) from exc
