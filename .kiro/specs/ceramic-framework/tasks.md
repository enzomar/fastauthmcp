# Implementation Plan: Ceramic Framework

## Overview

This plan implements the Ceramic framework as a Python package that wraps FastMCP via composition, providing enterprise capabilities (authentication, authorization, observability, session management) activated by a single import change and configured via `ceramic.yaml`. The implementation proceeds bottom-up: core infrastructure first, then layered enterprise features, and finally CLI and testing utilities.

## Tasks

- [x] 1. Project structure and core interfaces
  - [x] 1.1 Set up project structure and package scaffolding
    - Create `ceramic/` package with `__init__.py` exposing `FastMCP`, `require_role`, `require_group`, `identity`
    - Create `pyproject.toml` with dependencies: `fastmcp`, `pydantic`, `pyyaml`, `click`, `opentelemetry-api`, `opentelemetry-sdk`, `prometheus-client`, `hypothesis`, `pytest`, `pytest-asyncio`
    - Create directory structure: `ceramic/`, `ceramic/middleware/`, `ceramic/auth/`, `ceramic/cli/`, `ceramic/testing/`, `tests/`, `tests/properties/`, `tests/unit/`, `tests/integration/`
    - _Requirements: 1.1, 1.2_

  - [x] 1.2 Define exception hierarchy and data models
    - Implement `ceramic/exceptions.py` with `CeramicError`, `ConfigurationError`, `AuthenticationError`, `AuthorizationError`, `ProviderError`, `SessionError`, `PluginError`
    - Implement `ceramic/models.py` with `TokenSet`, `Session`, `OIDCEndpoints`, `LogEntry` dataclasses
    - Implement `ceramic/identity.py` with the frozen `IdentityContext` dataclass and module-level `identity()` function using `contextvars`
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6_

  - [x] 1.3 Define middleware protocol and RequestContext
    - Implement `ceramic/middleware/pipeline.py` with `RequestContext` class, `MiddlewareCallable` protocol, `MiddlewarePlugin` protocol
    - Implement middleware pipeline executor that chains middleware in registration order and executes after-hooks in reverse order
    - Support short-circuit (returning response without calling `next`) and exception routing to `on_exception` hooks
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.6_

  - [x]* 1.4 Write property tests for middleware pipeline
    - **Property 17: Middleware Execution Order** — verify before-hooks execute in registration order, after-hooks in reverse order
    - **Property 18: Middleware Short-Circuit** — verify short-circuit prevents subsequent middleware and handler from executing
    - **Property 19: Exception Routing** — verify unhandled exceptions route through `on_exception` chain and never propagate to FastMCP
    - **Validates: Requirements 8.2, 8.3, 8.4**

- [x] 2. Configuration system
  - [x] 2.1 Implement Pydantic configuration models
    - Create `ceramic/config.py` with `AuthConfig`, `AuthorizationConfig`, `AuthorizationPolicy`, `ObservabilityConfig`, `SessionsConfig`, `PluginRef`, `HotReloadConfig`, `CeramicConfig` Pydantic models
    - Include all field constraints (e.g., port ranges, TTL bounds, valid literals) as defined in the design
    - _Requirements: 2.3, 2.4, 2.5, 2.6_

  - [x] 2.2 Implement ConfigLoader with YAML parsing and env overrides
    - Create `ceramic/config_loader.py` with `ConfigLoader` class
    - Implement `load()` method: resolve path from `CERAMIC_CONFIG` env var or CWD `ceramic.yaml`
    - Implement `apply_env_overrides()`: scan `CERAMIC_` prefixed env vars, apply only to scalar values
    - Reject unknown top-level keys and invalid YAML with `ConfigurationError` and stderr output
    - _Requirements: 2.1, 2.2, 2.7, 2.8, 2.9_

  - [x]* 2.3 Write property tests for configuration
    - **Property 2: Configuration Source Resolution** — env var path takes precedence over CWD file
    - **Property 4: Environment Variable Override Semantics** — scalars overridden, non-scalars preserved
    - **Property 5: Invalid Configuration Rejection** — unknown keys or invalid YAML always raise errors
    - **Validates: Requirements 2.1, 2.7, 2.8, 2.9**

  - [x]* 2.4 Write unit tests for ConfigLoader
    - Test missing file with `CERAMIC_CONFIG` set produces stderr error
    - Test valid YAML loads all sections correctly
    - Test env var override of nested scalar values
    - Test rejection of non-scalar env var override attempts
    - _Requirements: 2.1, 2.2, 2.7, 2.8, 2.9_

- [x] 3. Checkpoint - Core infrastructure
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. CeramicFastMCP facade and API compatibility
  - [x] 4.1 Implement CeramicFastMCP class with delegation
    - Create `ceramic/server.py` with `CeramicFastMCP` class
    - Compose an internal `fastmcp.FastMCP` instance, forwarding `__init__` kwargs
    - Delegate `tool()`, `prompt()`, `resource()`, `run()` decorators/methods to the internal instance
    - Load `CeramicConfig` on init; if no config found, operate in passthrough mode (no middleware)
    - Raise `ConfigurationError` at startup for incompatible definitions
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 4.2 Implement plugin registration and middleware-attachment migration style
    - Implement `app.use(plugin)` method to register `MiddlewarePlugin` instances
    - Implement `CeramicFastMCP.enable_ceramic(app, config)` static method for wrapping existing FastMCP instances
    - If config path is invalid or YAML is bad, raise `ConfigurationError` and leave FastMCP unmodified
    - _Requirements: 8.5, 9.1, 9.2, 9.3, 9.4_

  - [x] 4.3 Wire middleware pipeline into request lifecycle
    - Construct middleware pipeline based on loaded config sections (Observability → Session → AuthN → AuthZ → Plugins → FastMCP delegation)
    - Register built-in middleware in fixed order per design
    - Activate `Property 3: Configuration Section Activates Middleware` behavior
    - _Requirements: 2.3, 2.4, 2.5, 2.6, 8.1, 8.2_

  - [x]* 4.4 Write property tests for API compatibility
    - **Property 1: API Compatibility** — any definition registered on FastMCP succeeds identically on CeramicFastMCP with no config, producing identical responses
    - **Property 3: Configuration Section Activates Middleware** — presence/absence of config sections controls middleware pipeline composition
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.3, 2.4, 2.5, 2.6**

- [x] 5. Security utilities
  - [x] 5.1 Implement LogRedactor
    - Create `ceramic/security.py` with `LogRedactor` class
    - Scan field names for "token", "secret", "credential", "password", "authorization" (case-insensitive)
    - Replace matching values with `[REDACTED]`
    - _Requirements: 11.1, 11.6_

  - [x] 5.2 Implement TLSEnforcer
    - Add `TLSEnforcer` to `ceramic/security.py`
    - `validate_url()` rejects non-HTTPS URLs with `ConfigurationError`
    - `get_ssl_context()` returns an `ssl.SSLContext` enforcing TLS 1.2 minimum
    - _Requirements: 11.4, 11.7_

  - [x]* 5.3 Write property tests for security
    - **Property 12: Log Redaction of Sensitive Fields** — any log record with sensitive field names has values replaced with `[REDACTED]`
    - **Property 13: Non-HTTPS Endpoint Rejection** — any non-HTTPS issuer or token endpoint URL is rejected at config validation
    - **Validates: Requirements 6.7, 11.1, 11.4, 11.6, 11.7**

- [x] 6. Authentication and token management
  - [x] 6.1 Implement OAuthService with PKCE and OIDC discovery
    - Create `ceramic/auth/oauth.py` with `OAuthService` class
    - Implement `discover_endpoints()`: fetch `.well-known/openid-configuration` from issuer URL
    - Implement `initiate_flow()`: generate PKCE code_verifier/challenge, open browser, start local callback server on random port with 120s timeout
    - Implement `exchange_code()`: POST to token endpoint with code and verifier (30s timeout)
    - Implement `refresh_token()`: POST to token endpoint with refresh_token grant
    - Enforce PKCE on all authorization code flows
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.7, 3.9, 11.2_

  - [x] 6.2 Implement platform-native TokenStorage
    - Create `ceramic/auth/token_storage.py` with `TokenStorage` protocol
    - Implement `KeychainTokenStorage` (macOS via `keyring` or Security framework)
    - Implement `EncryptedFileStorage` (Linux, AES-256 encrypted, file mode 600)
    - Implement `CredentialManagerStorage` (Windows via `keyring`)
    - Auto-detect platform and instantiate appropriate backend
    - _Requirements: 3.4, 11.5_

  - [x] 6.3 Implement AuthenticationMiddleware
    - Create `ceramic/middleware/authentication.py`
    - On `before_request`: check for valid token in session/storage; if expired, attempt refresh; if no token, initiate OAuth flow
    - On successful auth: populate `RequestContext.identity` with `IdentityContext`
    - On refresh failure: invalidate session, discard tokens, return auth error
    - Preserve stored tokens on transient provider failures
    - _Requirements: 3.1, 3.5, 3.6, 3.8, 4.1, 4.4_

  - [x]* 6.4 Write property test for token auto-refresh
    - **Property 23: Token Auto-Refresh** — when access token is expired and refresh token available, middleware attempts refresh before processing
    - **Validates: Requirements 3.5**

  - [x]* 6.5 Write unit tests for OAuthService
    - Test PKCE code_verifier generation (43-128 chars, URL-safe)
    - Test code exchange with mock HTTP responses
    - Test refresh token rotation handling (new token stored, old invalidated)
    - Test timeout and error conditions
    - _Requirements: 3.2, 3.3, 3.6, 3.8, 3.9, 11.3_

- [x] 7. Checkpoint - Authentication complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Identity context and authorization
  - [x] 8.1 Implement Identity_Context propagation via contextvars
    - Wire `IdentityContext` creation from JWT claims in `AuthenticationMiddleware`
    - Implement `ceramic.identity()` module-level function using `contextvars.ContextVar`
    - Raise explicit error when `ceramic.identity()` called outside active request context
    - Return `None` for `ctx.identity` when auth is disabled
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 8.2 Implement authorization decorators and AuthorizationMiddleware
    - Create `ceramic/authorization.py` with `require_role()` and `require_group()` decorators
    - Create `ceramic/middleware/authorization.py` with `AuthorizationMiddleware`
    - Evaluate decorator policies AND YAML-defined policies (AND semantics)
    - Reject with authorization error before tool body executes if any policy fails
    - Reject with auth-required error if Identity_Context is None on protected tool
    - Support glob patterns for YAML policy tool matching
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x]* 8.3 Write property tests for identity and authorization
    - **Property 6: IdentityContext Correctness** — email/subject from claims, immutability enforced
    - **Property 7: Dual Identity Access Equivalence** — `ctx.identity` and `ceramic.identity()` return same object
    - **Property 8: Claim-Based Authorization** — role/group checks are set membership tests
    - **Property 9: Authorization AND Semantics** — all decorators/policies must pass
    - **Property 10: Authorization Rejection Prevents Tool Execution** — tool body never invoked on rejection
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6**

- [x] 9. Observability
  - [x] 9.1 Implement TelemetryService and ObservabilityMiddleware
    - Create `ceramic/observability.py` with `TelemetryService` class
    - Implement `start_span()`, `end_span()`, `emit_log()`, `record_metric()` methods
    - Create `ceramic/middleware/observability.py` with `ObservabilityMiddleware`
    - On `before_tool`: assign UUID request_id, start OTel span with tool_name
    - On `after_tool`: record duration, outcome; emit structured JSON log entry; record Prometheus metric
    - Never include sensitive values in spans or logs (use `LogRedactor`)
    - _Requirements: 6.1, 6.2, 6.3, 6.7_

  - [x] 9.2 Implement Prometheus metrics exporter
    - Create `ceramic/metrics.py` with `MetricsExporter` class
    - Expose request count, error count, and latency histogram per tool at configurable path/port
    - Return an ASGI app that serves the metrics endpoint
    - _Requirements: 6.4_

  - [x] 9.3 Implement conditional observability loading
    - If observability is disabled, do not import or initialize OpenTelemetry or Prometheus libraries
    - If telemetry export fails, log warning and continue request processing
    - _Requirements: 6.5, 6.6_

  - [x]* 9.4 Write property tests for observability
    - **Property 11: Observability Completeness** — every tool invocation produces span + log entry + metric with required fields
    - **Property 12: Log Redaction of Sensitive Fields** — no sensitive values leak into logs or spans
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.7, 11.1**

- [x] 10. Session management
  - [x] 10.1 Implement SessionStore and InMemorySessionStore
    - Create `ceramic/sessions.py` with `SessionStore` protocol and `InMemorySessionStore`
    - Implement `create()`, `get()`, `update()`, `invalidate()` methods
    - Enforce TTL expiration check on `get()`
    - _Requirements: 7.1, 7.5, 7.6_

  - [x] 10.2 Implement SessionMiddleware
    - Create `ceramic/middleware/session.py` with `SessionMiddleware`
    - On `before_request`: check for session ID in request, restore IdentityContext if valid
    - On successful auth: create session record with subject + token set
    - On token refresh: update session with new token set
    - Invalidate session when refresh token is expired/revoked or TTL exceeded
    - Treat invalid/unrecognized session ID as unauthenticated
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.6, 7.7_

  - [x]* 10.3 Write property tests for sessions
    - **Property 14: Session Creation on Authentication** — successful auth creates retrievable session
    - **Property 15: Session Restoration Without Re-Authentication** — valid session restores identity without OAuth flow
    - **Property 16: Session TTL Enforcement** — elapsed TTL invalidates session regardless of token validity
    - **Validates: Requirements 7.1, 7.2, 7.5, 7.6**

- [x] 11. Checkpoint - Enterprise features complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Configuration hot reload
  - [-] 12.1 Implement hot-reload watcher
    - Add `watch()` method to `ConfigLoader` that monitors file modification time at configured interval
    - On change: re-parse YAML, validate; if valid, atomically swap observability and authorization config
    - If invalid: retain previous config, log warning
    - Block reload of `auth` and `sessions` sections
    - Emit INFO log on successful reload
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [ ]* 12.2 Write property tests for hot reload
    - **Property 20: Atomic Configuration Hot-Reload** — after reload, active config fully matches new file (no partial state)
    - **Property 21: Invalid Reload Retains Previous Configuration** — validation failure preserves old config
    - **Property 22: Non-Reloadable Sections Blocked** — auth/sessions changes not applied on reload
    - **Validates: Requirements 12.2, 12.3, 12.4**

- [ ] 13. CLI implementation
  - [ ] 13.1 Implement CLI commands with Click
    - Create `ceramic/cli/__init__.py` with Click group
    - Implement `ceramic run` — load config, start server, print ready message with host:port
    - Implement `ceramic login` — run OAuth flow, store tokens, print email
    - Implement `ceramic logout` — clear tokens, invalidate session
    - Implement `ceramic whoami` — display email, subject, roles; exit non-zero if no session
    - Implement `ceramic doctor` — check IDP connectivity, token freshness, config validity
    - Implement `ceramic config validate` — parse and report errors/warnings
    - All commands: exit 0 on success, non-zero + stderr message on failure
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10_

  - [ ]* 13.2 Write unit tests for CLI commands
    - Test `run` exits with error on missing/invalid config
    - Test `login` stores tokens and outputs email
    - Test `logout` clears tokens
    - Test `whoami` output format and non-zero exit when unauthenticated
    - Test `doctor` reports each check status
    - Test `config validate` reports errors
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10_

- [ ] 14. Testing utilities
  - [ ] 14.1 Implement CeramicTestClient and MockIdentityProvider
    - Create `ceramic/testing/__init__.py` with `CeramicTestClient` class
    - Accept `email`, `subject`, `claims`, `roles`, `groups` as constructor parameters
    - Bypass OAuth flows, inject identity directly into middleware pipeline
    - Trigger all authorization middleware as if real request
    - Implement `assert_authorized()` and `assert_unauthorized()` helpers
    - Create `MockIdentityProvider` that generates structurally valid JWTs without network calls
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

  - [ ]* 14.2 Write property tests for testing utilities
    - **Property 24: Test Client Fidelity** — test client identity matches configured params, authz enforced identically to production
    - **Property 25: Mock JWT Structural Validity** — issued tokens are decodable JWTs with correct header and payload
    - **Validates: Requirements 13.1, 13.2, 13.3, 13.5**

- [ ] 15. Integration wiring and package exports
  - [ ] 15.1 Wire all components in `ceramic/__init__.py` and finalize public API
    - Export `FastMCP` (alias for `CeramicFastMCP`), `require_role`, `require_group`, `identity`, `CeramicTestClient`
    - Ensure `from ceramic import FastMCP` works as drop-in replacement
    - Register CLI entry point in `pyproject.toml` (`[project.scripts] ceramic = "ceramic.cli:cli"`)
    - _Requirements: 1.1, 1.2, 9.1_

  - [ ]* 15.2 Write integration tests
    - Test full import-replacement migration: register tool on `ceramic.FastMCP`, call it, verify response
    - Test middleware-attachment: `enable_ceramic()` on existing FastMCP instance
    - Test end-to-end auth + authz flow with `CeramicTestClient`
    - Test observability metrics endpoint returns Prometheus format
    - Test hot-reload updates active config
    - _Requirements: 1.2, 9.1, 9.2, 9.3, 6.4, 12.2_

- [ ] 16. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The framework uses Python 3.11+ features (`typing` unions with `|`, `contextvars`, frozen dataclasses)
- All middleware is async (`async def __call__`) to support async FastMCP tools
- The project uses `pytest` + `hypothesis` for testing, `click` for CLI, `pydantic` for config validation

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "2.1"] },
    { "id": 3, "tasks": ["2.2"] },
    { "id": 4, "tasks": ["2.3", "2.4", "5.1", "5.2"] },
    { "id": 5, "tasks": ["4.1", "5.3"] },
    { "id": 6, "tasks": ["4.2", "4.3", "6.1", "6.2"] },
    { "id": 7, "tasks": ["4.4", "6.3"] },
    { "id": 8, "tasks": ["6.4", "6.5", "8.1"] },
    { "id": 9, "tasks": ["8.2"] },
    { "id": 10, "tasks": ["8.3", "9.1"] },
    { "id": 11, "tasks": ["9.2", "9.3", "10.1"] },
    { "id": 12, "tasks": ["9.4", "10.2"] },
    { "id": 13, "tasks": ["10.3", "12.1"] },
    { "id": 14, "tasks": ["12.2", "13.1"] },
    { "id": 15, "tasks": ["13.2", "14.1"] },
    { "id": 16, "tasks": ["14.2", "15.1"] },
    { "id": 17, "tasks": ["15.2"] }
  ]
}
```
