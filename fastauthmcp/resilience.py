"""Circuit breaker and resilient HTTP client for IDP calls.

Implements the circuit breaker pattern to protect against cascading failures
when identity providers are unavailable. All outbound IDP HTTP calls route
through these components.
"""

from __future__ import annotations

import asyncio
import ssl
import time
from enum import Enum

import httpx

from fastauthmcp.exceptions import ProviderError
from fastauthmcp.models import TokenSet


class CircuitState(Enum):
    """States for the circuit breaker state machine."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Async-safe circuit breaker for IDP HTTP calls.

    Thread-safe via asyncio.Lock. Shared across OAuthService and JWKSManager.

    State transitions:
        CLOSED → OPEN: when consecutive failures reach failure_threshold
        OPEN → HALF_OPEN: when cooldown_seconds elapse since last failure
        HALF_OPEN → CLOSED: when the single probe request succeeds
        HALF_OPEN → OPEN: when the single probe request fails

    In HALF_OPEN state, only one probe request is allowed through.
    All other requests are rejected with ProviderError until the probe completes.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0,
    ) -> None:
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._last_failure_time: float = 0.0
        self._lock = asyncio.Lock()
        self._probe_in_progress = False

    @property
    def state(self) -> CircuitState:
        """Current state (computed — checks cooldown expiry for OPEN→HALF_OPEN)."""
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self._cooldown_seconds:
                return CircuitState.HALF_OPEN
        return self._state

    async def execute(self, coro_factory):
        """Execute a coroutine through the circuit breaker.

        The state check happens under the lock; the actual HTTP call executes
        outside the lock to allow concurrency in CLOSED state.

        Args:
            coro_factory: A zero-arg async callable that performs the HTTP request.

        Returns:
            The result of the coroutine.

        Raises:
            ProviderError: If circuit is open or a probe is already in progress.
        """
        async with self._lock:
            current_state = self.state

            if current_state == CircuitState.OPEN:
                raise ProviderError(
                    "Circuit breaker is open — IDP calls are temporarily disabled. "
                    f"Will retry after {self._cooldown_seconds}s cooldown."
                )

            if current_state == CircuitState.HALF_OPEN:
                if self._probe_in_progress:
                    raise ProviderError(
                        "Circuit breaker is half-open — probe in progress, rejecting."
                    )
                self._probe_in_progress = True

        # Execute outside the lock to allow concurrency in CLOSED state
        try:
            result = await coro_factory()
            await self._record_success()
            return result
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            if self._is_failure(exc):
                await self._record_failure()
            raise

    async def _record_success(self) -> None:
        """Record a successful call — reset failure count, HALF_OPEN→CLOSED."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                # Probe succeeded — close the circuit
                self._state = CircuitState.CLOSED
                self._probe_in_progress = False
            self._failure_count = 0

    async def _record_failure(self) -> None:
        """Record a failed call — increment count, open at threshold, HALF_OPEN→OPEN."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — reopen and restart cooldown
                self._state = CircuitState.OPEN
                self._last_failure_time = time.monotonic()
                self._probe_in_progress = False
                return
            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                self._last_failure_time = time.monotonic()

    @staticmethod
    def _is_failure(exc: BaseException) -> bool:
        """Determine if an exception counts as a circuit breaker failure.

        Returns True for:
            - httpx.RequestError (connection errors, timeouts)
            - httpx.HTTPStatusError with 5xx status codes
        """
        if isinstance(exc, httpx.RequestError):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code >= 500
        return False

    def reset(self) -> None:
        """Reset the circuit breaker to CLOSED state (for testing)."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._probe_in_progress = False


class ResilientHttpClient:
    """Wraps httpx.AsyncClient with circuit breaker integration.

    Shared across OAuthService and JWKSManager. All IDP HTTP calls
    route through this client. Stateless — creates a fresh httpx.AsyncClient
    per request to avoid connection pool issues with circuit breaker state changes.

    When an ssl_context is provided (for mTLS), it is used as the ``verify``
    parameter for all outbound HTTPS requests, enabling client certificate
    presentation to the identity provider.
    """

    def __init__(
        self,
        circuit_breaker: CircuitBreaker,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self._cb = circuit_breaker
        self._ssl_context = ssl_context

    @property
    def _verify(self) -> ssl.SSLContext | bool:
        """Return the TLS verification parameter for httpx.

        If an mTLS SSLContext is configured, returns it so httpx presents the
        client certificate. Otherwise defaults to True (standard CA verification).
        """
        return self._ssl_context if self._ssl_context is not None else True

    async def get(
        self, url: str, *, timeout: float = 15, headers: dict | None = None
    ) -> httpx.Response:
        """GET with circuit breaker protection.

        Args:
            url: The URL to fetch.
            timeout: Request timeout in seconds (default 15).
            headers: Optional HTTP headers to include.

        Returns:
            The httpx.Response on success.

        Raises:
            httpx.HTTPStatusError: On non-2xx response (after circuit breaker records failure).
            httpx.RequestError: On connection/timeout errors (after circuit breaker records failure).
            ProviderError: If the circuit breaker is open.
        """

        async def _do_request() -> httpx.Response:
            async with httpx.AsyncClient(verify=self._verify, timeout=timeout) as client:
                resp = await client.get(url, headers=headers or {})
                resp.raise_for_status()
                return resp

        return await self._cb.execute(_do_request)

    async def post_form(self, url: str, data: dict, *, timeout: float = 30) -> httpx.Response:
        """POST form-encoded data with circuit breaker protection.

        Sends data as application/x-www-form-urlencoded with Accept: application/json.

        Args:
            url: The URL to POST to.
            data: Form fields to encode.
            timeout: Request timeout in seconds (default 30).

        Returns:
            The httpx.Response on success.

        Raises:
            httpx.HTTPStatusError: On non-2xx response (after circuit breaker records failure).
            httpx.RequestError: On connection/timeout errors (after circuit breaker records failure).
            ProviderError: If the circuit breaker is open.
        """

        async def _do_request() -> httpx.Response:
            async with httpx.AsyncClient(verify=self._verify, timeout=timeout) as client:
                resp = await client.post(
                    url,
                    data=data,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                    },
                )
                resp.raise_for_status()
                return resp

        return await self._cb.execute(_do_request)

    async def post_token(self, url: str, body: dict, timeout: float = 30) -> TokenSet:
        """POST to a token endpoint and parse the response into a TokenSet.

        Delegates to post_form for the HTTP call, then parses the JSON response.

        Args:
            url: The token endpoint URL.
            body: Form fields for the token request.
            timeout: Request timeout in seconds (default 30).

        Returns:
            A TokenSet parsed from the token endpoint response.

        Raises:
            httpx.HTTPStatusError: On non-2xx response.
            httpx.RequestError: On connection/timeout errors.
            ProviderError: If the circuit breaker is open.
        """
        from fastauthmcp.auth.oauth import _parse_token_response

        resp = await self.post_form(url, body, timeout=timeout)
        data = resp.json()
        return _parse_token_response(data)
