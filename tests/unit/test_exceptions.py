"""Tests for the Ceramic exception hierarchy."""

from ceramic.exceptions import (
    AuthenticationError,
    CeramicError,
    ConfigurationError,
    PluginError,
    ProviderError,
    SessionError,
)


class TestExceptionHierarchy:
    """All custom exceptions inherit from CeramicError."""

    def test_configuration_error_is_ceramic_error(self):
        assert issubclass(ConfigurationError, CeramicError)

    def test_authentication_error_is_ceramic_error(self):
        assert issubclass(AuthenticationError, CeramicError)

    def test_provider_error_is_ceramic_error(self):
        assert issubclass(ProviderError, CeramicError)

    def test_session_error_is_ceramic_error(self):
        assert issubclass(SessionError, CeramicError)

    def test_plugin_error_is_ceramic_error(self):
        assert issubclass(PluginError, CeramicError)

    def test_ceramic_error_is_exception(self):
        assert issubclass(CeramicError, Exception)

    def test_can_catch_all_via_base(self):
        """A catch block for CeramicError catches all subclasses."""
        for exc_class in (
            ConfigurationError,
            AuthenticationError,
            ProviderError,
            SessionError,
            PluginError,
        ):
            try:
                raise exc_class("test message")
            except CeramicError as e:
                assert str(e) == "test message"
