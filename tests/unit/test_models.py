"""Tests for the Ceramic data models."""

from datetime import datetime, timedelta

from ceramic.models import LogEntry, OIDCEndpoints, Session, TokenSet


class TestTokenSet:
    def test_basic_construction(self):
        ts = TokenSet(
            access_token="abc",
            refresh_token="def",
            expires_at=datetime(2025, 1, 1, 12, 0, 0),
        )
        assert ts.access_token == "abc"
        assert ts.refresh_token == "def"
        assert ts.token_type == "Bearer"
        assert ts.id_token is None

    def test_optional_fields(self):
        ts = TokenSet(
            access_token="tok",
            refresh_token=None,
            expires_at=datetime(2025, 6, 1),
            token_type="DPoP",
            id_token="id_tok",
        )
        assert ts.refresh_token is None
        assert ts.token_type == "DPoP"
        assert ts.id_token == "id_tok"


class TestSession:
    def test_not_expired(self):
        session = Session(
            session_id="s1",
            subject="user@example.com",
            token_set=TokenSet(
                access_token="a", refresh_token=None, expires_at=datetime(2099, 1, 1)
            ),
            created_at=datetime.utcnow(),
            ttl=3600,
        )
        assert not session.is_expired

    def test_expired(self):
        session = Session(
            session_id="s2",
            subject="user@example.com",
            token_set=TokenSet(
                access_token="a", refresh_token=None, expires_at=datetime(2099, 1, 1)
            ),
            created_at=datetime.utcnow() - timedelta(seconds=7200),
            ttl=3600,
        )
        assert session.is_expired


class TestOIDCEndpoints:
    def test_construction(self):
        ep = OIDCEndpoints(
            authorization_endpoint="https://idp.example.com/auth",
            token_endpoint="https://idp.example.com/token",
            userinfo_endpoint="https://idp.example.com/userinfo",
            jwks_uri="https://idp.example.com/.well-known/jwks.json",
        )
        assert ep.authorization_endpoint == "https://idp.example.com/auth"
        assert ep.userinfo_endpoint == "https://idp.example.com/userinfo"

    def test_userinfo_optional(self):
        ep = OIDCEndpoints(
            authorization_endpoint="https://idp.example.com/auth",
            token_endpoint="https://idp.example.com/token",
            userinfo_endpoint=None,
            jwks_uri="https://idp.example.com/.well-known/jwks.json",
        )
        assert ep.userinfo_endpoint is None


class TestLogEntry:
    def test_construction_with_defaults(self):
        entry = LogEntry(
            timestamp="2025-01-01T00:00:00Z",
            request_id="req-123",
            tool_name="my_tool",
            subject="user@example.com",
            duration_ms=42.5,
            status="success",
            level="info",
            message="Tool executed",
        )
        assert entry.extra == {}
        assert entry.status == "success"

    def test_extra_field(self):
        entry = LogEntry(
            timestamp="2025-01-01T00:00:00Z",
            request_id="req-456",
            tool_name=None,
            subject=None,
            duration_ms=None,
            status="error",
            level="error",
            message="Something went wrong",
            extra={"trace_id": "abc123"},
        )
        assert entry.extra == {"trace_id": "abc123"}
        assert entry.tool_name is None
