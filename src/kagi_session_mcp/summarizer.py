"""Summarizer module for Kagi Session MCP Server.

Accesses Kagi's internal summarizer endpoint via session token.
This is marked as experimental — the endpoint may change without notice.
"""

import logging

from .client import KagiSessionClient
from .exceptions import KagiSessionError

logger = logging.getLogger("kagi-session-mcp")

# Valid summarizer engines
VALID_ENGINES = {"cecil", "agnes", "daphne", "muriel"}

# Valid summary types
VALID_SUMMARY_TYPES = {"summary", "takeaway"}


def validate_engine(engine: str) -> str:
    """Validate and return the summarizer engine name.

    Args:
        engine: Engine name to validate

    Returns:
        Validated engine name

    Raises:
        ValueError: If engine is not valid
    """
    if engine not in VALID_ENGINES:
        raise ValueError(
            f"Invalid summarizer engine: '{engine}'. "
            f"Valid engines: {', '.join(sorted(VALID_ENGINES))}"
        )
    return engine


def validate_summary_type(summary_type: str) -> str:
    """Validate and return the summary type.

    Args:
        summary_type: Summary type to validate

    Returns:
        Validated summary type

    Raises:
        ValueError: If summary_type is not valid
    """
    if summary_type not in VALID_SUMMARY_TYPES:
        raise ValueError(
            f"Invalid summary type: '{summary_type}'. "
            f"Valid types: {', '.join(sorted(VALID_SUMMARY_TYPES))}"
        )
    return summary_type
