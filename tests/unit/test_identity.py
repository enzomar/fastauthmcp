"""Tests for the FastAuthMCP identity context module."""

import contextvars
from types import MappingProxyType

import pytest

from fastauthmcp.identity import IdentityContext, _identity_context_var, identity


class TestIdentityContext:
    def test_immutable(self):
        ctx = IdentityContext(
            email="user@example.com",
            subject="sub-123",
            claims=MappingProxyType({"sub": "sub-123", "email": "user@example.com"}),
            roles=frozenset({"admin"}),
            groups=frozenset({"ops"}),
        )
        with pytest.raises(AttributeError):
            ctx.email = "other@example.com"  # type: ignore[misc]

    def test_fields_accessible(self):
        claims = MappingProxyType({"sub": "s1", "custom": "value"})
        ctx = IdentityContext(
            email="a@b.com",
            subject="s1",
            claims=claims,
            roles=frozenset({"viewer"}),
            groups=frozenset(),
        )
        assert ctx.email == "a@b.com"
        assert ctx.subject == "s1"
        assert ctx.claims["custom"] == "value"
        assert "viewer" in ctx.roles
        assert ctx.groups == frozenset()

    def test_none_fields(self):
        ctx = IdentityContext(
            email=None,
            subject=None,
            claims=MappingProxyType({}),
            roles=frozenset(),
            groups=frozenset(),
        )
        assert ctx.email is None
        assert ctx.subject is None


class TestIdentityFunction:
    def test_raises_outside_request_context(self):
        """identity() raises RuntimeError when no context is set."""
        # Ensure we run in a clean context where the var has no value
        new_ctx = contextvars.copy_context()

        def _call():
            # Remove any value by running in a fresh context
            with pytest.raises(
                RuntimeError, match="outside of an active request context"
            ):
                identity()

        new_ctx.run(_call)

    def test_returns_context_when_set(self):
        """identity() returns the IdentityContext when set in the context var."""
        id_ctx = IdentityContext(
            email="test@test.com",
            subject="sub-1",
            claims=MappingProxyType({"sub": "sub-1"}),
            roles=frozenset({"user"}),
            groups=frozenset({"team-a"}),
        )

        def _call():
            token = _identity_context_var.set(id_ctx)
            try:
                result = identity()
                assert result is id_ctx
                assert result.email == "test@test.com"
            finally:
                _identity_context_var.reset(token)

        ctx = contextvars.copy_context()
        ctx.run(_call)
