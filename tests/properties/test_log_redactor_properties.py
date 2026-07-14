"""Property-based tests for LogRedactor.

Verifies the universal invariant: sensitive fields are ALWAYS redacted,
regardless of input shape, nesting depth, or value type.
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from ceramic.security import LogRedactor

redactor = LogRedactor()

# Strategies for generating test data
simple_values = st.one_of(
    st.text(),
    st.integers(),
    st.floats(allow_nan=False),
    st.booleans(),
    st.none(),
)

# Keys that should trigger redaction
sensitive_keys = st.sampled_from(
    [
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "client_secret",
        "credential",
        "password",
        "authorization",
        "Authorization",
        "TOKEN",
        "SECRET_KEY",
        "my_password_field",
        "user_credential_id",
    ]
)

# Keys that should NOT trigger redaction
safe_keys = st.sampled_from(
    [
        "name",
        "email",
        "status",
        "count",
        "url",
        "path",
        "method",
        "duration",
        "request_id",
        "tool_name",
    ]
)


@given(st.dictionaries(sensitive_keys, simple_values, min_size=1))
def test_sensitive_keys_always_redacted(data: dict) -> None:
    """Any dict with sensitive keys always has those values replaced."""
    result = redactor.redact(data)
    for key in result:
        if redactor._is_sensitive(key):
            assert result[key] == "[REDACTED]", (
                f"Key '{key}' was not redacted. Value: {result[key]!r}"
            )


@given(st.dictionaries(safe_keys, simple_values))
def test_safe_keys_never_redacted(data: dict) -> None:
    """Keys without sensitive patterns are never modified."""
    result = redactor.redact(data)
    for key in data:
        assert result[key] == data[key], f"Safe key '{key}' was unexpectedly modified"


@given(
    st.fixed_dictionaries(
        {
            "name": st.text(),
            "nested": st.fixed_dictionaries(
                {
                    "token": st.text(min_size=1),
                    "value": st.integers(),
                }
            ),
        }
    )
)
def test_nested_sensitive_keys_redacted(data: dict) -> None:
    """Sensitive keys in nested dicts are also redacted."""
    result = redactor.redact(data)
    assert result["nested"]["token"] == "[REDACTED]"
    assert result["nested"]["value"] == data["nested"]["value"]
    assert result["name"] == data["name"]


@given(st.dictionaries(st.text(min_size=1), simple_values))
def test_redaction_never_raises(data: dict) -> None:
    """Redactor handles any string key without raising exceptions."""
    # Should never raise, regardless of input
    result = redactor.redact(data)
    assert isinstance(result, dict)
    assert len(result) == len(data)


@given(st.dictionaries(st.text(min_size=1), simple_values))
def test_original_dict_unmodified(data: dict) -> None:
    """Redaction returns a new dict; original is never mutated."""
    original_copy = dict(data)
    _ = redactor.redact(data)
    assert data == original_copy
