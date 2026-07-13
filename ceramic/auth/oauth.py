"""OAuth2/OIDC service with PKCE support for the Ceramic framework."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import ssl
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any

from ceramic.config import AuthConfig
from ceramic.exceptions import AuthenticationError, ProviderError
from ceramic.models import OIDCEndpoints, TokenSet
from ceramic.security import TLSEnforcer


@dataclass
class AuthResult:
    """Result of initiating an OAuth2 flow, containing the code and verifier."""

    code: str
    verifier: str
    redirect_uri: str


class OAuthService:
    """Handles OAuth2/OIDC flows with PKCE.

    Implements OIDC discovery, PKCE-based authorization code flow,
    token exchange, and token refresh.
    """

    def __init__(self, provider_config: AuthConfig | None = None) -> None:
        self._provider_config = provider_config
        self._tls_enforcer = TLSEnforcer()
        self._endpoints: OIDCEndpoints | None = None

    async def discover_endpoints(self, issuer_url: str) -> OIDCEndpoints:
        """Fetch OIDC provider endpoints from .well-known/openid-configuration.

        Args:
            issuer_url: The OIDC issuer URL (must be HTTPS).

        Returns:
            OIDCEndpoints with discovered authorization, token, userinfo, and JWKS URIs.

        Raises:
            ProviderError: If the discovery document cannot be fetched or parsed.
            ConfigurationError: If the issuer URL or discovered endpoints are not HTTPS.
        """
        # Validate issuer URL uses HTTPS
        self._tls_enforcer.validate_url(issuer_url)

        # Strip trailing slash and build discovery URL
        issuer = issuer_url.rstrip("/")
        discovery_url = f"{issuer}/.well-known/openid-configuration"

        try:
            ssl_context = self._tls_enforcer.get_ssl_context()
            request = urllib.request.Request(
                discovery_url,
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(request, context=ssl_context, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError) as exc:
            raise ProviderError(
                f"Failed to fetch OIDC discovery document from {discovery_url}: {exc}"
            ) from exc

        # Extract required fields
        authorization_endpoint = data.get("authorization_endpoint")
        token_endpoint = data.get("token_endpoint")
        jwks_uri = data.get("jwks_uri")

        if not authorization_endpoint or not token_endpoint or not jwks_uri:
            raise ProviderError(
                "OIDC discovery document is missing required fields "
                "(authorization_endpoint, token_endpoint, or jwks_uri)"
            )

        # Validate discovered endpoints use HTTPS
        self._tls_enforcer.validate_url(authorization_endpoint)
        self._tls_enforcer.validate_url(token_endpoint)

        endpoints = OIDCEndpoints(
            authorization_endpoint=authorization_endpoint,
            token_endpoint=token_endpoint,
            userinfo_endpoint=data.get("userinfo_endpoint"),
            jwks_uri=jwks_uri,
        )

        # Cache for reuse
        self._endpoints = endpoints
        return endpoints

    async def initiate_flow(self, provider_config: AuthConfig) -> AuthResult:
        """Initiate OAuth2 Authorization Code flow with PKCE.

        Opens the system browser to the authorization URL and starts a local
        callback server to receive the authorization code.

        Args:
            provider_config: Authentication configuration with provider details.

        Returns:
            AuthResult containing the authorization code, verifier, and redirect URI.

        Raises:
            AuthenticationError: If the callback times out or the flow is aborted.
            ProviderError: If endpoint discovery fails.
        """
        # Discover endpoints if not already cached
        issuer_url = str(provider_config.issuer).rstrip("/")
        if self._endpoints is None:
            await self.discover_endpoints(issuer_url)

        assert self._endpoints is not None

        # Generate PKCE code_verifier and challenge
        code_verifier = _generate_code_verifier()
        code_challenge = _generate_code_challenge(code_verifier)

        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)

        # Start local callback server on a random port
        callback_server = _CallbackServer()
        port = callback_server.start()
        redirect_uri = f"http://localhost:{port}/callback"

        # Build authorization URL
        params = {
            "client_id": provider_config.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(provider_config.scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        auth_url = f"{self._endpoints.authorization_endpoint}?{urllib.parse.urlencode(params)}"

        # Open system browser
        webbrowser.open(auth_url)

        # Wait for callback with timeout
        timeout = provider_config.callback_timeout
        try:
            result = callback_server.wait_for_callback(timeout=timeout)
        except TimeoutError as exc:
            callback_server.shutdown()
            raise AuthenticationError(
                f"OAuth2 callback timed out after {timeout} seconds"
            ) from exc
        except Exception as exc:
            callback_server.shutdown()
            raise AuthenticationError(
                f"OAuth2 callback failed: {exc}"
            ) from exc

        # Validate state
        if result.get("state") != state:
            callback_server.shutdown()
            raise AuthenticationError("OAuth2 state mismatch — possible CSRF attack")

        # Check for error response
        if "error" in result:
            error_desc = result.get("error_description", result["error"])
            callback_server.shutdown()
            raise AuthenticationError(f"OAuth2 authorization denied: {error_desc}")

        code = result.get("code")
        if not code:
            callback_server.shutdown()
            raise AuthenticationError("OAuth2 callback did not contain an authorization code")

        callback_server.shutdown()

        return AuthResult(code=code, verifier=code_verifier, redirect_uri=redirect_uri)

    async def exchange_code(
        self,
        code: str,
        verifier: str,
        redirect_uri: str | None = None,
        provider_config: AuthConfig | None = None,
    ) -> TokenSet:
        """Exchange an authorization code for tokens.

        Args:
            code: The authorization code received from the callback.
            verifier: The PKCE code_verifier used during the authorization request.
            redirect_uri: The redirect URI used in the authorization request.
            provider_config: Optional config override; falls back to instance config.

        Returns:
            TokenSet with access_token, refresh_token, and expiry.

        Raises:
            ProviderError: If the token endpoint returns an error or is unreachable.
            AuthenticationError: If endpoints have not been discovered.
        """
        config = provider_config or self._provider_config
        if config is None:
            raise AuthenticationError("No provider configuration available for token exchange")

        if self._endpoints is None:
            raise AuthenticationError(
                "OIDC endpoints not discovered. Call discover_endpoints() first."
            )

        timeout = config.token_exchange_timeout

        # Build token request body with PKCE verifier
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri or f"http://localhost/callback",
            "client_id": config.client_id,
            "code_verifier": verifier,
        }

        # Include client_secret if configured
        if config.client_secret:
            body["client_secret"] = config.client_secret

        return self._post_token_request(body, timeout)

    async def refresh_token(
        self,
        refresh_token: str,
        provider_config: AuthConfig | None = None,
    ) -> TokenSet:
        """Refresh an access token using a refresh token.

        Args:
            refresh_token: The refresh token to use.
            provider_config: Optional config override; falls back to instance config.

        Returns:
            TokenSet with new access_token (and possibly rotated refresh_token).

        Raises:
            ProviderError: If the token endpoint returns an error or is unreachable.
            AuthenticationError: If endpoints have not been discovered.
        """
        config = provider_config or self._provider_config
        if config is None:
            raise AuthenticationError("No provider configuration available for token refresh")

        if self._endpoints is None:
            raise AuthenticationError(
                "OIDC endpoints not discovered. Call discover_endpoints() first."
            )

        body = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": config.client_id,
        }

        # Include client_secret if configured
        if config.client_secret:
            body["client_secret"] = config.client_secret

        return self._post_token_request(body, timeout=30)

    def _post_token_request(self, body: dict[str, str], timeout: int) -> TokenSet:
        """POST to the token endpoint and parse the response into a TokenSet.

        Args:
            body: Form-encoded body parameters.
            timeout: HTTP request timeout in seconds.

        Returns:
            Parsed TokenSet.

        Raises:
            ProviderError: On HTTP or parsing errors.
        """
        assert self._endpoints is not None

        token_url = self._endpoints.token_endpoint
        encoded_body = urllib.parse.urlencode(body).encode("utf-8")

        try:
            ssl_context = self._tls_enforcer.get_ssl_context()
            request = urllib.request.Request(
                token_url,
                data=encoded_body,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, context=ssl_context, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                error_body = json.loads(exc.read().decode("utf-8"))
                error_msg = error_body.get("error_description", error_body.get("error", str(exc)))
            except (json.JSONDecodeError, AttributeError):
                error_msg = str(exc)
            raise ProviderError(f"Token endpoint error: {error_msg}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ProviderError(f"Failed to reach token endpoint: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Invalid JSON response from token endpoint: {exc}") from exc

        return _parse_token_response(data)


def _generate_code_verifier() -> str:
    """Generate a PKCE code_verifier (43-128 character URL-safe random string)."""
    # secrets.token_urlsafe(32) produces ~43 chars; use 64 bytes for ~86 chars
    return secrets.token_urlsafe(64)


def _generate_code_challenge(verifier: str) -> str:
    """Generate a PKCE code_challenge from a code_verifier using S256.

    Returns:
        Base64url-encoded SHA-256 hash of the verifier, without padding.
    """
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _parse_token_response(data: dict[str, Any]) -> TokenSet:
    """Parse a token endpoint JSON response into a TokenSet.

    Args:
        data: Parsed JSON response from the token endpoint.

    Returns:
        TokenSet instance.

    Raises:
        ProviderError: If the response is missing required fields.
    """
    access_token = data.get("access_token")
    if not access_token:
        raise ProviderError("Token response missing 'access_token'")

    # Calculate expiry from expires_in (seconds from now)
    expires_in = data.get("expires_in", 3600)
    expires_at = datetime.now(timezone.utc).replace(microsecond=0)
    from datetime import timedelta

    expires_at = expires_at + timedelta(seconds=int(expires_in))

    return TokenSet(
        access_token=access_token,
        refresh_token=data.get("refresh_token"),
        expires_at=expires_at,
        token_type=data.get("token_type", "Bearer"),
        id_token=data.get("id_token"),
    )


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the OAuth2 callback."""

    def do_GET(self) -> None:  # noqa: N802
        """Handle GET request on the callback path."""
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/callback":
            params = urllib.parse.parse_qs(parsed.query)
            # Flatten single-value params
            result = {k: v[0] if len(v) == 1 else v for k, v in params.items()}
            self.server._callback_result = result  # type: ignore[attr-defined]

            # Send success response to browser
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Authentication successful</h1>"
                b"<p>You can close this window.</p></body></html>"
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default HTTP server logging."""
        pass


class _CallbackServer:
    """Local HTTP server that listens for OAuth2 callback on a random port."""

    def __init__(self) -> None:
        self._server: HTTPServer | None = None
        self._thread: Thread | None = None

    def start(self) -> int:
        """Start the callback server on a random available port.

        Returns:
            The port number the server is listening on.

        Raises:
            AuthenticationError: If the server cannot be started.
        """
        try:
            self._server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
            self._server._callback_result = None  # type: ignore[attr-defined]
            port = self._server.server_address[1]
            self._thread = Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            return port
        except OSError as exc:
            raise AuthenticationError(
                f"Failed to start local callback server: {exc}"
            ) from exc

    def wait_for_callback(self, timeout: float) -> dict[str, Any]:
        """Wait for the OAuth2 callback to arrive.

        Args:
            timeout: Maximum seconds to wait for the callback.

        Returns:
            Dictionary of query parameters from the callback.

        Raises:
            TimeoutError: If the callback does not arrive within the timeout.
        """
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._server and self._server._callback_result is not None:  # type: ignore[attr-defined]
                return self._server._callback_result  # type: ignore[attr-defined]
            time.sleep(0.1)

        raise TimeoutError(f"Callback not received within {timeout} seconds")

    def shutdown(self) -> None:
        """Shut down the callback server."""
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
