"""Configuration system for Kagi Session MCP Server.

Supports TOML config file and environment variable overrides.
Multi-token configuration with session_tokens list.
"""

import os
import stat
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .exceptions import ConfigError

# Default config file location (XDG-compliant)
_DEFAULT_CONFIG_DIR = Path.home() / ".config" / "kagi-session-mcp"
_DEFAULT_CONFIG_PATH = _DEFAULT_CONFIG_DIR / "config.toml"


@dataclass
class KagiConfig:
    """Kagi Session MCP configuration."""

    session_tokens: list[str]
    summarizer_engine: str = "cecil"
    timeout: int = 30
    max_retries: int = 2
    user_agent: str | None = None

    # Internal: track where config was loaded from
    _source: str = field(default="unknown", repr=False)

    @property
    def token_count(self) -> int:
        """Number of configured session tokens."""
        return len(self.session_tokens)


def _find_config_path() -> Path | None:
    """Find config file using search order.

    1. KAGI_SESSION_CONFIG env var (explicit path)
    2. ~/.config/kagi-session-mcp/config.toml (XDG-compliant)
    3. ./config.toml (current working directory, for development)
    """
    # Check explicit env var first
    if env_path := os.environ.get("KAGI_SESSION_CONFIG"):
        path = Path(env_path)
        if path.is_file():
            return path
        raise ConfigError(f"Config file not found at KAGI_SESSION_CONFIG={env_path}")

    # Check XDG-compliant location
    if _DEFAULT_CONFIG_PATH.is_file():
        return _DEFAULT_CONFIG_PATH

    # Check current directory
    cwd_config = Path.cwd() / "config.toml"
    if cwd_config.is_file():
        return cwd_config

    return None


def _check_config_permissions(path: Path) -> None:
    """Warn if config file has overly permissive permissions."""
    try:
        mode = path.stat().st_mode
        if mode & stat.S_IRGRP or mode & stat.S_IROTH:
            import logging
            logger = logging.getLogger("kagi-session-mcp")
            logger.warning(
                f"Config file {path} is readable by group/others. "
                f"Consider running: chmod 600 {path}"
            )
    except OSError:
        pass  # Permission check is best-effort on Windows


def _validate_tokens(tokens: list[str]) -> None:
    """Validate session tokens."""
    if not tokens:
        raise ConfigError(
            "No session token found. Configure via:\n"
            "  - KAGI_SESSION_TOKENS env var (comma-separated)\n"
            "  - KAGI_SESSION_TOKEN env var (single token)\n"
            "  - session_tokens in config.toml"
        )

    for i, token in enumerate(tokens):
        token = token.strip()
        if not token:
            raise ConfigError(f"Session token #{i + 1} is empty")
        if len(token) < 10:
            raise ConfigError(
                f"Session token #{i + 1} appears invalid (too short: {len(token)} chars)"
            )


def load_config() -> KagiConfig:
    """Load configuration from file and/or environment variables.

    Priority (highest to lowest):
    1. KAGI_SESSION_TOKENS env var (comma-separated)
    2. KAGI_SESSION_TOKEN env var (single token)
    3. session_tokens in config.toml
    4. session_token in config.toml (legacy single-token)
    """
    tokens: list[str] = []
    config_values: dict = {}
    source = "unknown"

    # --- Token sources (priority order) ---

    # 1. KAGI_SESSION_TOKENS env var (comma-separated, highest priority)
    if env_tokens := os.environ.get("KAGI_SESSION_TOKENS"):
        tokens = [t.strip() for t in env_tokens.split(",") if t.strip()]
        source = "env:KAGI_SESSION_TOKENS"

    # 2. KAGI_SESSION_TOKEN env var (single token)
    if not tokens and (env_token := os.environ.get("KAGI_SESSION_TOKEN")):
        tokens = [env_token.strip()]
        source = "env:KAGI_SESSION_TOKEN"

    # 3. Config file
    if not tokens:
        config_path = _find_config_path()
        if config_path:
            source = f"file:{config_path}"
            _check_config_permissions(config_path)

            try:
                raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError as e:
                raise ConfigError(f"Failed to parse config file {config_path}: {e}")

            kagi_section = raw.get("kagi", {})
            client_section = raw.get("client", {})

            # Support both session_tokens (list) and session_token (single, legacy)
            if "session_tokens" in kagi_section:
                val = kagi_section["session_tokens"]
                if isinstance(val, list):
                    tokens = [str(t).strip() for t in val if str(t).strip()]
                elif isinstance(val, str):
                    tokens = [val.strip()]
            elif "session_token" in kagi_section:
                val = kagi_section["session_token"]
                if isinstance(val, str):
                    tokens = [val.strip()]

            # Other config values
            config_values["summarizer_engine"] = kagi_section.get("summarizer_engine", "cecil")
            config_values["timeout"] = client_section.get("timeout", 30)
            config_values["max_retries"] = client_section.get("max_retries", 2)
            config_values["user_agent"] = client_section.get("user_agent")

    # Validate tokens
    _validate_tokens(tokens)

    return KagiConfig(
        session_tokens=tokens,
        summarizer_engine=config_values.get("summarizer_engine", "cecil"),
        timeout=config_values.get("timeout", 30),
        max_retries=config_values.get("max_retries", 2),
        user_agent=config_values.get("user_agent"),
        _source=source,
    )
