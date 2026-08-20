# Step 4 — Atomic token-bucket rate limiting (Redis + Lua)

Concurrent FastAPI workers would race if they read/modify Redis hashes in separate round-trips. The token bucket therefore runs **inside Redis** as a single Lua script (`EVALSHA`). Redis executes Lua atomically, so two in-flight requests cannot both observe the same token count.

## Algorithm (as implemented)

1. `HMGET` `tokens` and `last_updated`.
2. If the key is new, fill the bucket to `capacity`.
3. Otherwise add `elapsed_seconds * refill_rate`, capped at `capacity`.
4. If `tokens >= cost`, subtract `cost`, `HMSET`, set `EXPIRE`, return `{1, remaining}`.
5. Otherwise return `{0, remaining}` without mutating last-updated (so refill credit is not lost).

Script source: `app/services/rate_limiter.py` (`TOKEN_BUCKET_LUA`).

## FastAPI dependency

```python
principal: Principal = Depends(RateLimiter(cost=1))
```

Identity:

- API key → Redis key `rl:apikey:{api_key.id}` and the key’s `rate_limit_tier`
- JWT user → `rl:user:{user.id}` and a tier derived from role (viewer=free, writer=standard, admin=premium)

Default tiers (tokens / refill per second):

| Tier | Capacity | Refill |
| --- | --- | --- |
| `free` | 10 | 1/s |
| `standard` | 100 | 10/s |
| `premium` | 1000 | 100/s |

Response headers (success and 429):

- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset` (unix epoch when the client can reasonably retry)
- `Retry-After` on HTTP 429

The Lua SHA is loaded during lifespan. If Redis is restarted, `NoScriptError` triggers a reload and retry.
