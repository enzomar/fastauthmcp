# FastAuthMCP Integration Guides

Step-by-step guides for integrating FastAuthMCP with specific platforms and identity providers.

## By MCP Client Platform

| Guide | Platform | Description |
|-------|----------|-------------|
| [Claude Desktop](claude-desktop.md) | Anthropic Claude | Local MCP server with browser login |
| [Google Gemini](google-gemini.md) | Google AI | Cloud MCP with token exchange |
| [Cursor IDE](cursor-ide.md) | Cursor | Development MCP server with SSE |
| [Custom Agent](custom-agent.md) | Any | Build your own MCP client with auth |

## By Identity Provider

| Guide | IDP | Grant Types |
|-------|-----|-------------|
| [Zitadel](idp-zitadel.md) | Zitadel Cloud/Self-hosted | Auth Code + PKCE, Client Credentials, Token Exchange |
| [Keycloak](idp-keycloak.md) | Keycloak | Auth Code + PKCE, Client Credentials |
| [Auth0](idp-auth0.md) | Auth0 by Okta | Auth Code + PKCE, Client Credentials, Token Exchange |
| [Azure Entra ID](idp-azure.md) | Microsoft Entra ID | Auth Code + PKCE, On-Behalf-Of |
| [Google IAM](idp-google.md) | Google Cloud | Workload Identity, Token Exchange |
| [Okta](idp-okta.md) | Okta | Auth Code + PKCE, Client Credentials |

## By Deployment Scenario

| Guide | Scenario | Description |
|-------|----------|-------------|
| [Local Development](scenario-local.md) | Developer laptop | Browser login, stdio transport |
| [Cloud Deployment](scenario-cloud.md) | Cloud/K8s | Headless, SSE/HTTP, token exchange |
| [Enterprise Gateway](scenario-enterprise.md) | Multi-IDP, RBAC, SOAP | Full enterprise stack |
