"""Property-based tests for TLSEnforcer.

Verifies: any URL not using HTTPS is always rejected.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fastauthmcp.exceptions import ConfigurationError
from fastauthmcp.security import TLSEnforcer

enforcer = TLSEnforcer()


# Generate URLs with non-HTTPS schemes
non_https_schemes = st.sampled_from(["http", "ftp", "ws", "wss", "file", "tcp", ""])

# Generate valid-looking hostnames
hostnames = st.from_regex(r"[a-z][a-z0-9\-]{1,20}\.[a-z]{2,4}", fullmatch=True)


@given(scheme=non_https_schemes, host=hostnames)
def test_non_https_urls_always_rejected(scheme: str, host: str) -> None:
    """Any URL with a non-HTTPS scheme must raise ConfigurationError."""
    url = f"{scheme}://{host}/path"
    with pytest.raises(ConfigurationError):
        enforcer.validate_url(url)


@given(host=hostnames, path=st.from_regex(r"/[a-z/]{0,30}", fullmatch=True))
def test_https_urls_always_accepted(host: str, path: str) -> None:
    """Any URL with HTTPS scheme must pass validation."""
    url = f"https://{host}{path}"
    # Should not raise
    enforcer.validate_url(url)


@given(st.text())
def test_validate_url_never_crashes(url_string: str) -> None:
    """TLSEnforcer never crashes on arbitrary input (raises or passes cleanly)."""
    try:
        enforcer.validate_url(url_string)
    except ConfigurationError:
        pass  # Expected for non-HTTPS
    # Any other exception would be a bug (test fails if it propagates)
