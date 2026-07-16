"""Tests for the FastAuthMCP exception hierarchy."""

from fastauthmcp.exceptions import (
    AuthenticationError,
    ConfigurationError,
    FastAuthMCPError,
    PluginError,
    ProviderError,
    SessionError,
)


class TestExceptionHierarchy:
    """All custom exceptions inherit from FastAuthMCPError."""

    def test_configuration_error_is_fastauthmcp_error(self):
        assert issubclass(ConfigurationError, FastAuthMCPError)

    def test_authentication_error_is_fastauthmcp_error(self):
        assert issubclass(AuthenticationError, FastAuthMCPError)

    def test_provider_error_is_fastauthmcp_error(self):
        assert issubclass(ProviderError, FastAuthMCPError)

    def test_session_error_is_fastauthmcp_error(self):
        assert issubclass(SessionError, FastAuthMCPError)

    def test_plugin_error_is_fastauthmcp_error(self):
        assert issubclass(PluginError, FastAuthMCPError)

    def test_fastauthmcp_error_is_exception(self):
        assert issubclass(FastAuthMCPError, Exception)

    def test_can_catch_all_via_base(self):
        """A catch block for FastAuthMCPError catches all subclasses."""
        for exc_class in (
            ConfigurationError,
            AuthenticationError,
            ProviderError,
            SessionError,
            PluginError,
        ):
            try:
                raise exc_class("test message")
            except FastAuthMCPError as e:
                assert str(e) == "test message"
