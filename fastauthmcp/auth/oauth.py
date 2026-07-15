"""OAuth2/OIDC service with PKCE support for the FastAuthMCP framework.

Uses httpx for async HTTP and pyjwt for token decoding.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from fastauthmcp.auth.callback_server import CallbackServer
from fastauthmcp.config import AuthConfig
from fastauthmcp.exceptions import AuthenticationError, ProviderError
from fastauthmcp.models import OIDCEndpoints, TokenSet
from fastauthmcp.resilience import ResilientHttpClient
from fastauthmcp.security import TLSEnforcer

logger = logging.getLogger(__name__)


@dataclass
class AuthResult:
    """Result of initiating an OAuth2 flow, containing the code and verifier."""

    code: str
    verifier: str
    redirect_uri: str


class OAuthService:
    """Handles OAuth2/OIDC flows with PKCE.

    Uses httpx for all HTTP calls (async-native, proper timeouts).
    When a ResilientHttpClient is provided, all outbound HTTP routes through
    the circuit breaker for resilience. Otherwise falls back to raw httpx.

    When an ssl_context is provided (for mTLS), it is used for all direct
    httpx calls that bypass the ResilientHttpClient.
    """

    def __init__(
        self,
        provider_config: AuthConfig | None = None,
        http_client: ResilientHttpClient | None = None,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self._provider_config = provider_config
        self._http_client = http_client
        self._ssl_context = ssl_context
        self._tls_enforcer = TLSEnforcer()
        self._endpoints: OIDCEndpoints | None = None

    @property
    def _verify(self) -> ssl.SSLContext | bool:
        """TLS verification parameter for direct httpx calls."""
        return self._ssl_context if self._ssl_context is not None else True

    async def discover_endpoints(self, issuer_url: str) -> OIDCEndpoints:
        """Fetch OIDC provider endpoints from .well-known/openid-configuration."""
        import asyncio

        self._tls_enforcer.validate_url(issuer_url)

        issuer = issuer_url.rstrip("/")
        discovery_url = f"{issuer}/.well-known/openid-configuration"

        try:
            if self._http_client is not None:
                response = await self._http_client.get(
                    discovery_url, timeout=30, headers={"Accept": "application/json"}
                )
                data = response.json()
            else:

                def _sync_discover() -> dict:
                    with httpx.Client(verify=self._verify, timeout=30) as client:
                        response = client.get(
                            discovery_url, headers={"Accept": "application/json"}
                        )
                        response.raise_for_status()
                        return response.json()

                data = await asyncio.to_thread(_sync_discover)
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"OIDC discovery failed ({exc.response.status_code}): {discovery_url}"
            ) from exc
        except (httpx.RequestError, ValueError) as exc:
            raise ProviderError(
                f"Failed to fetch OIDC discovery from {discovery_url}: {exc}"
            ) from exc

        authorization_endpoint = data.get("authorization_endpoint")
        token_endpoint = data.get("token_endpoint")
        jwks_uri = data.get("jwks_uri")

        if not authorization_endpoint or not token_endpoint or not jwks_uri:
            raise ProviderError(
                "OIDC discovery document missing required fields "
                "(authorization_endpoint, token_endpoint, or jwks_uri)"
            )

        self._tls_enforcer.validate_url(authorization_endpoint)
        self._tls_enforcer.validate_url(token_endpoint)

        endpoints = OIDCEndpoints(
            authorization_endpoint=authorization_endpoint,
            token_endpoint=token_endpoint,
            userinfo_endpoint=data.get("userinfo_endpoint"),
            jwks_uri=jwks_uri,
        )
        self._endpoints = endpoints
        return endpoints

    async def initiate_flow(self, provider_config: AuthConfig) -> AuthResult:
        """Initiate OAuth2 Authorization Code flow with PKCE.

        Opens the system browser and waits for the callback.
        """
        issuer_url = str(provider_config.issuer).rstrip("/")
        if self._endpoints is None:
            await self.discover_endpoints(issuer_url)

        assert self._endpoints is not None

        code_verifier = _generate_code_verifier()
        code_challenge = _generate_code_challenge(code_verifier)
        state = secrets.token_urlsafe(32)

        # Start local callback server
        callback_server = CallbackServer()
        port = callback_server.start(provider_config.callback_port)
        redirect_uri = f"http://localhost:{port}/callback"

        # Verify the callback server is actually reachable
        try:
            # Quick self-test: hit a non-callback path to confirm the server responds
            urllib.request.urlopen(f"http://127.0.0.1:{port}/healthcheck", timeout=2)
        except urllib.error.HTTPError:
            # 404 is fine — it means the server IS responding
            pass
        except Exception as verify_exc:
            callback_server.shutdown()
            raise AuthenticationError(
                f"Callback server started but is not reachable on port {port}: {verify_exc}"
            ) from verify_exc

        # Build authorization URL
        params = {
            "client_id": provider_config.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(provider_config.scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "login",
        }
        auth_url = (
            f"{self._endpoints.authorization_endpoint}?{urllib.parse.urlencode(params)}"
        )

        # Open browser
        _open_browser(auth_url)
        logger.info("OAuth2 login URL: %s", auth_url)
        print(
            f"\n🔐 Browser opened for authentication.\n"
            f"   Waiting for login on port {port}...\n",
            file=sys.stderr,
            flush=True,
        )

        # Wait for callback (in a thread to not block the event loop)
        import asyncio

        timeout = provider_config.callback_timeout
        logger.info(
            "Waiting for OAuth2 callback on port %d (timeout=%ds)...", port, timeout
        )
        try:
            result = await asyncio.to_thread(callback_server.wait_for_callback, timeout)
            logger.info("OAuth2 callback received: keys=%s", list(result.keys()))
            print(
                "   ✓ Callback received, exchanging token...\n",
                file=sys.stderr,
                flush=True,
            )
        except TimeoutError as exc:
            callback_server.shutdown()
            raise AuthenticationError(
                f"OAuth2 callback timed out after {timeout} seconds"
            ) from exc
        except Exception as exc:
            callback_server.shutdown()
            logger.error("OAuth2 callback error: %s", exc, exc_info=True)
            raise AuthenticationError(f"OAuth2 callback failed: {exc}") from exc

        # Validate
        if result.get("state") != state:
            callback_server.shutdown()
            raise AuthenticationError("OAuth2 state mismatch — possible CSRF attack")

        if "error" in result:
            error_desc = result.get("error_description", result["error"])
            callback_server.shutdown()
            raise AuthenticationError(f"OAuth2 authorization denied: {error_desc}")

        code = result.get("code")
        if not code:
            callback_server.shutdown()
            raise AuthenticationError("Callback did not contain an authorization code")

        callback_server.shutdown()
        return AuthResult(code=code, verifier=code_verifier, redirect_uri=redirect_uri)

    async def exchange_code(
        self,
        code: str,
        verifier: str,
        redirect_uri: str | None = None,
        provider_config: AuthConfig | None = None,
    ) -> TokenSet:
        """Exchange an authorization code for tokens using httpx."""
        config = provider_config or self._provider_config
        if config is None:
            raise AuthenticationError("No provider configuration for token exchange")
        if self._endpoints is None:
            raise AuthenticationError("OIDC endpoints not discovered")

        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri or "http://localhost/callback",
            "client_id": config.client_id,
            "code_verifier": verifier,
        }
        if config.client_secret:
            body["client_secret"] = config.client_secret

        return await self._post_token_request(body, config.token_exchange_timeout)

    async def refresh_token(
        self,
        refresh_token: str,
        provider_config: AuthConfig | None = None,
    ) -> TokenSet:
        """Refresh an access token."""
        config = provider_config or self._provider_config
        if config is None:
            raise AuthenticationError("No provider configuration for token refresh")
        if self._endpoints is None:
            raise AuthenticationError("OIDC endpoints not discovered")

        body = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": config.client_id,
        }
        if config.client_secret:
            body["client_secret"] = config.client_secret

        return await self._post_token_request(body, 30)

    async def client_credentials(
        self,
        provider_config: AuthConfig | None = None,
    ) -> TokenSet:
        """Obtain a token via client_credentials grant (M2M)."""
        config = provider_config or self._provider_config
        if config is None:
            raise AuthenticationError(
                "No provider configuration for client credentials"
            )

        if not config.client_secret:
            raise AuthenticationError(
                "client_credentials grant requires a client_secret"
            )

        if self._endpoints is None:
            issuer_url = str(config.issuer).rstrip("/")
            await self.discover_endpoints(issuer_url)
        assert self._endpoints is not None

        body = {
            "grant_type": "client_credentials",
            "client_id": config.client_id,
            "client_secret": config.client_secret,
        }
        if config.scopes:
            body["scope"] = " ".join(config.scopes)

        return await self._post_token_request(body, config.token_exchange_timeout)

    async def token_exchange(
        self,
        subject_token: str,
        provider_config: AuthConfig | None = None,
        audience: str | None = None,
        scope: str | None = None,
    ) -> TokenSet:
        """Exchange an incoming user token for a downstream access token (RFC 8693).

        This implements the OAuth 2.0 Token Exchange grant type, enabling
        headless/cloud MCP servers to accept an upstream user token (e.g. from
        the MCP transport layer) and exchange it at the IDP for a scoped
        downstream token.

        Args:
            subject_token: The incoming user token to exchange.
            provider_config: Auth configuration (uses instance config if None).
            audience: Target audience for the exchanged token (downstream API).
            scope: Scopes to request on the exchanged token.

        Returns:
            A TokenSet containing the exchanged downstream access token.

        Raises:
            AuthenticationError: If configuration is missing or exchange fails.
            ProviderError: If the IDP rejects the exchange or is unreachable.
        """
        config = provider_config or self._provider_config
        if config is None:
            raise AuthenticationError("No provider configuration for token exchange")

        if not config.client_id:
            raise AuthenticationError("token_exchange requires a client_id")

        if self._endpoints is None:
            issuer_url = str(config.issuer).rstrip("/")
            await self.discover_endpoints(issuer_url)
        assert self._endpoints is not None

        body: dict[str, str] = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "client_id": config.client_id,
            "subject_token": subject_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        }
        if config.client_secret:
            body["client_secret"] = config.client_secret
        if audience or config.token_exchange_audience:
            body["audience"] = audience or config.token_exchange_audience or ""
        if scope or config.token_exchange_scope:
            body["scope"] = scope or config.token_exchange_scope or ""

        return await self._post_token_request(body, config.token_exchange_timeout)

    async def _post_token_request(self, body: dict[str, str], timeout: int) -> TokenSet:
        """POST to the token endpoint.

        When a ResilientHttpClient is available, delegates to post_token()
        which routes through the circuit breaker. Otherwise uses synchronous
        httpx in a thread to avoid event-loop conflicts with anyio.
        """
        import asyncio

        assert self._endpoints is not None
        token_url = self._endpoints.token_endpoint

        if self._http_client is not None:
            try:
                return await self._http_client.post_token(
                    token_url, body, timeout=timeout
                )
            except httpx.HTTPStatusError as exc:
                try:
                    error_body = exc.response.json()
                    error_msg = error_body.get(
                        "error_description", error_body.get("error", str(exc))
                    )
                except (ValueError, AttributeError):
                    error_msg = str(exc)
                raise ProviderError(f"Token endpoint error: {error_msg}") from exc
            except httpx.RequestError as exc:
                raise ProviderError(f"Failed to reach token endpoint: {exc}") from exc

        # Use synchronous httpx in a thread to avoid deadlocks with anyio's
        # event loop (FastMCP runs on anyio which can conflict with nested
        # async HTTP clients).
        def _sync_post() -> dict:
            with httpx.Client(verify=self._verify, timeout=timeout) as client:
                response = client.post(
                    token_url,
                    data=body,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                    },
                )
                response.raise_for_status()
                return response.json()

        try:
            data = await asyncio.to_thread(_sync_post)
        except httpx.HTTPStatusError as exc:
            try:
                error_body = exc.response.json()
                error_msg = error_body.get(
                    "error_description", error_body.get("error", str(exc))
                )
            except (ValueError, AttributeError):
                error_msg = str(exc)
            raise ProviderError(f"Token endpoint error: {error_msg}") from exc
        except httpx.RequestError as exc:
            raise ProviderError(f"Failed to reach token endpoint: {exc}") from exc

        return _parse_token_response(data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_code_verifier() -> str:
    """Generate a PKCE code_verifier (43-128 character URL-safe random string)."""
    return secrets.token_urlsafe(64)


def _generate_code_challenge(verifier: str) -> str:
    """Generate a PKCE code_challenge from a code_verifier using S256."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _parse_token_response(data: dict[str, Any]) -> TokenSet:
    """Parse a token endpoint JSON response into a TokenSet."""
    access_token = data.get("access_token")
    if not access_token:
        raise ProviderError("Token response missing 'access_token'")

    expires_in = data.get("expires_in", 3600)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    return TokenSet(
        access_token=access_token,
        refresh_token=data.get("refresh_token"),
        expires_at=expires_at,
        token_type=data.get("token_type", "Bearer"),
        id_token=data.get("id_token"),
    )


def _open_browser(url: str) -> None:
    """Open a URL in the system browser with fallbacks."""
    logger.info("Attempting to open browser for URL: %s", url[:80])
    try:
        opened = webbrowser.open(url)
        logger.info("webbrowser.open() returned: %s", opened)
        if not opened:
            logger.info("webbrowser.open failed, trying 'open' command")
            subprocess.Popen(
                ["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
    except Exception as exc:
        logger.warning("webbrowser.open() raised: %s, trying 'open' command", exc)
        try:
            subprocess.Popen(
                ["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception as exc2:
            logger.error("All browser open methods failed: %s", exc2)
            print(
                f"\n⚠ Could not open browser. Open this URL manually:\n\n  {url}\n",
                file=sys.stderr,
                flush=True,
            )
