# MyTrade — Multi-Agent AI Investment System

## Project Overview
AI-powered investment analysis for an Austrian long-term investor.
70% Core (VWCE+CSPX on Flatex, outside this system) / 30% Satellite (system-managed).
Currently: **Stufe 1 (Paper Trading)** — NO live trading, NO auto-execute.

## Tech Stack
- **Backend:** Python, FastAPI, Agno (agent framework)
- **LLM:** 3-Tier Model-Mix — Opus 4.6 (Heavy: Devil's Advocate, Synthesizer), Sonnet 4.6 (Standard: Analyse-Agents), Haiku 4.5 (Light: Extraction, Verification). Budget-Fallback: Opus→Sonnet→Haiku
- **Database:** Supabase PostgreSQL (EU region)
- **Frontend:** Next.js, React, Tailwind, shadcn/ui
- **Data:** Finnhub, Alpha Vantage, FRED, SEC EDGAR
- **Broker:** Alpaca Paper API (Stufe 1), IBKR (Stufe 2+)
- **Hosting:** Railway (backend), Vercel (frontend)

## Key Architecture Docs (read before implementing)
- @docs/00_build-brief/brief.md — Goal, non-goals, Definition of Done
- @docs/02_policy/ips-template.yaml — Machine-readable IPS (Policy Engine fallback/defaults)
- @docs/02_policy/settings-spec.md — 3-tier Settings System (Beginner/Presets/Advanced)
- @docs/02_policy/asset-universe.md — Allowed instruments and regions
- @docs/03_architecture/system-overview.md — Layers, data flow, agents
- @docs/03_architecture/database-schema.md — Full SQL + RLS policies
- @docs/03_architecture/agents.md — Agent-Spezifikationen, 3-Tier Model-Routing, Fallback-Logik
- @docs/04_verification/claim-schema.json — Verification Layer format
- @docs/05_risk/execution-contract.md — What the system may/may not do per stage

## Frontend & Design
- **Component Library:** shadcn/ui — use the `shadcn` MCP to browse/install components
- **Styling:** Tailwind CSS with CSS variables for theming
- **Design Sync:** Figma MCP for bidirectional design ↔ code
- **Docs Lookup:** Add `use context7` to any prompt needing current library docs
- **Anti-AI-Slop:** Use `/frontend-design` skill before building UI pages
- **Aesthetic:** LUVI-inspired premium look — clean, warm, trust-evoking (no purple gradients)
- **Dark Mode:** System-default with manual toggle

### MCP Usage Rules
- shadcn MCP: ALWAYS check component registry before building custom UI
- Context7: Use for Supabase, Next.js, Tailwind, Agno docs (append `use context7`)
- Figma: Use `get_design_context` to pull designs, `generate_figma_design` to push code back
- Supabase MCP: Direct DB queries, schema inspection, migration support. Authenticate via `/mcp` on first use
- Keep active MCP connections ≤ 5 to preserve context window

## Commands
- `cd backend && uvicorn src.main:app --reload`  # Start backend
- `cd frontend && npm run dev`                     # Start frontend
- `cd backend && pytest`                           # Run tests
- `supabase db push`                               # Apply migrations

## Critical Rules (summary — details in `.claude/rules/`)
- **Security:** No API keys in frontend. No secrets in NEXT_PUBLIC_*. RLS on all tables. See `rules/security.md`
- **Verification:** All LLM numbers through Verification Layer before display. See `rules/verification.md`
- **Policy Engine:** Deterministic Python, no LLM. Pre-Policy + Full-Policy. See `rules/policy-engine.md`
- **Stufe 1:** Paper Trading only. No real orders. No live broker access. See `rules/stufe-1.md`
- **Tax:** Austrian KESt 27.5% (estimate overlay only in MVP)
- **Core:** Flatex.at (manual) — system manages ONLY Satellite
- **Default:** When in doubt, flag for human review — never assume

## Two Agent Architectures (important distinction)

### Claude Code Dev-Agents (.claude/agents/)
These help YOU build the app. They run inside Claude Code during development:
- `backend-dev` (Opus) — writes FastAPI code, Agno agent definitions, Policy Engine
- `frontend-dev` (Sonnet) — writes Next.js/React code, uses shadcn/Figma MCPs
- `db-architect` (Sonnet) — writes Supabase migrations, RLS policies
- `security-reviewer` (Opus) — audits for API key leaks, RLS gaps, CORS issues
- `test-writer` (Sonnet) — writes pytest tests for Policy Engine, Verification, Execution

### Runtime LLM-Agents (backend/src/agents/)
These run INSIDE the app at runtime, analyzing stocks for the user:
- 10 agents defined in @docs/03_architecture/agents.md
- 3-Tier Model-Mix: Opus (Heavy), Sonnet (Standard), Haiku (Light)
- Orchestrated via Agno coordinate mode
- Token budgets, fallback chains, and cost tracking per agent

These are completely separate systems. Dev-Agents write the code that defines Runtime-Agents.

## Compaction Instructions
When compacting, always preserve: list of modified files, current sprint goals,
any test commands, and the vertical slice status (which components are connected).
