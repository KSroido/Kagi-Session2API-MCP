"""Unit tests for config module."""

import os
import tempfile
from pathlib import Path

import pytest

from kagi_session_mcp.config import KagiConfig, load_config, _validate_tokens
from kagi_session_mcp.exceptions import ConfigError


class TestValidateTokens:
    """Tests for token validation."""

    def test_valid_tokens(self):
        _validate_tokens(["a" * 20, "b" * 20])  # Should not raise

    def test_empty_list(self):
        with pytest.raises(ConfigError, match="No session token"):
            _validate_tokens([])

    def test_short_token(self):
        with pytest.raises(ConfigError, match="too short"):
            _validate_tokens(["abc"])

    def test_empty_token(self):
        with pytest.raises(ConfigError, match="empty"):
            _validate_tokens([""])


class TestLoadConfigFromEnv:
    """Tests for config loading from environment variables."""

    def test_single_token_env(self, monkeypatch):
        monkeypatch.setenv("KAGI_SESSION_TOKEN", "a" * 32)
        # Clear other env vars
        monkeypatch.delenv("KAGI_SESSION_TOKENS", raising=False)
        monkeypatch.delenv("KAGI_SESSION_CONFIG", raising=False)

        config = load_config()
        assert config.token_count == 1
        assert config.session_tokens[0] == "a" * 32
        assert "env:KAGI_SESSION_TOKEN" in config._source

    def test_multi_token_env(self, monkeypatch):
        monkeypatch.setenv("KAGI_SESSION_TOKENS", f"{'a' * 32},{'b' * 32}")
        monkeypatch.delenv("KAGI_SESSION_TOKEN", raising=False)
        monkeypatch.delenv("KAGI_SESSION_CONFIG", raising=False)

        config = load_config()
        assert config.token_count == 2
        assert "env:KAGI_SESSION_TOKENS" in config._source

    def test_tokens_env_takes_precedence(self, monkeypatch):
        """KAGI_SESSION_TOKENS should take precedence over KAGI_SESSION_TOKEN."""
        monkeypatch.setenv("KAGI_SESSION_TOKENS", f"{'a' * 32},{'b' * 32}")
        monkeypatch.setenv("KAGI_SESSION_TOKEN", "c" * 32)
        monkeypatch.delenv("KAGI_SESSION_CONFIG", raising=False)

        config = load_config()
        assert config.token_count == 2
        assert "env:KAGI_SESSION_TOKENS" in config._source

    def test_no_config_raises(self, monkeypatch):
        """Missing config should raise ConfigError."""
        monkeypatch.delenv("KAGI_SESSION_TOKEN", raising=False)
        monkeypatch.delenv("KAGI_SESSION_TOKENS", raising=False)
        monkeypatch.delenv("KAGI_SESSION_CONFIG", raising=False)

        with pytest.raises(ConfigError):
            load_config()


class TestLoadConfigFromFile:
    """Tests for config loading from TOML file."""

    def test_load_from_toml(self, monkeypatch, tmp_path):
        # Create a config file
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[kagi]\n'
            f'session_tokens = ["{"a" * 32}", "{"b" * 32}"]\n'
            'summarizer_engine = "agnes"\n'
            '\n'
            '[client]\n'
            'timeout = 60\n'
            'max_retries = 3\n'
        )

        monkeypatch.setenv("KAGI_SESSION_CONFIG", str(config_file))
        monkeypatch.delenv("KAGI_SESSION_TOKEN", raising=False)
        monkeypatch.delenv("KAGI_SESSION_TOKENS", raising=False)

        config = load_config()
        assert config.token_count == 2
        assert config.summarizer_engine == "agnes"
        assert config.timeout == 60
        assert config.max_retries == 3

    def test_legacy_single_token(self, monkeypatch, tmp_path):
        """Legacy session_token (singular) should still work."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            f'[kagi]\nsession_token = "{"a" * 32}"\n'
        )

        monkeypatch.setenv("KAGI_SESSION_CONFIG", str(config_file))
        monkeypatch.delenv("KAGI_SESSION_TOKEN", raising=False)
        monkeypatch.delenv("KAGI_SESSION_TOKENS", raising=False)

        config = load_config()
        assert config.token_count == 1

    def test_invalid_toml(self, monkeypatch, tmp_path):
        """Invalid TOML should raise ConfigError."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("invalid [toml [[[syntax")

        monkeypatch.setenv("KAGI_SESSION_CONFIG", str(config_file))
        monkeypatch.delenv("KAGI_SESSION_TOKEN", raising=False)
        monkeypatch.delenv("KAGI_SESSION_TOKENS", raising=False)

        with pytest.raises(ConfigError, match="Failed to parse"):
            load_config()

    def test_missing_config_file(self, monkeypatch):
        """Non-existent config file should raise ConfigError."""
        monkeypatch.setenv("KAGI_SESSION_CONFIG", "/nonexistent/config.toml")
        monkeypatch.delenv("KAGI_SESSION_TOKEN", raising=False)
        monkeypatch.delenv("KAGI_SESSION_TOKENS", raising=False)

        with pytest.raises(ConfigError, match="not found"):
            load_config()


class TestKagiConfig:
    """Tests for KagiConfig dataclass."""

    def test_token_count(self):
        config = KagiConfig(session_tokens=["a" * 20, "b" * 20])
        assert config.token_count == 2

    def test_defaults(self):
        config = KagiConfig(session_tokens=["a" * 20])
        assert config.summarizer_engine == "cecil"
        assert config.timeout == 30
        assert config.max_retries == 2
        assert config.user_agent is None
