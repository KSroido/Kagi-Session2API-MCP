"""HTTP client for Kagi session-based access with multi-token rotation.

Provides KagiSessionClient that manages a pool of httpx.AsyncClient instances,
one per session token, with Firefox UA spoofing and automatic token expiry detection.
Uses HTTP/2 for improved connection performance.
"""

import asyncio
import logging
import time
from typing import Any, Callable

import httpx

from .config import KagiConfig
from .exceptions import (
    KagiSessionError,
    NetworkError,
    RateLimitError,
    TokenExpiredError,
)
from .token_pool import TokenPool

logger = logging.getLogger("kagi-session2api-mcp")

# Firefox browser headers for UA spoofing
FIREFOX_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
        "Gecko/20100101 Firefox/128.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# Summarizer-specific headers (accepts JSON)
SUMMARIZER_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


async def retry_with_backoff(
    fn: Callable[..., Any],
    max_retries: int = 2,
    initial_delay: float = 1.0,
) -> Any:
    """Retry a callable with exponential backoff on transient errors.

    Only retries on timeout and network errors, NOT on auth or parse errors.
    """
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_error = e
            if attempt >= max_retries:
                raise NetworkError(f"Network error after {max_retries + 1} attempts: {e}")
            delay = initial_delay * (2**attempt)
            logger.warning(f"Retry {attempt + 1}/{max_retries} after {delay:.1f}s: {e}")
            await asyncio.sleep(delay)
    # Should not reach here, but just in case
    raise NetworkError(f"Network error: {last_error}")


class KagiSessionClient:
    """HTTP client for Kagi session-based access with multi-token rotation.

    Each session token gets its own httpx.AsyncClient instance with the correct
    cookie set. This avoids race conditions with cookie swapping on a shared client.

    Token rotation is handled by TokenPool (round-robin with per-token rate limiting).

    HTTP/2 is enabled for improved connection multiplexing and performance.
    """

    def __init__(self, config: KagiConfig):
        self.config = config
        self._pool = TokenPool(config.session_tokens, rate_per_token=5.0)
        self._clients: dict[int, httpx.AsyncClient] = {}

        # Override User-Agent if configured
        self._base_headers = dict(FIREFOX_HEADERS)
        if config.user_agent:
            self._base_headers["User-Agent"] = config.user_agent

    async def _get_client_for_token(self, token_index: int, token: str) -> httpx.AsyncClient:
        """Get or create an httpx client for a specific token.

        Each token gets its own client with the cookie pre-set.
        If the existing client is closed, create a new one.
        HTTP/2 is enabled for improved performance.
        """
        if token_index not in self._clients or self._clients[token_index].is_closed:
            self._clients[token_index] = httpx.AsyncClient(
                base_url="https://kagi.com",
                headers=self._base_headers,
                cookies={"kagi_session": token},
                timeout=self.config.timeout,
                follow_redirects=True,
                max_redirects=5,
                http2=True,
            )
        return self._clients[token_index]

    def _handle_response(
        self, response: httpx.Response, token_index: int
    ) -> None:
        """Handle HTTP response with appropriate error mapping.

        Raises:
            TokenExpiredError: On 401/403 or redirect to login
            RateLimitError: On 429
            KagiSessionError: On 5xx server errors
        """
        if response.status_code in (401, 403):
            self._pool.disable_token(token_index)
            raise TokenExpiredError(
                f"Token {self._pool.mask_token(token_index)} is invalid or expired. "
                f"Remaining active tokens: {self._pool.active_count}"
            )

        if response.status_code == 429:
            raise RateLimitError(
                "Rate limited by Kagi server. Please wait before retrying."
            )

        if response.status_code >= 500:
            raise KagiSessionError(
                f"Kagi server error (HTTP {response.status_code})"
            )

        # Check for redirect to login page
        if "/login" in str(response.url):
            self._pool.disable_token(token_index)
            raise TokenExpiredError(
                f"Token {self._pool.mask_token(token_index)} expired "
                f"(redirected to login page). "
                f"Remaining active tokens: {self._pool.active_count}"
            )

        response.raise_for_status()

    async def search_html(self, query: str) -> str:
        """Fetch search results as HTML from Kagi using token rotation.

        Uses the /html/search endpoint which returns server-rendered HTML.

        Args:
            query: Search query string (supports Kagi operators like site:, lang:, etc.)

        Returns:
            HTML string of the search results page

        Raises:
            TokenExpiredError: If all tokens are expired
            RateLimitError: If rate limited
            NetworkError: If network issues after retries
        """

        async def _do_search() -> str:
            token_index, token = await self._pool.acquire_token()
            client = await self._get_client_for_token(token_index, token)

            logger.debug(
                f"Searching Kagi for '{query[:50]}' "
                f"using token #{token_index + 1} ({self._pool.mask_token(token_index)})"
            )

            response = await client.get("/html/search", params={"q": query})
            self._handle_response(response, token_index)

            # Check for login page in HTML content (expired token but 200 status)
            html = response.text
            if _is_login_page(html):
                self._pool.disable_token(token_index)
                raise TokenExpiredError(
                    f"Token {self._pool.mask_token(token_index)} expired "
                    f"(login page in response). "
                    f"Remaining active tokens: {self._pool.active_count}"
                )

            return html

        return await retry_with_backoff(
            _do_search,
            max_retries=self.config.max_retries,
        )

    async def summarize(
        self,
        url: str,
        engine: str = "cecil",
        summary_type: str = "summary",
        target_language: str | None = None,
    ) -> dict:
        """Access summarizer via internal endpoint using token rotation.

        Uses /mother/summary_labs which returns JSON directly.

        Args:
            url: URL to summarize
            engine: Summarizer engine (cecil, agnes, daphne, muriel)
            summary_type: Type of summary (summary, takeaway)
            target_language: Target language code (e.g., 'EN')

        Returns:
            Parsed JSON response from the summarizer

        Raises:
            TokenExpiredError: If all tokens are expired
            RateLimitError: If rate limited
            NetworkError: If network issues after retries
        """

        async def _do_summarize() -> dict:
            token_index, token = await self._pool.acquire_token()
            client = await self._get_client_for_token(token_index, token)

            params: dict[str, str] = {
                "url": url,
                "engine": engine,
                "summary_type": summary_type,
            }
            if target_language:
                params["target_language"] = target_language

            logger.debug(
                f"Summarizing '{url[:50]}' using token #{token_index + 1}"
            )

            # Use summarizer-specific headers
            headers = {**self._base_headers, **SUMMARIZER_HEADERS}
            response = await client.get(
                "/mother/summary_labs", params=params, headers=headers
            )
            self._handle_response(response, token_index)

            return response.json()

        return await retry_with_backoff(
            _do_summarize,
            max_retries=self.config.max_retries,
        )

    async def close(self) -> None:
        """Close all httpx clients."""
        for idx, client in self._clients.items():
            if not client.is_closed:
                await client.aclose()
                logger.debug(f"Closed HTTP client for token #{idx + 1}")
        self._clients.clear()

    @property
    def pool_status(self) -> list[dict]:
        """Get current token pool status."""
        return self._pool.get_status()


def _is_login_page(html: str) -> bool:
    """Detect if the HTML response is a login page (token expired but 200 status).

    Checks for common indicators of Kagi's login page.
    """
    html_lower = html.lower()
    indicators = [
        'action="/authenticate"',
        'id="login"',
        'class="login-form"',
        "sign in to kagi",
        "log in to kagi",
        'name="email"',
    ]
    # If multiple indicators are present, it's likely a login page
    matches = sum(1 for ind in indicators if ind in html_lower)
    return matches >= 2
