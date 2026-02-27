---
name: new-agno-agent
description: 'Create a new Agno agent definition with system prompt, tools, token budget, and claim output format. Use when adding a new analysis agent to the system.'
context: fork
disable-model-invocation: true
---
Create a new Agno agent in backend/src/agents/ following this checklist:

## 1. Research first
- Read docs/03_architecture/agents.md for the 10-agent spec and 3-Tier Model-Mix
- Read docs/04_verification/claim-schema.json for required output format
- Read docs/02_policy/ips-template.yaml for policy constraints
- Check existing agents in backend/src/agents/ for established patterns

## 2. Choose the right tier

| Tier | Model | API String | Use when |
|------|-------|-----------|----------|
| Heavy | Opus 4.6 | `claude-opus-4-6` | Nuanced reasoning, counter-arguments, final synthesis |
| Standard | Sonnet 4.6 | `claude-sonnet-4-6` | Solid analysis, most agents |
| Light | Haiku 4.5 | `claude-haiku-4-5` | Structured extraction, schema-bound JSON, number comparison |

## 3. Agent template

```python
from agno.agent import Agent
from agno.models.anthropic import Claude

agent = Agent(
    name="$ARGUMENTS",
    model=Claude(id="claude-sonnet-4-6"),  # Choose tier from table above
    tools=[...],
    instructions=[
        # System prompt here — be specific about output format
        # End with: "Output structured JSON matching the schema."
    ],
    markdown=True,
    # Token budget: set max_tokens based on tier
    # Heavy: ~10-15K, Standard: ~8-30K, Light: ~3-5K
)
```

## 4. Fallback chain (required)
Every agent must handle failures with the bidirectional fallback:

```python
# Quality fallback (up): Schema fail → 1x retry same model → next higher tier
# Budget fallback (down): Monthly cap reached → next lower tier
#
# Example for a Light-tier agent:
# Haiku → Schema fail → retry Haiku → fail → Sonnet fallback
# Example for a Heavy-tier agent:
# Opus → Budget 80% → Sonnet degraded → Budget 95% → Haiku degraded
```

## 5. Coordinate mode (if part of team)
If this agent runs as part of the analysis team (not standalone):

```python
from agno.team import Team

# The Portfolio Synthesizer is team leader
# New agents join as team members via coordinate mode
# See docs/03_architecture/agents.md "Agent-Orchestrierung" section
```

## 6. Output requirements
- Every numeric output MUST include `{value, source, timestamp}`
- Agent output is fed to Claim Extractor (Haiku) which extracts claims per claim-schema.json
- Claims are then verified by Verification Agent against a 2nd source
- Trade-critical claims need Tier A verification before execution

## 7. Checklist before committing
- [ ] Agent file created in backend/src/agents/
- [ ] Model tier matches task complexity (don't use Opus for extraction)
- [ ] Token budget set and documented
- [ ] Fallback chain implemented (quality up + budget down)
- [ ] Output format matches claim-schema.json requirements
- [ ] Agent registered in agent registry
- [ ] Basic tests written (happy path + schema validation failure)
- [ ] Cost estimate added to docs/03_architecture/monitoring.md budget table
