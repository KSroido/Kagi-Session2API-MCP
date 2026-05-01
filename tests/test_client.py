"""Unit tests for HTTP client module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from kagi_session_mcp.client import (
    KagiSessionClient,
    _is_login_page,
    retry_with_backoff,
)
from kagi_session_mcp.config import KagiConfig
from kagi_session_mcp.exceptions import (
    NetworkError,
    RateLimitError,
    TokenExpiredError,
)


class TestIsLoginPage:
    """Tests for login page detection."""

    def test_login_page(self):
        html = '<html><body><form action="/authenticate" id="login"><input name="email"></form></body></html>'
        assert _is_login_page(html) is True

    def test_not_login_page(self):
        html = "<html><body><div class='search-result'>Results</div></body></html>"
        assert _is_login_page(html) is False

    def test_partial_indicators(self):
        """Only one indicator should not trigger detection."""
        html = "<html><body><h1>Welcome to Kagi</h1></body></html>"
        assert _is_login_page(html) is False


class TestRetryWithBackoff:
    """Tests for retry_with_backoff function."""

    @pytest.mark.asyncio
    async def test_success_first_try(self):
        fn = AsyncMock(return_value="ok")
        result = await retry_with_backoff(fn, max_retries=2)
        assert result == "ok"
        assert fn.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self):
        fn = AsyncMock(
            side_effect=[
                httpx.TimeoutException("timeout"),
                "ok",
            ]
        )
        result = await retry_with_backoff(fn, max_retries=2, initial_delay=0.01)
        assert result == "ok"
        assert fn.call_count == 2

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        fn = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        with pytest.raises(NetworkError, match="Network error"):
            await retry_with_backoff(fn, max_retries=1, initial_delay=0.01)

    @pytest.mark.asyncio
    async def test_no_retry_on_auth_error(self):
        """Auth errors should not be retried."""
        fn = AsyncMock(side_effect=TokenExpiredError("expired"))
        with pytest.raises(TokenExpiredError):
            await retry_with_backoff(fn, max_retries=2, initial_delay=0.01)
        assert fn.call_count == 1  # No retry


class TestKagiSessionClient:
    """Tests for KagiSessionClient."""

    @pytest.fixture
    def config(self):
        return KagiConfig(
            session_tokens=["a" * 32],
            timeout=10,
            max_retries=0,
        )

    @pytest.fixture
    def multi_config(self):
        return KagiConfig(
            session_tokens=["a" * 32, "b" * 32],
            timeout=10,
            max_retries=0,
        )

    def test_init_single_token(self, config):
        client = KagiSessionClient(config)
        assert client._pool.total_count == 1
        assert client._pool.active_count == 1

    def test_init_multi_token(self, multi_config):
        client = KagiSessionClient(multi_config)
        assert client._pool.total_count == 2
        assert client._pool.active_count == 2

    def test_custom_user_agent(self):
        config = KagiConfig(
            session_tokens=["a" * 32],
            user_agent="CustomBot/1.0",
        )
        client = KagiSessionClient(config)
        assert client._base_headers["User-Agent"] == "CustomBot/1.0"

    @pytest.mark.asyncio
    async def test_close(self, config):
        client = KagiSessionClient(config)
        # Create a client for a token
        await client._get_client_for_token(0, config.session_tokens[0])
        assert 0 in client._clients

        await client.close()
        assert len(client._clients) == 0

    def test_pool_status(self, config):
        client = KagiSessionClient(config)
        status = client.pool_status
        assert len(status) == 1
        assert status[0]["disabled"] is False
