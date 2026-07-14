"""JWT claim parsing and identity context building utilities.

Extracted from authentication.py — these functions parse JWT payloads
(without signature verification) and build IdentityContext from claims.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from ceramic.identity import IdentityContext


def parse_jwt_claims(token: str) -> dict[str, Any]:
    """Parse claims from a JWT token without full signature verification.

    Uses PyJWT to decode the token payload. Signature verification is handled
    separately by the JWKSManager. This function is used as a fallback for
    extracting claims when JWKS verification has already passed or when
    dealing with opaque/JWE tokens that fall back to id_token.

    Args:
        token: The JWT token string (JWS with 3 parts).

    Returns:
        Dictionary of claims parsed from the JWT payload.

    Raises:
        ValueError: If the token is malformed or cannot be decoded.
    """
    import jwt

    try:
        claims = jwt.decode(
            token,
            options={"verify_signature": False},
            algorithms=["RS256", "HS256", "ES256", "PS256"],
        )
        return claims
    except jwt.exceptions.DecodeError as exc:
        raise ValueError(f"Failed to decode JWT: {exc}") from exc


def extract_nested_claim(claims: dict[str, Any], claim_path: str) -> list[str]:
    """Extract a nested claim value using a dot-separated path.

    For example, "realm_access.roles" will look up claims["realm_access"]["roles"].

    Args:
        claims: The full claims dictionary.
        claim_path: Dot-separated path to the claim (e.g. "realm_access.roles").

    Returns:
        List of strings found at the claim path, or empty list if not found.
    """
    parts = claim_path.split(".")
    current: Any = claims
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return []
        if current is None:
            return []

    if isinstance(current, list):
        return [str(item) for item in current]
    elif isinstance(current, dict):
        # Some providers (e.g. Zitadel) encode roles/groups as an object
        # where keys are role names: {"viewer": {...}, "admin": {...}}
        return list(current.keys())
    elif isinstance(current, str):
        return [current]
    return []


def build_identity_context(
    claims: dict[str, Any],
    role_claim_path: str = "realm_access.roles",
    group_claim_path: str = "groups",
) -> IdentityContext:
    """Build an IdentityContext from JWT claims.

    Args:
        claims: Parsed JWT claims dictionary.
        role_claim_path: Dot-path to extract roles from claims.
        group_claim_path: Dot-path to extract groups from claims.

    Returns:
        A populated IdentityContext instance.
    """
    email = claims.get("email")
    subject = claims.get("sub")
    roles = frozenset(extract_nested_claim(claims, role_claim_path))
    groups = frozenset(extract_nested_claim(claims, group_claim_path))

    return IdentityContext(
        email=email,
        subject=subject,
        claims=MappingProxyType(claims),
        roles=roles,
        groups=groups,
    )
