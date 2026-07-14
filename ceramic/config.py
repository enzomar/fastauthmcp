"""Pydantic configuration models for the Ceramic framework.

These models define and validate the structure of ceramic.yaml configuration.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration for IDP HTTP calls."""

    failure_threshold: int = Field(default=5, ge=1, le=100)
    cooldown_seconds: int = Field(default=30, ge=1, le=300)


class MtlsConfig(BaseModel):
    """Mutual TLS (mTLS) configuration for IDP communication.

    When configured, all outbound HTTPS calls to the identity provider
    (discovery, token endpoint, JWKS) will present the client certificate
    for mutual authentication.
    """

    client_cert: str = Field(
        description="Path to the PEM-encoded client certificate file.",
    )
    client_key: str | None = Field(
        default=None,
        description="Path to the PEM-encoded client private key file. "
        "If None, the key is expected to be bundled in the client_cert file.",
    )
    ca_bundle: str | None = Field(
        default=None,
        description="Path to a custom CA bundle (PEM) for verifying the IDP's "
        "server certificate. If None, uses the system/certifi CA bundle.",
    )


class AuthConfig(BaseModel):
    """Authentication configuration for OIDC providers."""

    provider: Literal["oidc"] = "oidc"
    issuer: HttpUrl
    client_id: str
    client_secret: str | None = None
    scopes: list[str] = ["openid", "profile", "email"]
    grant_type: Literal[
        "authorization_code", "client_credentials", "token_exchange"
    ] = "authorization_code"
    callback_port: int = Field(default=9876, ge=1, le=65535)
    callback_timeout: int = Field(default=120, ge=1, le=600)
    token_exchange_timeout: int = Field(default=30, ge=1, le=120)
    mtls: MtlsConfig | None = Field(
        default=None,
        description="Mutual TLS configuration for IDP communication. "
        "When set, all outbound HTTPS calls to the identity provider "
        "will present the client certificate.",
    )
    # Token exchange (RFC 8693) — for headless/cloud deployments where
    # a user token arrives via the MCP transport/request metadata
    upstream_token_header: str | None = Field(
        default=None,
        description="Header or metadata key containing the upstream user token "
        "to exchange. If set with grant_type=token_exchange, Ceramic will "
        "exchange the incoming token for a downstream access token.",
    )
    token_exchange_audience: str | None = Field(
        default=None,
        description="Target audience for the exchanged token (the downstream API).",
    )
    token_exchange_scope: str | None = Field(
        default=None,
        description="Scopes to request on the exchanged token.",
    )
    token_exchange_provider: str | None = Field(
        default=None,
        pattern=r"^[a-zA-Z0-9\-]{1,64}$",
        description="Provider adapter identifier for token exchange. "
        "Built-in: 'rfc8693' (default), 'google', 'entra'.",
    )
    circuit_breaker: CircuitBreakerConfig | None = Field(
        default=None,
        description="Circuit breaker settings for IDP HTTP calls.",
    )
    jwks_cache_ttl: int = Field(
        default=600,
        ge=60,
        le=86400,
        description="JWKS cache TTL in seconds before stale-while-revalidate kicks in.",
    )


class ObservabilityConfig(BaseModel):
    """Observability configuration for metrics, tracing, and logging."""

    enabled: bool = True
    metrics_path: str = "/metrics"
    metrics_port: int = Field(default=9090, ge=1, le=65535)
    exporter: Literal["otlp", "console", "none"] = "otlp"
    otlp_endpoint: str = "http://localhost:4317"
    log_format: Literal["json", "text"] = "json"
    log_level: Literal["debug", "info", "warning", "error"] = "info"


class SessionsConfig(BaseModel):
    """Session management configuration."""

    enabled: bool = True
    ttl: int = Field(default=3600, ge=60, le=86400)
    backend: Literal["memory"] = "memory"


class PluginRef(BaseModel):
    """Reference to a plugin module with optional configuration."""

    module: str
    config: dict[str, Any] = {}


class HotReloadConfig(BaseModel):
    """Hot-reload configuration for dynamic config updates."""

    enabled: bool = False
    watch_interval: int = Field(default=5, ge=1, le=60)
    reloadable_sections: list[str] = ["observability"]


class CeramicConfig(BaseModel):
    """Top-level Ceramic configuration model.

    Rejects unknown top-level keys via extra='forbid'.
    """

    model_config = ConfigDict(extra="forbid")

    auth: AuthConfig | None = None
    observability: ObservabilityConfig | None = None
    sessions: SessionsConfig | None = None
    plugins: list[PluginRef] | None = None
    hot_reload: HotReloadConfig | None = None
