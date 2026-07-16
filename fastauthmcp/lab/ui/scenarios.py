"""Scenario definitions for the Lab UI.

Each scenario provides:
- A mock identity (injected into FastAuthMCP)
- Available MCP tools
- The provider simulation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScenarioConfig:
    """Configuration for a UI scenario."""

    id: str
    label: str
    provider: str
    identity: dict[str, Any]
    tools: list[str] = field(default_factory=list)
    description: str = ""


SCENARIOS: list[ScenarioConfig] = [
    ScenarioConfig(
        id="zitadel_pkce",
        label="ZITADEL — Auth Code + PKCE",
        provider="zitadel",
        identity={
            "sub": "zitadel-user-001",
            "email": "user@zitadel-org.com",
            "roles": ["viewer", "editor"],
            "groups": ["engineering"],
        },
        tools=["whoami", "list_pets", "get_pet", "add_pet", "admin_action"],
        description="Interactive login via Zitadel with PKCE. User has viewer+editor roles.",
    ),
    ScenarioConfig(
        id="keycloak_m2m",
        label="Keycloak — Client Credentials (M2M)",
        provider="keycloak",
        identity={
            "sub": "service-account-mcp",
            "email": "svc@keycloak-org.com",
            "roles": ["service"],
            "groups": [],
        },
        tools=["whoami", "list_pets", "get_pet"],
        description="Machine-to-machine auth via Keycloak. Service account with limited access.",
    ),
    ScenarioConfig(
        id="auth0_admin",
        label="Auth0 — Admin User",
        provider="auth0",
        identity={
            "sub": "auth0|admin-001",
            "email": "admin@auth0-org.com",
            "roles": ["admin", "editor", "viewer"],
            "groups": ["platform-team"],
        },
        tools=["whoami", "list_pets", "get_pet", "add_pet", "admin_action"],
        description="Admin user via Auth0. Has full access including admin_action.",
    ),
    ScenarioConfig(
        id="azure_viewer",
        label="Azure Entra ID — Viewer",
        provider="azure",
        identity={
            "sub": "azure-oid-viewer",
            "email": "viewer@corporate.com",
            "roles": ["Reader"],
            "groups": ["all-employees"],
        },
        tools=["whoami", "list_pets", "get_pet"],
        description="Corporate viewer via Azure Entra ID. Read-only access.",
    ),
    ScenarioConfig(
        id="okta_groups",
        label="Okta — Group-Based Access",
        provider="okta",
        identity={
            "sub": "okta-user-00u789",
            "email": "devops@okta-org.com",
            "roles": ["user", "deployer"],
            "groups": ["mcp-admins", "ops-team"],
        },
        tools=["whoami", "list_pets", "get_pet", "add_pet", "admin_action"],
        description="DevOps user via Okta with group-based access control.",
    ),
    ScenarioConfig(
        id="expired_token",
        label="Security — Expired Token",
        provider="mock",
        identity={
            "sub": "expired-user",
            "email": "expired@test.com",
            "roles": [],
            "groups": [],
        },
        tools=["whoami"],
        description="Simulates an expired token scenario. Tool calls should show auth errors.",
    ),
    ScenarioConfig(
        id="unauthorized",
        label="Security — Unauthorized (No Admin)",
        provider="mock",
        identity={
            "sub": "basic-user",
            "email": "basic@test.com",
            "roles": ["viewer"],
            "groups": [],
        },
        tools=["whoami", "list_pets", "get_pet", "admin_action"],
        description="User without admin role tries to access admin_action. Should be rejected.",
    ),
]
