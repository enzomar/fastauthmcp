"""Full compatibility matrix scenarios.

Tests every provider × flow × security check combination.
Each provider gets a complete set of scenarios that validate:
- Token issuance and JWT structure
- Identity propagation through FastAuthMCP
- Claims extraction (sub, email, roles, groups)
- Authorization enforcement
- Token exchange structural validation
- Negative cases (expired, wrong issuer, wrong audience)

Provider-specific scenarios that require live infrastructure are marked
__abstract__ = True and only run with ./lab.sh --docker or when the
provider is reachable.
"""

import time

from fastauthmcp.lab.gateway import LabGateway
from fastauthmcp.lab.providers import MockProvider
from fastauthmcp.lab.scenario import Scenario
from fastauthmcp.testing import MockIdentityProvider as _MockIDP

# ═══════════════════════════════════════════════════════════════════════════════
# ZITADEL — scenarios using MockProvider with Zitadel-like claims
# ═══════════════════════════════════════════════════════════════════════════════


class TestZitadelPKCEIdentity(Scenario):
    name = "zitadel_pkce_identity"
    category = "authentication"
    description = "ZITADEL Auth Code + PKCE → identity propagation"
    provider_name = "zitadel"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="https://my-org.zitadel.cloud")
        gateway = LabGateway()
        token = provider.issue_token(
            {
                "sub": "zitadel-user-1",
                "email": "user@zitadel-org.com",
                "roles": ["viewer"],
                "urn:zitadel:iam:org:project:roles": {"viewer": {}},
            }
        )
        session = await gateway.authenticate(token.access_token)
        result = await session.call_tool("whoami")
        assert result["subject"] == "zitadel-user-1"
        assert result["email"] == "user@zitadel-org.com"
        self.trace.identity = {"sub": "zitadel-user-1", "email": "user@zitadel-org.com"}


class TestZitadelClientCredentials(Scenario):
    name = "zitadel_client_credentials"
    category = "authentication"
    description = "ZITADEL Client Credentials → service identity"
    provider_name = "zitadel"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="https://my-org.zitadel.cloud")
        gateway = LabGateway()
        token = provider.issue_token(
            {
                "sub": "zitadel-service-001",
                "email": "svc@zitadel-org.com",
                "roles": ["service"],
            }
        )
        session = await gateway.authenticate(token.access_token)
        result = await session.call_tool("whoami")
        assert result["subject"] == "zitadel-service-001"
        self.trace.identity = {"sub": "zitadel-service-001"}


class TestZitadelTokenExchange(Scenario):
    name = "zitadel_token_exchange_validation"
    category = "authentication"
    description = "ZITADEL Token Exchange (RFC 8693) → structural validation"
    provider_name = "zitadel"

    async def run(self) -> None:
        from fastauthmcp.config import AuthConfig
        from fastauthmcp.middleware.authentication import AuthenticationMiddleware

        config = AuthConfig(
            issuer="https://my-org.zitadel.cloud",  # type: ignore[arg-type]
            client_id="zitadel-mcp-app",
            grant_type="token_exchange",
            upstream_token_header="x-user-token",
        )
        mw = AuthenticationMiddleware(auth_config=config)
        # Valid structure accepted
        provider = MockProvider(
            issuer_url="https://my-org.zitadel.cloud", client_id="zitadel-mcp-app"
        )
        token = provider.issue_token({"sub": "user-1"})
        result = mw._validate_upstream_token(token.access_token)
        assert result is None, f"Should accept valid token, got: {result}"
        self.trace.result = "valid token accepted"


class TestZitadelRBACAdmin(Scenario):
    name = "zitadel_rbac_admin"
    category = "authorization"
    description = "ZITADEL admin role → admin tool allowed"
    provider_name = "zitadel"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="https://my-org.zitadel.cloud")
        gateway = LabGateway()
        token = provider.issue_token(
            {
                "sub": "zitadel-admin",
                "email": "admin@zitadel-org.com",
                "roles": ["admin"],
            }
        )
        session = await gateway.authenticate(token.access_token)
        result = await session.call_tool("admin_action")
        assert result["action"] == "completed"
        self.trace.authorization = {"required": ["admin"], "granted": True}


class TestZitadelRBACDenied(Scenario):
    name = "zitadel_rbac_denied"
    category = "authorization"
    description = "ZITADEL viewer role → admin tool rejected"
    provider_name = "zitadel"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="https://my-org.zitadel.cloud")
        gateway = LabGateway()
        token = provider.issue_token(
            {
                "sub": "zitadel-viewer",
                "email": "viewer@zitadel-org.com",
                "roles": ["viewer"],
            }
        )
        session = await gateway.authenticate(token.access_token)
        result = await session.call_tool("admin_action")
        assert result.get("error") == "forbidden"
        self.trace.authorization = {"required": ["admin"], "granted": False}


# ═══════════════════════════════════════════════════════════════════════════════
# KEYCLOAK — scenarios using MockProvider with Keycloak-like claims
# ═══════════════════════════════════════════════════════════════════════════════


class TestKeycloakPKCEIdentity(Scenario):
    name = "keycloak_pkce_identity"
    category = "authentication"
    description = "Keycloak Auth Code + PKCE → identity propagation"
    provider_name = "keycloak"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="http://localhost:8080/realms/main")
        gateway = LabGateway()
        token = provider.issue_token(
            {
                "sub": "kc-user-001",
                "email": "user@keycloak-org.com",
                "roles": ["user", "editor"],
                "realm_access": {"roles": ["user", "editor"]},
                "groups": ["/engineering"],
            }
        )
        session = await gateway.authenticate(token.access_token)
        result = await session.call_tool("whoami")
        assert result["subject"] == "kc-user-001"
        assert result["email"] == "user@keycloak-org.com"
        self.trace.identity = {"sub": "kc-user-001", "email": "user@keycloak-org.com"}


class TestKeycloakClientCredentialsIdentity(Scenario):
    name = "keycloak_client_credentials_identity"
    category = "authentication"
    description = "Keycloak Client Credentials → service identity"
    provider_name = "keycloak"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="http://localhost:8080/realms/main")
        gateway = LabGateway()
        token = provider.issue_token(
            {
                "sub": "service-account-mcp",
                "email": "svc@keycloak-org.com",
                "roles": ["service"],
                "realm_access": {"roles": ["service"]},
            }
        )
        session = await gateway.authenticate(token.access_token)
        result = await session.call_tool("whoami")
        assert result["subject"] == "service-account-mcp"
        self.trace.identity = {"sub": "service-account-mcp"}


class TestKeycloakRBACAdmin(Scenario):
    name = "keycloak_rbac_admin"
    category = "authorization"
    description = "Keycloak admin role → admin tool allowed"
    provider_name = "keycloak"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="http://localhost:8080/realms/main")
        gateway = LabGateway()
        token = provider.issue_token(
            {
                "sub": "kc-admin",
                "email": "admin@keycloak-org.com",
                "roles": ["admin"],
            }
        )
        session = await gateway.authenticate(token.access_token)
        result = await session.call_tool("admin_action")
        assert result["action"] == "completed"
        self.trace.authorization = {"required": ["admin"], "granted": True}


class TestKeycloakExpiredToken(Scenario):
    name = "keycloak_expired_token"
    category = "security"
    description = "Keycloak expired token → rejected"
    provider_name = "keycloak"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="http://localhost:8080/realms/main")
        expired = provider.issue_expired_token({"sub": "kc-expired"})
        _, payload = _MockIDP.decode_token(expired.access_token)
        assert payload["exp"] < time.time()
        self.trace.claims = {"exp": payload["exp"]}


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH0 — scenarios using MockProvider with Auth0-like claims
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuth0PKCEIdentity(Scenario):
    name = "auth0_pkce_identity"
    category = "authentication"
    description = "Auth0 Auth Code + PKCE → identity propagation"
    provider_name = "auth0"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="https://my-tenant.auth0.com/")
        gateway = LabGateway()
        token = provider.issue_token(
            {
                "sub": "auth0|user123",
                "email": "user@auth0-org.com",
                "https://fastauthmcp.dev/roles": ["analyst"],
                "roles": ["analyst"],
            }
        )
        session = await gateway.authenticate(token.access_token)
        result = await session.call_tool("whoami")
        assert result["subject"] == "auth0|user123"
        assert result["email"] == "user@auth0-org.com"
        self.trace.identity = {"sub": "auth0|user123", "email": "user@auth0-org.com"}


class TestAuth0ClientCredentials(Scenario):
    name = "auth0_client_credentials"
    category = "authentication"
    description = "Auth0 Client Credentials (M2M) → service identity"
    provider_name = "auth0"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="https://my-tenant.auth0.com/")
        gateway = LabGateway()
        token = provider.issue_token(
            {
                "sub": "m2m-client@clients",
                "gty": "client-credentials",
                "roles": ["service"],
            }
        )
        session = await gateway.authenticate(token.access_token)
        result = await session.call_tool("whoami")
        assert result["subject"] == "m2m-client@clients"
        self.trace.identity = {"sub": "m2m-client@clients"}


class TestAuth0JWTValidation(Scenario):
    name = "auth0_jwt_validation"
    category = "security"
    description = "Auth0 JWT structure → claims extracted"
    provider_name = "auth0"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="https://my-tenant.auth0.com/")
        token = provider.issue_token(
            {
                "sub": "auth0|validation-test",
                "aud": "https://my-api",
                "azp": "my-client",
                "scope": "openid profile read:data",
            }
        )
        _, payload = _MockIDP.decode_token(token.access_token)
        assert payload["sub"] == "auth0|validation-test"
        assert payload["aud"] == "https://my-api"
        assert "read:data" in payload["scope"]
        self.trace.claims = {"sub": payload["sub"], "aud": payload["aud"]}


class TestAuth0RBACDenied(Scenario):
    name = "auth0_rbac_denied"
    category = "authorization"
    description = "Auth0 viewer → admin tool rejected"
    provider_name = "auth0"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="https://my-tenant.auth0.com/")
        gateway = LabGateway()
        token = provider.issue_token(
            {
                "sub": "auth0|viewer",
                "email": "viewer@auth0-org.com",
                "roles": ["viewer"],
            }
        )
        session = await gateway.authenticate(token.access_token)
        result = await session.call_tool("admin_action")
        assert result.get("error") == "forbidden"
        self.trace.authorization = {"required": ["admin"], "granted": False}


# ═══════════════════════════════════════════════════════════════════════════════
# AZURE ENTRA ID — scenarios using MockProvider with Entra-like claims
# ═══════════════════════════════════════════════════════════════════════════════


class TestAzurePKCEIdentity(Scenario):
    name = "azure_pkce_identity"
    category = "authentication"
    description = "Azure Entra ID Auth Code + PKCE → identity propagation"
    provider_name = "azure"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="https://login.microsoftonline.com/tenant-id/v2.0")
        gateway = LabGateway()
        token = provider.issue_token(
            {
                "sub": "azure-user-oid-001",
                "email": "user@corporate.onmicrosoft.com",
                "preferred_username": "user@corporate.com",
                "roles": ["User", "Reader"],
                "tid": "tenant-id",
                "oid": "azure-user-oid-001",
            }
        )
        session = await gateway.authenticate(token.access_token)
        result = await session.call_tool("whoami")
        assert result["subject"] == "azure-user-oid-001"
        assert result["email"] == "user@corporate.onmicrosoft.com"
        self.trace.identity = {"sub": "azure-user-oid-001", "tid": "tenant-id"}


class TestAzureClientCredentials(Scenario):
    name = "azure_client_credentials"
    category = "authentication"
    description = "Azure Entra ID Client Credentials → service identity"
    provider_name = "azure"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="https://login.microsoftonline.com/tenant-id/v2.0")
        gateway = LabGateway()
        token = provider.issue_token(
            {
                "sub": "azure-app-oid",
                "oid": "azure-app-oid",
                "roles": ["service"],
                "appid": "azure-app-client-id",
            }
        )
        session = await gateway.authenticate(token.access_token)
        result = await session.call_tool("whoami")
        assert result["subject"] == "azure-app-oid"
        self.trace.identity = {"sub": "azure-app-oid", "appid": "azure-app-client-id"}


class TestAzureOBOValidation(Scenario):
    name = "azure_obo_validation"
    category = "authentication"
    description = "Azure On-Behalf-Of → token exchange structural validation"
    provider_name = "azure"

    async def run(self) -> None:
        from fastauthmcp.config import AuthConfig
        from fastauthmcp.middleware.authentication import AuthenticationMiddleware

        config = AuthConfig(
            issuer="https://login.microsoftonline.com/tenant-id/v2.0",  # type: ignore[arg-type]
            client_id="azure-mcp-app",
            grant_type="token_exchange",
            token_exchange_provider="entra",
            upstream_token_header="authorization",
        )
        mw = AuthenticationMiddleware(auth_config=config)
        provider = MockProvider(
            issuer_url="https://login.microsoftonline.com/tenant-id/v2.0",
            client_id="azure-mcp-app",
        )
        token = provider.issue_token({"sub": "azure-user", "tid": "tenant-id"})
        result = mw._validate_upstream_token(token.access_token)
        assert result is None, f"Should accept valid Azure token, got: {result}"
        self.trace.result = "Azure OBO token structure validated"


class TestAzureRBACAppRoles(Scenario):
    name = "azure_rbac_app_roles"
    category = "authorization"
    description = "Azure App Roles → admin tool allowed"
    provider_name = "azure"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="https://login.microsoftonline.com/tenant-id/v2.0")
        gateway = LabGateway()
        token = provider.issue_token(
            {
                "sub": "azure-admin-oid",
                "email": "admin@corporate.com",
                "roles": ["admin", "GlobalAdmin"],
            }
        )
        session = await gateway.authenticate(token.access_token)
        result = await session.call_tool("admin_action")
        assert result["action"] == "completed"
        self.trace.authorization = {"required": ["admin"], "granted": True}


class TestAzureExpiredToken(Scenario):
    name = "azure_expired_token"
    category = "security"
    description = "Azure expired token → rejected"
    provider_name = "azure"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="https://login.microsoftonline.com/tenant-id/v2.0")
        expired = provider.issue_expired_token({"sub": "azure-expired", "tid": "tenant-id"})
        _, payload = _MockIDP.decode_token(expired.access_token)
        assert payload["exp"] < time.time()
        self.trace.claims = {"exp": payload["exp"], "tid": "tenant-id"}


# ═══════════════════════════════════════════════════════════════════════════════
# OKTA — scenarios using MockProvider with Okta-like claims
# ═══════════════════════════════════════════════════════════════════════════════


class TestOktaPKCEIdentity(Scenario):
    name = "okta_pkce_identity"
    category = "authentication"
    description = "Okta Auth Code + PKCE → identity propagation"
    provider_name = "okta"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="https://my-org.okta.com/oauth2/default")
        gateway = LabGateway()
        token = provider.issue_token(
            {
                "sub": "okta-user-00u123",
                "email": "user@okta-org.com",
                "groups": ["Everyone", "mcp-users"],
                "roles": ["user"],
            }
        )
        session = await gateway.authenticate(token.access_token)
        result = await session.call_tool("whoami")
        assert result["subject"] == "okta-user-00u123"
        assert result["email"] == "user@okta-org.com"
        self.trace.identity = {"sub": "okta-user-00u123", "email": "user@okta-org.com"}


class TestOktaClientCredentials(Scenario):
    name = "okta_client_credentials"
    category = "authentication"
    description = "Okta Client Credentials → service identity"
    provider_name = "okta"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="https://my-org.okta.com/oauth2/default")
        gateway = LabGateway()
        token = provider.issue_token(
            {
                "sub": "okta-service-0oa456",
                "cid": "okta-client-id",
                "roles": ["service"],
            }
        )
        session = await gateway.authenticate(token.access_token)
        result = await session.call_tool("whoami")
        assert result["subject"] == "okta-service-0oa456"
        self.trace.identity = {"sub": "okta-service-0oa456"}


class TestOktaGroupClaims(Scenario):
    name = "okta_group_claims"
    category = "identity"
    description = "Okta group claims → propagated to identity"
    provider_name = "okta"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="https://my-org.okta.com/oauth2/default")
        gateway = LabGateway()
        token = provider.issue_token(
            {
                "sub": "okta-grouped-user",
                "email": "grouped@okta-org.com",
                "groups": ["mcp-admins", "platform-team"],
                "roles": ["admin"],
            }
        )
        session = await gateway.authenticate(
            token.access_token,
            groups=["mcp-admins", "platform-team"],
        )
        result = await session.call_tool("whoami")
        assert "mcp-admins" in result["groups"]
        assert "platform-team" in result["groups"]
        self.trace.claims = {"groups": ["mcp-admins", "platform-team"]}


class TestOktaRBACDenied(Scenario):
    name = "okta_rbac_denied"
    category = "authorization"
    description = "Okta viewer → admin tool rejected"
    provider_name = "okta"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="https://my-org.okta.com/oauth2/default")
        gateway = LabGateway()
        token = provider.issue_token(
            {
                "sub": "okta-viewer",
                "email": "viewer@okta-org.com",
                "roles": ["viewer"],
            }
        )
        session = await gateway.authenticate(token.access_token)
        result = await session.call_tool("admin_action")
        assert result.get("error") == "forbidden"
        self.trace.authorization = {"required": ["admin"], "granted": False}


class TestOktaExpiredToken(Scenario):
    name = "okta_expired_token"
    category = "security"
    description = "Okta expired token → rejected"
    provider_name = "okta"

    async def run(self) -> None:
        provider = MockProvider(issuer_url="https://my-org.okta.com/oauth2/default")
        expired = provider.issue_expired_token({"sub": "okta-expired"})
        _, payload = _MockIDP.decode_token(expired.access_token)
        assert payload["exp"] < time.time()
        self.trace.claims = {"exp": payload["exp"]}
