"""Authentication and identity propagation scenarios (mock provider)."""

from fastauthmcp.lab.scenario import Scenario
from fastauthmcp.lab.providers import MockProvider
from fastauthmcp.lab.gateway import LabGateway


class TestClientCredentialsFlow(Scenario):
    """Client credentials grant → identity set on service account."""

    name = "client_credentials_flow"
    category = "authentication"
    description = "Client Credentials → service identity"
    provider_name = "mock"

    async def run(self) -> None:
        provider = MockProvider()
        gateway = LabGateway()

        token_result = provider.issue_token(
            {"sub": "service-account", "email": "svc@lab.test", "roles": ["service"]}
        )

        session = await gateway.authenticate(token_result.access_token)
        result = await session.call_tool("whoami")

        assert result["subject"] == "service-account"
        assert result["email"] == "svc@lab.test"

        self.trace.identity = {"sub": result["subject"], "email": result["email"]}
        self.trace.result = "authenticated"


class TestJWTValidationAndIdentity(Scenario):
    """JWT issued → claims extracted → identity propagated to MCP tool."""

    name = "jwt_validation_identity_propagation"
    category = "authentication"
    description = "JWT validation → identity propagation to MCP tool"
    provider_name = "mock"

    async def run(self) -> None:
        provider = MockProvider()
        gateway = LabGateway()

        token_result = provider.issue_token(
            {"sub": "user-42", "email": "alice@lab.test", "roles": ["admin", "viewer"]}
        )

        session = await gateway.authenticate(token_result.access_token)
        result = await session.call_tool("whoami")

        assert result["subject"] == "user-42"
        assert result["email"] == "alice@lab.test"
        assert "admin" in result["roles"]
        assert "viewer" in result["roles"]

        self.trace.identity = {"sub": "user-42", "email": "alice@lab.test"}
        self.trace.claims = {"roles": ["admin", "viewer"]}


class TestIdentityForwardingToBackend(Scenario):
    """JWT claims forwarded through FastAuthMCP to downstream tool code."""

    name = "identity_forwarding_jwt_to_tool"
    category = "identity"
    description = "MCP → tool code: identity() returns JWT claims"
    provider_name = "mock"

    async def run(self) -> None:
        provider = MockProvider()
        gateway = LabGateway()

        custom_claims = {
            "sub": "user-99",
            "email": "custom@lab.test",
            "org_id": "org-123",
            "tier": "enterprise",
            "roles": ["user"],
        }
        token_result = provider.issue_token(custom_claims)

        session = await gateway.authenticate(token_result.access_token)
        result = await session.call_tool("get_profile")

        assert result["user"] == "custom@lab.test"

        self.trace.identity = {"sub": "user-99", "email": "custom@lab.test"}
        self.trace.claims = {"org_id": "org-123", "tier": "enterprise"}


class TestAdminRoleGrantsAccess(Scenario):
    """Admin role present → admin_action tool succeeds."""

    name = "admin_role_grants_access"
    category = "authorization"
    description = "Admin role → admin_action tool allowed"
    provider_name = "mock"

    async def run(self) -> None:
        provider = MockProvider()
        gateway = LabGateway()

        token_result = provider.issue_token(
            {"sub": "admin-1", "email": "admin@lab.test", "roles": ["admin"]}
        )

        session = await gateway.authenticate(token_result.access_token)
        result = await session.call_tool("admin_action")

        assert result["action"] == "completed"
        assert result["by"] == "admin@lab.test"

        self.trace.identity = {"sub": "admin-1", "email": "admin@lab.test"}
        self.trace.authorization = {"required": ["admin"], "granted": True}


class TestNonAdminRejected(Scenario):
    """Non-admin role → admin_action tool returns forbidden."""

    name = "non_admin_role_rejected"
    category = "authorization"
    description = "Viewer role → admin_action tool rejected"
    provider_name = "mock"

    async def run(self) -> None:
        provider = MockProvider()
        gateway = LabGateway()

        token_result = provider.issue_token(
            {"sub": "user-1", "email": "user@lab.test", "roles": ["viewer"]}
        )

        session = await gateway.authenticate(token_result.access_token)
        result = await session.call_tool("admin_action")

        assert result.get("error") == "forbidden", f"Got: {result}"

        self.trace.identity = {"sub": "user-1", "email": "user@lab.test"}
        self.trace.authorization = {"required": ["admin"], "granted": False}
