# Deployment Rollback Failure

## Symptoms
- A deploy caused a regression, and attempting to roll back doesn't fully resolve it
- Old and new behavior appear mixed (some instances on new version, some on old)
- Database schema changes from the new deploy aren't compatible with the old code

## Likely Causes
- Rolling deployment not fully complete before rollback was triggered — mixed versions
  running simultaneously
- A database migration in the new deploy isn't backward-compatible with the previous
  application version
- Cached artifacts/config from the new deploy still being served

## Diagnostic Steps
1. Confirm which version each instance/pod is actually running
2. Check whether the deploy included a database migration, and whether it's reversible
3. Check CDN/cache layers for stale artifacts from the new version

## Resolution Steps
1. Force all instances to the same version rather than allowing a mixed state
2. If a migration is not backward-compatible, this may require rolling forward with a
   fix rather than back — assess before committing to a rollback strategy
3. Purge caches/CDN if stale artifacts are part of the issue

## Escalation
Escalate to team lead immediately if a migration makes rollback unsafe — this is a
judgment call that shouldn't be made solo under pressure.
