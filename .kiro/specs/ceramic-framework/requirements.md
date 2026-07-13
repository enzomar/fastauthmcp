# Requirements Document

## Introduction

Ceramic Framework (ceramic-fwk) is a production-grade open-source Python framework that sits on top of FastMCP, providing enterprise capabilities (authentication, authorization, observability, session management) while remaining 100% compatible with FastMCP's public API. A developer migrates an existing FastMCP server by changing a single import statement and optionally pointing to a YAML configuration file—no modifications to existing MCP tools, decorators, prompts, resources, or transports are required.

## Glossary

- **Ceramic**: The Python framework described in this document, providing enterprise features on top of FastMCP.
- **FastMCP**: The upstream open-source Python framework implementing the Model Context Protocol (MCP).
- **MCP_Tool**: A function decorated with `@mcp.tool()` that implements a callable capability in the MCP protocol.
- **Identity_Context**: A structured object containing the authenticated user's email, subject identifier, and claims, made available to MCP tools without manual JWT parsing.
- **Middleware**: A composable processing layer that intercepts requests before or after they reach the underlying FastMCP handler.
- **Plugin**: A self-contained extension registered with Ceramic via middleware hooks to add cross-cutting behavior.
- **ceramic.yaml**: The YAML configuration file that controls Ceramic's enterprise features.
- **PKCE**: Proof Key for Code Exchange—an OAuth2 extension that prevents authorization code interception attacks.
- **OIDC**: OpenID Connect—an identity layer on top of OAuth2 that provides user identity claims.
- **OpenTelemetry**: An open-source observability framework for traces, metrics, and logs.
- **CLI**: The `ceramic` command-line interface used for running servers, managing authentication, and validating configuration.
- **Hot_Reload**: The ability to apply configuration changes at runtime without restarting the server process.
- **Token_Storage**: A secure, platform-appropriate store for OAuth2 access and refresh tokens.
- **Request_Context**: The per-request state carried through the middleware pipeline, including identity, session, and trace information.

## Requirements

### Requirement 1: FastMCP API Compatibility

**User Story:** As a developer with an existing FastMCP server, I want to migrate to Ceramic by changing only the import statement, so that I gain enterprise features without rewriting my tools.

#### Acceptance Criteria

1. THE Ceramic SHALL expose the same public API surface as the installed version of FastMCP, including the `FastMCP` class, tool decorator, prompt decorator, resource decorator, and all transport methods, such that all public callable signatures remain signature-compatible.
2. WHEN a developer replaces `from fastmcp import FastMCP` with `from ceramic import FastMCP`, THE Ceramic SHALL load and execute all existing MCP tool definitions, prompts, resources, and transports without requiring any code changes beyond the import statement.
3. THE Ceramic SHALL delegate all MCP protocol handling to the composed FastMCP instance, such that MCP protocol requests produce responses identical in structure and content to those produced by a standalone FastMCP server.
4. IF no ceramic.yaml configuration file is provided, THEN THE Ceramic SHALL produce identical responses to identical MCP protocol requests as a standalone FastMCP server with default settings, with no enterprise features active.
5. IF a tool, prompt, or resource definition is incompatible with the Ceramic runtime, THEN THE Ceramic SHALL raise an error at server startup indicating which definition is incompatible and the reason for incompatibility.

### Requirement 2: YAML Configuration

**User Story:** As an operator, I want to configure all enterprise features through a single YAML file, so that I can enable capabilities without writing code.

#### Acceptance Criteria

1. THE Ceramic SHALL read enterprise feature configuration from a file named ceramic.yaml located in the current working directory or at a path specified by the `CERAMIC_CONFIG` environment variable, with the environment variable taking precedence over the default location.
2. IF the `CERAMIC_CONFIG` environment variable is set but the specified file does not exist, THEN THE Ceramic SHALL reject the configuration at startup and report an error message to stderr identifying the missing file path.
3. WHEN ceramic.yaml contains an `auth` section, THE Ceramic SHALL enable authentication middleware with the specified provider settings.
4. WHEN ceramic.yaml contains an `observability` section, THE Ceramic SHALL enable metrics, tracing, and structured logging as specified.
5. WHEN ceramic.yaml contains an `authorization` section, THE Ceramic SHALL enable policy-based access control.
6. WHEN ceramic.yaml contains a `sessions` section, THE Ceramic SHALL enable session management.
7. THE Ceramic SHALL support configuration override via environment variables using the prefix `CERAMIC_` followed by the uppercase dot-path of the YAML key (e.g., `CERAMIC_AUTH_PROVIDER` overrides `auth.provider`), where environment variable values take precedence over values defined in ceramic.yaml.
8. IF ceramic.yaml contains invalid YAML syntax or unknown top-level keys, THEN THE Ceramic SHALL reject the configuration at startup, exit with a non-zero exit code, and report an error message to stderr identifying the invalid entry.
9. THE Ceramic SHALL apply environment variable overrides only to scalar (string, number, boolean) configuration values, not to object or list structures.

### Requirement 3: OAuth2 Authentication

**User Story:** As a developer, I want Ceramic to handle the full OAuth2/OIDC login flow automatically, so that my tools receive authenticated requests without manual token management.

#### Acceptance Criteria

1. WHILE authentication is enabled, WHEN a request arrives without a token or with an expired or malformed token, THE Ceramic SHALL initiate the OAuth2 Authorization Code flow with PKCE.
2. WHEN the OAuth2 flow is initiated from a CLI context, THE Ceramic SHALL open the system browser to the authorization URL and start a local callback listener on a random available port, waiting no longer than 120 seconds for the identity provider callback before timing out.
3. WHEN the identity provider returns an authorization code to the callback, THE Ceramic SHALL exchange the code for access and refresh tokens within a 30-second HTTP request timeout.
4. THE Ceramic SHALL store tokens in the platform-appropriate Token_Storage (keychain on macOS, credential manager on Windows, encrypted file on Linux).
5. WHEN a stored access token has expired and a refresh token is available, THE Ceramic SHALL automatically refresh the access token before processing the request.
6. IF token refresh fails, THEN THE Ceramic SHALL invalidate the session, discard the stored tokens, and return an authentication error indicating that re-authentication is required.
7. WHEN the `issuer` URL is provided in ceramic.yaml, THE Ceramic SHALL fetch provider endpoints via the `.well-known/openid-configuration` discovery document.
8. IF the identity provider is unreachable or returns an error during token exchange or token refresh, THEN THE Ceramic SHALL return an authentication error indicating the provider failure and preserve any previously stored tokens unchanged.
9. IF the local callback listener fails to start or the browser callback times out, THEN THE Ceramic SHALL abort the OAuth2 flow and return an authentication error indicating the failure reason.

### Requirement 4: Identity Context Propagation

**User Story:** As a tool developer, I want to access the authenticated user's identity inside my tool without parsing JWTs, so that I can implement user-specific logic cleanly.

#### Acceptance Criteria

1. WHEN authentication is enabled and a request is authenticated, THE Ceramic SHALL inject an Identity_Context object into the MCP request context.
2. THE Identity_Context SHALL contain the user's email, subject identifier, and the full set of token claims. IF the email or subject claim is absent from the token, THEN the corresponding Identity_Context field SHALL be `None`.
3. THE Ceramic SHALL make the Identity_Context accessible via `ctx.identity` on the tool context object and via the module-level `ceramic.identity()` function.
4. WHEN authentication is disabled, THE Ceramic SHALL provide a `None` value for the Identity_Context rather than raising an error.
5. THE Identity_Context object SHALL be immutable; any attempt to modify its fields SHALL raise an `AttributeError`.
6. IF `ceramic.identity()` is called outside of an active request context, THEN THE Ceramic SHALL raise an explicit error indicating that no request context is active.

### Requirement 5: Authorization

**User Story:** As a developer, I want to restrict tool access based on roles and groups using decorators, so that I can enforce access policies declaratively.

#### Acceptance Criteria

1. THE Ceramic SHALL provide a `@ceramic.require_role("role_name")` decorator that restricts MCP_Tool execution to users whose Identity_Context claims contain the specified role.
2. THE Ceramic SHALL provide a `@ceramic.require_group("group_name")` decorator that restricts MCP_Tool execution to users whose Identity_Context claims contain the specified group membership.
3. WHEN a user invokes an MCP_Tool and the authorization policy evaluation fails, THE Ceramic SHALL reject the request with an authorization error indicating insufficient permissions before executing the tool function, ensuring the tool function body is never invoked.
4. WHEN the `authorization` section is present in ceramic.yaml, THE Ceramic SHALL evaluate authorization policies defined there in addition to decorator-based policies, requiring the user to satisfy both.
5. IF multiple authorization decorators are applied to the same MCP_Tool, THEN THE Ceramic SHALL require the user to satisfy all decorator conditions (AND semantics).
6. IF a user invokes an MCP_Tool protected by an authorization decorator and the Identity_Context is None, THEN THE Ceramic SHALL reject the request with an authorization error indicating that authentication is required.

### Requirement 6: Observability

**User Story:** As an operator, I want automatic telemetry on every tool invocation without instrumenting my code, so that I can monitor system health and debug issues.

#### Acceptance Criteria

1. WHEN observability is enabled, THE Ceramic SHALL automatically create an OpenTelemetry span for each MCP_Tool invocation, recording tool name, execution duration in milliseconds, and outcome (success or error).
2. WHEN observability is enabled, THE Ceramic SHALL assign a UUID request ID to each incoming request and propagate the request ID through all log entries and trace spans associated with that request.
3. WHEN observability is enabled, THE Ceramic SHALL emit structured JSON log entries for each request containing timestamp in ISO 8601 format, request ID, tool name, user subject identifier (if authentication is enabled and the user is authenticated), duration in milliseconds, and result status.
4. WHEN observability is enabled, THE Ceramic SHALL expose Prometheus-compatible metrics at a configurable HTTP endpoint path including request count, error count, and latency histogram per MCP_Tool.
5. IF observability is disabled, THEN THE Ceramic SHALL not import or initialize OpenTelemetry or metrics libraries.
6. IF observability is enabled and telemetry export fails, THEN THE Ceramic SHALL log the export failure and continue processing MCP_Tool invocations without interruption.
7. WHEN observability is enabled, THE Ceramic SHALL not include token values, client secrets, or other credentials in span attributes or structured log fields.

### Requirement 7: Session Management

**User Story:** As a developer, I want Ceramic to manage user sessions automatically, so that repeated requests from the same user share context without re-authentication.

#### Acceptance Criteria

1. WHEN sessions are enabled and a user authenticates successfully, THE Ceramic SHALL create a session record associating the user's subject identifier with their token set.
2. WHEN a request arrives with a valid session identifier, THE Ceramic SHALL restore the associated Identity_Context without re-performing the OAuth2 flow.
3. WHEN a session's associated access token expires and refresh succeeds, THE Ceramic SHALL update the session record with the new token.
4. IF a session's associated refresh token is expired or revoked, THEN THE Ceramic SHALL invalidate the session and require re-authentication.
5. THE Ceramic SHALL support configurable session TTL via the `sessions.ttl` key in ceramic.yaml, with a default value of 3600 seconds when the key is absent.
6. WHEN a session's TTL has elapsed since creation, THE Ceramic SHALL invalidate the session regardless of token validity and require re-authentication.
7. IF a request arrives with an invalid or unrecognized session identifier, THEN THE Ceramic SHALL treat the request as unauthenticated and initiate the authentication flow.

### Requirement 8: Middleware and Plugin Architecture

**User Story:** As a framework extender, I want to register custom middleware at well-defined hook points, so that I can add cross-cutting behavior composably.

#### Acceptance Criteria

1. THE Ceramic SHALL provide the following middleware hook points: `before_request`, `after_request`, `before_tool`, `after_tool`, `on_authentication`, `on_authorization`, `on_exception`, and `on_shutdown`.
2. WHEN multiple middleware plugins are registered for the same hook point, THE Ceramic SHALL execute them in registration order (first registered executes first).
3. THE Ceramic SHALL allow middleware to modify the Request_Context, short-circuit request processing by returning a response directly (skipping all subsequent middleware and the handler), or pass control to the next middleware in the chain.
4. WHEN a middleware raises an unhandled exception, THE Ceramic SHALL invoke the `on_exception` hook chain and prevent the exception from propagating to FastMCP unhandled. IF an `on_exception` handler itself raises an exception, THEN THE Ceramic SHALL log the secondary exception and terminate request processing with a generic error response without propagating either exception to FastMCP.
5. THE Ceramic SHALL support plugin registration via the `app.use(plugin)` method or via the `plugins` section of ceramic.yaml. IF a plugin referenced in ceramic.yaml cannot be loaded or instantiated, THEN THE Ceramic SHALL reject the configuration at startup and report an error message identifying the failing plugin.
6. THE Ceramic SHALL require each middleware to be a callable that accepts the Request_Context and a `next` callable as arguments and returns a response or calls `next` to continue the chain.

### Requirement 9: Migration Support

**User Story:** As a developer migrating from FastMCP, I want multiple integration styles so that I can adopt Ceramic incrementally.

#### Acceptance Criteria

1. THE Ceramic SHALL support the import-replacement migration style where replacing `from fastmcp import FastMCP` with `from ceramic import FastMCP` is the only source code change required to start the server and execute all previously registered MCP_Tools, prompts, and resources.
2. THE Ceramic SHALL support the middleware-attachment style via `app.enable_ceramic(config="ceramic.yaml")` applied to an existing `fastmcp.FastMCP` instance, enabling the same set of enterprise features (authentication, authorization, observability, session management) as the import-replacement style.
3. WHEN the middleware-attachment style is used, THE Ceramic SHALL wrap the existing FastMCP instance such that all previously registered MCP_Tools remain callable with their original names, signatures, and return values, and the total count of registered tools is unchanged.
4. IF `app.enable_ceramic()` is called with a config path that does not exist or contains invalid YAML, THEN THE Ceramic SHALL raise a configuration error at the time of the `enable_ceramic()` call and leave the FastMCP instance in its original unmodified state.

### Requirement 10: CLI

**User Story:** As a developer, I want a `ceramic` CLI to run servers, manage authentication state, and validate configuration, so that I can operate the framework from the terminal.

#### Acceptance Criteria

1. THE CLI SHALL provide a `ceramic run` command that starts the Ceramic server using the ceramic.yaml configuration and prints a ready message to stdout including the bound host and port once the server is accepting connections.
2. THE CLI SHALL provide a `ceramic login` command that initiates the OAuth2 authentication flow, stores the resulting tokens in Token_Storage, and prints the authenticated user's email to stdout on success.
3. THE CLI SHALL provide a `ceramic logout` command that clears stored tokens from Token_Storage and invalidates the active session.
4. THE CLI SHALL provide a `ceramic whoami` command that displays the current authenticated user's email, subject, and active roles to stdout.
5. IF `ceramic whoami` is invoked and no valid authentication session exists, THEN THE CLI SHALL exit with a non-zero exit code and print an error message to stderr indicating that no authenticated session is active.
6. THE CLI SHALL provide a `ceramic doctor` command that checks connectivity to the identity provider, validates token freshness, verifies that ceramic.yaml is parseable, and reports the pass or fail status of each check to stdout.
7. THE CLI SHALL provide a `ceramic config validate` command that parses ceramic.yaml and reports all errors and warnings to stdout.
8. IF a CLI command encounters a configuration error, THEN THE CLI SHALL exit with a non-zero exit code and print an error message to stderr identifying the source and nature of the configuration problem.
9. WHEN a CLI command completes successfully, THE CLI SHALL exit with exit code 0.
10. IF `ceramic run` cannot locate or parse ceramic.yaml, THEN THE CLI SHALL exit with a non-zero exit code and print an error message to stderr indicating the missing or invalid configuration file path.

### Requirement 11: Security

**User Story:** As a security engineer, I want the framework to follow security best practices by default, so that sensitive material is never exposed in logs, errors, or network traffic.

#### Acceptance Criteria

1. THE Ceramic SHALL redact access tokens, refresh tokens, and client secrets from all log output and error messages by scanning log fields whose names contain "token", "secret", "credential", "password", or "authorization" and replacing their values with `[REDACTED]`.
2. THE Ceramic SHALL use PKCE for all OAuth2 Authorization Code flows.
3. WHEN a refresh token is used and the identity provider returns a rotated refresh token, THE Ceramic SHALL store the new refresh token and invalidate the previous one.
4. THE Ceramic SHALL enforce a minimum of TLS 1.2 for all outbound HTTP connections to identity providers and token endpoints.
5. THE Ceramic SHALL store tokens using platform-native credential storage or AES-256 encrypted files with file permissions restricted to owner-only (mode 600).
6. IF a token or secret is inadvertently included in a structured log field, THEN THE Ceramic SHALL replace the value with `[REDACTED]` before emitting the log entry.
7. IF a configured identity provider or token endpoint URL does not use HTTPS, THEN THE Ceramic SHALL reject the configuration at startup and report an error identifying the non-TLS endpoint.
8. IF a refresh token is used and the identity provider does not return a new refresh token, THEN THE Ceramic SHALL retain the existing refresh token for subsequent refresh attempts.

### Requirement 12: Configuration Hot Reload

**User Story:** As an operator, I want to update non-critical configuration without restarting the server, so that I can tune observability and authorization policies at runtime.

#### Acceptance Criteria

1. WHERE hot reload is enabled in ceramic.yaml, THE Ceramic SHALL monitor the configuration file for changes and detect modifications within 10 seconds of a file write.
2. WHEN the configuration file changes and hot reload is enabled, THE Ceramic SHALL re-apply observability and authorization settings atomically without restarting the server process, ensuring that subsequent requests use the new configuration.
3. WHEN the configuration file changes and the new configuration is invalid, THE Ceramic SHALL retain the previous valid configuration, log a warning identifying the validation error, and continue serving requests with the previous settings.
4. THE Ceramic SHALL not hot-reload authentication provider settings or session storage backend settings, as these require a restart.
5. WHEN configuration is successfully hot-reloaded, THE Ceramic SHALL emit a log entry at INFO level indicating that the configuration has been updated.

### Requirement 13: Testing Support

**User Story:** As a developer, I want testing utilities provided by the framework, so that I can write tests for authenticated and authorized tool flows without a live identity provider.

#### Acceptance Criteria

1. THE Ceramic SHALL provide a `CeramicTestClient` class that simulates authenticated requests with configurable Identity_Context values, accepting email, subject, claims, roles, and groups as constructor or method parameters.
2. THE Ceramic SHALL provide mock identity provider fixtures that return structurally valid JWT tokens without making network calls.
3. WHEN the `CeramicTestClient` is used, THE Ceramic SHALL bypass actual OAuth2 flows and inject the provided identity directly into the middleware pipeline, including triggering all registered authorization middleware as if a real request were processed.
4. THE Ceramic SHALL provide `assert_authorized(response)` and `assert_unauthorized(response)` helper methods that verify the response status indicates successful authorization or an authorization rejection respectively.
5. WHEN the `CeramicTestClient` is configured with an Identity_Context that lacks required roles or groups, THE Ceramic SHALL enforce authorization policies and reject the request identically to production behavior.
