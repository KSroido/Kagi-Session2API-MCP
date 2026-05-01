"""Token pool: round-robin rotation with per-token rate limiting.

Provides TokenBucket (5 req/s per token) and TokenPool (round-robin
rotation with auto-disable for expired tokens).
"""

import asyncio
import logging
import time

from .exceptions import RateLimitError, TokenExpiredError

logger = logging.getLogger("kagi-session-mcp")


class TokenBucket:
    """Per-token rate limiter using token bucket algorithm.

    Rate: 5 requests per second per token.
    Burst: allows up to `burst` requests instantly, then 1 request every (1/rate) seconds.
    """

    def __init__(self, rate: float = 5.0, burst: int = 5):
        self.rate = rate
        self.burst = burst
        self._tokens: float = float(burst)
        self._last_refill: float = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """Acquire one token. Returns wait time in seconds (0 if no wait).

        If the bucket has capacity, returns 0 immediately.
        If depleted, returns the time that would need to be waited.
        Does NOT actually sleep — caller decides whether to wait.
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return 0.0
            else:
                wait = (1.0 - self._tokens) / self.rate
                self._tokens = 0.0
                return wait

    @property
    def available(self) -> float:
        """Current number of available tokens (approximate, no lock)."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        return min(self.burst, self._tokens + elapsed * self.rate)


class TokenPool:
    """Manages a pool of session tokens with round-robin rotation.

    Strategy:
    - Round-robin: each request uses the next token in sequence
    - Per-token rate limit: 5 req/s per token (token bucket)
    - If current token is rate-limited, try next token
    - Only blocks when ALL tokens are rate-limited
    - Marks expired tokens as disabled (skipped in rotation)
    """

    def __init__(self, tokens: list[str], rate_per_token: float = 5.0):
        if not tokens:
            raise ValueError("Token pool requires at least one token")

        self._tokens = tokens
        self._buckets = [TokenBucket(rate=rate_per_token) for _ in tokens]
        self._disabled = [False] * len(tokens)
        self._index = 0
        self._lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        """Number of active (non-disabled) tokens."""
        return sum(1 for d in self._disabled if not d)

    @property
    def total_count(self) -> int:
        """Total number of tokens (including disabled)."""
        return len(self._tokens)

    @property
    def is_all_disabled(self) -> bool:
        """Whether all tokens are disabled."""
        return self.active_count == 0

    async def acquire_token(self) -> tuple[int, str]:
        """Get the next available token (index, value) respecting rate limits.

        Round-robin with skip: try each token in order; if rate-limited, try next.
        Only wait if ALL tokens are rate-limited.

        Returns:
            Tuple of (token_index, token_value)

        Raises:
            TokenExpiredError: If all tokens are disabled
            RateLimitError: If no tokens are available (shouldn't happen normally)
        """
        async with self._lock:
            n = len(self._tokens)

            if self.active_count == 0:
                raise TokenExpiredError(
                    "All session tokens are expired or disabled. "
                    "Please update your configuration and restart the server."
                )

            # First pass: find a token that doesn't need waiting
            for offset in range(n):
                idx = (self._index + offset) % n
                if self._disabled[idx]:
                    continue
                wait = await self._buckets[idx].acquire()
                if wait == 0.0:
                    self._index = (idx + 1) % n
                    return idx, self._tokens[idx]
                # This token needs waiting, refund and try next
                self._buckets[idx]._tokens += 1.0

            # All active tokens need waiting — find the one with shortest wait
            waits: list[tuple[int, float]] = []
            for offset in range(n):
                idx = (self._index + offset) % n
                if self._disabled[idx]:
                    continue
                wait = await self._buckets[idx].acquire()
                waits.append((idx, wait))

            if not waits:
                raise RateLimitError("No available tokens in pool")

            # Pick the token with shortest wait
            best_idx, best_wait = min(waits, key=lambda x: x[1])

            # Refund all the tokens we just acquired (we only need one)
            for idx, _ in waits:
                self._buckets[idx]._tokens += 1.0

            # Now actually acquire the best one
            wait = await self._buckets[best_idx].acquire()

            # Release the lock before sleeping
        # Sleep outside the lock so other coroutines can proceed
        if best_wait > 0:
            logger.debug(f"Rate limit: waiting {best_wait:.3f}s for token #{best_idx + 1}")
            await asyncio.sleep(best_wait)

        # Re-acquire lock to update index
        async with self._lock:
            self._index = (best_idx + 1) % n
            return best_idx, self._tokens[best_idx]

    def disable_token(self, index: int) -> None:
        """Mark a token as disabled (e.g., expired).

        Args:
            index: Token index to disable
        """
        if 0 <= index < len(self._disabled):
            self._disabled[index] = True
            logger.warning(
                f"Token #{index + 1} ({self.mask_token(index)}) has been disabled. "
                f"Remaining active tokens: {self.active_count}/{self.total_count}"
            )

    def mask_token(self, index: int) -> str:
        """Get a masked version of a token for logging.

        Shows first 4 chars + *** + last 4 chars.
        Short tokens are fully masked.
        """
        if index < 0 or index >= len(self._tokens):
            return "***invalid***"
        token = self._tokens[index]
        if len(token) <= 8:
            return "***"
        return f"{token[:4]}***{token[-4:]}"

    def get_status(self) -> list[dict]:
        """Get status of all tokens in the pool (for diagnostics)."""
        return [
            {
                "index": i,
                "masked": self.mask_token(i),
                "disabled": self._disabled[i],
                "available": round(self._buckets[i].available, 2),
            }
            for i in range(len(self._tokens))
        ]
