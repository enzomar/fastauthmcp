# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | ✅ Current release |

## Reporting a Vulnerability

**Do NOT open a public issue for security vulnerabilities.**

Please report security issues through [GitHub Security Advisories](https://github.com/enzomar/ceramic-fwk/security/advisories/new) (private).

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We aim to respond within 48 hours and coordinate disclosure within 90 days.

## Security Design

Ceramic's security model is documented in `.ai/security.md`. Key principles:

- TLS 1.2+ enforced on all IDP communication
- PKCE mandatory on all authorization_code flows
- Sensitive values (tokens, secrets) automatically redacted from logs
- Circuit breaker prevents cascading failures from IDP outages
- Tokens validated locally (structure, expiration, audience) before IDP exchange

## Scope

The following are in-scope for security reports:
- Authentication bypass
- Token leakage (logs, error messages, responses)
- TLS downgrade or bypass
- Credential storage vulnerabilities
- CSRF or state manipulation in OAuth flows
- Circuit breaker bypass leading to DoS

Out of scope:
- Denial of service via resource exhaustion (we already have circuit breaker)
- Issues requiring physical access to the machine
- Issues in dependencies (report upstream, but let us know)
