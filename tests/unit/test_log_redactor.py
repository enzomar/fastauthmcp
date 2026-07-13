"""Tests for the LogRedactor security utility."""

from ceramic.security import LogRedactor


class TestLogRedactor:
    def setup_method(self):
        self.redactor = LogRedactor()

    def test_redacts_token_field(self):
        record = {"access_token": "eyJhbGciOi...", "tool_name": "calculator"}
        result = self.redactor.redact(record)
        assert result == {"access_token": "[REDACTED]", "tool_name": "calculator"}

    def test_redacts_authorization_field(self):
        record = {"Authorization": "Bearer xxx"}
        result = self.redactor.redact(record)
        assert result == {"Authorization": "[REDACTED]"}

    def test_redacts_nested_password_field(self):
        record = {"user": {"password_hash": "abc"}}
        result = self.redactor.redact(record)
        assert result == {"user": {"password_hash": "[REDACTED]"}}

    def test_redacts_secret_field(self):
        record = {"client_secret": "s3cr3t"}
        result = self.redactor.redact(record)
        assert result == {"client_secret": "[REDACTED]"}

    def test_redacts_credential_field(self):
        record = {"user_credential": "some-cred", "name": "test"}
        result = self.redactor.redact(record)
        assert result == {"user_credential": "[REDACTED]", "name": "test"}

    def test_case_insensitive_matching(self):
        record = {
            "ACCESS_TOKEN": "value1",
            "Client_Secret": "value2",
            "PASSWORD": "value3",
        }
        result = self.redactor.redact(record)
        assert result == {
            "ACCESS_TOKEN": "[REDACTED]",
            "Client_Secret": "[REDACTED]",
            "PASSWORD": "[REDACTED]",
        }

    def test_preserves_non_sensitive_fields(self):
        record = {"tool_name": "calculator", "duration_ms": 42, "status": "success"}
        result = self.redactor.redact(record)
        assert result == record

    def test_does_not_modify_original(self):
        original = {"access_token": "secret-value", "name": "test"}
        original_copy = original.copy()
        self.redactor.redact(original)
        assert original == original_copy

    def test_deeply_nested_redaction(self):
        record = {
            "request": {
                "headers": {
                    "authorization": "Bearer token123",
                    "content-type": "application/json",
                }
            }
        }
        result = self.redactor.redact(record)
        assert result == {
            "request": {
                "headers": {
                    "authorization": "[REDACTED]",
                    "content-type": "application/json",
                }
            }
        }

    def test_empty_dict(self):
        result = self.redactor.redact({})
        assert result == {}

    def test_multiple_sensitive_fields(self):
        record = {
            "token": "t1",
            "secret": "s1",
            "password": "p1",
            "credential": "c1",
            "authorization": "a1",
            "safe_field": "ok",
        }
        result = self.redactor.redact(record)
        assert result == {
            "token": "[REDACTED]",
            "secret": "[REDACTED]",
            "password": "[REDACTED]",
            "credential": "[REDACTED]",
            "authorization": "[REDACTED]",
            "safe_field": "ok",
        }

    def test_returns_new_dict(self):
        record = {"key": "value"}
        result = self.redactor.redact(record)
        assert result is not record

    def test_nested_returns_new_dicts(self):
        inner = {"password": "secret"}
        record = {"nested": inner}
        result = self.redactor.redact(record)
        assert result["nested"] is not inner
