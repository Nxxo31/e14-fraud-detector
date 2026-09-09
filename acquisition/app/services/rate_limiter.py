"""E14 Acquisition — Rate limiter (token bucket)."""

import time
import threading


class TokenBucket:
    """Thread-safe token bucket rate limiter.

    Serves as a global governor across all workers so we never exceed the
    Registraduría CDN rate limit (~8 req/s).
    """

    def __init__(self, rate: float = 8.0, burst: int = 8):
        self._rate = rate          # tokens per second
        self._capacity = burst     # max tokens (burst size)
        self._tokens = float(burst)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0, block: bool = True) -> float:
        """Acquire *tokens* (default 1). Sleeps if needed when *block*=True.

        Returns the wait time in seconds (0.0 if no wait).
        """
        if block:
            wait = self._wait(tokens)
            if wait > 0:
                time.sleep(wait)
            return wait

        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0
            return (tokens - self._tokens) / self._rate

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last = now

    def _wait(self, tokens: float) -> float:
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0
            deficit = tokens - self._tokens
            self._tokens = 0.0
        return deficit / self._rate