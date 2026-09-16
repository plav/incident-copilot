# Stale Cache Serving Incorrect Data

## Symptoms
- Users report seeing outdated information (old balances, old status, etc.)
- Data is correct in the database but wrong via the API/UI
- Issue often clears itself after a delay, or after a manual cache clear

## Likely Causes
- Cache invalidation not triggered on the relevant write path
- TTL set too long for how frequently the underlying data changes
- A recent change added a new write path that bypasses existing invalidation logic

## Diagnostic Steps
1. Confirm the discrepancy directly — compare cached value vs database value for the
   same record
2. Trace the write path that updated the record — does it invalidate the cache key?
3. Check if this is a new/rare write path introduced recently

## Resolution Steps
1. Manually invalidate the specific affected cache keys/records as an immediate fix
2. Add cache invalidation to the write path that's missing it
3. Consider whether TTL is appropriate for the data's actual volatility

## Escalation
Escalate to team lead if the incorrect data has financial or compliance implications
(e.g. incorrect balances shown to customers), since this may require customer
communication beyond just a technical fix.
