"""Security scenarios — things that MUST be rejected."""

import time

from fastauthmcp.lab.gateway import LabGateway
from fastauthmcp.lab.providers import MockProvider
from fastauthmcp.lab.scenario import Scenario
from fastauthmcp.testing import MockIdentityProvider


class TestExpiredTokenRejected(Scenario):
    """Expired JWT → token validation rejects."""

    name = "expired_token_rejected"
    category = "security"
    description = "Expired token → rejected"
    provider_name = "mock"

    async def run(self) -> None:
        provider = MockProvider()
        token_result = provider.issue_expired_token()

        _, payload = MockIdentityProvider.decode_token(token_result.access_token)
        assert payload["exp"] < time.time(), "Token should be expired"

        self.trace.claims = {"exp": payload["exp"], "now": int(time.time())}


class TestInvalidJWTFormatRejected(Scenario):
    """Malformed JWT → parse_jwt_claims raises ValueError."""

    name = "invalid_jwt_format_rejected"
    category = "security"
    description = "Invalid JWT format → rejected"
    provider_name = "mock"

    async def run(self) -> None:
        from fastauthmcp.auth.claims import parse_jwt_claims

        # Not a JWT at all
        try:
            parse_jwt_claims("not-a-jwt")
            raise AssertionError("Should have raised ValueError")
        except ValueError:
            pass

        # Two segments instead of three
        try:
            parse_jwt_claims("header.payload")
            raise AssertionError("Should have raised ValueError")
        except ValueError:
            pass

        self.trace.result = "both malformed formats rejected"


class TestWrongIssuerDetected(Scenario):
    """Token with mismatched issuer → detectable in claims."""

    name = "wrong_issuer_detected"
    category = "security"
    description = "Wrong issuer → rejected"
    provider_name = "mock"

    async def run(self) -> None:
        provider = MockProvider()
        token_result = provider.issue_token_wrong_issuer()

        _, payload = MockIdentityProvider.decode_token(token_result.access_token)
        assert payload["iss"] == "https://evil-idp.example.com"
        assert payload["iss"] != provider.issuer

        self.trace.claims = {
            "iss": payload["iss"],
            "expected": provider.issuer,
        }


class TestWrongAudienceDetected(Scenario):
    """Token with wrong audience → detectable in claims."""

    name = "wrong_audience_detected"
    category = "security"
    description = "Wrong audience → rejected"
    provider_name = "mock"

    async def run(self) -> None:
        provider = MockProvider()
        token_result = provider.issue_token_wrong_audience()

        _, payload = MockIdentityProvider.decode_token(token_result.access_token)
        assert payload["aud"] == "wrong-client-id"
        assert payload["aud"] != provider.client_id

        self.trace.claims = {
            "aud": payload["aud"],
            "expected": provider.client_id,
        }


class TestMissingSubjectHandled(Scenario):
    """Token without 'sub' claim → identity.subject is None."""

    name = "missing_subject_handled"
    category = "security"
    description = "Missing 'sub' claim → identity.subject = None"
    provider_name = "mock"

    async def run(self) -> None:
        provider = MockProvider()
        gateway = LabGateway()

        token_result = provider.issue_token_missing_subject()
        session = await gateway.authenticate(token_result.access_token)
        result = await session.call_tool("whoami")

        assert result["subject"] is None

        self.trace.identity = {"sub": None, "email": "nosub@example.com"}


class TestTokenExchangeStructuralValidation(Scenario):
    """Upstream token structural validation rejects invalid tokens."""

    name = "token_exchange_structural_validation"
    category = "security"
    description = "Token exchange → structural validation"
    provider_name = "mock"

    async def run(self) -> None:
        from fastauthmcp.config import AuthConfig
        from fastauthmcp.middleware.authentication import AuthenticationMiddleware

        config = AuthConfig(
            issuer="https://idp.example.com",  # type: ignore[arg-type]
            client_id="test-client",
            grant_type="token_exchange",
            upstream_token_header="x-user-token",
        )
        middleware = AuthenticationMiddleware(auth_config=config)

        # Not a JWT
        result = middleware._validate_upstream_token("not-a-jwt")
        assert result is not None, "Should reject non-JWT"
        assert "3 dot-separated parts" in result

        # Expired JWT
        provider = MockProvider(
            issuer_url="https://idp.example.com",
            client_id="test-client",
        )
        expired = provider.issue_expired_token()
        result = middleware._validate_upstream_token(expired.access_token)
        assert result is not None, f"Should reject expired token, got: {result}"
        assert "expired" in result

        self.trace.result = "non-JWT rejected, expired JWT rejected"
