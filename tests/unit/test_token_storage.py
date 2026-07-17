"""Unit tests for fastauthmcp.auth.token_storage module."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fastauthmcp.auth.token_storage import (
    CredentialManagerStorage,
    EncryptedFileStorage,
    KeychainTokenStorage,
    _deserialize_token_set,
    _serialize_token_set,
    get_token_storage,
)
from fastauthmcp.models import TokenSet


@pytest.fixture
def sample_token_set() -> TokenSet:
    """Create a sample TokenSet for testing."""
    return TokenSet(
        access_token="access-123",
        refresh_token="refresh-456",
        expires_at=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        token_type="Bearer",
        id_token="id-token-789",
    )


@pytest.fixture
def sample_token_set_no_optional() -> TokenSet:
    """Create a TokenSet without optional fields."""
    return TokenSet(
        access_token="access-only",
        refresh_token=None,
        expires_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        token_type="Bearer",
        id_token=None,
    )


class TestSerialization:
    """Tests for TokenSet serialization/deserialization."""

    def test_serialize_full_token_set(self, sample_token_set: TokenSet) -> None:
        raw = _serialize_token_set(sample_token_set)
        data = json.loads(raw)

        assert data["access_token"] == "access-123"
        assert data["refresh_token"] == "refresh-456"
        assert data["token_type"] == "Bearer"
        assert data["id_token"] == "id-token-789"
        assert "2025-06-15" in data["expires_at"]

    def test_serialize_minimal_token_set(self, sample_token_set_no_optional: TokenSet) -> None:
        raw = _serialize_token_set(sample_token_set_no_optional)
        data = json.loads(raw)

        assert data["access_token"] == "access-only"
        assert data["refresh_token"] is None
        assert data["id_token"] is None

    def test_roundtrip(self, sample_token_set: TokenSet) -> None:
        raw = _serialize_token_set(sample_token_set)
        restored = _deserialize_token_set(raw)

        assert restored.access_token == sample_token_set.access_token
        assert restored.refresh_token == sample_token_set.refresh_token
        assert restored.expires_at == sample_token_set.expires_at
        assert restored.token_type == sample_token_set.token_type
        assert restored.id_token == sample_token_set.id_token

    def test_roundtrip_no_optional(self, sample_token_set_no_optional: TokenSet) -> None:
        raw = _serialize_token_set(sample_token_set_no_optional)
        restored = _deserialize_token_set(raw)

        assert restored.access_token == sample_token_set_no_optional.access_token
        assert restored.refresh_token is None
        assert restored.id_token is None


class TestKeychainTokenStorage:
    """Tests for KeychainTokenStorage (macOS)."""

    @patch.dict("sys.modules", {"keyring": MagicMock()})
    def test_init_succeeds_with_keyring(self) -> None:
        storage = KeychainTokenStorage()
        assert storage._keyring is not None

    def test_init_fails_without_keyring(self) -> None:
        with patch.dict("sys.modules", {"keyring": None}):
            with pytest.raises(ImportError, match="keyring"):
                KeychainTokenStorage()

    @patch("keyring.set_password")
    @patch("keyring.get_password")
    @patch("keyring.delete_password")
    @pytest.mark.asyncio
    async def test_store_and_retrieve(
        self,
        mock_delete: MagicMock,
        mock_get: MagicMock,
        mock_set: MagicMock,
        sample_token_set: TokenSet,
    ) -> None:
        mock_keyring = MagicMock()
        stored_data: dict[str, str] = {}

        def set_password(service: str, key: str, data: str) -> None:
            stored_data[f"{service}:{key}"] = data

        def get_password(service: str, key: str) -> str | None:
            return stored_data.get(f"{service}:{key}")

        mock_keyring.set_password = set_password
        mock_keyring.get_password = get_password

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            storage = KeychainTokenStorage()

        await storage.store("default", sample_token_set)
        result = await storage.retrieve("default")

        assert result is not None
        assert result.access_token == "access-123"
        assert result.refresh_token == "refresh-456"

    @pytest.mark.asyncio
    async def test_retrieve_returns_none_for_missing_key(self) -> None:
        mock_keyring = MagicMock()
        mock_keyring.get_password = MagicMock(return_value=None)

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            storage = KeychainTokenStorage()

        result = await storage.retrieve("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_ignores_missing_key(self) -> None:
        mock_keyring = MagicMock()
        mock_keyring.delete_password = MagicMock(side_effect=Exception("not found"))

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            storage = KeychainTokenStorage()

        # Should not raise
        await storage.delete("nonexistent")


class TestCredentialManagerStorage:
    """Tests for CredentialManagerStorage (Windows)."""

    @patch.dict("sys.modules", {"keyring": MagicMock()})
    def test_init_succeeds_with_keyring(self) -> None:
        storage = CredentialManagerStorage()
        assert storage._keyring is not None

    def test_init_fails_without_keyring(self) -> None:
        with patch.dict("sys.modules", {"keyring": None}):
            with pytest.raises(ImportError, match="keyring"):
                CredentialManagerStorage()

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, sample_token_set: TokenSet) -> None:
        mock_keyring = MagicMock()
        stored_data: dict[str, str] = {}

        def set_password(service: str, key: str, data: str) -> None:
            stored_data[f"{service}:{key}"] = data

        def get_password(service: str, key: str) -> str | None:
            return stored_data.get(f"{service}:{key}")

        mock_keyring.set_password = set_password
        mock_keyring.get_password = get_password

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            storage = CredentialManagerStorage()

        await storage.store("user1", sample_token_set)
        result = await storage.retrieve("user1")

        assert result is not None
        assert result.access_token == "access-123"


class TestEncryptedFileStorage:
    """Tests for EncryptedFileStorage (Linux)."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_without_crypto(
        self, tmp_path: Path, sample_token_set: TokenSet
    ) -> None:
        """Test plaintext fallback when cryptography is not available."""
        with patch.dict("sys.modules", {"cryptography": None}):
            storage = EncryptedFileStorage(storage_dir=tmp_path)
            storage._has_crypto = False

        await storage.store("default", sample_token_set)
        result = await storage.retrieve("default")

        assert result is not None
        assert result.access_token == "access-123"
        assert result.refresh_token == "refresh-456"
        assert result.id_token == "id-token-789"

    @pytest.mark.asyncio
    async def test_retrieve_returns_none_for_missing_key(self, tmp_path: Path) -> None:
        storage = EncryptedFileStorage(storage_dir=tmp_path)
        storage._has_crypto = False

        result = await storage.retrieve("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_removes_file(self, tmp_path: Path, sample_token_set: TokenSet) -> None:
        storage = EncryptedFileStorage(storage_dir=tmp_path)
        storage._has_crypto = False

        await storage.store("to-delete", sample_token_set)
        file_path = storage._get_file_path("to-delete")
        assert file_path.exists()

        await storage.delete("to-delete")
        assert not file_path.exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key_is_noop(self, tmp_path: Path) -> None:
        storage = EncryptedFileStorage(storage_dir=tmp_path)
        storage._has_crypto = False

        # Should not raise
        await storage.delete("nonexistent")

    @pytest.mark.asyncio
    async def test_file_permissions(self, tmp_path: Path, sample_token_set: TokenSet) -> None:
        """Verify files are created with mode 600."""
        storage = EncryptedFileStorage(storage_dir=tmp_path)
        storage._has_crypto = False

        await storage.store("perms-test", sample_token_set)
        file_path = storage._get_file_path("perms-test")

        mode = oct(os.stat(file_path).st_mode & 0o777)
        assert mode == "0o600"

    @pytest.mark.asyncio
    async def test_directory_permissions(self, tmp_path: Path) -> None:
        """Verify storage directory is created with mode 700."""
        storage_dir = tmp_path / "tokens"
        EncryptedFileStorage(storage_dir=storage_dir)

        mode = oct(os.stat(storage_dir).st_mode & 0o777)
        assert mode == "0o700"

    @pytest.mark.asyncio
    async def test_store_and_retrieve_with_crypto(
        self, tmp_path: Path, sample_token_set: TokenSet
    ) -> None:
        """Test AES-256-GCM encryption when cryptography is available."""
        try:
            import cryptography  # noqa: F401
        except ImportError:
            pytest.skip("cryptography package not installed")

        storage = EncryptedFileStorage(storage_dir=tmp_path)
        assert storage._has_crypto is True

        await storage.store("encrypted-key", sample_token_set)
        result = await storage.retrieve("encrypted-key")

        assert result is not None
        assert result.access_token == "access-123"
        assert result.refresh_token == "refresh-456"

        # Verify file is not plaintext
        file_path = storage._get_file_path("encrypted-key")
        raw_content = file_path.read_bytes()
        assert b"access-123" not in raw_content

    @pytest.mark.asyncio
    async def test_key_sanitization(self, tmp_path: Path) -> None:
        """Test that keys with path separators are sanitized."""
        storage = EncryptedFileStorage(storage_dir=tmp_path)
        storage._has_crypto = False

        file_path = storage._get_file_path("user/special\\key")
        assert "/" not in file_path.name
        assert "\\" not in file_path.name

    @pytest.mark.asyncio
    async def test_roundtrip_with_no_optional_fields(
        self, tmp_path: Path, sample_token_set_no_optional: TokenSet
    ) -> None:
        storage = EncryptedFileStorage(storage_dir=tmp_path)
        storage._has_crypto = False

        await storage.store("minimal", sample_token_set_no_optional)
        result = await storage.retrieve("minimal")

        assert result is not None
        assert result.access_token == "access-only"
        assert result.refresh_token is None
        assert result.id_token is None


class TestGetTokenStorage:
    """Tests for the get_token_storage() auto-detection function."""

    @patch("fastauthmcp.auth.token_storage.sys")
    def test_darwin_returns_keychain(self, mock_sys: MagicMock) -> None:
        mock_sys.platform = "darwin"
        mock_keyring = MagicMock()
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            storage = get_token_storage()
        assert isinstance(storage, KeychainTokenStorage)

    @patch("fastauthmcp.auth.token_storage.sys")
    def test_win32_returns_credential_manager(self, mock_sys: MagicMock) -> None:
        mock_sys.platform = "win32"
        mock_keyring = MagicMock()
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            storage = get_token_storage()
        assert isinstance(storage, CredentialManagerStorage)

    @patch("fastauthmcp.auth.token_storage.sys")
    def test_linux_returns_encrypted_file(self, mock_sys: MagicMock, tmp_path: Path) -> None:
        mock_sys.platform = "linux"
        storage = get_token_storage(storage_dir=tmp_path)
        assert isinstance(storage, EncryptedFileStorage)
