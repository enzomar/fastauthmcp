"""Mock identity provider for local testing without Docker.

Uses the existing MockIdentityProvider from fastauthmcp.testing to generate
structurally valid JWTs.
"""

from __future__ import annotations

import time
from typing import Any

from fastauthmcp.lab.providers.base import IdentityProvider, TokenResult
from fastauthmcp.testing import MockIdentityProvider as _MockIDP


class MockProvider(IdentityProvider):
    """In-process mock OIDC provider.

    Generates HS256-signed JWTs without network calls.
    Useful for testing token validation logic, negative scenarios,
    and running the lab without Docker.
    """

    name = "mock"

    def __init__(
        self,
        issuer_url: str = "https://mock-idp.local",
        client_id: str = "lab-test-client",
    ) -> None:
        self._issuer_url = issuer_url
        self._client_id = client_id
        self._idp = _MockIDP()

    def discovery_url(self) -> str:
        return f"{self._issuer_url}/.well-known/openid-configuration"

    @property
    def issuer(self) -> str:
        return self._issuer_url

    @property
    def client_id(self) -> str:
        return self._client_id

    def issue_token(self, claims: dict[str, Any] | None = None) -> TokenResult:
        base_claims = {
            "iss": self._issuer_url,
            "aud": self._client_id,
            "sub": "lab-user-001",
            "email": "labuser@example.com",
            "roles": ["user"],
            "groups": ["lab-testers"],
        }
        if claims:
            base_claims.update(claims)

        token = self._idp.issue_token(base_claims)
        return TokenResult(
            access_token=token,
            claims=base_claims,
            expires_in=3600,
        )

    def issue_expired_token(self, claims: dict[str, Any] | None = None) -> TokenResult:
        expired_claims = {
            "iss": self._issuer_url,
            "aud": self._client_id,
            "sub": "expired-user",
        }
        if claims:
            expired_claims.update(claims)

        # MockIdentityProvider.issue_token adds exp=now+3600 by default.
        # We need to generate the token manually with an expired exp.
        import base64
        import hashlib
        import hmac
        import json as _json

        now = int(time.time())
        payload = {**expired_claims, "iat": now - 7200, "exp": now - 3600}

        header = {"alg": "HS256", "typ": "JWT"}
        secret = self._idp.DEFAULT_SECRET

        def _b64(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

        h = _b64(_json.dumps(header, separators=(",", ":")).encode())
        p = _b64(_json.dumps(payload, separators=(",", ":")).encode())
        sig = hmac.HMAC(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()

        token = f"{h}.{p}.{_b64(sig)}"
        return TokenResult(
            access_token=token,
            claims=payload,
            expires_in=-3600,
        )

    def issue_token_wrong_issuer(self) -> TokenResult:
        """Issue a token with a mismatched issuer."""
        return self.issue_token({"iss": "https://evil-idp.example.com"})

    def issue_token_wrong_audience(self) -> TokenResult:
        """Issue a token with a mismatched audience."""
        return self.issue_token({"aud": "wrong-client-id"})

    def issue_token_missing_subject(self) -> TokenResult:
        """Issue a token without a 'sub' claim."""
        claims = {
            "iss": self._issuer_url,
            "aud": self._client_id,
            "email": "nosub@example.com",
        }
        # Remove sub explicitly
        token = self._idp.issue_token(claims)
        return TokenResult(access_token=token, claims=claims)
