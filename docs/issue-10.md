**Problem 10**
**
**
Problem ten is a **measurement problem**, not a service bug.

**Best immediate solution:** treat `429` as expected during load tests and exclude it from the failure metric in k6.

The most practical fix is to update the k6 check to count `429` as acceptable, and adjust the failed-rate threshold to ignore those responses.

Example pattern:

```javascript
check(res, {
  "accepted or rate-limited": (r) => r.status === 200 || r.status === 429,
});
```

Then also set the threshold based on actual errors only:

```javascript
thresholds: {
  http_req_failed: ["rate<0.05"],
}
```

But this only works correctly if the test logic marks `429` as a successful operation for the load-test scenario. In other words, the load test should not treat rate limiting as a failure condition when it is intentional.

Best short-term rule:
- `200` and `429` are valid outcomes
- `500`, `502`, `503`, connection failures, and unexpected auth failures are real failures
- keep the failure threshold low, but exclude intentional rate-limit events from the error count

This is the right temporary fix because:
- it matches the project’s design
- keeps load testing honest
- prevents false alarms from expected limiter behavior

If you want to go further later, you can add a separate metric like:
- `rate_limit_hits`
- `non_429_errors`
- `p95 latency while rate-limited`
**

** Try to fix the issue and after fixing give a step by step documentation how did you solve . Don't make the doc large just provide point to point info. **
**




**Solution:**
**  
Listed directory loadtest
Viewed k6_events.js:1-40
Viewed locustfile.py:1-48
Edited k6_events.js

I have corrected the measurement issue in the load testing scripts. Here is the step-by-step documentation of how this was solved:

### How the Issue Was Solved (Measurement Correction)

1. **Diagnosed the k6 Metric Gap:**
   - In `loadtest/k6_events.js`, the `check()` function was successfully asserting that `429` responses were acceptable. However, the core `k6` engine still treats any HTTP 4xx or 5xx code as a failure for the built-in `http_req_failed` metric unless explicitly told otherwise.

2. **Excluded Rate-Limits from Failure Counts (k6):**
   - Updated the `http.post` request options in `k6_events.js` to include `responseCallback: http.expectedStatuses(200, 429)`.
   - This officially informs the k6 engine that `429 Too Many Requests` is a fully intentional, expected outcome for this load test scenario, keeping the `http_req_failed` rate completely clean of false alarms.

3. **Verified Locust Parity:**
   - Reviewed `locustfile.py` and confirmed it was already properly handling this nuance by explicitly calling `response.success()` when a `429` is caught during the request execution. No changes were required there.

**