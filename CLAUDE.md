# MyTrade — Multi-Agent AI Investment System

## Project Overview
AI-powered investment analysis for an Austrian long-term investor.
70% Core (VWCE+CSPX on Flatex, outside this system) / 30% Satellite (system-managed).
Currently: **Stufe 1 (Paper Trading)** — NO live trading, NO auto-execute.

## Tech Stack
- **Backend:** Python, FastAPI, Agno (agent framework)
- **LLM:** Claude Opus 4.6 (analysis), Sonnet 4.5 (fallback/cost-cap)
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
- Keep active MCP connections ≤ 5 to preserve context window

## Commands
- `cd backend && uvicorn src.main:app --reload`  # Start backend
- `cd frontend && npm run dev`                     # Start frontend
- `cd backend && pytest`                           # Run tests
- `supabase db push`                               # Apply migrations

## Critical Rules
- NEVER expose API keys in frontend code (broker keys ONLY in backend)
- ALL LLM numeric outputs MUST go through Verification Layer before display
- Policy Engine (deterministic Python): Pre-Policy BEFORE agent call, Full-Policy AFTER verification
- Austrian tax: KESt 27.5% on all capital gains
- Core ETFs run on Flatex.at (manual) — system manages ONLY Satellite
- Stufe 1: Paper Trading only. System must NOT create real orders.
- When in doubt, flag for human review — never assume

## Compaction Instructions
When compacting, always preserve: list of modified files, current sprint goals,
any test commands, and the vertical slice status (which components are connected).
