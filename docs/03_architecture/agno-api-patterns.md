# Agno API Patterns — MyTrade

> **Quelle:** Agno-Dokumentation via Context7 MCP (Feb 2026)
> **Scope:** WIE man Agents mit Agno baut. WAS die Agents tun → @docs/03_architecture/agents.md

---

## 1. Dependencies

```
agno
agno[anthropic]
agno[postgres]
agno[sql]
```

Relevante Imports:

```python
from agno.agent import Agent, RunOutput
from agno.models.anthropic import Claude
from agno.db.postgres import PostgresDb
from agno.team import Team
from agno.team.mode import TeamMode
```

---

## 2. Agent-Erstellung (3-Tier Model-Mix)

```python
from agno.agent import Agent
from agno.models.anthropic import Claude

agent = Agent(
    name="Fundamental Analyst",
    model=Claude(id="claude-sonnet-4-6"),
    description="Senior Equity Research Analyst",
    instructions=["Jede Zahl mit {value, source, timestamp}.", "Strukturiertes JSON."],
    tools=[get_stock_fundamentals],       # Custom Functions oder Tool-Klassen
    output_schema=FundamentalAnalysis,    # Pydantic Model (Section 5)
    markdown=True,
)

response: RunOutput = agent.run("Analyze AAPL fundamentals")
```

### Agent → Tier → Model Mapping

| Agent | Tier | Model-ID | Token-Budget | Step |
|-------|------|----------|-------------|------|
| Fundamental Analyst | Standard | `claude-sonnet-4-6` | ~30K | 5 |
| Macro Analyst | Standard | `claude-sonnet-4-6` | ~15K | Phase 2+ |
| Technical Analyst | Standard | `claude-sonnet-4-6` | ~10K | Phase 2+ |
| Sentiment Analyst | Standard | `claude-sonnet-4-6` | ~8K | Phase 2+ |
| Risk Manager | Standard | `claude-sonnet-4-6` | ~12K | Phase 2+ |
| Devil's Advocate | Heavy | `claude-opus-4-6` | ~15K | Phase 2+ |
| Portfolio Synthesizer | Heavy | `claude-opus-4-6` | ~10K | Phase 2+ |
| Claim Extractor | Light | `claude-haiku-4-5` | ~5K | 6 |
| Verification Agent | Light | `claude-haiku-4-5` | ~3K | 7 |

> **Data Collector + Policy Engine** sind deterministisches Python — KEIN Agno, kein LLM.

---

## 3. Model-IDs + Konfiguration

```python
# Heavy (Opus) — Devil's Advocate, Synthesizer
Claude(id="claude-opus-4-6", max_tokens=8192, cache_system_prompt=True)

# Standard (Sonnet) — Analyse-Agents
Claude(id="claude-sonnet-4-6", max_tokens=4096, cache_system_prompt=True)

# Light (Haiku) — Extraktion, Verification
Claude(id="claude-haiku-4-5", max_tokens=4096, cache_system_prompt=True)
```

> **TODO Step 3:** Model-IDs per Smoke-Test verifizieren. Die Agno-Docs zeigen teilweise
> `claude-sonnet-4-5-20250929` als Format. Testen: `Claude(id="claude-sonnet-4-6")` —
> falls Fehler, auf versionierten String wechseln.

---

## 4. Tool-Integration

Agno akzeptiert einfache Python-Funktionen als Tools:

```python
import os
import httpx
import json

def get_stock_fundamentals(ticker: str) -> str:
    """Fetch fundamental data from Finnhub for a given ticker."""
    response = httpx.get(
        "https://finnhub.io/api/v1/stock/metric",
        params={
            "symbol": ticker,
            "metric": "all",
            "token": os.environ["FINNHUB_API_KEY"],
        },
    )
    return json.dumps(response.json())

agent = Agent(
    model=Claude(id="claude-sonnet-4-6"),
    tools=[get_stock_fundamentals],  # Funktion direkt übergeben
)
```

Für direkte DB-Queries (optional, nur wenn Agent selbst SQL braucht):

```python
from agno.tools.sql import SQLTools
agent = Agent(tools=[SQLTools(db_url="postgresql+psycopg://...")])
```

---

## 5. Structured Output (Pydantic)

```python
from pydantic import BaseModel, Field

class FundamentalAnalysis(BaseModel):
    """Vereinfacht — wird in Step 5 mit voll typisierten Nested Models definiert."""
    business_model: str
    financials: dict       # Step 5: eigenes Pydantic Model
    valuation: dict        # Step 5: eigenes Pydantic Model
    quality: dict          # Step 5: eigenes Pydantic Model
    moat_rating: str
    score: int = Field(ge=0, le=100)
    sources: list[dict]

agent = Agent(
    model=Claude(id="claude-sonnet-4-6"),
    output_schema=FundamentalAnalysis,
)

response = agent.run("Analyze AAPL")
analysis: FundamentalAnalysis = response.content  # Typisiert
```

> Pydantic-Models für Claims → @docs/04_verification/claim-schema.json. Werden in Steps 5-7 definiert.

---

## 6. FastAPI Integration

**Empfehlung: Manuelle Integration** (nicht AgentOS). Grund: MyTrade braucht custom Auth-Middleware,
Pre/Full-Policy Checks um Agent-Calls herum, und strukturierte Error-Responses. AgentOS generiert
eigene Endpoints die diesen Pipeline-Flow nicht abbilden.

```python
from fastapi import FastAPI, Depends, HTTPException

app = FastAPI(title="MyTrade API")

@app.post("/api/analyze/{ticker}")
async def analyze(ticker: str, user = Depends(get_current_user)):
    # 1. Pre-Policy (deterministisch — kein LLM)
    policy_check = pre_policy_check(ticker, user.id)
    if not policy_check.allowed:
        raise HTTPException(403, detail=policy_check.reason)

    # 2. Data Collection (deterministisch)
    await data_collector.fetch(ticker)

    # 3. Agent Analysis (Agno)
    try:
        response = await fundamental_agent.arun(prompt)
    except Exception as e:
        # Log to error_log, return partial result
        await log_error("fundamental_agent", str(e))
        raise HTTPException(502, detail="Agent analysis failed")

    # 4. Claim Extraction + Verification (Steps 6-7)
    # 5. Full-Policy Check (Step 8)
    # 6. Return Investment Note
    return response.content
```

---

## 7. Async Execution

```python
# MVP (Step 5): Sequenziell, 1 Agent
response = await fundamental_agent.arun("Analyze AAPL")

# Phase 2+: Parallel, mehrere Agents gleichzeitig
import asyncio
macro, fundamental, technical, sentiment = await asyncio.gather(
    macro_agent.arun(macro_prompt),
    fundamental_agent.arun(fund_prompt),
    technical_agent.arun(tech_prompt),
    sentiment_agent.arun(sent_prompt),
)
```

---

## 8. PostgreSQL Storage (Supabase)

Agno speichert Agent-Memory/Sessions in eigenen Tabellen (getrennt von MyTrade-App-Tabellen).

```python
from agno.db.postgres import PostgresDb

db = PostgresDb(db_url="postgresql+psycopg://user:pw@host:5432/postgres")

agent = Agent(
    model=Claude(id="claude-sonnet-4-6"),
    db=db,
    # WICHTIG: add_history_to_context=False (Default) für Analyse-Agents.
    # MyTrade-Analysen sind stateless — jede Analyse ist unabhängig.
    # History im Kontext würde Ergebnisse verfälschen.
)

# user_id für Audit-Trail, session_id pro Analyse-Run
response = agent.run("Analyze AAPL", user_id="user-uuid", session_id="analysis-run-uuid")
```

> **Supabase:** Direct Connection (Port 5432) verwenden, nicht Pooler (Port 6543).
> Agno verwaltet eigene Sessions und braucht persistent connections.
>
> **Stateless Analyse:** `add_history_to_context` und `num_history_runs` sind für
> konversationelle Agents gedacht. MyTrade-Analyse-Agents sollen KEINE vorherigen
> Analysen als Kontext erhalten — jeder Run ist unabhängig.

---

## 9. Team / Coordinate Mode (Phase 2+)

> **Nicht im MVP.** MVP nutzt nur den Fundamental Analyst als einzelnen Agent.

```python
from agno.team import Team
from agno.team.mode import TeamMode

team = Team(
    name="Investment Analysis Team",
    model=Claude(id="claude-opus-4-6"),  # Synthesizer als Leader
    members=[macro_agent, fundamental_agent, risk_agent, devil_agent],
    mode=TeamMode.coordinate,
    show_members_responses=True,
)

response = team.run("Full analysis for AAPL")
```

---

## 10. Caching + Fallback (Kurzreferenz)

**Prompt Caching:** `Claude(cache_system_prompt=True)` cacht System-Prompts, IPS-Kontext, Schemas (~15K Token/Analyse, 90% Ersparnis). Details → @docs/03_architecture/monitoring.md

**Quality-Fallback** (aufwärts bei Schema-Fehler): Haiku → Retry Haiku → Sonnet → Opus.
**Budget-Fallback** (abwärts bei Kostenlimit): Opus → Sonnet → Haiku.
Implementation in Step 11. Routing-Logik → @docs/03_architecture/agents.md "Model-Routing und Fallback-Logik".

---

## Referenzen

- @docs/03_architecture/agents.md — Agent-Spezifikationen, Model-Routing, Token-Budgets
- @docs/03_architecture/system-overview.md — Architektur-Layer
- @docs/05_risk/policy-engine.md — Policy Engine ist deterministisches Python, kein Agno
- @docs/04_verification/claim-schema.json — Output-Schema für Claim Extractor
- @docs/03_architecture/monitoring.md — Budget-Caps, Caching-Strategie
