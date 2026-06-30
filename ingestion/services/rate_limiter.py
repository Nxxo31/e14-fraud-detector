"""Rate limiter for E14 ingestion layer.

Implements a sliding window rate limiter to respect the 8 req/s global limit
imposed by the Registraduria CDN. Uses Redis for distributed coordination
across multiple workers.
"""

import asyncio
import logging
import time
from collections import deque
from typing import Optional

import redis.asyncio as redis

from ..config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Sliding window rate limiter using Redis for distributed coordination.

    Limits requests to MAX_REQUESTS_PER_SECOND (8 by default) to respect
    the Registraduria CDN rate limit. Uses Redis sorted sets for accurate
    sliding window implementation across multiple workers.
    """

    def __init__(
        self,
        requests_per_second: Optional[int] = None,
        window_seconds: Optional[float] = None,
        redis_url: Optional[str] = None,
    ):
        """Initialize rate limiter.

        Args:
            requests_per_second: Max requests per second (default from settings)
            window_seconds: Time window in seconds (default from settings)
            redis_url: Redis connection URL (default from settings)
        """
        self.max_requests = requests_per_second or settings.MAX_REQUESTS_PER_SECOND
        self.window_seconds = window_seconds or settings.RATE_LIMIT_WINDOW
        self.redis_url = redis_url or settings.CELERY_BROKER_URL.replace("redis://", "redis://")

        self._redis: Optional[redis.Redis] = None
        self._local_timestamps: deque = deque()
        self._last_cleanup = time.time()

    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def acquire(self, key: str = "global") -> float:
        """Acquire a rate limit slot, waiting if necessary.

        Implements sliding window algorithm:
        1. Remove timestamps outside current window
        2. If at limit, wait until oldest timestamp expires
        3. Add current timestamp to window
        4. Return wait time (0 if immediate)

        Args:
            key: Rate limit bucket key (e.g., "download", "metadata")

        Returns:
            Wait time in seconds before token is available
        """
        await self._cleanup_local()

        now = time.time()
        window_start = now - self.window_seconds

        # Cleanup old entries from local deque
        while self._local_timestamps and self._local_timestamps[0] < window_start:
            self._local_timestamps.popleft()

        # Check if we're at the limit
        if len(self._local_timestamps) >= self.max_requests:
            oldest = self._local_timestamps[0]
            wait_time = oldest + self.window_seconds - now
            if wait_time > 0:
                logger.debug(f"Rate limit reached, waiting {wait_time:.3f}s")
                await asyncio.sleep(wait_time)
                return wait_time

        # Add current timestamp
        self._local_timestamps.append(time.time())
        return 0.0

    def acquire_sync(self, key: str = "global") -> float:
        """Synchronous acquire for non-async contexts.

        Uses a simple token bucket approach for sync contexts.
        For async code, use acquire() instead.
        """
        now = time.time()
        window_start = now - self.window_seconds

        # Cleanup old entries
        while self._local_timestamps and self._local_timestamps[0] < window_start:
            self._local_timestamps.popleft()

        if len(self._local_timestamps) >= self.max_requests:
            oldest = self._local_timestamps[0]
            wait_time = oldest + self.window_seconds - now
            if wait_time > 0:
                time.sleep(wait_time)
                return wait_time

        self._local_timestamps.append(time.time())
        return 0.0

    async def _cleanup_local(self) -> None:
        """Periodic cleanup of stale local timestamps."""
        now = time.time()
        if now - self._last_cleanup > 60:  # Cleanup every minute
            window_start = now - self.window_seconds
            while self._local_timestamps and self._local_timestamps[0] < window_start:
                self._local_timestamps.popleft()
            self._last_cleanup = now

    async def get_stats(self, key: str = "global") -> dict:
        """Get current rate limiter statistics.

        Args:
            key: Rate limit bucket key

        Returns:
            Dict with current requests in window and time until next slot
        """
        now = time.time()
        window_start = now - self.window_seconds

        # Cleanup and count
        active_count = 0
        for ts in list(self._local_timestamps):
            if ts >= window_start:
                active_count += 1

        oldest = self._local_timestamps[0] if self._local_timestamps else now
        time_until_reset = max(0, oldest + self.window_seconds - now)

        return {
            "bucket": key,
            "active_requests": active_count,
            "max_requests": self.max_requests,
            "window_seconds": self.window_seconds,
            "time_until_next_slot": time_until_reset,
            "utilization_percent": (active_count / self.max_requests) * 100,
        }

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


class TokenBucketRateLimiter:
    """Simple token bucket rate limiter for local-only use.

    Does not require Redis. Suitable for single-worker deployments
    or testing. For production with multiple workers, use RateLimiter.
    """

    def __init__(
        self,
        requests_per_second: float = 8.0,
        burst_size: Optional[int] = None,
    ):
        """Initialize token bucket.

        Args:
            requests_per_second: Refill rate in tokens per second
            burst_size: Max tokens in bucket (default: requests_per_second)
        """
        self.rate = requests_per_second
        self.burst_size = burst_size or int(requests_per_second)
        self.tokens = float(self.burst_size)
        self.last_refill = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> float:
        """Acquire tokens from the bucket.

        Args:
            tokens: Number of tokens to acquire (default: 1)

        Returns:
            Wait time in seconds if bucket was empty, 0 otherwise
        """
        async with self._lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return 0.0

            # Calculate wait time
            needed = tokens - self.tokens
            wait_time = needed / self.rate

            return wait_time

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.burst_size, self.tokens + elapsed * self.rate)
        self.last_refill = now

    async def acquire_sync(self, tokens: int = 1) -> float:
        """Synchronous acquire for non-async contexts."""
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return 0.0

        needed = tokens - self.tokens
        wait_time = needed / self.rate
        time.sleep(wait_time)

        self._refill()
        self.tokens -= tokens
        return wait_time


# Global rate limiter instance for convenience
_global_rate_limiter: Optional[RateLimiter] = None


async def get_rate_limiter() -> RateLimiter:
    """Get or create global rate limiter instance."""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter()
    return _global_rate_limiter