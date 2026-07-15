# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Per-tool authorization decorators** — `@require_roles()`, `@require_groups()`, `@require_scopes()` with automatic policy enforcement before tool execution
- **Authorization middleware** — Evaluates decorator-based and YAML-defined policies (glob patterns on tool names, AND semantics)
- **Rate limiting** — Token bucket rate limiter with per-tool and per-user limits, configurable RPM and burst
- **Audit logging** — Structured, immutable records of auth, authz, tool invocation, and token exchange events
- **Downstream credential mapping** — Route tools to different downstream APIs with scope-aware token caching
- **Secret management integration** — `${SECRET:backend:key}` syntax for resolving secrets from env, AWS, Vault
- **Request-scoped context propagation** — `set_context()` / `get_context()` for passing correlation IDs, tenant context through the pipeline
- **Multi-IdP support** — Route authentication to different providers based on issuer claim, tool mapping, or request header
- **Graceful degradation** — Continue serving during IdP outages (trust stale sessions, allow public tools)
- **Schema export** — Generate JSON/Markdown API documentation including auth requirements and rate limits
- Token exchange adapter system: built-in adapters for RFC 8693 (default), Google STS, and Microsoft Entra OBO
- `AdapterRegistry` for registering custom token exchange adapters
- Resilient JWKS key management with request coalescing, stale-while-revalidate, and exponential backoff
- Circuit breaker for all IDP HTTP calls (configurable failure threshold and cooldown)
- `ResilientHttpClient` routing all outbound IDP calls through circuit breaker
- `token_exchange_provider` config field for selecting token exchange adapter
- `circuit_breaker` config section (failure_threshold, cooldown_seconds)
- `jwks_cache_ttl` config field for JWKS key cache TTL
- `AuthorizationError` exception for policy evaluation failures

### Changed
- Improved `fastauthmcp doctor` diagnostics with actionable fix suggestions
- Token exchange now routes through adapter system instead of direct HTTP calls
- Middleware pipeline now includes authorization after authentication when auth is configured
- Public API expanded with `require_roles`, `require_groups`, `require_scopes`, `get_context`, `set_context`, `request_context`

---

## [0.1.0] — 2026-07-14

### Added
- **Core framework** — `FastAuthMCP` drop-in replacement wrapping FastMCP via composition
- **Authentication middleware** — OAuth2/OIDC with PKCE (authorization_code) and client_credentials grants
- **Authorization middleware** — Role and group-based access control with `@require_roles` / `@require_groups` decorators
- **Observability middleware** — OpenTelemetry traces, Prometheus metrics, structured JSON logging
- **Session middleware** — Durable in-memory sessions with configurable TTL
- **Identity propagation** — `identity()` function returning `IdentityContext` via contextvars
- **Configuration system** — Single `fastauthmcp.yaml` with Pydantic validation, env var overrides, hot reload
- **Token storage** — Platform-native backends (macOS Keychain, Windows Credential Manager, encrypted file)
- **CLI** — `fastauthmcp run`, `fastauthmcp login`, `fastauthmcp logout`, `fastauthmcp whoami`, `fastauthmcp doctor`, `fastauthmcp config validate`
- **Testing utilities** — `FastAuthMCPTestClient` and `MockIdentityProvider` for auth-free testing
- **Security** — `LogRedactor` (sensitive field masking), `TLSEnforcer` (HTTPS in production)
- **Plugin system** — Custom middleware via `app.use()` or `plugins:` config section
- **Examples** — Basic server, auth server, migration example, full Zitadel E2E demo
- **CI/CD** — GitHub Actions for testing (3.11/3.12/3.13), release automation, PyPI publishing

### Security
- PKCE enforced for all interactive OAuth flows
- TLS 1.2+ required for IDP communication in production
- Tokens, secrets, credentials automatically redacted from logs and traces
- No sensitive values stored in plaintext (keyring or encrypted file backends)

[Unreleased]: https://github.com/enzomar/fastauthmcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/enzomar/fastauthmcp/releases/tag/v0.1.0
