"""Kagi Session MCP Server - FastMCP server with search and summarizer tools.

Provides kagi_search_fetch and kagi_summarizer tools that mirror the official
kagimcp tool signatures for compatibility, but use session token authentication
instead of the official API.
"""

import argparse
import logging
import time
from typing import Literal

from fastmcp import FastMCP
from pydantic import Field

from .client import KagiSessionClient
from .config import KagiConfig, load_config
from .exceptions import (
    KagiSessionError,
    NetworkError,
    ParseError,
    RateLimitError,
    TokenExpiredError,
)
from .formatter import format_search_results, format_summarizer_result
from .parser import parse_search_html
from .summarizer import validate_engine, validate_summary_type

# --- Global state ---
config: KagiConfig | None = None
client: KagiSessionClient | None = None

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("kagi-session2api-mcp")

# --- MCP Server ---
mcp = FastMCP(
    "kagi-session2api-mcp",
    instructions=(
        "Kagi Search MCP server using session-based access. "
        "Provides kagi_search_fetch for web search and kagi_summarizer "
        "for URL summarization. Requires a Kagi session token in config. "
        "Search supports Kagi operators: site:, -site:, filetype:, intitle:, "
        'inurl:, lang:, loc:, before:, after:, "exact phrase", +term, -term'
    ),
)


@mcp.tool()
async def kagi_search_fetch(
    queries: list[str] = Field(
        description=(
            "One or more concise, keyword-focused search queries. "
            "Include essential context within each query for standalone use. "
            "Supports Kagi operators: site:, -site:, filetype:/ext:, intitle:, "
            'inurl:, lang:, loc:, before:, after:, "exact phrase", +term, -term'
        )
    ),
    limit: int | None = Field(
        default=None,
        description="Maximum number of results per query. Default: all available.",
    ),
) -> str:
    """Fetch web results based on one or more queries using Kagi Search.

    Use for general search and when the user explicitly tells you to
    'fetch' results/information. Results are from all queries given.
    They are numbered continuously, so that a user may be able to refer
    to a result by a specific number.
    """
    if not queries:
        raise ValueError("Search called with no queries.")

    if client is None:
        raise RuntimeError("Server not initialized. Session client is missing.")

    responses = []
    for query in queries:
        start = time.monotonic()
        html = await client.search_html(query)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        response = parse_search_html(html, query, elapsed_ms)

        # Apply limit if specified
        if limit is not None and limit > 0:
            response.data = response.data[:limit]

        responses.append(response)

    return format_search_results(queries, responses)


@mcp.tool()
async def kagi_summarizer(
    url: str = Field(description="A URL to a document to summarize."),
    summary_type: Literal["summary", "takeaway"] = Field(
        default="summary",
        description=(
            "Type of summary to produce. Options are 'summary' for "
            "paragraph prose and 'takeaway' for a bulleted list of key points."
        ),
    ),
    target_language: str | None = Field(
        default=None,
        description=(
            "Desired output language using language codes "
            "(e.g., 'EN' for English). If not specified, the document's "
            "original language influences the output."
        ),
    ),
    engine: Literal["cecil", "agnes", "daphne", "muriel"] = Field(
        default="cecil",
        description=(
            "Summarizer engine to use. 'cecil' is the default. "
            "Note: This is an experimental feature — the summarizer "
            "endpoint may change without notice."
        ),
    ),
) -> str:
    """Summarize content from a URL using the Kagi Summarizer.

    The Summarizer can summarize any document type (text webpage, video,
    audio, etc.)

    Note: This tool uses Kagi's internal summarizer endpoint accessed via
    session token. This is experimental and may break if Kagi changes
    their internal API.
    """
    if not url:
        raise ValueError("Summarizer called with no URL.")

    if client is None:
        raise RuntimeError("Server not initialized. Session client is missing.")

    # Validate parameters
    engine = validate_engine(engine)
    summary_type = validate_summary_type(summary_type)

    result = await client.summarize(
        url=url,
        engine=engine,
        summary_type=summary_type,
        target_language=target_language,
    )

    return format_summarizer_result(result)


def _log_startup_info(cfg: KagiConfig, transport: str) -> None:
    """Log startup configuration information."""
    logger.info("=" * 50)
    logger.info("Kagi Session MCP Server starting...")
    logger.info(f"Config source: {cfg._source}")
    logger.info(f"Token pool: {cfg.token_count} token(s) configured")

    if client is not None:
        for i in range(cfg.token_count):
            logger.info(f"  Token #{i + 1}: {client._pool.mask_token(i)}")

    effective_rate = 5 * cfg.token_count
    logger.info(f"Rate limit: 5 req/s per token (effective: {effective_rate} req/s)")
    logger.info(f"Summarizer engine: {cfg.summarizer_engine}")
    logger.info(f"Timeout: {cfg.timeout}s")
    logger.info(f"Max retries: {cfg.max_retries}")
    logger.info(f"Transport: {transport}")
    logger.info("=" * 50)


def main() -> None:
    """Main entry point for the Kagi Session MCP Server."""
    global config, client

    parser = argparse.ArgumentParser(
        description="Kagi Session MCP Server - Search and Summarize via session tokens"
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Use HTTP transport (streamable-http) instead of stdio",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (HTTP transport only, default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (HTTP transport only, default: 8000)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()

    # Set log level
    logging.getLogger("kagi-session2api-mcp").setLevel(args.log_level)

    # Load configuration
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise SystemExit(1) from e

    # Initialize HTTP client
    client = KagiSessionClient(config)

    # Determine transport
    transport = "streamable-http" if args.http else "stdio"

    # Log startup info
    _log_startup_info(config, transport)

    # Run server
    if args.http:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run("streamable-http")
    else:
        mcp.run()  # stdio transport (default for MCP)


if __name__ == "__main__":
    main()
