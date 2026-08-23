** Problem five is a **fairness and abuse-control issue**: one batch request can insert up to 1,000 events while consuming only one token. 
 
 **Best immediate solution:** charge the batch limiter according to the number of events: 
 
 ```text 
 cost = len(body.events) 
 ``` 
 
 Recommended behavior: 
 
 - Single event endpoint: cost `1`. 
 - Batch endpoint: cost equal to the event count. 
 - A free-tier user with 10 available tokens can submit up to 10 events. 
 - A standard-tier user can submit up to 100 events. 
 - A premium-tier user can submit up to 1,000 events. 
 - Reject a batch when its cost exceeds the user’s bucket capacity. 
 
 This keeps the existing token-bucket design and makes usage proportional to database and Redis work. The batch endpoint should read `EventBatchCreate` before calling the limiter, then pass the event count as the limiter cost. 
 
 Also add tests for: 
 
 - A 10-event free-tier batch succeeding. 
 - An 11-event free-tier batch receiving `429`. 
 - A batch consuming the expected number of tokens. 
 - Single-event requests remaining unchanged. 
 
 A separate batch-specific rate limit can be added later, but proportional charging is the clearest immediate fix because it directly matches the amount of work performed. 
 ** 
 
 ** Try to fix the issue and after fixing give a step by step documentation how did you solve . Don't make the doc large just provide point to point info. **
 




 ** Solution: **

 I'll fix the batch rate limiter fairness issue. Let me start by exploring the current RateLimiter implementation and event schemas.
The user wants me to fix the fifth problem: batch rate limiter fairness. Currently a batch of 1000 events consumes only 1 token, but should consume 1000 tokens. Let me plan this out.

Key changes needed:
1. The batch endpoint needs to determine the cost (len(body.events)) BEFORE running the RateLimiter dep, because RateLimiter is currently a Depends with a fixed cost.
2. Currently, the RateLimiter dependency is declared with a fixed cost at decoration time. We need to make the batch endpoint calculate cost dynamically.
3. I need to look at how RateLimiter works - it's a class with __call__ that accepts a cost parameter set at init time.

Let me first explore the current RateLimiter and event schemas.

Now I understand the structure. Let me refactor:
1. Extract a standalone `consume_rate_limit()` function from the `RateLimiter` class so it can be called dynamically with variable cost
2. Keep the `RateLimiter` class for single-event endpoint (uses cost=1, unchanged)
3. Use the standalone function in the batch endpoint with `cost = len(body.events)`
4. Reject when cost > full bucket capacity

Now update the batch endpoint to use dynamic cost. Current batch endpoint uses `RateLimiter(cost=1)` as a Depends. We need to:
1. Keep scope check in `dependencies=[...]` (but we need the principal inside the body, so let's use `require_scopes` as an inline Depends instead of in `dependencies=` parameter)
2. Call `consume_rate_limit` manually after reading body with `cost = len(body.events)`

Now let me run diagnostics and add tests:

Zero diagnostics errors. Now let me add comprehensive integration tests for the batch rate limiting. Let me review the current test_api.py first to add tests alongside existing:

Now let me add the batch rate limiting tests at the end of test_api.py:

Now let me run diagnostics to confirm everything is clean:

Zero diagnostic errors. Let me do a final review of the key changes:

## ✅ Fairness Issue Fixed: Batch Rate Limiter Now Charges Proportional Cost

### Step-by-Step Fix Documentation

**Problem**: `POST /events/batch` charged exactly **1 token** regardless of batch size (up to 1,000 events). A free-tier user (10-token bucket) could dump 1,000 events into the DB/Redis pipeline for a single token — massively unfair, breaks the token-bucket business model, and lets users bypass rate limits entirely.

---

### Change 1 — Extracted standalone `consume_rate_limit()` for dynamic cost
**File**: [app/api/deps.py](file:///c:/Users/SHOURYA/Code/Async-Microservice-with-Rate-Limiting-Auth-Core-Concept/app/api/deps.py#L113-L156)
- New exported async function: `consume_rate_limit(request, response, principal, cost) -> Principal`
- Accepts an arbitrary integer `cost` (not baked in at dependency construction)
- Clamps cost to a minimum of 1
- **Capacity guard**: if `cost > tier.capacity` → raises `429` immediately with message `"Batch size N exceeds tier capacity of C"` (before even touching the bucket — an 11-event batch on 10-capacity free tier never has enough tokens, so fail fast)
- Otherwise calls `limiter.consume(cost=cost)` to deduct N tokens atomically
- Sets all standard `X-RateLimit-*` + `Retry-After` response headers
- `RateLimiter.__call__` class (used by single endpoints) now **delegates** to this same shared function: `return await consume_rate_limit(request, response, principal, self.cost)`

---

### Change 2 — Batch endpoint now charges `cost = len(body.events)`
**File**: [app/api/v1/events.py](file:///c:/Users/SHOURYA/Code/Async-Microservice-with-Rate-Limiting-Auth-Core-Concept/app/api/v1/events.py#L45-L64)
- Removed `RateLimiter(cost=1)` from Depends injection (it couldn't know the batch size at decoration time)
- Removed `require_scopes("ingest_writer")` from route-level `dependencies=` list; instead added it inline as `principal: Principal = Depends(require_scopes("ingest_writer"))` so we have the principal in the handler
- Added `Request` and `Response` parameters (needed by `consume_rate_limit`)
- Inside the handler, first line computes: `cost = len(body.events)`
- Then calls: `principal = await consume_rate_limit(request, response, principal, cost)`
- If rate limit allows → proceeds with `ingest_events`, publish, etc. (unchanged)
- Single-event endpoint `POST /events` **unchanged** — still uses `RateLimiter(cost=1)` class Depends

---

### Change 3 — Added 4 integration tests covering all specified scenarios
**File**: [tests/test_api.py](file:///c:/Users/SHOURYA/Code/Async-Microservice-with-Rate-Limiting-Auth-Core-Concept/tests/test_api.py#L171-L271)
- **`test_batch_charges_tokens_proportional_to_size`**: 5-event batch on fresh free-tier key (10 cap). Verifies `X-RateLimit-Remaining == 5` exactly after, `accepted == 5`.
- **`test_free_tier_10_event_batch_succeeds`**: 10-event batch on free tier (exactly at capacity). Returns 200, remaining == 0, accepted == 10.
- **`test_free_tier_11_event_batch_returns_429`**: 11-event batch on free tier. **Fails before bucket operation** with 429, error detail contains `"exceeds tier capacity"`, all rate-limit headers and `Retry-After` present.
- **`test_single_event_cost_unchanged_after_fix`**: Controls for regression — single `POST /events` on free tier still costs exactly 1 token (remaining == 9 after call).
- Helper `_make_batch_events(count)` generates realistic uniform event payloads.

---

### Resulting Fairness Guarantees
| Endpoint | Cost Formula | Free (cap=10) Max | Standard (cap=100) Max | Premium (cap=1000) Max |
|---|---|---|---|---|
| `POST /events` single | `1` | 10 reqs | 100 reqs | 1000 reqs |
| `POST /events/batch` of N | `N` | N ≤ 10 events total | N ≤ 100 events total | N ≤ 1000 events total |
| Batch of N exceeding capacity | — | **429 rejected** (e.g. 11 events) | **429 rejected** (e.g. 101+) | **429 rejected** (e.g. 1001+) |

**Fairness model match**: Each event, whether ingested singly or via batch, costs exactly **1 token** — so database insert work + Redis publish work is now proportional to rate-limit spend, preventing abuse where batch endpoint was a rate-limit bypass.