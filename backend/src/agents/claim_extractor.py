"""Claim Extractor Agent — extracts verifiable claims from agent outputs.

Uses Haiku (Light Tier) for schema-bound extraction with fallback to Sonnet.
Pattern: Same as fundamental.py — _get_client singleton, messages.parse(), AgentError.

Fallback chain per agents.md:
  Haiku attempt 1 -> Haiku retry (with error context) -> Sonnet fallback -> AgentError
"""

import json
import logging
from functools import lru_cache
from typing import Literal

import anthropic
from pydantic import BaseModel

from src.config import get_settings
from src.services.error_logger import log_error
from src.services.exceptions import AgentError
from src.services.llm_json_repair import extract_raw_text, try_repair_json

logger = logging.getLogger(__name__)

MODEL_HAIKU = "claude-haiku-4-5"
MODEL_SONNET = "claude-sonnet-4-6"
MAX_OUTPUT_TOKENS = 4096

# Pricing per token (as of 2026-03)
HAIKU_INPUT_PRICE = 0.80 / 1_000_000  # $0.80/MTok
HAIKU_OUTPUT_PRICE = 4.00 / 1_000_000  # $4.00/MTok
SONNET_INPUT_PRICE = 3.00 / 1_000_000  # $3.00/MTok
SONNET_OUTPUT_PRICE = 15.00 / 1_000_000  # $15.00/MTok


# --- Pydantic Output Schema ---


class RawClaim(BaseModel):
    claim_text: str  # "AAPL Revenue TTM: $394.3B"
    claim_type: Literal["number", "ratio", "event", "opinion", "forecast"]
    value: float | None  # Numeric value, None for opinions/events
    unit: str  # "USD", "USD_B", "pct", "ratio", "text", "score"
    ticker: str
    period: str  # "TTM", "FY2025", "current"
    source: str  # "finnhub", "alpha_vantage", "calculated"
    retrieved_at: str  # ISO-8601


class RawClaimsOutput(BaseModel):
    claims: list[RawClaim]


# --- System Prompt ---

SYSTEM_PROMPT = """Du bist ein Daten-Extraktions-Spezialist. Extrahiere alle verifizierbaren numerischen und faktischen Claims aus dem Agent-Output. Jeder Claim muss dem vorgegebenen Schema entsprechen. Erfinde KEINE Zahlen — extrahiere NUR was im Input vorhanden ist.

FÜR JEDES DataPoint-Feld im JSON:
1. Erstelle einen Claim mit dem exakten Wert, der Unit, der Quelle und dem Zeitstempel.
2. claim_type bestimmen:
   - "number" für absolute Werte (Revenue, Net Income, EPS, FCF)
   - "ratio" für Verhältniszahlen (P/E, P/B, EV/EBITDA, ROE, ROIC, FCF Yield, F-Score, Z-Score)
   - "opinion" für qualitative Bewertungen (Moat-Bewertung, Valuation Assessment, Quality Assessment)
   - "forecast" für Prognosen
   - "event" für Ereignisse
3. value: Exakter numerischer Wert für number/ratio. null für opinion/event/forecast.
4. unit: "USD" für Dollar-Beträge, "ratio" für Verhältniszahlen, "pct" für Prozent, "text" für Meinungen, "score" für Scores.
5. source: Exakt den Wert aus dem "source"-Feld des DataPoint übernehmen.
6. retrieved_at: Exakt den ISO-8601 Timestamp aus dem "retrieved_at"-Feld übernehmen.
7. period: Exakt den Wert aus dem "period"-Feld des DataPoint übernehmen.

REGELN:
- NUR Claims extrahieren die im JSON vorhanden sind. KEINE Zahlen erfinden.
- Überspringe DataPoints mit value: null (keine verifizierbaren Werte).
- Für opinion-Claims (Moat-Bewertung, Valuation Assessment): claim_text = die Bewertung, value = null.
- Für den Overall Score: claim_type = "number", value = der Score-Wert, unit = "score".
- Risiken als einzelne forecast/opinion Claims extrahieren.
- Jeder Claim braucht ALLE Felder: claim_text, claim_type, value, unit, ticker, period, source, retrieved_at."""


@lru_cache(maxsize=1)
def _get_client() -> anthropic.Anthropic:
    """Lazy singleton — created on first LLM call, not at import time."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")
    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=60.0,  # Haiku is 3-5x faster than Sonnet, 60s is sufficient
        max_retries=2,  # SDK auto-retries on HTTP 429/500
    )


def _calculate_attempt_cost(
    input_tokens: int, output_tokens: int, model: str
) -> float:
    """Calculate cost for a single attempt based on the model used."""
    if model == MODEL_HAIKU:
        return input_tokens * HAIKU_INPUT_PRICE + output_tokens * HAIKU_OUTPUT_PRICE
    return input_tokens * SONNET_INPUT_PRICE + output_tokens * SONNET_OUTPUT_PRICE


def _attempt_extraction(
    client: anthropic.Anthropic,
    model: str,
    user_prompt: str,
) -> tuple[list[dict] | None, dict, str | None]:
    """Single extraction attempt via messages.parse().

    Returns:
        (parsed_claims_or_none, usage_dict, error_description_or_none)
        - parsed_claims: list of claim dicts if successful, None if parse failed
        - usage_dict: {"input_tokens": N, "output_tokens": N}
        - error_description: str describing failure, None if success

    Raises:
        AgentError: On hard API errors (timeout, 500) — NOT on parse failures.
    """
    usage = {"input_tokens": 0, "output_tokens": 0}

    response = client.messages.parse(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        output_format=RawClaimsOutput,
    )

    usage["input_tokens"] = response.usage.input_tokens
    usage["output_tokens"] = response.usage.output_tokens

    if response.parsed_output is None:
        # Try JSON repair before giving up this attempt
        raw_text = extract_raw_text(response)
        if raw_text:
            repaired = try_repair_json(raw_text, RawClaimsOutput)
            if repaired is not None:
                logger.info("JSON repair succeeded for claim_extractor (%s)", model)
                log_error("claim_extractor", "json_repair", f"Repaired malformed JSON output ({model})")
                claims = [claim.model_dump() for claim in repaired.claims]
                return claims, usage, None

        error_desc = f"No parsed output (stop_reason: {response.stop_reason})"
        return None, usage, error_desc

    claims = [claim.model_dump() for claim in response.parsed_output.claims]
    return claims, usage, None


def call_claim_extractor(
    ticker: str,
    fundamental_out: dict,
) -> tuple[list[dict], dict]:
    """Extract claims from fundamental analysis output using Haiku with Sonnet fallback.

    Returns:
        (raw_claims_list, usage_dict) where usage_dict has:
        input_tokens, output_tokens, cost_usd, model_used

    Raises:
        AgentError: On all extraction attempts failing, API errors, or timeouts.
    """
    client = _get_client()
    user_prompt = (
        f"Extrahiere alle verifizierbaren Claims aus folgendem "
        f"Fundamental-Analyse-Output für {ticker}:\n\n"
        f"{json.dumps(fundamental_out, indent=2, ensure_ascii=False)}"
    )

    total_usage = {"input_tokens": 0, "output_tokens": 0}
    total_cost = 0.0
    last_model = MODEL_HAIKU  # Tracks which model was last attempted (for error reporting)

    try:
        # --- Attempt 1: Haiku with original prompt ---
        claims, usage, error_desc = _attempt_extraction(client, MODEL_HAIKU, user_prompt)
        total_usage["input_tokens"] += usage["input_tokens"]
        total_usage["output_tokens"] += usage["output_tokens"]
        total_cost += _calculate_attempt_cost(
            usage["input_tokens"], usage["output_tokens"], MODEL_HAIKU
        )

        if claims is not None:
            return claims, {
                **total_usage,
                "cost_usd": total_cost,
                "model_used": MODEL_HAIKU,
            }

        logger.warning("Haiku attempt 1 failed: %s — retrying with error context", error_desc)

        # --- Attempt 2: Haiku retry with error context ---
        retry_prompt = (
            user_prompt
            + "\n\n[RETRY] Dein vorheriger Output war nicht schema-konform. "
            f"Fehler: {error_desc}. "
            "Korrigiere und gib NUR valides JSON zurück."
        )

        claims, usage, error_desc = _attempt_extraction(client, MODEL_HAIKU, retry_prompt)
        total_usage["input_tokens"] += usage["input_tokens"]
        total_usage["output_tokens"] += usage["output_tokens"]
        total_cost += _calculate_attempt_cost(
            usage["input_tokens"], usage["output_tokens"], MODEL_HAIKU
        )

        if claims is not None:
            return claims, {
                **total_usage,
                "cost_usd": total_cost,
                "model_used": MODEL_HAIKU,
            }

        logger.warning("Haiku attempt 2 failed: %s — falling back to Sonnet", error_desc)

        # --- Attempt 3: Sonnet fallback with original prompt (clean input) ---
        last_model = MODEL_SONNET
        claims, usage, error_desc = _attempt_extraction(client, MODEL_SONNET, user_prompt)
        total_usage["input_tokens"] += usage["input_tokens"]
        total_usage["output_tokens"] += usage["output_tokens"]
        total_cost += _calculate_attempt_cost(
            usage["input_tokens"], usage["output_tokens"], MODEL_SONNET
        )

        if claims is not None:
            return claims, {
                **total_usage,
                "cost_usd": total_cost,
                "model_used": MODEL_SONNET,
            }

        # All attempts failed
        raise AgentError(
            agent_name="claim_extractor",
            message=f"All extraction attempts failed. Last error: {error_desc}",
            error_type="extraction_failed",
            usage={**total_usage, "cost_usd": total_cost, "model_used": last_model},
        )

    except AgentError:
        raise

    except anthropic.APITimeoutError as exc:
        raise AgentError(
            agent_name="claim_extractor",
            message=f"API timeout: {exc}",
            error_type="timeout",
            usage={**total_usage, "cost_usd": total_cost, "model_used": last_model},
        ) from exc

    except anthropic.APIError as exc:
        raise AgentError(
            agent_name="claim_extractor",
            message=f"API error ({exc.status_code}): {exc.message}",
            error_type="api_error",
            usage={**total_usage, "cost_usd": total_cost, "model_used": last_model},
        ) from exc

    except Exception as exc:
        raise AgentError(
            agent_name="claim_extractor",
            message=f"Unexpected error: {exc}",
            error_type="unexpected",
            usage={**total_usage, "cost_usd": total_cost, "model_used": last_model},
        ) from exc
