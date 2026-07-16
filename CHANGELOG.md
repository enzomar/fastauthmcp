# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Security & Interoperability Lab (34 scenarios, 5 providers)
- Per-platform integration guides (Claude Desktop, Gemini, Cursor, etc.)
- Per-IDP guides (Zitadel, Keycloak, Auth0, Azure Entra ID, Okta, Google)
- Makefile with build, test, release, demo, and lab helpers
- `extra="forbid"` on all config models — typos now raise errors
- Cross-field validation: `client_credentials` requires `client_secret`, `token_exchange` requires `upstream_token_header`
- Token exchange adapter system wired into `OAuthService.token_exchange()` — `google` and `entra` adapters now functional
- `tenacity` for JWKS retry logic (replaces custom backoff loop)
- `authlib` as a dependency (preparing for deeper OIDC integration)

### Fixed
- OAuth callback server `shutdown()` deadlock when browser sends `/favicon.ico`
- Token exchange POST hanging under anyio event loop (now uses sync httpx in thread)
- `callback_server.wait_for_callback()` no longer calls `shutdown()` internally
- Duplicate `_parse_token_response()` in `resilience.py` removed (now imports from `oauth.py`)

### Changed
- Demo default transport changed to stdio (most reliable)
- `_post_token_request` and `discover_endpoints` use sync httpx in threads to avoid anyio conflicts
- `zeep`, `opentelemetry-*`, `prometheus-client` moved to optional extras (`[soap]`, `[observability]`)
- Core install is now lighter: only `authlib`, `httpx`, `pyjwt`, `tenacity`, `pydantic`, `click`, `certifi`

## [0.1.3] — 2025-07-16

### Added
- Initial public release
- OAuth2/OIDC authentication (Authorization Code + PKCE, Client Credentials, Token Exchange)
- Token exchange adapters (RFC 8693, Google STS, Entra OBO)
- Middleware pipeline (Observability → Session → Authentication → Authorization)
- Per-tool authorization decorators (`@require_roles`, `@require_groups`, `@require_scopes`)
- Identity propagation via `identity()` and `access_token()`
- Downstream API clients (HTTP + SOAP with automatic token injection)
- Circuit breaker and resilient JWKS management
- OpenTelemetry tracing and Prometheus metrics
- Session management
- CLI (`fastauthmcp login/logout/whoami/doctor/run`)
- `FastAuthMCPTestClient` and `MockIdentityProvider` for testing
- Platform-native token storage (macOS Keychain, Windows Credential Manager, encrypted file)

[Unreleased]: https://github.com/enzomar/fastauthmcp/compare/v0.1.3...HEAD
[0.1.3]: https://github.com/enzomar/fastauthmcp/releases/tag/v0.1.3
