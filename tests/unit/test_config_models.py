"""Slim config model tests — Pydantic handles field-range validation itself.

We verify only the 5 essential behaviors:
1. Minimal valid config constructs correctly
2. Full config round-trips
3. Invalid provider is rejected
4. Unknown top-level keys are rejected (extra_forbidden)
5. Required fields are enforced
"""

import pytest
from pydantic import ValidationError

from ceramic.config import (
    AuthConfig,
    CeramicConfig,
    ObservabilityConfig,
    SessionsConfig,
)


class TestConfigModels:
    def test_minimal_auth_config(self):
        cfg = AuthConfig(issuer="https://idp.example.com", client_id="my-app")
        assert str(cfg.issuer) == "https://idp.example.com/"
        assert cfg.client_id == "my-app"
        assert cfg.provider == "oidc"

    def test_full_ceramic_config(self):
        cfg = CeramicConfig(
            auth=AuthConfig(issuer="https://idp.example.com", client_id="app"),
            observability=ObservabilityConfig(log_level="debug"),
            sessions=SessionsConfig(ttl=7200),
        )
        assert cfg.auth.client_id == "app"
        assert cfg.observability.log_level == "debug"
        assert cfg.sessions.ttl == 7200

    def test_invalid_provider_rejected(self):
        with pytest.raises(ValidationError, match="provider"):
            AuthConfig(provider="saml", issuer="https://idp.example.com", client_id="x")

    def test_unknown_keys_rejected(self):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            CeramicConfig(unknown_field="value")

    def test_required_fields_enforced(self):
        with pytest.raises(ValidationError, match="issuer"):
            AuthConfig(client_id="app")
