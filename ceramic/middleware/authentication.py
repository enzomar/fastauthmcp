"""Authentication middleware for the Ceramic framework.

Handles token validation, refresh, and OAuth2 flow initiation.
Populates RequestContext.identity with IdentityContext on successful auth.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Awaitable, Callable

from ceramic.auth.oauth import OAuthService
from ceramic.auth.token_storage import TokenStorage, get_token_storage
from ceramic.config import AuthConfig
from ceramic.exceptions import AuthenticationError, ProviderError
from ceramic.identity import IdentityContext, _identity_context_var
from ceramic.middleware.pipeline import RequestContext
from ceramic.models import TokenSet

logger = logging.getLogger(__name__)

# Default storage key for token persistence
_DEFAULT_STORAGE_KEY = "default"


def _derive_storage_key(auth_config: AuthConfig) -> str:
    """Derive a storage key from the issuer URL, or use default."""
    issuer = str(auth_config.issuer).rstrip("/")
    # Use a simplified key based on the issuer hostname
    try:
        from urllib.parse import urlparse

        parsed = urlparse(issuer)
        return parsed.hostname or _DEFAULT_STORAGE_KEY
    except Exception:
        return _DEFAULT_STORAGE_KEY


def _parse_jwt_claims(access_token: str) -> dict[str, Any]:
    """Parse claims from a JWT access token by base64-decoding the payload.

    This performs NO signature verification — we trust the token from our own
    OAuth flow.

    Args:
        access_token: The JWT access token string.

    Returns:
        Dictionary of claims parsed from the JWT payload.

    Raises:
        ValueError: If the token is malformed or cannot be decoded.
    """
    parts = access_token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed JWT: expected 3 dot-separated segments")

    payload_segment = parts[1]
    # Add padding if needed (base64url uses no padding)
    padding = 4 - len(payload_segment) % 4
    if padding != 4:
        payload_segment += "=" * padding

    try:
        decoded = base64.urlsafe_b64decode(payload_segment)
        claims = json.loads(decoded)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"Failed to decode JWT payload: {exc}") from exc

    return claims


def _extract_nested_claim(claims: dict[str, Any], claim_path: str) -> list[str]:
    """Extract a nested claim value using a dot-separated path.

    For example, "realm_access.roles" will look up claims["realm_access"]["roles"].

    Args:
        claims: The full claims dictionary.
        claim_path: Dot-separated path to the claim (e.g. "realm_access.roles").

    Returns:
        List of strings found at the claim path, or empty list if not found.
    """
    parts = claim_path.split(".")
    current: Any = claims
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return []
        if current is None:
            return []

    if isinstance(current, list):
        return [str(item) for item in current]
    elif isinstance(current, str):
        return [current]
    return []


def _build_identity_context(
    claims: dict[str, Any],
    role_claim_path: str = "realm_access.roles",
    group_claim_path: str = "groups",
) -> IdentityContext:
    """Build an IdentityContext from JWT claims.

    Args:
        claims: Parsed JWT claims dictionary.
        role_claim_path: Dot-path to extract roles from claims.
        group_claim_path: Dot-path to extract groups from claims.

    Returns:
        A populated IdentityContext instance.
    """
    email = claims.get("email")
    subject = claims.get("sub")
    roles = frozenset(_extract_nested_claim(claims, role_claim_path))
    groups = frozenset(_extract_nested_claim(claims, group_claim_path))

    return IdentityContext(
        email=email,
        subject=subject,
        claims=MappingProxyType(claims),
        roles=roles,
        groups=groups,
    )


class AuthenticationMiddleware:
    """Middleware that handles authentication: token validation, refresh, and OAuth flow.

    Supports two grant types:

    1. **authorization_code** (default) — Interactive OAuth2 + PKCE flow that opens
       a browser for user login. Suitable for CLI/desktop apps running locally (stdio).

    2. **client_credentials** — M2M (machine-to-machine) flow that authenticates
       using client_id + client_secret without user interaction. Suitable for
       remote/headless server deployments where a browser can't be opened.

    On before_request:
    1. Try to get token from storage
    2. If token exists and valid → populate identity → call next
    3. If token exists but expired → attempt refresh (authorization_code) or
       re-acquire (client_credentials)
    4. If no token → initiate appropriate flow based on grant_type
    5. On transient provider errors → preserve stored tokens, return auth error
    """

    def __init__(
        self,
        auth_config: AuthConfig,
        token_storage: TokenStorage | None = None,
        oauth_service: OAuthService | None = None,
        role_claim_path: str = "realm_access.roles",
        group_claim_path: str = "groups",
    ) -> None:
        self.auth_config = auth_config
        self.oauth_service = oauth_service or OAuthService(provider_config=auth_config)
        self.token_storage = token_storage or get_token_storage()
        self._storage_key = _derive_storage_key(auth_config)
        self._role_claim_path = role_claim_path
        self._group_claim_path = group_claim_path
        self._is_m2m = auth_config.grant_type == "client_credentials"

    async def __call__(
        self, ctx: RequestContext, next: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Execute authentication logic before passing to the next middleware."""
        # 1. Try to get token from storage
        token_set = await self.token_storage.retrieve(self._storage_key)

        if token_set is not None:
            # 2. Token exists — check if it's still valid
            if self._is_token_valid(token_set):
                # Token is valid — populate identity and proceed
                self._populate_identity(ctx, token_set)
                return await next()

            # 3. Token is expired
            if self._is_m2m:
                # M2M: no refresh tokens — just re-acquire via client_credentials
                await self.token_storage.delete(self._storage_key)
                return await self._handle_client_credentials(ctx, next)

            # Interactive: attempt refresh if we have a refresh token
            if token_set.refresh_token:
                return await self._handle_refresh(ctx, token_set, next)
            else:
                # No refresh token available — need to re-authenticate
                await self.token_storage.delete(self._storage_key)
                return await self._handle_oauth_flow(ctx, next)
        else:
            # 4. No token in storage — initiate appropriate flow
            if self._is_m2m:
                return await self._handle_client_credentials(ctx, next)
            else:
                return await self._handle_oauth_flow(ctx, next)

    def _is_token_valid(self, token_set: TokenSet) -> bool:
        """Check if the token is still valid (not expired)."""
        return token_set.expires_at > datetime.now(timezone.utc)

    def _populate_identity(self, ctx: RequestContext, token_set: TokenSet) -> None:
        """Parse JWT claims and set identity on the request context."""
        try:
            claims = _parse_jwt_claims(token_set.access_token)
        except ValueError:
            # If we can't parse claims, create a minimal identity
            claims = {}

        identity = _build_identity_context(
            claims,
            role_claim_path=self._role_claim_path,
            group_claim_path=self._group_claim_path,
        )
        ctx.identity = identity
        _identity_context_var.set(identity)

    async def _handle_refresh(
        self,
        ctx: RequestContext,
        token_set: TokenSet,
        next: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Attempt to refresh an expired token.

        On success: update storage, populate identity, call next.
        On refresh failure (AuthenticationError): invalidate session, discard tokens,
            return auth error.
        On transient provider failure (ProviderError): preserve stored tokens,
            return provider error.
        """
        try:
            new_token_set = await self.oauth_service.refresh_token(
                refresh_token=token_set.refresh_token,  # type: ignore[arg-type]
            )
            # Preserve the old refresh token if the provider didn't rotate it
            if new_token_set.refresh_token is None:
                new_token_set = TokenSet(
                    access_token=new_token_set.access_token,
                    refresh_token=token_set.refresh_token,
                    expires_at=new_token_set.expires_at,
                    token_type=new_token_set.token_type,
                    id_token=new_token_set.id_token,
                )

            # Store the new token set
            await self.token_storage.store(self._storage_key, new_token_set)
            self._populate_identity(ctx, new_token_set)
            return await next()

        except ProviderError as exc:
            # Transient provider failure — preserve stored tokens
            logger.warning("Token refresh failed due to provider error: %s", exc)
            return {
                "error": "provider_error",
                "message": f"Identity provider unavailable: {exc}",
            }

        except AuthenticationError as exc:
            # Refresh failed (e.g., token revoked) — invalidate and discard
            logger.info("Token refresh failed, invalidating session: %s", exc)
            await self.token_storage.delete(self._storage_key)
            return {
                "error": "authentication_failed",
                "message": "Token refresh failed. Re-authentication required.",
            }

    async def _handle_oauth_flow(
        self,
        ctx: RequestContext,
        next: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Initiate the OAuth2 flow to obtain new tokens.

        On success: store token, populate identity, call next.
        On failure: return auth error.
        On transient provider errors: preserve stored tokens, return provider error.
        """
        try:
            # Initiate the OAuth2 authorization code flow
            auth_result = await self.oauth_service.initiate_flow(self.auth_config)

            # Exchange the authorization code for tokens
            token_set = await self.oauth_service.exchange_code(
                code=auth_result.code,
                verifier=auth_result.verifier,
                redirect_uri=auth_result.redirect_uri,
            )

            # Store the new token set
            await self.token_storage.store(self._storage_key, token_set)
            self._populate_identity(ctx, token_set)
            return await next()

        except ProviderError as exc:
            # Transient provider failure — preserve any stored tokens
            logger.warning("OAuth flow failed due to provider error: %s", exc)
            return {
                "error": "provider_error",
                "message": f"Identity provider unavailable: {exc}",
            }

        except AuthenticationError as exc:
            # Auth flow failed (timeout, user cancelled, etc.)
            logger.info("OAuth flow failed: %s", exc)
            return {
                "error": "authentication_required",
                "message": f"Authentication required: {exc}",
            }

    async def _handle_client_credentials(
        self,
        ctx: RequestContext,
        next: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Obtain a token via the client_credentials grant (M2M flow).

        No browser interaction required. Uses client_id + client_secret to
        authenticate directly with the token endpoint.

        On success: store token, populate identity, call next.
        On failure: return auth error.
        On transient provider errors: return provider error.
        """
        try:
            token_set = await self.oauth_service.client_credentials(
                provider_config=self.auth_config,
            )

            # Store the token set
            await self.token_storage.store(self._storage_key, token_set)
            self._populate_identity(ctx, token_set)
            return await next()

        except ProviderError as exc:
            logger.warning(
                "Client credentials flow failed due to provider error: %s", exc
            )
            return {
                "error": "provider_error",
                "message": f"Identity provider unavailable: {exc}",
            }

        except AuthenticationError as exc:
            logger.info("Client credentials flow failed: %s", exc)
            return {
                "error": "authentication_failed",
                "message": f"M2M authentication failed: {exc}",
            }
