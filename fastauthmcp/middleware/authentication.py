"""Authentication middleware for the FastAuthMCP framework.

Handles token validation, refresh, and OAuth2 flow initiation.
Populates RequestContext.identity with IdentityContext on successful auth.
"""

from __future__ import annotations

import hashlib
import logging
import ssl
import sys
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from fastauthmcp.auth.claims import build_identity_context, parse_jwt_claims
from fastauthmcp.auth.jwks_manager import JWKSManager
from fastauthmcp.auth.oauth import OAuthService
from fastauthmcp.auth.token_storage import TokenStorage, get_token_storage
from fastauthmcp.config import AuthConfig
from fastauthmcp.exceptions import AuthenticationError, ProviderError
from fastauthmcp.identity import _access_token_var, _identity_context_var
from fastauthmcp.middleware.pipeline import RequestContext
from fastauthmcp.models import TokenSet

logger = logging.getLogger(__name__)

# Default storage key for token persistence
_DEFAULT_STORAGE_KEY = "default"


def _derive_storage_key(auth_config: AuthConfig) -> str:
    """Derive a storage key from the issuer URL, or use default."""
    issuer = str(auth_config.issuer).rstrip("/")
    try:
        from urllib.parse import urlparse

        parsed = urlparse(issuer)
        return parsed.hostname or _DEFAULT_STORAGE_KEY
    except Exception:
        return _DEFAULT_STORAGE_KEY


class AuthenticationMiddleware:
    """Middleware that handles authentication: token validation, refresh, and OAuth flow.

    Supports three grant types:

    1. **authorization_code** (default) — Interactive OAuth2 + PKCE flow.
    2. **client_credentials** — M2M flow using client_id + client_secret.
    3. **token_exchange** — Exchanges an upstream token for a downstream token.

    On before_request:
    1. Try to get token from storage
    2. If token exists and valid → populate identity → call next
    3. If token exists but expired → attempt refresh or re-acquire
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
        ssl_context: ssl.SSLContext | None = None,
        jwks_manager: JWKSManager | None = None,
    ) -> None:
        self.auth_config = auth_config
        self._ssl_context = ssl_context
        self.oauth_service = oauth_service or OAuthService(
            provider_config=auth_config, ssl_context=ssl_context
        )
        self.token_storage = token_storage or get_token_storage()
        self._storage_key = _derive_storage_key(auth_config)
        self._role_claim_path = role_claim_path
        self._group_claim_path = group_claim_path
        self._is_m2m = auth_config.grant_type == "client_credentials"
        self._is_token_exchange = auth_config.grant_type == "token_exchange"
        self._upstream_token_header = auth_config.upstream_token_header
        # Token exchange cache: hash(upstream_token) → (TokenSet, expiry_time)
        self._exchange_cache: dict[str, tuple[TokenSet, float]] = {}
        self._exchange_cache_ttl = 60.0  # seconds

        # JWKS-based token verification (optional)
        # If a JWKSManager is provided, use it directly. Otherwise, create one
        # if auth_config has a circuit_breaker configured (indicating resilient HTTP is desired).
        self._jwks_manager: JWKSManager | None = jwks_manager
        if self._jwks_manager is None and auth_config.circuit_breaker is not None:
            try:
                from fastauthmcp.resilience import CircuitBreaker, ResilientHttpClient

                cb = CircuitBreaker(
                    failure_threshold=auth_config.circuit_breaker.failure_threshold,
                    cooldown_seconds=auth_config.circuit_breaker.cooldown_seconds,
                )
                http_client = ResilientHttpClient(
                    circuit_breaker=cb,
                    ssl_context=ssl_context,
                )
                self._jwks_manager = JWKSManager(
                    issuer=str(auth_config.issuer),
                    client_id=auth_config.client_id,
                    http_client=http_client,
                    cache_ttl=auth_config.jwks_cache_ttl,
                )
            except Exception as exc:
                logger.debug(
                    "Could not initialize JWKSManager, falling back to unverified decode: %s",
                    exc,
                )
                self._jwks_manager = None

    async def __call__(self, ctx: RequestContext, next: Callable[[], Awaitable[Any]]) -> Any:
        """Execute authentication logic before passing to the next middleware."""
        if self._is_token_exchange:
            return await self._handle_token_exchange(ctx, next)

        token_set = await self.token_storage.retrieve(self._storage_key)

        if token_set is not None:
            if self._is_token_valid(token_set):
                await self._populate_identity(ctx, token_set)
                return await next()

            if self._is_m2m:
                await self.token_storage.delete(self._storage_key)
                return await self._handle_client_credentials(ctx, next)

            if token_set.refresh_token:
                return await self._handle_refresh(ctx, token_set, next)
            else:
                await self.token_storage.delete(self._storage_key)
                return await self._handle_oauth_flow(ctx, next)
        else:
            if self._is_m2m:
                return await self._handle_client_credentials(ctx, next)
            else:
                return await self._handle_oauth_flow(ctx, next)

    def _is_token_valid(self, token_set: TokenSet) -> bool:
        """Check if the token is still valid (not expired)."""
        return token_set.expires_at > datetime.now(timezone.utc)

    async def _populate_identity(self, ctx: RequestContext, token_set: TokenSet) -> None:
        """Parse JWT claims and set identity on the request context.

        If a JWKSManager is available, attempts cryptographic verification first.
        Falls back to unverified decode on verification failure (graceful degradation).

        NOTE: Signature verification is intentionally skipped here.
        Tokens are acquired directly from the IDP over TLS (token endpoint),
        not from untrusted sources. For token_exchange mode where tokens come
        from external sources, structural validation is performed in
        _validate_upstream_token(). Full JWKS verification is available via
        JWKSManager for use cases that require it (e.g., validating tokens
        from third-party callers).
        """
        claims: dict[str, Any] = {}

        # If JWKSManager is available, attempt signature verification first
        if self._jwks_manager is not None:
            try:
                claims = await self._jwks_manager.verify_token(token_set.access_token)
            except Exception as exc:
                logger.debug(
                    "JWKS token verification failed, falling back to unverified decode: %s",
                    exc,
                )
                claims = {}

        # Fallback: unverified decode (or if JWKS not configured)
        if not claims:
            # Try access_token first
            try:
                claims = parse_jwt_claims(token_set.access_token)
            except ValueError:
                pass

        # If access_token didn't yield useful claims, try id_token
        if not claims.get("sub") and token_set.id_token:
            try:
                claims = parse_jwt_claims(token_set.id_token)
            except ValueError:
                pass

        identity = build_identity_context(
            claims,
            role_claim_path=self._role_claim_path,
            group_claim_path=self._group_claim_path,
        )
        ctx.identity = identity
        _identity_context_var.set(identity)
        _access_token_var.set(token_set.access_token)

    async def _handle_refresh(
        self,
        ctx: RequestContext,
        token_set: TokenSet,
        next: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Attempt to refresh an expired token."""
        try:
            new_token_set = await self.oauth_service.refresh_token(
                refresh_token=token_set.refresh_token,  # type: ignore[arg-type]
            )
            if new_token_set.refresh_token is None:
                new_token_set = TokenSet(
                    access_token=new_token_set.access_token,
                    refresh_token=token_set.refresh_token,
                    expires_at=new_token_set.expires_at,
                    token_type=new_token_set.token_type,
                    id_token=new_token_set.id_token,
                )

            await self.token_storage.store(self._storage_key, new_token_set)
            await self._populate_identity(ctx, new_token_set)
            return await next()

        except ProviderError as exc:
            logger.warning("Token refresh failed due to provider error: %s", exc)
            return {
                "error": "provider_error",
                "message": f"Identity provider unavailable: {exc}",
            }

        except AuthenticationError as exc:
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
        """Initiate the OAuth2 PKCE flow to obtain new tokens."""
        import asyncio

        try:
            token_set = await asyncio.shield(self._do_oauth_flow())
            await self._populate_identity(ctx, token_set)
            return await next()

        except asyncio.CancelledError:
            logger.info("OAuth flow interrupted by transport")
            raise

        except ProviderError as exc:
            logger.warning("OAuth flow failed due to provider error: %s", exc)
            return {
                "error": "provider_error",
                "message": f"Identity provider unavailable: {exc}",
            }

        except AuthenticationError as exc:
            logger.info("OAuth flow failed: %s", exc)
            return {
                "error": "authentication_required",
                "message": f"Authentication required: {exc}",
            }

        except TimeoutError as exc:
            logger.warning("OAuth flow timed out: %s", exc)
            return {
                "error": "authentication_timeout",
                "message": f"Authentication timed out: {exc}",
            }

    async def _do_oauth_flow(self) -> TokenSet:
        """Execute the full OAuth flow: initiate → callback → exchange."""
        auth_result = await self.oauth_service.initiate_flow(self.auth_config)

        logger.info("OAuth callback received, exchanging code for tokens...")

        token_set = await self.oauth_service.exchange_code(
            code=auth_result.code,
            verifier=auth_result.verifier,
            redirect_uri=auth_result.redirect_uri,
        )

        logger.info("Token exchange successful, storing tokens...")
        print(
            "   ✓ Token exchange successful, authenticated!\n",
            file=sys.stderr,
            flush=True,
        )

        await self.token_storage.store(self._storage_key, token_set)
        return token_set

    async def _handle_client_credentials(
        self,
        ctx: RequestContext,
        next: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Obtain a token via the client_credentials grant (M2M flow)."""
        try:
            token_set = await self.oauth_service.client_credentials(
                provider_config=self.auth_config,
            )
            await self.token_storage.store(self._storage_key, token_set)
            await self._populate_identity(ctx, token_set)
            return await next()

        except ProviderError as exc:
            logger.warning("Client credentials flow failed: %s", exc)
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

    async def _handle_token_exchange(
        self,
        ctx: RequestContext,
        next: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Handle token exchange for headless/cloud deployments.

        Extracts the upstream user token, validates its structure,
        checks the cache, then exchanges it at the IDP.
        """
        # --- Extract upstream token ---
        upstream_token: str | None = None

        if self._upstream_token_header:
            upstream_token = ctx.metadata.get(self._upstream_token_header)

        if not upstream_token:
            upstream_token = ctx.metadata.get("upstream_token")

        if not upstream_token:
            auth_header = ctx.metadata.get("authorization", "")
            if auth_header.lower().startswith("bearer "):
                upstream_token = auth_header[7:]

        if not upstream_token:
            return {
                "error": "authentication_required",
                "message": (
                    "Token exchange mode requires an upstream user token. "
                    f"Provide it via metadata key "
                    f"'{self._upstream_token_header or 'upstream_token'}' "
                    "or 'authorization: Bearer <token>'."
                ),
            }

        # --- Structural validation (no IDP call) ---
        validation_error = self._validate_upstream_token(upstream_token)
        if validation_error:
            return {
                "error": "authentication_failed",
                "message": f"Upstream token rejected: {validation_error}",
            }

        # --- Check cache ---
        cache_key = hashlib.sha256(upstream_token.encode()).hexdigest()[:32]
        cached = self._exchange_cache.get(cache_key)
        if cached is not None:
            cached_token_set, cached_at = cached
            if (time.monotonic() - cached_at) < self._exchange_cache_ttl:
                if self._is_token_valid(cached_token_set):
                    await self._populate_identity(ctx, cached_token_set)
                    return await next()
            del self._exchange_cache[cache_key]

        # --- Exchange at IDP ---
        try:
            token_set = await self.oauth_service.token_exchange(
                subject_token=upstream_token,
                provider_config=self.auth_config,
            )

            # Cache the result
            self._exchange_cache[cache_key] = (token_set, time.monotonic())

            # Evict old entries (simple size cap)
            if len(self._exchange_cache) > 1000:
                oldest_key = min(self._exchange_cache, key=lambda k: self._exchange_cache[k][1])
                del self._exchange_cache[oldest_key]

            await self._populate_identity(ctx, token_set)
            return await next()

        except ProviderError as exc:
            logger.warning("Token exchange failed: %s", exc)
            return {
                "error": "provider_error",
                "message": f"Token exchange failed: {exc}",
            }

        except AuthenticationError as exc:
            logger.info("Token exchange failed: %s", exc)
            return {
                "error": "authentication_failed",
                "message": f"Token exchange rejected: {exc}",
            }

    def _validate_upstream_token(self, token: str) -> str | None:
        """Validate upstream token structure before exchanging at the IDP.

        Performs cheap local checks to reject obviously invalid tokens
        without making an IDP roundtrip.

        Returns:
            None if the token passes validation.
            An error message string if validation fails.
        """
        import base64
        import json as _json

        # 1. Must be a 3-part JWT
        parts = token.split(".")
        if len(parts) != 3:
            return "not a valid JWT (expected 3 dot-separated parts)"

        # 2. Decode payload and check expiration
        try:
            payload_b64 = parts[1]
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            payload_bytes = base64.urlsafe_b64decode(payload_b64)
            claims = _json.loads(payload_bytes)
        except (ValueError, _json.JSONDecodeError, UnicodeDecodeError):
            return "JWT payload is not decodable"

        # 3. Check expiration
        exp = claims.get("exp")
        if exp is not None:
            try:
                if float(exp) < time.time():
                    return "token has expired"
            except (TypeError, ValueError):
                pass

        # 4. Audience check
        expected_client_id = self.auth_config.client_id
        if expected_client_id:
            aud = claims.get("aud")
            azp = claims.get("azp")

            if aud is not None:
                if isinstance(aud, str):
                    aud_list = [aud]
                elif isinstance(aud, list):
                    aud_list = aud
                else:
                    aud_list = []

                if expected_client_id not in aud_list:
                    if azp != expected_client_id:
                        return (
                            f"token audience '{aud}' does not include "
                            f"this service '{expected_client_id}'"
                        )

        return None
