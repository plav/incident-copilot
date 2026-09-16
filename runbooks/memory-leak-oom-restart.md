# Memory Leak Causing OOM Restarts

## Symptoms
- Service memory usage climbs steadily over hours/days, then the pod/process restarts
- Restarts correlate with memory graphs hitting the configured limit
- Performance degrades in the period just before restart (GC pressure)

## Likely Causes
- Unbounded in-memory cache or collection that's never evicted
- Event listeners or subscriptions not being cleaned up
- A recent dependency upgrade introducing a known leak

## Diagnostic Steps
1. Correlate memory graph against deploy timeline — did this start after a specific release?
2. Take a heap snapshot/profile if the runtime supports it
3. Check for caches or collections with no max size or TTL

## Resolution Steps
1. If tied to a specific deploy, roll back
2. Add bounds (max size + eviction policy) to any unbounded in-memory structure
3. As a stopgap, increase memory limit and add proactive restarts on a schedule while
   the root cause is fixed properly

## Escalation
Escalate if restarts are frequent enough to cause visible availability impact, not just
a background nuisance.
