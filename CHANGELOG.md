# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Token exchange adapter system: built-in adapters for RFC 8693 (default), Google STS, and Microsoft Entra OBO
- `AdapterRegistry` for registering custom token exchange adapters
- Resilient JWKS key management with request coalescing, stale-while-revalidate, and exponential backoff
- Circuit breaker for all IDP HTTP calls (configurable failure threshold and cooldown)
- `ResilientHttpClient` routing all outbound IDP calls through circuit breaker
- `token_exchange_provider` config field for selecting token exchange adapter
- `circuit_breaker` config section (failure_threshold, cooldown_seconds)
- `jwks_cache_ttl` config field for JWKS key cache TTL

### Changed
- Improved `ceramic doctor` diagnostics with actionable fix suggestions
- Token exchange now routes through adapter system instead of direct HTTP calls

---

## [0.1.0] — 2026-07-14

### Added
- **Core framework** — `CeramicFastMCP` drop-in replacement wrapping FastMCP via composition
- **Authentication middleware** — OAuth2/OIDC with PKCE (authorization_code) and client_credentials grants
- **Authorization middleware** — Role and group-based access control with `@require_roles` / `@require_groups` decorators
- **Observability middleware** — OpenTelemetry traces, Prometheus metrics, structured JSON logging
- **Session middleware** — Durable in-memory sessions with configurable TTL
- **Identity propagation** — `identity()` function returning `IdentityContext` via contextvars
- **Configuration system** — Single `ceramic.yaml` with Pydantic validation, env var overrides, hot reload
- **Token storage** — Platform-native backends (macOS Keychain, Windows Credential Manager, encrypted file)
- **CLI** — `ceramic run`, `ceramic login`, `ceramic logout`, `ceramic whoami`, `ceramic doctor`, `ceramic config validate`
- **Testing utilities** — `CeramicTestClient` and `MockIdentityProvider` for auth-free testing
- **Security** — `LogRedactor` (sensitive field masking), `TLSEnforcer` (HTTPS in production)
- **Plugin system** — Custom middleware via `app.use()` or `plugins:` config section
- **Examples** — Basic server, auth server, migration example, full Zitadel E2E demo
- **CI/CD** — GitHub Actions for testing (3.11/3.12/3.13), release automation, PyPI publishing

### Security
- PKCE enforced for all interactive OAuth flows
- TLS 1.2+ required for IDP communication in production
- Tokens, secrets, credentials automatically redacted from logs and traces
- No sensitive values stored in plaintext (keyring or encrypted file backends)

[Unreleased]: https://github.com/enzomar/ceramic-fwk/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/enzomar/ceramic-fwk/releases/tag/v0.1.0
