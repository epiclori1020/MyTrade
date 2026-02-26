---
name: new-agno-agent
description: 'Create a new Agno agent definition with system prompt, tools, token budget, and claim output format. Use when adding a new analysis agent to the system.'
disable-model-invocation: true
---
Create a new Agno agent in backend/src/agents/ following this template:

1. Read docs/03_architecture/agents.md for existing agent patterns
2. Read docs/04_verification/claim-schema.json for required output format
3. Read docs/02_policy/ips-template.yaml for policy constraints

Agent file structure:
```python
from agno.agent import Agent
from agno.models.anthropic import Claude

agent = Agent(
    name="$ARGUMENTS",
    model=Claude(id="claude-opus-4-6"),  # or claude-sonnet-4-5 for lighter tasks
    tools=[...],
    instructions=[...],
    markdown=True,
)
```

Every agent output MUST include structured claims matching claim-schema.json.
Add the new agent to the agent registry and write basic tests.
