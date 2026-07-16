"""Resilient JWKS key management with coalescing and stale-while-revalidate.

Uses tenacity for retry logic and PyJWT's PyJWKClient as the base:
- Request coalescing: concurrent requests share one fetch
- Exponential backoff via tenacity: 1s base, 2x multiplier, 60s cap, jitter
- Stale-while-revalidate: cached keys served while background refresh runs
- Max staleness guard: rejects verification after max_staleness without successful refresh
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
import jwt
from jwt import PyJWK, PyJWKSet
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from fastauthmcp.exceptions import ProviderError
from fastauthmcp.resilience import ResilientHttpClient

logger = logging.getLogger(__name__)


class _RetryableHTTPError(Exception):
    """Wrapper to signal tenacity that a 5xx HTTP error is retryable."""

    pass


class JWKSManager:
    """Resilient JWKS key management with coalescing and stale-while-revalidate.

    Provides:
    - Request coalescing: concurrent requests share one outbound fetch
    - Exponential backoff with jitter on transient failures
    - Stale-while-revalidate caching for uninterrupted verification
    - Max staleness guard to reject tokens when keys are too old
    """

    def __init__(
        self,
        issuer: str,
        client_id: str,
        http_client: ResilientHttpClient,
        *,
        cache_ttl: int = 600,
        max_staleness: int = 3600,
        max_retries: int = 3,
        base_backoff: float = 1.0,
        max_backoff: float = 60.0,
        jitter_factor: float = 0.25,
    ) -> None:
        # Configuration
        self._issuer = issuer.rstrip("/")
        self._client_id = client_id
        self._http = http_client
        self._cache_ttl = cache_ttl
        self._max_staleness = max_staleness

        # Retry config
        self._max_retries = max_retries
        self._base_backoff = base_backoff
        self._max_backoff = max_backoff
        self._jitter_factor = jitter_factor

        # Cached JWKS state
        self._jwks_uri: str | None = None
        self._cached_keys: PyJWKSet | None = None
        self._last_successful_fetch: float = 0.0  # monotonic time

        # Coalescing state
        self._inflight_future: asyncio.Future | None = None
        self._lock = asyncio.Lock()

        # Background refresh state
        self._bg_task: asyncio.Task | None = None

    async def _discover_jwks_uri(self) -> str:
        """Discover the JWKS URI from the issuer's OpenID configuration.

        Fetches {issuer}/.well-known/openid-configuration and extracts
        the jwks_uri field.

        Returns:
            The JWKS URI string.

        Raises:
            ProviderError: If discovery fails or jwks_uri is missing.
        """
        url = f"{self._issuer}/.well-known/openid-configuration"
        try:
            resp = await self._http.get(url)
            data = resp.json()
            jwks_uri = data.get("jwks_uri")
            if not jwks_uri:
                raise ProviderError(f"OpenID configuration at {url} does not contain 'jwks_uri'")
            return jwks_uri
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            raise ProviderError(f"Failed to discover JWKS URI from {url}: {exc}") from exc

    async def _fetch_jwks_with_backoff(self) -> PyJWKSet:
        """Fetch JWKS with exponential backoff and jitter via tenacity.

        Retries on 5xx/network errors. Fails fast on 4xx (no retry).

        Returns:
            A PyJWKSet containing the fetched keys.

        Raises:
            ProviderError: After all retries exhausted or on 4xx.
        """
        if self._jwks_uri is None:
            self._jwks_uri = await self._discover_jwks_uri()

        @retry(
            retry=retry_if_exception_type((httpx.RequestError, _RetryableHTTPError)),
            stop=stop_after_attempt(self._max_retries + 1),
            wait=wait_exponential_jitter(
                initial=self._base_backoff,
                max=self._max_backoff,
                jitter=self._max_backoff * self._jitter_factor,
            ),
            reraise=True,
        )
        async def _do_fetch() -> PyJWKSet:
            try:
                resp = await self._http.get(self._jwks_uri)  # type: ignore[arg-type]
                data = resp.json()
                return PyJWKSet.from_dict(data)
            except httpx.HTTPStatusError as exc:
                if 400 <= exc.response.status_code < 500:
                    raise ProviderError(
                        f"JWKS fetch failed with {exc.response.status_code} (not retryable): {exc}"
                    ) from exc
                # 5xx → wrap for tenacity retry
                raise _RetryableHTTPError(exc) from exc

        try:
            return await _do_fetch()
        except _RetryableHTTPError as exc:
            raise ProviderError(
                f"JWKS fetch failed after {self._max_retries + 1} attempts: {exc}"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                f"JWKS fetch failed after {self._max_retries + 1} attempts: {exc}"
            ) from exc

    async def _coalesced_fetch(self) -> PyJWKSet:
        """Coalesce concurrent fetch requests into a single network call.

        Uses asyncio.Future as a shared result holder:
        - First caller creates the Future and starts the fetch task
        - Subsequent callers await the same Future
        - Future resolves with result or exception

        Returns:
            A PyJWKSet from the (shared) fetch result.

        Raises:
            ProviderError: If the fetch fails.
        """
        async with self._lock:
            if self._inflight_future is not None:
                future = self._inflight_future
            else:
                loop = asyncio.get_running_loop()
                future = loop.create_future()
                self._inflight_future = future
                asyncio.create_task(self._run_fetch_and_resolve(future))

        return await future

    async def _run_fetch_and_resolve(self, future: asyncio.Future) -> None:
        """Execute the fetch and resolve the shared Future.

        Updates the cache atomically on success. Clears the inflight
        future under lock regardless of outcome.
        """
        try:
            result = await self._fetch_jwks_with_backoff()
            # Update cache atomically
            self._cached_keys = result
            self._last_successful_fetch = time.monotonic()
            if not future.done():
                future.set_result(result)
        except Exception as exc:
            if not future.done():
                future.set_exception(exc)
        finally:
            async with self._lock:
                self._inflight_future = None

    async def get_signing_key(self, token: str) -> PyJWK:
        """Get the signing key for a JWT token.

        Implements stale-while-revalidate:
        1. If cache is fresh (age < cache_ttl) → return cached key
        2. If cache is stale (age < max_staleness) → return cached + trigger background refresh
        3. If cache is too stale (age >= max_staleness) → raise ProviderError
        4. If cache is empty → blocking coalesced fetch, then return key

        Args:
            token: The JWT token string (used to extract kid from header).

        Returns:
            The matching PyJWK signing key.

        Raises:
            ProviderError: If keys are too stale, fetch fails, or kid not found.
        """
        # Decode header to get kid
        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.exceptions.DecodeError as exc:
            raise ProviderError(f"Failed to decode JWT header: {exc}") from exc

        kid = unverified_header.get("kid")

        if self._cached_keys is not None:
            age = time.monotonic() - self._last_successful_fetch

            if age < self._cache_ttl:
                # Fresh cache — return immediately
                return self._find_key(kid)

            if age < self._max_staleness:
                # Stale but within tolerance — return cached + background refresh
                await self._trigger_background_refresh()
                return self._find_key(kid)

            # Too stale — reject
            raise ProviderError(
                f"JWKS keys are too stale ({age:.0f}s > {self._max_staleness}s) "
                f"— cannot verify tokens."
            )

        # Cache empty — blocking fetch
        await self._coalesced_fetch()
        return self._find_key(kid)

    def _find_key(self, kid: str | None) -> PyJWK:
        """Find a key in the cached key set by kid.

        Args:
            kid: The key ID to look up. If None, returns the first key.

        Returns:
            The matching PyJWK.

        Raises:
            ProviderError: If no matching key is found.
        """
        if self._cached_keys is None:
            raise ProviderError("No JWKS keys cached")

        for key in self._cached_keys.keys:
            if kid is None or key.key_id == kid:
                return key

        raise ProviderError(
            f"No key found in JWKS for kid='{kid}'. "
            f"Available kids: {[k.key_id for k in self._cached_keys.keys]}"
        )

    async def _trigger_background_refresh(self) -> None:
        """Start a background refresh if one isn't already running.

        Guards against duplicate background tasks using the _bg_task reference.
        """
        async with self._lock:
            if self._bg_task is not None and not self._bg_task.done():
                return  # Already refreshing
            self._bg_task = asyncio.create_task(self._background_refresh())

    async def _background_refresh(self) -> None:
        """Background refresh — does NOT block callers on failure.

        Updates cache on success. Logs a warning on failure; stale keys
        remain in cache for callers to use until max_staleness is exceeded.
        """
        try:
            result = await self._fetch_jwks_with_backoff()
            self._cached_keys = result
            self._last_successful_fetch = time.monotonic()
            logger.info("Background JWKS refresh succeeded")
        except Exception as exc:
            logger.warning("Background JWKS refresh failed: %s", exc)
            # Stale keys remain in cache — callers continue using them

    async def verify_token(self, token: str) -> dict[str, Any]:
        """Verify a JWT token and return its claims.

        Uses get_signing_key to obtain the appropriate key, then decodes
        and verifies the token with issuer and audience checks.

        Args:
            token: The JWT token string to verify.

        Returns:
            A dict of verified JWT claims.

        Raises:
            ProviderError: If key retrieval or token verification fails.
        """
        key = await self.get_signing_key(token)
        try:
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._client_id,
            )
            return claims
        except jwt.exceptions.InvalidTokenError as exc:
            raise ProviderError(f"Token verification failed: {exc}") from exc

    def invalidate_cache(self) -> None:
        """Invalidate the JWKS cache.

        Forces the next get_signing_key call to perform a blocking fetch.
        Useful for handling key rotation scenarios.
        """
        self._cached_keys = None
        self._last_successful_fetch = 0.0
