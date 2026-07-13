"""Pydantic configuration models for the Ceramic framework.

These models define and validate the structure of ceramic.yaml configuration.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class AuthConfig(BaseModel):
    """Authentication configuration for OIDC providers."""

    provider: Literal["oidc"] = "oidc"
    issuer: HttpUrl
    client_id: str
    client_secret: str | None = None
    scopes: list[str] = ["openid", "profile", "email"]
    callback_timeout: int = Field(default=120, ge=1, le=600)
    token_exchange_timeout: int = Field(default=30, ge=1, le=120)


class AuthorizationPolicy(BaseModel):
    """A single authorization policy matching tools to role/group requirements."""

    tool: str  # Glob pattern matching tool names
    require_role: str | None = None
    require_group: str | None = None


class AuthorizationConfig(BaseModel):
    """Authorization configuration with claim paths and policies."""

    role_claim: str = "realm_access.roles"
    group_claim: str = "groups"
    policies: list[AuthorizationPolicy] = []


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
    reloadable_sections: list[str] = ["observability", "authorization"]


class CeramicConfig(BaseModel):
    """Top-level Ceramic configuration model.

    Rejects unknown top-level keys via extra='forbid'.
    """

    model_config = ConfigDict(extra="forbid")

    auth: AuthConfig | None = None
    authorization: AuthorizationConfig | None = None
    observability: ObservabilityConfig | None = None
    sessions: SessionsConfig | None = None
    plugins: list[PluginRef] | None = None
    hot_reload: HotReloadConfig | None = None
