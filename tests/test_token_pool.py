"""Unit tests for token_pool module."""

import asyncio
import time

import pytest

from kagi_session_mcp.token_pool import TokenBucket, TokenPool
from kagi_session_mcp.exceptions import TokenExpiredError, RateLimitError


class TestTokenBucket:
    """Tests for TokenBucket rate limiter."""

    @pytest.mark.asyncio
    async def test_initial_burst(self):
        """Token bucket should allow burst requests instantly."""
        bucket = TokenBucket(rate=5.0, burst=5)
        for _ in range(5):
            wait = await bucket.acquire()
            assert wait == 0.0

    @pytest.mark.asyncio
    async def test_rate_limit_after_burst(self):
        """After burst is consumed, next acquire should return positive wait time."""
        bucket = TokenBucket(rate=5.0, burst=5)

        # Consume burst
        for _ in range(5):
            await bucket.acquire()

        # Next should require waiting
        wait = await bucket.acquire()
        assert wait > 0

    @pytest.mark.asyncio
    async def test_refill_over_time(self):
        """Tokens should refill over time."""
        bucket = TokenBucket(rate=100.0, burst=1)

        # Consume the single token
        wait = await bucket.acquire()
        assert wait == 0.0

        # Wait for refill (10ms at 100/s rate)
        time.sleep(0.02)

        wait = await bucket.acquire()
        assert wait == 0.0

    def test_available_property(self):
        """available property should return approximate token count."""
        bucket = TokenBucket(rate=5.0, burst=5)
        assert bucket.available == pytest.approx(5.0, abs=0.5)


class TestTokenPool:
    """Tests for TokenPool round-robin rotation."""

    @pytest.mark.asyncio
    async def test_round_robin_single_token(self):
        """Single token should always return the same token."""
        pool = TokenPool(["token_A"])

        idx1, val1 = await pool.acquire_token()
        idx2, val2 = await pool.acquire_token()

        assert idx1 == idx2 == 0
        assert val1 == val2 == "token_A"

    @pytest.mark.asyncio
    async def test_round_robin_multiple_tokens(self):
        """Multiple tokens should rotate in order."""
        pool = TokenPool(["token_A", "token_B", "token_C"])

        indices = []
        for _ in range(6):
            idx, val = await pool.acquire_token()
            indices.append(idx)

        # Should cycle: 0, 1, 2, 0, 1, 2
        assert indices == [0, 1, 2, 0, 1, 2]

    @pytest.mark.asyncio
    async def test_disable_token(self):
        """Disabled tokens should be skipped in rotation."""
        pool = TokenPool(["token_A", "token_B", "token_C"])
        pool.disable_token(1)  # Disable token_B

        indices = []
        for _ in range(4):
            idx, val = await pool.acquire_token()
            indices.append(idx)

        # Should skip index 1: 0, 2, 0, 2
        assert 1 not in indices
        assert indices == [0, 2, 0, 2]

    @pytest.mark.asyncio
    async def test_all_tokens_disabled(self):
        """Should raise TokenExpiredError when all tokens are disabled."""
        pool = TokenPool(["token_A"])
        pool.disable_token(0)

        with pytest.raises(TokenExpiredError):
            await pool.acquire_token()

    def test_active_count(self):
        """active_count should reflect non-disabled tokens."""
        pool = TokenPool(["token_A", "token_B", "token_C"])
        assert pool.active_count == 3

        pool.disable_token(0)
        assert pool.active_count == 2

        pool.disable_token(2)
        assert pool.active_count == 1

    def test_mask_token(self):
        """mask_token should return first 4 + *** + last 4 chars."""
        pool = TokenPool(["abcdefghijklmnop"])
        masked = pool.mask_token(0)
        assert masked == "abcd***mnop"

    def test_mask_short_token(self):
        """Short tokens should be fully masked."""
        pool = TokenPool(["abc"])
        masked = pool.mask_token(0)
        assert masked == "***"

    def test_get_status(self):
        """get_status should return status of all tokens."""
        pool = TokenPool(["token_A", "token_B"])
        pool.disable_token(1)

        status = pool.get_status()
        assert len(status) == 2
        assert status[0]["disabled"] is False
        assert status[1]["disabled"] is True

    def test_empty_pool_raises(self):
        """Empty token list should raise ValueError."""
        with pytest.raises(ValueError):
            TokenPool([])
