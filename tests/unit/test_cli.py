"""Unit tests for the FastAuthMCP CLI commands."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from fastauthmcp.cli import cli
from fastauthmcp.exceptions import ConfigurationError, ProviderError
from fastauthmcp.models import TokenSet


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def valid_config_yaml(tmp_path):
    """Create a valid fastauthmcp.yaml."""
    content = """\
auth:
  provider: oidc
  issuer: https://idp.example.com
  client_id: my-app
  scopes:
    - openid
    - profile
    - email
observability:
  enabled: true
  log_level: info
sessions:
  ttl: 3600
"""
    path = tmp_path / "fastauthmcp.yaml"
    path.write_text(content)
    return path


@pytest.fixture
def minimal_config_yaml(tmp_path):
    """Create a minimal fastauthmcp.yaml without auth."""
    content = """\
observability:
  enabled: true
"""
    path = tmp_path / "fastauthmcp.yaml"
    path.write_text(content)
    return path


def _make_jwt(claims: dict) -> str:
    """Create a fake JWT with given claims (no signature verification)."""
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        .rstrip(b"=")
        .decode()
    )
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    signature = base64.urlsafe_b64encode(b"fake-signature").rstrip(b"=").decode()
    return f"{header}.{payload}.{signature}"


def _make_token_set(
    email: str = "user@example.com",
    subject: str = "user-123",
    roles: list[str] | None = None,
    expired: bool = False,
) -> TokenSet:
    """Create a TokenSet with JWT access/id tokens containing given claims."""
    claims = {
        "email": email,
        "sub": subject,
        "realm_access": {"roles": roles or ["user"]},
    }
    access_token = _make_jwt(claims)
    id_token = _make_jwt(claims)

    if expired:
        expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    else:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    return TokenSet(
        access_token=access_token,
        refresh_token="refresh-token-123",
        expires_at=expires_at,
        token_type="Bearer",
        id_token=id_token,
    )


class TestRunCommand:
    """Tests for `fastauthmcp run`."""

    def test_run_exits_error_on_invalid_config(self, runner, tmp_path):
        """Test that `run` exits with error on invalid config path."""
        bad_path = str(tmp_path / "nonexistent.yaml")
        result = runner.invoke(cli, ["run", "--config", bad_path])
        assert result.exit_code != 0
        assert "Error" in result.output or "Error" in (result.output + (result.output or ""))

    def test_run_exits_error_on_invalid_yaml(self, runner, tmp_path):
        """Test that `run` exits with error on invalid YAML."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("invalid: [unclosed")
        result = runner.invoke(cli, ["run", "--config", str(bad_yaml)])
        assert result.exit_code != 0

    @patch("fastauthmcp.cli.FastAuthMCP")
    @patch("fastauthmcp.cli.ConfigLoader")
    def test_run_prints_ready_message(self, mock_loader_cls, mock_server_cls, runner, tmp_path):
        """Test that `run` prints a ready message on success."""
        mock_loader = MagicMock()
        mock_config = MagicMock()
        mock_loader.load.return_value = mock_config
        mock_loader_cls.return_value = mock_loader

        mock_server = MagicMock()
        mock_server.run.return_value = None
        mock_server_cls.return_value = mock_server

        config_file = tmp_path / "fastauthmcp.yaml"
        config_file.write_text("observability:\n  enabled: true\n")

        result = runner.invoke(cli, ["run", "--config", str(config_file)])
        assert result.exit_code == 0
        assert "FastAuthMCP server starting (stdio transport)" in result.output


class TestLoginCommand:
    """Tests for `fastauthmcp login`."""

    @patch("fastauthmcp.cli.get_token_storage")
    @patch("fastauthmcp.cli.OAuthService")
    @patch("fastauthmcp.cli.ConfigLoader")
    def test_login_stores_tokens_and_outputs_email(
        self, mock_loader_cls, mock_oauth_cls, mock_storage_fn, runner
    ):
        """Test successful login stores tokens and prints email."""
        # Set up config loader mock
        mock_loader = MagicMock()
        mock_config = MagicMock()
        mock_config.auth = MagicMock()
        mock_config.auth.issuer = "https://idp.example.com"
        mock_config.auth.scopes = ["openid", "profile", "email"]
        mock_loader.load.return_value = mock_config
        mock_loader_cls.return_value = mock_loader

        # Set up OAuth mock
        mock_oauth = MagicMock()
        mock_oauth.discover_endpoints = AsyncMock()
        mock_auth_result = MagicMock()
        mock_auth_result.code = "auth-code-123"
        mock_auth_result.verifier = "verifier-123"
        mock_auth_result.redirect_uri = "http://localhost:12345/callback"
        mock_oauth.initiate_flow = AsyncMock(return_value=mock_auth_result)

        token_set = _make_token_set(email="alice@example.com")
        mock_oauth.exchange_code = AsyncMock(return_value=token_set)
        mock_oauth_cls.return_value = mock_oauth

        # Set up storage mock
        mock_storage = MagicMock()
        mock_storage.store = AsyncMock()
        mock_storage_fn.return_value = mock_storage

        result = runner.invoke(cli, ["login"])
        assert result.exit_code == 0
        assert "alice@example.com" in result.output
        mock_storage.store.assert_called_once()

    @patch("fastauthmcp.cli.ConfigLoader")
    def test_login_exits_error_when_no_auth_config(self, mock_loader_cls, runner):
        """Test login exits with error when no auth section in config."""
        mock_loader = MagicMock()
        mock_config = MagicMock()
        mock_config.auth = None
        mock_loader.load.return_value = mock_config
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(cli, ["login"])
        assert result.exit_code != 0
        assert "No auth configuration" in result.output

    @patch("fastauthmcp.cli.get_token_storage")
    @patch("fastauthmcp.cli.OAuthService")
    @patch("fastauthmcp.cli.ConfigLoader")
    def test_login_exits_error_on_auth_failure(
        self, mock_loader_cls, mock_oauth_cls, mock_storage_fn, runner
    ):
        """Test login exits with error when OAuth flow fails."""
        mock_loader = MagicMock()
        mock_config = MagicMock()
        mock_config.auth = MagicMock()
        mock_config.auth.issuer = "https://idp.example.com"
        mock_loader.load.return_value = mock_config
        mock_loader_cls.return_value = mock_loader

        mock_oauth = MagicMock()
        mock_oauth.discover_endpoints = AsyncMock(side_effect=ProviderError("IDP unreachable"))
        mock_oauth_cls.return_value = mock_oauth

        mock_storage_fn.return_value = MagicMock()

        result = runner.invoke(cli, ["login"])
        assert result.exit_code != 0
        assert "IDP unreachable" in result.output


class TestLogoutCommand:
    """Tests for `fastauthmcp logout`."""

    @patch("fastauthmcp.cli.get_token_storage")
    def test_logout_clears_tokens(self, mock_storage_fn, runner):
        """Test that logout clears stored tokens."""
        mock_storage = MagicMock()
        mock_storage.delete = AsyncMock()
        mock_storage_fn.return_value = mock_storage

        result = runner.invoke(cli, ["logout"])
        assert result.exit_code == 0
        assert "Logged out successfully." in result.output
        mock_storage.delete.assert_called_once_with("default")

    @patch("fastauthmcp.cli.get_token_storage")
    def test_logout_exits_error_on_failure(self, mock_storage_fn, runner):
        """Test that logout exits with error if deletion fails."""
        mock_storage = MagicMock()
        mock_storage.delete = AsyncMock(side_effect=RuntimeError("Storage failure"))
        mock_storage_fn.return_value = mock_storage

        result = runner.invoke(cli, ["logout"])
        assert result.exit_code != 0
        assert "Error" in result.output


class TestWhoamiCommand:
    """Tests for `fastauthmcp whoami`."""

    @patch("fastauthmcp.cli.get_token_storage")
    def test_whoami_displays_user_info(self, mock_storage_fn, runner):
        """Test that whoami displays email, subject, and roles."""
        token_set = _make_token_set(
            email="alice@corp.com",
            subject="sub-456",
            roles=["admin", "user"],
        )
        mock_storage = MagicMock()
        mock_storage.retrieve = AsyncMock(return_value=token_set)
        mock_storage_fn.return_value = mock_storage

        result = runner.invoke(cli, ["whoami"])
        assert result.exit_code == 0
        assert "alice@corp.com" in result.output
        assert "sub-456" in result.output
        assert "admin" in result.output
        assert "user" in result.output

    @patch("fastauthmcp.cli.get_token_storage")
    def test_whoami_exits_nonzero_when_no_session(self, mock_storage_fn, runner):
        """Test that whoami exits non-zero when no tokens are stored."""
        mock_storage = MagicMock()
        mock_storage.retrieve = AsyncMock(return_value=None)
        mock_storage_fn.return_value = mock_storage

        result = runner.invoke(cli, ["whoami"])
        assert result.exit_code != 0
        assert "No authenticated session" in result.output

    @patch("fastauthmcp.cli.get_token_storage")
    def test_whoami_shows_no_roles(self, mock_storage_fn, runner):
        """Test whoami with user that has no roles."""
        claims = {"email": "norole@example.com", "sub": "user-789"}
        access_token = _make_jwt(claims)
        token_set = TokenSet(
            access_token=access_token,
            refresh_token=None,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            token_type="Bearer",
            id_token=None,
        )
        mock_storage = MagicMock()
        mock_storage.retrieve = AsyncMock(return_value=token_set)
        mock_storage_fn.return_value = mock_storage

        result = runner.invoke(cli, ["whoami"])
        assert result.exit_code == 0
        assert "norole@example.com" in result.output
        assert "none" in result.output


class TestDoctorCommand:
    """Tests for `fastauthmcp doctor`."""

    @patch("fastauthmcp.cli.get_token_storage")
    @patch("fastauthmcp.cli.ConfigLoader")
    def test_doctor_all_checks_pass(self, mock_loader_cls, mock_storage_fn, runner):
        """Test doctor reports all checks passing."""
        # Config check passes
        mock_loader = MagicMock()
        mock_config = MagicMock()
        mock_config.auth = None  # No auth configured
        mock_loader.load.return_value = mock_config
        mock_loader_cls.return_value = mock_loader

        # Token check: no stored token
        mock_storage = MagicMock()
        mock_storage.retrieve = AsyncMock(return_value=None)
        mock_storage_fn.return_value = mock_storage

        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "Configuration file is valid" in result.output

    @patch("fastauthmcp.cli.get_token_storage")
    @patch("fastauthmcp.cli.ConfigLoader")
    def test_doctor_reports_expired_token(self, mock_loader_cls, mock_storage_fn, runner):
        """Test doctor reports expired token."""
        mock_loader = MagicMock()
        mock_config = MagicMock()
        mock_config.auth = None
        mock_loader.load.return_value = mock_config
        mock_loader_cls.return_value = mock_loader

        expired_token_set = _make_token_set(expired=True)
        mock_storage = MagicMock()
        mock_storage.retrieve = AsyncMock(return_value=expired_token_set)
        mock_storage_fn.return_value = mock_storage

        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code != 0
        assert "expired" in result.output

    @patch("fastauthmcp.cli.get_token_storage")
    @patch("fastauthmcp.cli.ConfigLoader")
    def test_doctor_reports_config_error(self, mock_loader_cls, mock_storage_fn, runner):
        """Test doctor reports config error."""
        mock_loader = MagicMock()
        mock_loader.load.side_effect = ConfigurationError("Invalid YAML")
        mock_loader_cls.return_value = mock_loader

        mock_storage = MagicMock()
        mock_storage.retrieve = AsyncMock(return_value=None)
        mock_storage_fn.return_value = mock_storage

        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code != 0
        assert "Invalid YAML" in result.output

    @patch("fastauthmcp.cli.get_token_storage")
    @patch("fastauthmcp.cli.OAuthService")
    @patch("fastauthmcp.cli.ConfigLoader")
    def test_doctor_reports_idp_unreachable(
        self, mock_loader_cls, mock_oauth_cls, mock_storage_fn, runner
    ):
        """Test doctor reports IDP connectivity failure."""
        mock_loader = MagicMock()
        mock_config = MagicMock()
        mock_auth = MagicMock()
        mock_auth.issuer = "https://idp.example.com"
        mock_config.auth = mock_auth
        mock_loader.load.return_value = mock_config
        mock_loader_cls.return_value = mock_loader

        mock_oauth = MagicMock()
        mock_oauth.discover_endpoints = AsyncMock(side_effect=ProviderError("Connection refused"))
        mock_oauth_cls.return_value = mock_oauth

        mock_storage = MagicMock()
        mock_storage.retrieve = AsyncMock(return_value=None)
        mock_storage_fn.return_value = mock_storage

        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code != 0
        assert "Identity provider" in result.output or "Connection refused" in result.output


class TestConfigValidateCommand:
    """Tests for `fastauthmcp config validate`."""

    def test_config_validate_valid_file(self, runner, valid_config_yaml, monkeypatch):
        """Test validate reports success for valid config."""
        monkeypatch.setenv("FASTAUTHMCP_CONFIG", str(valid_config_yaml))
        result = runner.invoke(cli, ["config", "validate"])
        assert result.exit_code == 0
        assert "Configuration is valid" in result.output

    def test_config_validate_invalid_yaml(self, runner, tmp_path, monkeypatch):
        """Test validate reports errors for invalid YAML."""
        bad_yaml = tmp_path / "fastauthmcp.yaml"
        bad_yaml.write_text("unknown_top_key: true\n")
        monkeypatch.setenv("FASTAUTHMCP_CONFIG", str(bad_yaml))
        result = runner.invoke(cli, ["config", "validate"])
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_config_validate_missing_file(self, runner, tmp_path, monkeypatch):
        """Test validate reports error for missing file."""
        monkeypatch.setenv("FASTAUTHMCP_CONFIG", str(tmp_path / "nope.yaml"))
        result = runner.invoke(cli, ["config", "validate"])
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_config_validate_warnings_for_client_secret(self, runner, tmp_path, monkeypatch):
        """Test validate shows warning when client_secret is in config."""
        content = """\
auth:
  provider: oidc
  issuer: https://idp.example.com
  client_id: my-app
  client_secret: supersecret
"""
        yaml_path = tmp_path / "fastauthmcp.yaml"
        yaml_path.write_text(content)
        monkeypatch.setenv("FASTAUTHMCP_CONFIG", str(yaml_path))
        result = runner.invoke(cli, ["config", "validate"])
        assert result.exit_code == 0
        assert "Warning" in result.output
        assert "client_secret" in result.output


class TestCLIExitCodes:
    """Test that all commands follow exit code conventions."""

    def test_successful_commands_exit_zero(self, runner):
        """Test that the CLI group itself exits zero."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0

    def test_run_help_exits_zero(self, runner):
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0

    def test_login_help_exits_zero(self, runner):
        result = runner.invoke(cli, ["login", "--help"])
        assert result.exit_code == 0

    def test_config_validate_help_exits_zero(self, runner):
        result = runner.invoke(cli, ["config", "validate", "--help"])
        assert result.exit_code == 0
