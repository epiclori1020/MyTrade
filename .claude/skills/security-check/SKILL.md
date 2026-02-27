---
name: security-check
description: 'Run a security audit checking for exposed API keys, RLS gaps, and CORS misconfigurations. Use before committing or deploying.'
context: fork
disable-model-invocation: true
---
Run a security audit using the security-reviewer agent:

1. Invoke the security-reviewer agent
2. Check all items on the security checklist
3. Report results as ✅ PASS or ❌ FAIL

Quick checks you can run immediately:
```bash
# Check for hardcoded API keys in source
grep -rn 'sk-ant\|AKIA\|pk_live\|sk_live' --include='*.py' --include='*.ts' --include='*.tsx' .

# Check .env is gitignored
grep '.env' .gitignore

# Check frontend for secret references
grep -rn 'SERVICE_ROLE\|ALPACA_SECRET\|ANTHROPIC_API' frontend/

# Check ALPACA_PAPER_MODE
grep -rn 'PAPER_MODE' backend/
```
