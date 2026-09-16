# Database Connection Pool Exhaustion

## Symptoms
- API requests timing out or returning 500 errors intermittently
- Logs show "connection pool exhausted" or "timeout waiting for connection"
- Database itself shows normal CPU/memory, but application can't connect

## Likely Causes
- A slow or hanging query holding connections open longer than expected
- Connection leak — code path that acquires a connection but doesn't release it on error
- Pool size configured too small for current traffic volume
- A recent deploy introduced a new code path that doesn't close connections properly

## Diagnostic Steps
1. Check current active vs idle connections in the pool metrics/dashboard
2. Query the database for long-running or idle-in-transaction queries
3. Review recent deploys for changes touching data access code
4. Check application logs for repeated connection acquisition without matching release

## Resolution Steps
1. If a specific query is hanging, kill it manually and identify the offending code path
2. If it's a leak, roll back the most recent deploy touching data access code
3. As a short-term mitigation, increase pool size if traffic genuinely outgrew it
4. Add/verify connection timeout and proper try/finally (or context manager) release patterns

## Escalation
Escalate to on-call DBA if the database itself shows resource exhaustion, not just the
application pool. Escalate to team lead if resolution requires a rollback affecting
other services.
