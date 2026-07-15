# Requirements Document

## Introduction

This feature adds three hardening capabilities to the FastAuthMCP framework's IDP integration layer: provider-specific token exchange adapters (Google Cloud STS, Microsoft Entra ID), a circuit breaker pattern for all outbound IDP HTTP calls, and JWKS resilience improvements to handle thundering herd scenarios. Together these changes make FastAuthMCP production-ready for multi-cloud deployments where IDP availability cannot be assumed and provider-specific quirks must be normalized.

## Glossary

- **Token_Exchange_Adapter**: A provider-specific implementation that translates FastAuthMCP's internal token exchange request into the wire format required by a particular IDP, and normalizes the response back into a standard TokenSet.
- **Circuit_Breaker**: A stateful component that monitors outbound IDP HTTP calls and transitions between Closed (allowing calls), Open (failing fast), and Half-Open (probing recovery) states based on configurable failure thresholds and cooldown timers.
- **JWKS_Manager**: The component responsible for fetching, caching, and refreshing JSON Web Key Sets used for JWT signature verification.
- **Request_Coalescer**: A mechanism that deduplicates concurrent in-flight requests for the same resource, ensuring only one network call is made while all waiters share the result.
- **Stale_While_Revalidate**: A caching strategy where the cached JWKS keys continue to be served to callers while a background refresh is attempted, avoiding blocking on network calls.
- **IDP**: Identity Provider — the external OIDC-compliant service (e.g., Zitadel, Google, Entra ID) that issues and validates tokens.
- **OAuthService**: The existing FastAuthMCP component in `fastauthmcp/auth/oauth.py` that handles OIDC discovery, token endpoint calls, and token exchange.
- **JWKSVerifier**: The existing FastAuthMCP component in `fastauthmcp/middleware/authentication.py` that fetches JWKS and verifies JWT signatures.
- **Adapter_Registry**: A mapping from provider identifiers to their corresponding Token_Exchange_Adapter implementations, used to select the correct adapter at runtime.

## Requirements

### Requirement 1: Token Exchange Adapter Interface

**User Story:** As a framework maintainer, I want a unified adapter interface for provider-specific token exchange, so that new IDP providers can be supported without modifying the core OAuthService logic.

#### Acceptance Criteria

1. THE Token_Exchange_Adapter SHALL expose an async method that accepts a subject token (non-empty string), an AuthConfig, and discovered OIDCEndpoints, and returns a TokenSet.
2. THE Adapter_Registry SHALL select the appropriate Token_Exchange_Adapter based on a provider identifier string (1 to 64 characters, alphanumeric and hyphens only) configured in AuthConfig.
3. IF the provider identifier in AuthConfig does not match any registered adapter, THEN THE Adapter_Registry SHALL raise a ConfigurationError indicating the unrecognized provider identifier.
4. WHEN no provider-specific adapter is configured (provider identifier field is absent or null), THE Adapter_Registry SHALL select the default RFC 8693 adapter that performs the token exchange grant using the parameters defined in AuthConfig (subject_token, subject_token_type, audience, scope, client credentials).
5. THE Token_Exchange_Adapter interface SHALL accept an optional audience parameter (string, maximum 256 characters) and an optional scope parameter (space-delimited string, maximum 512 characters) for the exchanged token.
6. IF the Token_Exchange_Adapter async method fails due to a provider communication or token rejection error, THEN THE Token_Exchange_Adapter SHALL raise a ProviderError containing an error description from the provider response.

### Requirement 2: Google Cloud STS Adapter

**User Story:** As a developer deploying on Google Cloud, I want FastAuthMCP to exchange tokens via Google Cloud STS, so that I can use Google-issued credentials with the MCP server.

#### Acceptance Criteria

1. WHEN the provider identifier is "google", THE Token_Exchange_Adapter SHALL POST to the Google STS endpoint at `https://sts.googleapis.com/v1/token`.
2. WHEN exchanging a token with the Google adapter, THE Token_Exchange_Adapter SHALL send the request body encoded as `application/x-www-form-urlencoded`.
3. WHEN exchanging a token with the Google adapter, THE Token_Exchange_Adapter SHALL use the parameter name `subjectToken` instead of `subject_token`.
4. WHEN exchanging a token with the Google adapter, THE Token_Exchange_Adapter SHALL use the parameter name `subjectTokenType` instead of `subject_token_type`.
5. WHEN exchanging a token with the Google adapter, THE Token_Exchange_Adapter SHALL include a `grantType` parameter set to `urn:ietf:params:oauth:grant-type:token-exchange`.
6. WHEN the Google STS endpoint returns an `access_token` field, THE Token_Exchange_Adapter SHALL map the response to a TokenSet with `access_token` from the response, `expires_at` computed as the current UTC time plus the `expires_in` value in seconds (defaulting to 3600 if absent), and `token_type` from the response (defaulting to "Bearer" if absent).
7. IF the Google STS endpoint returns an HTTP response with status code 400 or above, THEN THE Token_Exchange_Adapter SHALL raise a ProviderError containing the `error_description` field from the response body, or the `error` field if `error_description` is absent, or the HTTP status code if the body cannot be parsed.
8. IF the Google STS endpoint response does not contain an `access_token` field, THEN THE Token_Exchange_Adapter SHALL raise a ProviderError with a message indicating the response is missing the required `access_token` field.
9. WHEN exchanging a token with the Google adapter, THE Token_Exchange_Adapter SHALL enforce a request timeout of 30 seconds for the HTTP POST to the Google STS endpoint.

### Requirement 3: Microsoft Entra ID Adapter

**User Story:** As a developer deploying on Azure, I want FastAuthMCP to exchange tokens via Entra ID's on-behalf-of flow, so that I can use Azure AD-issued credentials with the MCP server.

#### Acceptance Criteria

1. WHEN the provider identifier is "entra", THE Token_Exchange_Adapter SHALL POST to the Entra ID token endpoint discovered via OIDC discovery using the `token_exchange_timeout` from AuthConfig as the HTTP request timeout.
2. WHEN exchanging a token with the Entra adapter, THE Token_Exchange_Adapter SHALL set the `grant_type` parameter to `urn:ietf:params:oauth:grant-type:jwt-bearer`.
3. WHEN exchanging a token with the Entra adapter, THE Token_Exchange_Adapter SHALL include an `assertion` parameter containing the subject token.
4. WHEN exchanging a token with the Entra adapter, THE Token_Exchange_Adapter SHALL include a `requested_token_use` parameter set to `on_behalf_of`.
5. WHEN exchanging a token with the Entra adapter, THE Token_Exchange_Adapter SHALL include the `client_id` and `client_secret` from the AuthConfig, and a `scope` parameter from the adapter's scope argument or the AuthConfig `token_exchange_scope` if provided.
6. WHEN the Entra token endpoint returns an `access_token` field, THE Token_Exchange_Adapter SHALL normalize the response into a TokenSet by mapping `access_token`, `refresh_token`, `token_type`, and `id_token` directly and computing `expires_at` from the `expires_in` field relative to the current UTC time.
7. IF the Entra token endpoint returns an HTTP error, THEN THE Token_Exchange_Adapter SHALL raise a ProviderError containing the `error_description` field from the response body, or the `error` field if `error_description` is absent.
8. IF the AuthConfig `client_secret` is not set when the Entra adapter is invoked, THEN THE Token_Exchange_Adapter SHALL raise an AuthenticationError indicating that the Entra on-behalf-of flow requires a client secret.

### Requirement 4: Circuit Breaker for IDP Calls

**User Story:** As an operator running FastAuthMCP in production, I want IDP calls to fail fast when the provider is down, so that cascading failures do not degrade the MCP server.

#### Acceptance Criteria

1. THE Circuit_Breaker SHALL maintain one of three states: Closed, Open, or Half-Open.
2. WHILE the Circuit_Breaker is in Closed state, THE Circuit_Breaker SHALL forward all IDP HTTP requests and record their outcome as a failure if the response is an HTTP 5xx status code, a connection error, or a request timeout, and as a success otherwise.
3. WHEN the number of consecutive failures reaches the configured failure threshold, THE Circuit_Breaker SHALL transition from Closed to Open state.
4. WHILE the Circuit_Breaker is in Open state, THE Circuit_Breaker SHALL immediately raise a ProviderError indicating that the circuit is open, without making a network call.
5. WHEN the configured cooldown period elapses after the Circuit_Breaker enters Open state, THE Circuit_Breaker SHALL transition to Half-Open state.
6. WHILE the Circuit_Breaker is in Half-Open state, THE Circuit_Breaker SHALL allow exactly one probe request through to the IDP and SHALL reject all other concurrent requests with a ProviderError as if in Open state until the probe completes.
7. WHEN a probe request in Half-Open state succeeds, THE Circuit_Breaker SHALL transition to Closed state and reset the failure counter to zero.
8. WHEN a probe request in Half-Open state fails, THE Circuit_Breaker SHALL transition back to Open state and restart the cooldown timer.
9. THE Circuit_Breaker SHALL maintain a single shared instance across all outbound IDP HTTP call types: OIDC discovery, token endpoint, JWKS fetch, and token exchange.
10. THE Circuit_Breaker SHALL accept a configurable failure threshold with a default value of 5.
11. THE Circuit_Breaker SHALL accept a configurable cooldown period in seconds with a default value of 30.
12. WHEN a successful request occurs while the Circuit_Breaker is in Closed state, THE Circuit_Breaker SHALL reset the consecutive failure counter to zero.

### Requirement 5: Circuit Breaker Configuration

**User Story:** As an operator, I want to configure the circuit breaker thresholds via fastauthmcp.yaml, so that I can tune resilience behavior for my deployment environment.

#### Acceptance Criteria

1. THE AuthConfig SHALL accept an optional `circuit_breaker` section containing `failure_threshold` and `cooldown_seconds` fields, where both fields are optional and independent of each other.
2. WHEN the `circuit_breaker` section is not present in the configuration, THE Circuit_Breaker SHALL use default values of 5 for failure threshold and 30 for cooldown seconds.
3. WHEN the `circuit_breaker` section is present but a field is omitted, THE Circuit_Breaker SHALL use the default value for the omitted field (5 for `failure_threshold`, 30 for `cooldown_seconds`).
4. THE `failure_threshold` configuration field SHALL accept an integer value between 1 and 100 inclusive.
5. THE `cooldown_seconds` configuration field SHALL accept an integer value between 1 and 300 inclusive.
6. IF a `circuit_breaker` field value is outside its valid range or is not an integer, THEN THE System SHALL reject the configuration at load time with an error message indicating the field name, the invalid value, and the acceptable range.

### Requirement 6: JWKS Request Coalescing

**User Story:** As an operator, I want concurrent JWKS refresh requests to be deduplicated, so that a burst of token verifications does not create a thundering herd of outbound calls to the IDP.

#### Acceptance Criteria

1. WHEN multiple concurrent callers request a JWKS refresh for the same issuer, THE JWKS_Manager SHALL issue only one outbound HTTP request to that issuer's JWKS endpoint and SHALL complete or fail within 30 seconds.
2. WHEN the coalesced JWKS fetch completes successfully, THE JWKS_Manager SHALL distribute the fetched key set to all callers that were waiting for that same issuer.
3. IF the coalesced JWKS fetch fails due to a network error, HTTP response with status 4xx or 5xx, or timeout, THEN THE JWKS_Manager SHALL propagate an error indicating the failure reason to all waiting callers for that issuer.
4. WHEN a new JWKS request arrives after a coalesced fetch completes (either successfully or with an error), THE JWKS_Manager SHALL allow a fresh outbound fetch to proceed.
5. WHEN concurrent callers request JWKS refreshes for different issuers, THE JWKS_Manager SHALL issue independent outbound HTTP requests for each distinct issuer without blocking on one another.

### Requirement 7: JWKS Exponential Backoff

**User Story:** As an operator, I want JWKS fetch retries to use exponential backoff, so that a temporarily unavailable IDP is not overwhelmed with retry traffic.

#### Acceptance Criteria

1. WHEN a JWKS fetch fails due to a network error or an HTTP response with status code 500 or above, THE JWKS_Manager SHALL retry with exponential backoff starting at 1 second and doubling the delay on each subsequent failure.
2. IF a JWKS fetch fails with an HTTP response status code below 500, THEN THE JWKS_Manager SHALL NOT retry and SHALL immediately raise a ProviderError indicating the status code and response body.
3. THE JWKS_Manager SHALL cap the maximum backoff interval at 60 seconds.
4. THE JWKS_Manager SHALL attempt a maximum of 3 retries before raising a ProviderError to the caller indicating that the JWKS endpoint is unreachable.
5. THE JWKS_Manager SHALL add random jitter uniformly distributed between 0 and 25 percent of the computed backoff interval to each retry delay.

### Requirement 8: JWKS Stale-While-Revalidate

**User Story:** As an operator, I want token verification to continue using cached JWKS keys while a background refresh is in progress, so that transient IDP outages do not block request processing.

#### Acceptance Criteria

1. WHILE the JWKS cache contains keys and the cache TTL has expired, THE JWKS_Manager SHALL continue serving the cached keys to callers while initiating a background refresh.
2. WHEN the background JWKS refresh succeeds, THE JWKS_Manager SHALL atomically replace the cached keys with the fresh keys.
3. IF the background JWKS refresh fails after all retries, THEN THE JWKS_Manager SHALL continue serving the stale cached keys, log a warning, and schedule the next refresh attempt after the backoff interval defined in Requirement 7. IF the stale cached keys have exceeded a maximum staleness period of 3600 seconds since their last successful fetch, THEN THE JWKS_Manager SHALL reject token verification requests and return an error indicating that JWKS keys are too stale.
4. WHEN the JWKS cache is empty and no keys have ever been fetched, THE JWKS_Manager SHALL perform a blocking fetch with retries as defined in Requirement 7. IF the blocking fetch fails after all retries, THEN THE JWKS_Manager SHALL raise a ProviderError to the caller within 30 seconds of the initial request.
5. THE JWKS_Manager SHALL consider cached keys as stale after a configurable TTL with a default of 600 seconds. THE configurable TTL SHALL accept an integer value between 60 and 86400 seconds.
6. WHILE a background refresh is already in-flight, THE JWKS_Manager SHALL NOT initiate an additional background refresh, and SHALL continue serving cached keys until the in-flight refresh completes or fails.
