"""Keycloak integration scenarios (require Docker).

Marked abstract by default — enabled via ./lab.sh --docker
"""

from fastauthmcp.lab.scenario import Scenario
from fastauthmcp.lab.providers.keycloak import KeycloakProvider
from fastauthmcp.lab.gateway import LabGateway


class TestKeycloakClientCredentials(Scenario):
    """Keycloak → client_credentials → identity propagated."""

    name = "keycloak_client_credentials"
    category = "authentication"
    description = "Keycloak client credentials → identity"
    provider_name = "keycloak"
    __abstract__ = True  # Only run when explicitly enabled via --docker

    async def setup(self) -> None:
        import httpx

        try:
            resp = httpx.get("http://localhost:8080/health/ready", timeout=2)
            if resp.status_code != 200:
                raise RuntimeError("Keycloak not healthy")
        except Exception:
            raise RuntimeError("Keycloak not running (use: ./lab.sh --docker)")

    async def run(self) -> None:
        provider = KeycloakProvider()
        gateway = LabGateway()

        token_result = provider.issue_token()
        session = await gateway.authenticate(
            token_result.access_token,
            subject="service-account-lab-test-client",
            email=None,
            roles=["service"],
        )
        result = await session.call_tool("whoami")
        assert result["subject"] is not None

        self.trace.identity = {"sub": result["subject"]}
        self.trace.result = "authenticated via Keycloak"
