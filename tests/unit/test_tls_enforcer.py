"""Tests for TLSEnforcer security utility."""

from __future__ import annotations

import ssl

import pytest

from ceramic.exceptions import ConfigurationError
from ceramic.security import TLSEnforcer


class TestValidateUrl:
    def setup_method(self):
        self.enforcer = TLSEnforcer()

    def test_valid_https_url_passes(self):
        """A well-formed HTTPS URL should not raise."""
        self.enforcer.validate_url(
            "https://idp.example.com/.well-known/openid-configuration"
        )

    def test_http_url_raises(self):
        """An HTTP URL should raise ConfigurationError."""
        with pytest.raises(ConfigurationError, match="Non-TLS endpoint"):
            self.enforcer.validate_url("http://insecure.example.com/token")

    def test_empty_scheme_raises(self):
        """A URL with no scheme should raise ConfigurationError."""
        with pytest.raises(ConfigurationError, match="Non-TLS endpoint"):
            self.enforcer.validate_url("//no-scheme.example.com/path")

    def test_mixed_case_https_passes(self):
        """HTTPS in mixed case should be accepted."""
        self.enforcer.validate_url("HTTPS://example.com/resource")
        self.enforcer.validate_url("Https://example.com/resource")
        self.enforcer.validate_url("hTtPs://example.com/secure")

    def test_ftp_scheme_raises(self):
        """Non-HTTP(S) schemes should also be rejected."""
        with pytest.raises(ConfigurationError, match="Non-TLS endpoint"):
            self.enforcer.validate_url("ftp://files.example.com/data")

    def test_error_message_includes_url(self):
        """The error message should include the offending URL."""
        with pytest.raises(ConfigurationError, match="http://bad.url"):
            self.enforcer.validate_url("http://bad.url/path")


class TestGetSslContext:
    def setup_method(self):
        self.enforcer = TLSEnforcer()

    def test_returns_ssl_context(self):
        """get_ssl_context() should return an ssl.SSLContext."""
        ctx = self.enforcer.get_ssl_context()
        assert isinstance(ctx, ssl.SSLContext)

    def test_minimum_tls_version(self):
        """The context should enforce TLS 1.2 as minimum."""
        ctx = self.enforcer.get_ssl_context()
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2

    def test_certificate_verification_enabled(self):
        """The context should have certificate verification enabled (CERT_REQUIRED)."""
        ctx = self.enforcer.get_ssl_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    def test_check_hostname_enabled(self):
        """The context should verify hostnames by default."""
        ctx = self.enforcer.get_ssl_context()
        assert ctx.check_hostname is True
