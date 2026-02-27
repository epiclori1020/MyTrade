---
name: db-migrate
description: 'Create a new Supabase migration file with proper timestamp, SQL schema, RLS policies, and indexes. Use when the database schema needs changes.'
context: fork
allowed-tools: Read, Write, Bash
disable-model-invocation: true
---
Create a new Supabase migration:

1. Read docs/03_architecture/database-schema.md for existing schema
2. Read docs/02_policy/settings-spec.md for user_policy + policy_change_log tables
3. Read docs/09_broker/security.md for RLS requirements

Steps:
1. Generate timestamp: `date +%Y%m%d%H%M%S`
2. Create file: `supabase/migrations/{timestamp}_$ARGUMENTS.sql`
3. Include in the migration:
   - CREATE TABLE with proper types, constraints, foreign keys
   - ENABLE ROW LEVEL SECURITY
   - RLS policies (users see only own data via auth.uid())
   - Indexes on user_id and frequently queried columns
4. Validate SQL syntax

CRITICAL: Remember service_role bypasses RLS. See docs/09_broker/security.md.
