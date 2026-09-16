# Third-Party API Timeout Cascade

## Symptoms
- Requests to our API are slow or timing out
- Logs show repeated timeouts calling an external/third-party service
- Symptom often spreads — unrelated endpoints slow down too, because threads/workers
  are blocked waiting on the external call

## Likely Causes
- The third-party service is degraded or down
- No timeout configured on our client, so a hung external call blocks a worker indefinitely
- No circuit breaker — every request keeps retrying the failing dependency instead of
  failing fast

## Diagnostic Steps
1. Check the third-party provider's status page
2. Check our outbound request logs for latency/error spikes to that specific host
3. Check worker/thread pool saturation — are all workers blocked on this one dependency?

## Resolution Steps
1. If the third party is down, enable a circuit breaker or feature flag to fail fast
   or degrade gracefully rather than hang
2. Confirm/add an explicit timeout on the HTTP client for that integration
3. Once the third party recovers, monitor before fully re-enabling normal traffic

## Escalation
Escalate immediately if the affected endpoint is on the critical path (e.g. payment
processing). Notify client-facing teams if customer-visible functionality is degraded.
