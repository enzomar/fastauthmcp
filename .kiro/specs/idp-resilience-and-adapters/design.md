# Technical Design: IDP Resilience and Adapters

## Overview

This design introduces three new subsystems into FastAuthMCP's auth layer: a pluggable token exchange adapter system, a circuit breaker for IDP HTTP calls, and a resilient JWKS manager with request coalescing and stale-while-revalidate caching. All three integrate into the existing `OAuthService` and `JWKSVerifier` without changing the public API surface.

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FastAuthMCPFastMCP                                │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                  AuthenticationMiddleware                       │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐  │  │
│  │  │ OAuthService │  │ JWKSManager  │  │  CircuitBreaker     │  │  │
│  │  │             │  │ (new)        │  │  (shared)           │  │  │
│  │  └──────┬──────┘  └──────┬───────┘  └──────────┬──────────┘  │  │
│  │         │                 │                      │             │  │
│  │  ┌──────▼──────────────────▼──────────────────────▼──────────┐ │  │
│  │  │              ResilientHttpClient (new)                     │ │  │
│  │  │  Wraps httpx.AsyncClient with circuit breaker              │ │  │
│  │  └──────────────────────────────────────────────────────────┘ │  │
│  │         │                                                      │  │
│  │  ┌──────▼──────────────────────────────────────────────────┐  │  │
│  │  │              AdapterRegistry (new)                        │  │  │
│  │  │  ┌────────────┐ ┌──────────────┐ ┌────────────────────┐ │  │  │
│  │  │  │ RFC8693    │ │ GoogleSTS    │ │ EntraOBO           │ │  │  │
│  │  │  │ (default)  │ │ Adapter      │ │ Adapter            │ │  │  │
│  │  │  └────────────┘ └──────────────┘ └────────────────────┘ │  │  │
│  │  └──────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow: Token Exchange with Adapter

```
Tool Call → AuthMiddleware → _handle_token_exchange()
  → AdapterRegistry.get_adapter(config.token_exchange_provider)
  → adapter.exchange(subject_token, config, endpoints, audience, scope)
    → ResilientHttpClient.post(url, body)
      → CircuitBreaker.execute(httpx_call)
    → TokenSet
  → _populate_identity_async(ctx, token_set)
  → next()
```

### Data Flow: JWKS Verification with Resilience

```
Token arrives → JWKSManager.get_signing_key(kid)
  → cache hit + not stale? → return cached key
  → cache hit + stale?
    → return cached key immediately
    → fire background refresh (coalesced)
      → ResilientHttpClient.get(jwks_uri) with backoff
      → atomically replace cache
  → cache miss (cold start)?
    → blocking fetch with backoff + coalescing
    → populate cache
    → return key
```

## New Files

| File | Purpose |
|------|---------|
| `fastauthmcp/auth/adapters/__init__.py` | Re-exports: TokenExchangeAdapter, AdapterRegistry, RFC8693Adapter, GoogleSTSAdapter, EntraOBOAdapter |
| `fastauthmcp/auth/adapters/base.py` | TokenExchangeAdapter Protocol definition |
| `fastauthmcp/auth/adapters/registry.py` | AdapterRegistry class (provider selection logic) |
| `fastauthmcp/auth/adapters/rfc8693.py` | RFC8693Adapter — default RFC 8693 token exchange |
| `fastauthmcp/auth/adapters/google.py` | GoogleSTSAdapter — Google Cloud STS with camelCase params |
| `fastauthmcp/auth/adapters/entra.py` | EntraOBOAdapter — Microsoft Entra ID on-behalf-of flow |
| `fastauthmcp/resilience.py` | CircuitBreaker, ResilientHttpClient |
| `fastauthmcp/auth/jwks_manager.py` | JWKSManager with coalescing, backoff, stale-while-revalidate |

## Modified Files

| File | Changes |
|------|---------|
| `fastauthmcp/config.py` | Add `CircuitBreakerConfig`, `token_exchange_provider` field, `jwks_cache_ttl` field |
| `fastauthmcp/auth/oauth.py` | Use `ResilientHttpClient` instead of raw httpx; delegate token exchange to `AdapterRegistry` |
| `fastauthmcp/middleware/authentication.py` | Replace `JWKSVerifier` with `JWKSManager`; pass circuit breaker to OAuthService |
| `fastauthmcp/server.py` | Instantiate CircuitBreaker and share it across OAuthService and JWKSManager |

---

## Detailed Design

### 1. Token Exchange Adapter System (`fastauthmcp/auth/adapters.py`)

#### Protocol

```python
from typing import Protocol
from fastauthmcp.config import AuthConfig
from fastauthmcp.models import OIDCEndpoints, TokenSet

class TokenExchangeAdapter(Protocol):
    """Protocol for provider-specific token exchange implementations."""

    @property
    def provider_id(self) -> str:
        """Unique identifier for this adapter (e.g. 'google', 'entra')."""
        ...

    async def exchange(
        self,
        subject_token: str,
        config: AuthConfig,
        endpoints: OIDCEndpoints,
        *,
        audience: str | None = None,
        scope: str | None = None,
    ) -> TokenSet:
        """Exchange subject_token for a downstream TokenSet."""
        ...
```

#### AdapterRegistry

```python
class AdapterRegistry:
    """Registry mapping provider identifiers to adapter instances."""

    _adapters: dict[str, TokenExchangeAdapter]

    def __init__(self) -> None:
        self._adapters = {}
        # Register built-in adapters
        self.register(RFC8693Adapter())
        self.register(GoogleSTSAdapter())
        self.register(EntraOBOAdapter())

    def register(self, adapter: TokenExchangeAdapter) -> None:
        self._adapters[adapter.provider_id] = adapter

    def get_adapter(self, provider_id: str | None) -> TokenExchangeAdapter:
        """Get adapter by ID. Returns RFC8693 if provider_id is None."""
        if provider_id is None:
            return self._adapters["rfc8693"]
        if provider_id not in self._adapters:
            raise ConfigurationError(
                f"Unknown token exchange provider: '{provider_id}'. "
                f"Available: {sorted(self._adapters.keys())}"
            )
        return self._adapters[provider_id]
```

#### RFC8693Adapter (default — preserves current behavior)

```python
class RFC8693Adapter:
    provider_id = "rfc8693"

    async def exchange(self, subject_token, config, endpoints, *, audience=None, scope=None):
        body = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "client_id": config.client_id,
            "subject_token": subject_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        }
        if config.client_secret:
            body["client_secret"] = config.client_secret
        if audience or config.token_exchange_audience:
            body["audience"] = audience or config.token_exchange_audience
        if scope or config.token_exchange_scope:
            body["scope"] = scope or config.token_exchange_scope
        # POST to endpoints.token_endpoint via ResilientHttpClient
        return await self._http.post_token(endpoints.token_endpoint, body, config.token_exchange_timeout)
```

#### GoogleSTSAdapter

```python
class GoogleSTSAdapter:
    provider_id = "google"
    _GOOGLE_STS_URL = "https://sts.googleapis.com/v1/token"

    async def exchange(self, subject_token, config, endpoints, *, audience=None, scope=None):
        body = {
            "grantType": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subjectToken": subject_token,
            "subjectTokenType": "urn:ietf:params:oauth:token-type:access_token",
            "requestedTokenType": "urn:ietf:params:oauth:token-type:access_token",
        }
        if audience or config.token_exchange_audience:
            body["audience"] = audience or config.token_exchange_audience
        if scope or config.token_exchange_scope:
            body["scope"] = scope or config.token_exchange_scope
        # POST to fixed Google STS URL (not discovery endpoint)
        return await self._http.post_token(self._GOOGLE_STS_URL, body, timeout=30)
```

#### EntraOBOAdapter

```python
class EntraOBOAdapter:
    provider_id = "entra"

    async def exchange(self, subject_token, config, endpoints, *, audience=None, scope=None):
        if not config.client_secret:
            raise AuthenticationError("Entra on-behalf-of flow requires client_secret")
        body = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "assertion": subject_token,
            "requested_token_use": "on_behalf_of",
        }
        if scope or config.token_exchange_scope:
            body["scope"] = scope or config.token_exchange_scope
        # POST to discovered token endpoint (Entra uses standard OIDC discovery)
        return await self._http.post_token(
            endpoints.token_endpoint, body, config.token_exchange_timeout
        )
```

---

### 2. Circuit Breaker (`fastauthmcp/resilience.py`)

#### State Machine

```python
import asyncio
import time
from enum import Enum
from fastauthmcp.exceptions import ProviderError

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
```

#### CircuitBreaker Class

```python
class CircuitBreaker:
    """Async-safe circuit breaker for IDP HTTP calls.

    Thread-safe via asyncio.Lock. Shared across OAuthService and JWKSManager.
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
        """Current state (computed — checks cooldown expiry)."""
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self._cooldown_seconds:
                return CircuitState.HALF_OPEN
        return self._state

    async def execute(self, coro_factory):
        """Execute a coroutine through the circuit breaker.

        Args:
            coro_factory: A zero-arg async callable that performs the HTTP request.

        Returns:
            The result of the coroutine.

        Raises:
            ProviderError: If circuit is open or probe fails.
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
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                # Probe succeeded — close the circuit
                self._state = CircuitState.CLOSED
                self._probe_in_progress = False
            self._failure_count = 0

    async def _record_failure(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — reopen
                self._state = CircuitState.OPEN
                self._last_failure_time = time.monotonic()
                self._probe_in_progress = False
                return
            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                self._last_failure_time = time.monotonic()

    @staticmethod
    def _is_failure(exc) -> bool:
        """Determine if an exception counts as a circuit breaker failure."""
        if isinstance(exc, httpx.RequestError):
            return True  # connection error, timeout
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code >= 500
        return False
```

#### ResilientHttpClient

```python
class ResilientHttpClient:
    """Wraps httpx.AsyncClient with circuit breaker integration.

    Shared across OAuthService and JWKSManager. All IDP HTTP calls
    route through this client.
    """

    def __init__(self, circuit_breaker: CircuitBreaker) -> None:
        self._cb = circuit_breaker

    async def get(self, url: str, *, timeout: float = 15, headers: dict | None = None):
        """GET with circuit breaker protection."""
        async def _do_request():
            async with httpx.AsyncClient(verify=True, timeout=timeout) as client:
                resp = await client.get(url, headers=headers or {})
                resp.raise_for_status()
                return resp
        return await self._cb.execute(_do_request)

    async def post_form(self, url: str, data: dict, *, timeout: float = 30):
        """POST form-encoded data with circuit breaker protection."""
        async def _do_request():
            async with httpx.AsyncClient(verify=True, timeout=timeout) as client:
                resp = await client.post(
                    url, data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded",
                             "Accept": "application/json"},
                )
                resp.raise_for_status()
                return resp
        return await self._cb.execute(_do_request)

    async def post_token(self, url: str, body: dict, timeout: float = 30) -> TokenSet:
        """POST to token endpoint and parse response into TokenSet."""
        resp = await self.post_form(url, body, timeout=timeout)
        data = resp.json()
        return _parse_token_response(data)
```

---

### 3. JWKS Manager (`fastauthmcp/auth/jwks_manager.py`)

The new `JWKSManager` replaces the current `JWKSVerifier` class, implementing request coalescing, exponential backoff with jitter, and stale-while-revalidate caching.

#### Class Signature

```python
class JWKSManager:
    """Resilient JWKS key management with coalescing and stale-while-revalidate.

    Replaces the existing JWKSVerifier with production-grade resilience:
    - Request coalescing: concurrent requests share one fetch
    - Exponential backoff: 1s base, 2x multiplier, 60s cap, 25% jitter, 3 retries
    - Stale-while-revalidate: cached keys served while background refresh runs
    - Max staleness guard: rejects verification after 3600s without successful refresh
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
        ...
```

#### Internal State

```python
    # Cache state
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
    self._cached_keys: Any | None = None  # jwt.PyJWKSet or equivalent
    self._last_successful_fetch: float = 0.0  # monotonic time
    self._last_fetch_attempt: float = 0.0

    # Coalescing state
    self._inflight_future: asyncio.Future | None = None
    self._lock = asyncio.Lock()

    # Background refresh state
    self._bg_task: asyncio.Task | None = None
```

#### Key Methods

```python
    async def get_signing_key(self, token: str) -> Any:
        """Get the signing key for a JWT token.

        Implements stale-while-revalidate:
        1. If cache is fresh → return cached key
        2. If cache is stale → return cached + trigger background refresh
        3. If cache is empty → blocking fetch with retries
        4. If cache is too stale (>max_staleness) → raise ProviderError
        """
        ...

    async def verify_token(self, token: str) -> dict[str, Any]:
        """Verify a JWT and return claims. Uses get_signing_key internally."""
        ...

    async def _fetch_jwks_with_backoff(self) -> Any:
        """Fetch JWKS with exponential backoff and jitter.

        Retries on 5xx/network errors. Fails fast on 4xx.
        Base=1s, multiplier=2x, max=60s, jitter=±25%, max_retries=3.
        """
        for attempt in range(self._max_retries + 1):
            try:
                return await self._do_fetch()
            except ProviderError as exc:
                if not self._is_retryable(exc) or attempt == self._max_retries:
                    raise
                delay = min(self._base_backoff * (2 ** attempt), self._max_backoff)
                jitter = random.uniform(0, self._jitter_factor * delay)
                await asyncio.sleep(delay + jitter)

    async def _coalesced_fetch(self) -> Any:
        """Coalesce concurrent fetch requests into a single network call.

        Uses asyncio.Future as a shared result holder:
        - First caller creates the Future and starts the fetch
        - Subsequent callers await the same Future
        - Future resolves with result or exception
        """
        async with self._lock:
            if self._inflight_future is not None:
                # Another fetch is in progress — wait for it
                future = self._inflight_future
            else:
                # We're the first — create a Future and start fetching
                future = asyncio.get_running_loop().create_future()
                self._inflight_future = future
                asyncio.create_task(self._run_fetch_and_resolve(future))

        return await future

    async def _run_fetch_and_resolve(self, future: asyncio.Future) -> None:
        """Execute the fetch and resolve the shared Future."""
        try:
            result = await self._fetch_jwks_with_backoff()
            future.set_result(result)
            # Update cache atomically
            self._cached_keys = result
            self._last_successful_fetch = time.monotonic()
        except Exception as exc:
            future.set_exception(exc)
        finally:
            async with self._lock:
                self._inflight_future = None

    async def _trigger_background_refresh(self) -> None:
        """Start a background refresh if one isn't already running."""
        async with self._lock:
            if self._bg_task is not None and not self._bg_task.done():
                return  # Already refreshing
            self._bg_task = asyncio.create_task(self._background_refresh())

    async def _background_refresh(self) -> None:
        """Background refresh — does NOT block callers on failure."""
        try:
            result = await self._fetch_jwks_with_backoff()
            self._cached_keys = result
            self._last_successful_fetch = time.monotonic()
        except Exception as exc:
            logger.warning("Background JWKS refresh failed: %s", exc)
            # Stale keys remain in cache — callers continue using them
```

---

### 4. Configuration Changes (`fastauthmcp/config.py`)

#### New Models

```python
class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration for IDP HTTP calls."""
    failure_threshold: int = Field(default=5, ge=1, le=100)
    cooldown_seconds: int = Field(default=30, ge=1, le=300)


class AuthConfig(BaseModel):
    # ... existing fields ...

    # NEW: Token exchange provider adapter selection
    token_exchange_provider: str | None = Field(
        default=None,
        pattern=r"^[a-zA-Z0-9\-]{1,64}$",
        description="Provider adapter identifier for token exchange. "
        "Built-in: 'rfc8693' (default), 'google', 'entra'.",
    )

    # NEW: Circuit breaker configuration
    circuit_breaker: CircuitBreakerConfig | None = Field(
        default=None,
        description="Circuit breaker settings for IDP HTTP calls.",
    )

    # NEW: JWKS cache TTL override
    jwks_cache_ttl: int = Field(
        default=600, ge=60, le=86400,
        description="JWKS cache TTL in seconds before stale-while-revalidate kicks in.",
    )
```

#### Example fastauthmcp.yaml

```yaml
auth:
  provider: oidc
  issuer: https://login.microsoftonline.com/tenant-id/v2.0
  client_id: my-mcp-server
  client_secret: ${CERAMIC_AUTH_CLIENT_SECRET}
  grant_type: token_exchange
  token_exchange_provider: entra          # NEW: select adapter
  token_exchange_scope: "api://downstream/.default"
  circuit_breaker:                         # NEW
    failure_threshold: 3
    cooldown_seconds: 60
  jwks_cache_ttl: 300                      # NEW
```

---

### 5. Integration in `fastauthmcp/server.py`

The `FastAuthMCPFastMCP._build_pipeline()` method changes to:

```python
def _build_pipeline(self) -> MiddlewarePipeline:
    # ...
    if self._config.auth is not None:
        # Build shared resilience components
        cb_config = self._config.auth.circuit_breaker or CircuitBreakerConfig()
        circuit_breaker = CircuitBreaker(
            failure_threshold=cb_config.failure_threshold,
            cooldown_seconds=cb_config.cooldown_seconds,
        )
        http_client = ResilientHttpClient(circuit_breaker)

        # Build JWKS Manager (replaces JWKSVerifier)
        jwks_manager = JWKSManager(
            issuer=str(self._config.auth.issuer),
            client_id=self._config.auth.client_id,
            http_client=http_client,
            cache_ttl=self._config.auth.jwks_cache_ttl,
        )

        # Build OAuthService with resilient client
        oauth_service = OAuthService(
            provider_config=self._config.auth,
            http_client=http_client,
        )

        # Build adapter registry
        adapter_registry = AdapterRegistry(http_client=http_client)

        pipeline.add_before(
            AuthenticationMiddleware(
                self._config.auth,
                oauth_service=oauth_service,
                jwks_manager=jwks_manager,
                adapter_registry=adapter_registry,
            )
        )
```

---

### 6. Changes to `AuthenticationMiddleware`

The `_handle_token_exchange` method delegates to the adapter registry:

```python
async def _handle_token_exchange(self, ctx, next):
    # ... extract upstream_token (unchanged) ...

    # Select adapter based on config
    adapter = self._adapter_registry.get_adapter(
        self.auth_config.token_exchange_provider
    )

    try:
        token_set = await adapter.exchange(
            subject_token=upstream_token,
            config=self.auth_config,
            endpoints=await self._ensure_endpoints(),
            audience=self.auth_config.token_exchange_audience,
            scope=self.auth_config.token_exchange_scope,
        )
        await self._populate_identity_async(ctx, token_set)
        return await next()
    except ProviderError as exc:
        # ... existing error handling ...
```

The `_populate_identity_async` method uses `JWKSManager.verify_token()` instead of `JWKSVerifier.verify_token()` — same signature, different implementation.

---

## Error Handling Strategy

| Scenario | Behavior |
|----------|----------|
| Circuit open | ProviderError("Circuit breaker is open...") — fast fail, no network call |
| JWKS stale but within max_staleness | Serve cached keys + background refresh |
| JWKS too stale (>3600s) | ProviderError("JWKS keys are too stale...") |
| Adapter not found | ConfigurationError at server startup |
| Google STS 4xx | ProviderError with error_description from body |
| Entra OBO missing client_secret | AuthenticationError at exchange time |
| Network timeout (within threshold) | Normal ProviderError, failure counted |
| Network timeout (threshold reached) | Circuit opens, subsequent calls fail fast |

---

## Concurrency Model

- **CircuitBreaker**: Uses `asyncio.Lock` for state transitions. The lock is held only during state reads/writes (microseconds). Actual HTTP calls execute outside the lock.
- **JWKSManager coalescing**: Uses `asyncio.Future` as a shared result. First caller creates and drives the fetch; subsequent callers await the same Future.
- **Background refresh**: Uses `asyncio.create_task` — non-blocking. A guard prevents duplicate background tasks.
- **ResilientHttpClient**: Stateless — creates a fresh `httpx.AsyncClient` per request. This avoids connection pool issues with circuit breaker state changes.

---

## Backward Compatibility

- **No breaking changes to public API.** `identity()`, `access_token()`, `FastMCP`, and `FastAuthMCPTestClient` all remain unchanged.
- **No new required config fields.** All new fields (`token_exchange_provider`, `circuit_breaker`, `jwks_cache_ttl`) are optional with sensible defaults.
- **Default adapter is RFC 8693.** Existing `grant_type: token_exchange` configs continue to work without adding `token_exchange_provider`.
- **JWKSVerifier → JWKSManager**: Internal replacement. The verification API (`verify_token(token) -> claims`) stays the same.

---

## Testing Strategy

| Component | Test Type | Approach |
|-----------|-----------|----------|
| CircuitBreaker | Unit | Mock time, verify state transitions |
| AdapterRegistry | Unit | Verify selection, unknown provider error |
| GoogleSTSAdapter | Unit | Mock httpx responses, verify parameter names |
| EntraOBOAdapter | Unit | Mock httpx responses, verify OBO params |
| JWKSManager coalescing | Unit | Concurrent asyncio tasks, mock HTTP, assert single fetch |
| JWKSManager backoff | Unit | Mock failures, verify delays with tolerance |
| JWKSManager stale-while-revalidate | Unit | Expire TTL, verify cached keys served + background task |
| CircuitBreaker + JWKSManager | Integration | Simulate IDP outage, verify graceful degradation |
| Config validation | Unit | Invalid ranges, missing fields, validation errors |

---

## Components and Interfaces

### Component: TokenExchangeAdapter (Protocol)

| Method | Signature | Description |
|--------|-----------|-------------|
| `exchange` | `async (subject_token: str, config: AuthConfig, endpoints: OIDCEndpoints, *, audience: str \| None, scope: str \| None) -> TokenSet` | Exchange a subject token for a downstream TokenSet |
| `provider_id` | `@property -> str` | Unique identifier for this adapter |

**Implementations:** `RFC8693Adapter`, `GoogleSTSAdapter`, `EntraOBOAdapter`

### Component: AdapterRegistry

| Method | Signature | Description |
|--------|-----------|-------------|
| `register` | `(adapter: TokenExchangeAdapter) -> None` | Register a new adapter |
| `get_adapter` | `(provider_id: str \| None) -> TokenExchangeAdapter` | Look up adapter by ID, default to RFC8693 |

### Component: CircuitBreaker

| Method | Signature | Description |
|--------|-----------|-------------|
| `execute` | `async (coro_factory: Callable[[], Awaitable[T]]) -> T` | Execute an async call through the breaker |
| `state` | `@property -> CircuitState` | Current computed state |
| `reset` | `() -> None` | Manual reset to CLOSED (for testing) |

### Component: ResilientHttpClient

| Method | Signature | Description |
|--------|-----------|-------------|
| `get` | `async (url: str, *, timeout: float, headers: dict \| None) -> httpx.Response` | GET with circuit breaker |
| `post_form` | `async (url: str, data: dict, *, timeout: float) -> httpx.Response` | POST form data with circuit breaker |
| `post_token` | `async (url: str, body: dict, timeout: float) -> TokenSet` | POST + parse token response |

### Component: JWKSManager

| Method | Signature | Description |
|--------|-----------|-------------|
| `verify_token` | `async (token: str) -> dict[str, Any]` | Verify JWT signature and claims |
| `get_signing_key` | `async (token: str) -> Any` | Get signing key for JWT (with caching/coalescing) |
| `invalidate_cache` | `() -> None` | Force cache invalidation (e.g. on key rotation) |

---

## Data Models

### CircuitBreakerConfig (Pydantic)

```python
class CircuitBreakerConfig(BaseModel):
    failure_threshold: int = Field(default=5, ge=1, le=100)
    cooldown_seconds: int = Field(default=30, ge=1, le=300)
```

### CircuitState (Enum)

```python
class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
```

### AuthConfig additions

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `token_exchange_provider` | `str \| None` | `None` | Provider adapter ID (`"google"`, `"entra"`, or `None` for RFC 8693) |
| `circuit_breaker` | `CircuitBreakerConfig \| None` | `None` | Circuit breaker thresholds |
| `jwks_cache_ttl` | `int` | `600` | JWKS cache TTL in seconds (60–86400) |

### JWKSManager internal state

| Field | Type | Description |
|-------|------|-------------|
| `_cached_keys` | `PyJWKSet \| None` | Currently cached key set |
| `_last_successful_fetch` | `float` | Monotonic time of last successful JWKS fetch |
| `_inflight_future` | `asyncio.Future \| None` | Shared result for coalesced requests |
| `_bg_task` | `asyncio.Task \| None` | Background refresh task reference |

---

## Error Handling

### Circuit Breaker Errors

- **Circuit Open**: `ProviderError("Circuit breaker is open — IDP calls are temporarily disabled. Will retry after {cooldown}s cooldown.")`
- **Half-Open Probe Rejected**: `ProviderError("Circuit breaker is half-open — probe in progress, rejecting.")`

### JWKS Manager Errors

- **Keys Too Stale**: `ProviderError("JWKS keys are too stale ({age}s > {max_staleness}s) — cannot verify tokens.")`
- **Cold Start Failure**: `ProviderError("JWKS endpoint unreachable after {retries} retries.")`
- **Non-retryable Error (4xx)**: `ProviderError("JWKS fetch failed with status {code}: {body}")`

### Adapter Errors

- **Unknown Provider**: `ConfigurationError("Unknown token exchange provider: '{id}'. Available: [...]")`
- **Missing Secret (Entra)**: `AuthenticationError("Entra on-behalf-of flow requires client_secret")`
- **Token Endpoint Error**: `ProviderError("Token endpoint error: {error_description}")`
- **Missing access_token**: `ProviderError("Token response missing 'access_token'")`

---

## Correctness Properties

### Property 1: Circuit Breaker Monotonicity

The failure counter only increases on consecutive failures and resets to zero on any success. It never decreases without a success event.

**Validates: Requirements 4.3, 4.12**

### Property 2: Coalescing Safety

At most one outbound JWKS HTTP request is in-flight per issuer at any time. The `_inflight_future` is created atomically under a lock and cleared only after the fetch task completes.

**Validates: Requirements 6.1, 6.4**

### Property 3: Stale-While-Revalidate Consistency

Callers always receive a consistent key set — either the current cache (if fresh or stale-but-within-staleness) or the result of a blocking fetch. The cache is replaced atomically (single assignment).

**Validates: Requirements 8.1, 8.2**

### Property 4: Adapter Idempotency

Token exchange adapters are stateless — the same inputs always produce the same HTTP request body. No adapter maintains mutable state between calls.

**Validates: Requirements 1.1, 2.3, 3.2**

### Property 5: Circuit Breaker Fairness

In HALF_OPEN state, exactly one probe request is allowed. All other concurrent requests receive a fast-fail error. The probe flag is cleared atomically under the lock regardless of outcome.

**Validates: Requirements 4.6, 4.7, 4.8**

### Property 6: Background Refresh Isolation

A failed background refresh does not affect callers currently using cached keys. Exceptions are caught and logged, never propagated to tool handlers.

**Validates: Requirements 8.3, 8.6**
