"""Unit tests for Ceramic Pydantic configuration models."""

import pytest
from pydantic import ValidationError

from ceramic.config import (
    AuthConfig,
    AuthorizationConfig,
    AuthorizationPolicy,
    CeramicConfig,
    HotReloadConfig,
    ObservabilityConfig,
    PluginRef,
    SessionsConfig,
)


# --- AuthConfig Tests ---


class TestAuthConfig:
    def test_valid_minimal(self):
        cfg = AuthConfig(issuer="https://idp.example.com", client_id="my-app")
        assert str(cfg.issuer) == "https://idp.example.com/"
        assert cfg.client_id == "my-app"
        assert cfg.provider == "oidc"
        assert cfg.client_secret is None
        assert cfg.scopes == ["openid", "profile", "email"]
        assert cfg.callback_timeout == 120
        assert cfg.token_exchange_timeout == 30

    def test_valid_full(self):
        cfg = AuthConfig(
            issuer="https://idp.example.com",
            client_id="my-app",
            client_secret="secret123",
            scopes=["openid", "custom"],
            callback_timeout=60,
            token_exchange_timeout=10,
        )
        assert cfg.client_secret == "secret123"
        assert cfg.scopes == ["openid", "custom"]
        assert cfg.callback_timeout == 60
        assert cfg.token_exchange_timeout == 10

    def test_invalid_provider(self):
        with pytest.raises(ValidationError, match="provider"):
            AuthConfig(
                provider="saml",
                issuer="https://idp.example.com",
                client_id="app",
            )

    def test_callback_timeout_too_low(self):
        with pytest.raises(ValidationError, match="callback_timeout"):
            AuthConfig(
                issuer="https://idp.example.com",
                client_id="app",
                callback_timeout=0,
            )

    def test_callback_timeout_too_high(self):
        with pytest.raises(ValidationError, match="callback_timeout"):
            AuthConfig(
                issuer="https://idp.example.com",
                client_id="app",
                callback_timeout=601,
            )

    def test_token_exchange_timeout_too_low(self):
        with pytest.raises(ValidationError, match="token_exchange_timeout"):
            AuthConfig(
                issuer="https://idp.example.com",
                client_id="app",
                token_exchange_timeout=0,
            )

    def test_token_exchange_timeout_too_high(self):
        with pytest.raises(ValidationError, match="token_exchange_timeout"):
            AuthConfig(
                issuer="https://idp.example.com",
                client_id="app",
                token_exchange_timeout=121,
            )

    def test_missing_issuer(self):
        with pytest.raises(ValidationError, match="issuer"):
            AuthConfig(client_id="app")

    def test_missing_client_id(self):
        with pytest.raises(ValidationError, match="client_id"):
            AuthConfig(issuer="https://idp.example.com")

    def test_invalid_issuer_url(self):
        with pytest.raises(ValidationError):
            AuthConfig(issuer="not-a-url", client_id="app")


# --- AuthorizationPolicy Tests ---


class TestAuthorizationPolicy:
    def test_valid_with_role(self):
        policy = AuthorizationPolicy(tool="admin_*", require_role="admin")
        assert policy.tool == "admin_*"
        assert policy.require_role == "admin"
        assert policy.require_group is None

    def test_valid_with_group(self):
        policy = AuthorizationPolicy(tool="deploy_*", require_group="ops-team")
        assert policy.require_group == "ops-team"
        assert policy.require_role is None

    def test_tool_required(self):
        with pytest.raises(ValidationError, match="tool"):
            AuthorizationPolicy()


# --- AuthorizationConfig Tests ---


class TestAuthorizationConfig:
    def test_defaults(self):
        cfg = AuthorizationConfig()
        assert cfg.role_claim == "realm_access.roles"
        assert cfg.group_claim == "groups"
        assert cfg.policies == []

    def test_with_policies(self):
        cfg = AuthorizationConfig(
            policies=[
                AuthorizationPolicy(tool="admin_*", require_role="admin"),
                AuthorizationPolicy(tool="deploy_*", require_group="ops"),
            ]
        )
        assert len(cfg.policies) == 2
        assert cfg.policies[0].require_role == "admin"


# --- ObservabilityConfig Tests ---


class TestObservabilityConfig:
    def test_defaults(self):
        cfg = ObservabilityConfig()
        assert cfg.enabled is True
        assert cfg.metrics_path == "/metrics"
        assert cfg.metrics_port == 9090
        assert cfg.exporter == "otlp"
        assert cfg.otlp_endpoint == "http://localhost:4317"
        assert cfg.log_format == "json"
        assert cfg.log_level == "info"

    def test_metrics_port_min(self):
        cfg = ObservabilityConfig(metrics_port=1)
        assert cfg.metrics_port == 1

    def test_metrics_port_max(self):
        cfg = ObservabilityConfig(metrics_port=65535)
        assert cfg.metrics_port == 65535

    def test_metrics_port_too_low(self):
        with pytest.raises(ValidationError, match="metrics_port"):
            ObservabilityConfig(metrics_port=0)

    def test_metrics_port_too_high(self):
        with pytest.raises(ValidationError, match="metrics_port"):
            ObservabilityConfig(metrics_port=65536)

    def test_invalid_exporter(self):
        with pytest.raises(ValidationError, match="exporter"):
            ObservabilityConfig(exporter="invalid")

    def test_invalid_log_format(self):
        with pytest.raises(ValidationError, match="log_format"):
            ObservabilityConfig(log_format="xml")

    def test_invalid_log_level(self):
        with pytest.raises(ValidationError, match="log_level"):
            ObservabilityConfig(log_level="trace")

    def test_valid_exporter_console(self):
        cfg = ObservabilityConfig(exporter="console")
        assert cfg.exporter == "console"

    def test_valid_exporter_none(self):
        cfg = ObservabilityConfig(exporter="none")
        assert cfg.exporter == "none"


# --- SessionsConfig Tests ---


class TestSessionsConfig:
    def test_defaults(self):
        cfg = SessionsConfig()
        assert cfg.enabled is True
        assert cfg.ttl == 3600
        assert cfg.backend == "memory"

    def test_ttl_min(self):
        cfg = SessionsConfig(ttl=60)
        assert cfg.ttl == 60

    def test_ttl_max(self):
        cfg = SessionsConfig(ttl=86400)
        assert cfg.ttl == 86400

    def test_ttl_too_low(self):
        with pytest.raises(ValidationError, match="ttl"):
            SessionsConfig(ttl=59)

    def test_ttl_too_high(self):
        with pytest.raises(ValidationError, match="ttl"):
            SessionsConfig(ttl=86401)

    def test_invalid_backend(self):
        with pytest.raises(ValidationError, match="backend"):
            SessionsConfig(backend="redis")


# --- PluginRef Tests ---


class TestPluginRef:
    def test_valid_minimal(self):
        ref = PluginRef(module="ceramic_rate_limit")
        assert ref.module == "ceramic_rate_limit"
        assert ref.config == {}

    def test_valid_with_config(self):
        ref = PluginRef(
            module="ceramic_rate_limit",
            config={"max_requests": 100, "window_seconds": 60},
        )
        assert ref.config["max_requests"] == 100

    def test_module_required(self):
        with pytest.raises(ValidationError, match="module"):
            PluginRef()


# --- HotReloadConfig Tests ---


class TestHotReloadConfig:
    def test_defaults(self):
        cfg = HotReloadConfig()
        assert cfg.enabled is False
        assert cfg.watch_interval == 5
        assert cfg.reloadable_sections == ["observability", "authorization"]

    def test_watch_interval_min(self):
        cfg = HotReloadConfig(watch_interval=1)
        assert cfg.watch_interval == 1

    def test_watch_interval_max(self):
        cfg = HotReloadConfig(watch_interval=60)
        assert cfg.watch_interval == 60

    def test_watch_interval_too_low(self):
        with pytest.raises(ValidationError, match="watch_interval"):
            HotReloadConfig(watch_interval=0)

    def test_watch_interval_too_high(self):
        with pytest.raises(ValidationError, match="watch_interval"):
            HotReloadConfig(watch_interval=61)


# --- CeramicConfig Tests ---


class TestCeramicConfig:
    def test_empty_config(self):
        cfg = CeramicConfig()
        assert cfg.auth is None
        assert cfg.authorization is None
        assert cfg.observability is None
        assert cfg.sessions is None
        assert cfg.plugins is None
        assert cfg.hot_reload is None

    def test_rejects_unknown_keys(self):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            CeramicConfig(unknown_field="value")

    def test_full_config(self):
        cfg = CeramicConfig(
            auth=AuthConfig(
                issuer="https://idp.example.com",
                client_id="my-app",
            ),
            authorization=AuthorizationConfig(
                policies=[AuthorizationPolicy(tool="admin_*", require_role="admin")]
            ),
            observability=ObservabilityConfig(log_level="debug"),
            sessions=SessionsConfig(ttl=7200),
            plugins=[PluginRef(module="my_plugin")],
            hot_reload=HotReloadConfig(enabled=True),
        )
        assert cfg.auth is not None
        assert cfg.auth.client_id == "my-app"
        assert cfg.authorization is not None
        assert len(cfg.authorization.policies) == 1
        assert cfg.observability.log_level == "debug"
        assert cfg.sessions.ttl == 7200
        assert len(cfg.plugins) == 1
        assert cfg.hot_reload.enabled is True

    def test_partial_config(self):
        cfg = CeramicConfig(
            observability=ObservabilityConfig(),
            sessions=SessionsConfig(),
        )
        assert cfg.auth is None
        assert cfg.observability is not None
        assert cfg.sessions is not None
