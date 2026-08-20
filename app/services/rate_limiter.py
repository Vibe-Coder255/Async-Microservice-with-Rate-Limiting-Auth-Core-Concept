import hashlib
import json
import secrets
import time
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import NoScriptError

from app.core.config import settings

TOKEN_BUCKET_LUA = """
-- KEYS[1]: rate limit key
-- ARGV[1]: capacity, ARGV[2]: refill_rate_per_sec, ARGV[3]: cost, ARGV[4]: current_time
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local data = redis.call("HMGET", key, "tokens", "last_updated")
local tokens = tonumber(data[1])
local last_updated = tonumber(data[2])

if tokens == nil then
    tokens = capacity
    last_updated = now
else
    local delta = math.max(0, now - last_updated)
    tokens = math.min(capacity, tokens + delta * refill_rate)
end

if tokens >= cost then
    tokens = tokens - cost
    redis.call("HMSET", key, "tokens", tokens, "last_updated", now)
    redis.call("EXPIRE", key, math.ceil(capacity / refill_rate) * 2)
    return {1, math.floor(tokens)}
else
    return {0, math.floor(tokens)}
end
"""


class TokenBucketLimiter:
    """Atomic token-bucket limiter executed entirely inside Redis via Lua."""

    def __init__(self, redis: Redis):
        self.redis = redis
        self._sha: str | None = None

    async def load_script(self) -> str:
        self._sha = await self.redis.script_load(TOKEN_BUCKET_LUA)
        return self._sha

    async def consume(
        self,
        key: str,
        capacity: float,
        refill_rate: float,
        cost: int = 1,
    ) -> tuple[bool, int, int]:
        now = time.time()
        args = (str(capacity), str(refill_rate), str(cost), str(now))
        try:
            if self._sha is None:
                await self.load_script()
            result = await self.redis.evalsha(self._sha, 1, key, *args)
        except NoScriptError:
            await self.load_script()
            result = await self.redis.evalsha(self._sha, 1, key, *args)

        allowed = bool(int(result[0]))
        remaining = int(result[1])
        missing = max(0.0, (cost if not allowed else 0) - remaining)
        if allowed:
            seconds_to_full = max(0.0, (capacity - remaining) / refill_rate)
        else:
            seconds_to_full = (missing / refill_rate) if refill_rate else 1.0
        reset_epoch = int(now + max(1.0, seconds_to_full))
        return allowed, remaining, reset_epoch


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return f"eik_{secrets.token_urlsafe(32)}"


def tier_params(tier: str) -> dict[str, float]:
    return settings.rate_limit_tiers.get(tier, settings.rate_limit_tiers["free"])


async def publish_events(redis: Redis, messages: list[dict[str, Any]]) -> None:
    if not messages:
        return
    async with redis.pipeline(transaction=False) as pipe:
        for message in messages:
            pipe.publish(settings.redis_events_channel, json.dumps(message, default=str))
        await pipe.execute()
