"""Ceramic CLI - command-line interface for running servers and managing auth."""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from ceramic.auth.oauth import OAuthService
from ceramic.auth.token_storage import get_token_storage
from ceramic.config_loader import ConfigLoader
from ceramic.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ProviderError,
)
from ceramic.server import CeramicFastMCP


@click.group()
def cli() -> None:
    """Ceramic Framework CLI."""


@cli.command()
@click.option("--config", "config_path", default=None, type=click.Path(), help="Path to ceramic.yaml")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse", "http", "streamable-http"]),
    default="stdio",
    help="Transport protocol (default: stdio)",
)
@click.option("--host", default="localhost", help="Host to bind to (for HTTP transports)")
@click.option("--port", default=8000, type=int, help="Port to bind to (for HTTP transports)")
def run(config_path: str | None, transport: str, host: str, port: int) -> None:
    """Start the Ceramic server."""
    try:
        path = Path(config_path) if config_path else None
        loader = ConfigLoader()
        loader.load(path=path)

        server = CeramicFastMCP(name="ceramic", config=config_path)

        if transport == "stdio":
            click.echo("Ceramic server starting (stdio transport)")
        else:
            click.echo(f"Ceramic server ready on http://{host}:{port} ({transport} transport)")

        server.run(transport=transport, host=host, port=port)
    except ConfigurationError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@cli.command()
def login() -> None:
    """Authenticate with the identity provider."""
    try:
        loader = ConfigLoader()
        config = loader.load()

        if config.auth is None:
            click.echo("Error: No auth configuration found in ceramic.yaml", err=True)
            sys.exit(1)

        oauth = OAuthService(provider_config=config.auth)
        storage = get_token_storage()

        async def _do_login() -> str:
            # Discover OIDC endpoints
            issuer_url = str(config.auth.issuer).rstrip("/")
            await oauth.discover_endpoints(issuer_url)

            # Initiate OAuth flow (opens browser)
            result = await oauth.initiate_flow(config.auth)

            # Exchange code for tokens
            token_set = await oauth.exchange_code(
                code=result.code,
                verifier=result.verifier,
                redirect_uri=result.redirect_uri,
                provider_config=config.auth,
            )

            # Store the tokens
            await storage.store("default", token_set)

            # Extract email from ID token or access token
            email = _extract_email_from_tokens(token_set)
            return email

        email = asyncio.run(_do_login())
        click.echo(email)

    except (AuthenticationError, ProviderError, ConfigurationError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@cli.command()
def logout() -> None:
    """Clear stored tokens and invalidate session."""
    try:
        storage = get_token_storage()

        async def _do_logout() -> None:
            await storage.delete("default")

        asyncio.run(_do_logout())
        click.echo("Logged out successfully.")

    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@cli.command()
def whoami() -> None:
    """Display current authenticated user info."""
    try:
        storage = get_token_storage()

        async def _get_token_set():
            return await storage.retrieve("default")

        token_set = asyncio.run(_get_token_set())

        if token_set is None:
            click.echo("Error: No authenticated session found", err=True)
            sys.exit(1)

        # Parse claims from the token
        claims = _decode_jwt_claims(token_set.access_token)
        if claims is None and token_set.id_token:
            claims = _decode_jwt_claims(token_set.id_token)

        if claims is None:
            click.echo("Error: Unable to parse token claims", err=True)
            sys.exit(1)

        email = claims.get("email", "N/A")
        subject = claims.get("sub", "N/A")
        roles = claims.get("realm_access", {}).get("roles", [])
        if isinstance(roles, str):
            roles = [roles]

        click.echo(f"Email: {email}")
        click.echo(f"Subject: {subject}")
        click.echo(f"Roles: {', '.join(roles) if roles else 'none'}")

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@cli.command()
def doctor() -> None:
    """Run diagnostics on the Ceramic configuration and connectivity."""
    all_passed = True

    # Check 1: Config file parseable
    try:
        loader = ConfigLoader()
        config = loader.load()
        click.echo("✓ Configuration file is valid")
    except ConfigurationError as exc:
        click.echo(f"✗ Configuration file: {exc}")
        all_passed = False
        config = None

    # Check 2: IDP connectivity (if auth configured)
    if config and config.auth:
        try:
            oauth = OAuthService(provider_config=config.auth)
            issuer_url = str(config.auth.issuer).rstrip("/")

            async def _check_idp():
                await oauth.discover_endpoints(issuer_url)

            asyncio.run(_check_idp())
            click.echo("✓ Identity provider is reachable")
        except (ProviderError, ConfigurationError, Exception) as exc:
            click.echo(f"✗ Identity provider connectivity: {exc}")
            all_passed = False
    else:
        click.echo("- Identity provider check skipped (no auth configured)")

    # Check 3: Token freshness (if stored token exists)
    try:
        storage = get_token_storage()

        async def _check_token():
            return await storage.retrieve("default")

        token_set = asyncio.run(_check_token())

        if token_set is not None:
            now = datetime.now(timezone.utc)
            if token_set.expires_at > now:
                click.echo("✓ Stored token is fresh")
            else:
                click.echo("✗ Stored token has expired")
                all_passed = False
        else:
            click.echo("- Token freshness check skipped (no stored token)")
    except Exception as exc:
        click.echo(f"✗ Token freshness check: {exc}")
        all_passed = False

    if not all_passed:
        sys.exit(1)


@cli.group()
def config() -> None:
    """Configuration management commands."""


@config.command("validate")
def config_validate() -> None:
    """Validate the ceramic.yaml configuration file."""
    try:
        loader = ConfigLoader()
        loaded_config = loader.load()

        # Report warnings for optional but potentially misconfigured items
        warnings: list[str] = []

        if loaded_config.auth and loaded_config.auth.client_secret:
            warnings.append(
                "Warning: client_secret is set in config. "
                "Consider using environment variable CERAMIC_AUTH_CLIENT_SECRET instead."
            )

        if loaded_config.observability and loaded_config.observability.exporter == "otlp":
            if loaded_config.observability.otlp_endpoint.startswith("http://"):
                warnings.append(
                    "Warning: OTLP endpoint uses HTTP instead of HTTPS."
                )

        click.echo("Configuration is valid.")
        for warning in warnings:
            click.echo(warning)

    except ConfigurationError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# Register the config subgroup with the main CLI
cli.add_command(config)


def _decode_jwt_claims(token: str) -> dict | None:
    """Decode JWT payload without signature verification (for display only).

    Args:
        token: A JWT string.

    Returns:
        Decoded claims dict, or None if decoding fails.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        # Decode the payload (second part)
        payload = parts[1]
        # Add padding if needed
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _extract_email_from_tokens(token_set) -> str:
    """Extract email from id_token or access_token claims.

    Args:
        token_set: A TokenSet instance.

    Returns:
        The email string, or "unknown" if not found.
    """
    # Try ID token first
    if token_set.id_token:
        claims = _decode_jwt_claims(token_set.id_token)
        if claims and "email" in claims:
            return claims["email"]

    # Fall back to access token
    claims = _decode_jwt_claims(token_set.access_token)
    if claims and "email" in claims:
        return claims["email"]

    return "unknown"
