"""Platform-native secure token storage for OAuth2 tokens.

Provides TokenStorage protocol and platform-specific implementations:
- KeychainTokenStorage (macOS via keyring)
- CredentialManagerStorage (Windows via keyring)
- EncryptedFileStorage (Linux, AES-256-GCM encrypted, file mode 600)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ceramic.models import TokenSet

logger = logging.getLogger(__name__)

SERVICE_NAME = "ceramic-fwk"


class TokenStorage(Protocol):
    """Platform-native secure token storage."""

    async def store(self, key: str, token_set: TokenSet) -> None:
        """Store a token set under the given key."""
        ...

    async def retrieve(self, key: str) -> TokenSet | None:
        """Retrieve a token set by key, or None if not found."""
        ...

    async def delete(self, key: str) -> None:
        """Delete a token set by key."""
        ...


def _serialize_token_set(token_set: TokenSet) -> str:
    """Serialize a TokenSet to JSON string."""
    data = {
        "access_token": token_set.access_token,
        "refresh_token": token_set.refresh_token,
        "expires_at": token_set.expires_at.isoformat(),
        "token_type": token_set.token_type,
        "id_token": token_set.id_token,
    }
    return json.dumps(data)


def _deserialize_token_set(raw: str) -> TokenSet:
    """Deserialize a JSON string back to a TokenSet."""
    data = json.loads(raw)
    return TokenSet(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_at=datetime.fromisoformat(data["expires_at"]),
        token_type=data["token_type"],
        id_token=data.get("id_token"),
    )


class KeychainTokenStorage:
    """macOS token storage using the system Keychain via keyring."""

    def __init__(self) -> None:
        try:
            import keyring  # noqa: F401

            self._keyring = keyring
        except ImportError as e:
            raise ImportError(
                "The 'keyring' package is required for macOS token storage. "
                "Install it with: pip install keyring"
            ) from e

    async def store(self, key: str, token_set: TokenSet) -> None:
        """Store token set in macOS Keychain."""
        data = _serialize_token_set(token_set)
        await asyncio.to_thread(self._keyring.set_password, SERVICE_NAME, key, data)

    async def retrieve(self, key: str) -> TokenSet | None:
        """Retrieve token set from macOS Keychain."""
        raw = await asyncio.to_thread(self._keyring.get_password, SERVICE_NAME, key)
        if raw is None:
            return None
        return _deserialize_token_set(raw)

    async def delete(self, key: str) -> None:
        """Delete token set from macOS Keychain."""
        try:
            await asyncio.to_thread(self._keyring.delete_password, SERVICE_NAME, key)
        except Exception:
            # Key may not exist; ignore deletion errors
            pass


class CredentialManagerStorage:
    """Windows token storage using Credential Manager via keyring."""

    def __init__(self) -> None:
        try:
            import keyring  # noqa: F401

            self._keyring = keyring
        except ImportError as e:
            raise ImportError(
                "The 'keyring' package is required for Windows token storage. "
                "Install it with: pip install keyring"
            ) from e

    async def store(self, key: str, token_set: TokenSet) -> None:
        """Store token set in Windows Credential Manager."""
        data = _serialize_token_set(token_set)
        await asyncio.to_thread(self._keyring.set_password, SERVICE_NAME, key, data)

    async def retrieve(self, key: str) -> TokenSet | None:
        """Retrieve token set from Windows Credential Manager."""
        raw = await asyncio.to_thread(self._keyring.get_password, SERVICE_NAME, key)
        if raw is None:
            return None
        return _deserialize_token_set(raw)

    async def delete(self, key: str) -> None:
        """Delete token set from Windows Credential Manager."""
        try:
            await asyncio.to_thread(self._keyring.delete_password, SERVICE_NAME, key)
        except Exception:
            # Key may not exist; ignore deletion errors
            pass


class EncryptedFileStorage:
    """Linux token storage using AES-256-GCM encrypted files with mode 600.

    Falls back to plaintext JSON with restricted file permissions if the
    'cryptography' package is not installed (reduced security).
    """

    def __init__(self, storage_dir: Path | None = None) -> None:
        self._storage_dir = storage_dir or Path.home() / ".ceramic" / "tokens"
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        # Ensure directory is owner-only
        os.chmod(self._storage_dir, 0o700)

        self._has_crypto = False
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401

            self._has_crypto = True
        except ImportError:
            logger.warning(
                "The 'cryptography' package is not installed. "
                "Token storage will use plaintext JSON with restricted file "
                "permissions (reduced security). Install 'cryptography' for "
                "AES-256-GCM encryption."
            )

    def _get_file_path(self, key: str) -> Path:
        """Get the file path for a given key."""
        # Sanitize key to be filesystem-safe
        safe_key = key.replace("/", "_").replace("\\", "_")
        return self._storage_dir / f"{safe_key}.json"

    def _derive_key(self) -> bytes:
        """Derive an AES-256 encryption key from machine-specific data."""
        # Use machine-specific salt for key derivation
        machine_id = _get_machine_id()
        salt = hashlib.sha256(machine_id.encode()).digest()

        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        # Use a static passphrase combined with the machine ID
        passphrase = f"ceramic-fwk-{machine_id}".encode()
        return kdf.derive(passphrase)

    def _encrypt(self, data: str) -> bytes:
        """Encrypt data using AES-256-GCM."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = self._derive_key()
        nonce = os.urandom(12)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, data.encode(), None)
        # Store nonce + ciphertext
        return nonce + ciphertext

    def _decrypt(self, encrypted: bytes) -> str:
        """Decrypt AES-256-GCM encrypted data."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = self._derive_key()
        nonce = encrypted[:12]
        ciphertext = encrypted[12:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode()

    async def store(self, key: str, token_set: TokenSet) -> None:
        """Store token set as an encrypted file."""
        file_path = self._get_file_path(key)
        data = _serialize_token_set(token_set)

        if self._has_crypto:
            content = self._encrypt(data)
            await asyncio.to_thread(self._write_binary, file_path, content)
        else:
            await asyncio.to_thread(self._write_text, file_path, data)

    async def retrieve(self, key: str) -> TokenSet | None:
        """Retrieve and decrypt token set from file."""
        file_path = self._get_file_path(key)
        if not file_path.exists():
            return None

        if self._has_crypto:
            content = await asyncio.to_thread(self._read_binary, file_path)
            if content is None:
                return None
            try:
                raw = self._decrypt(content)
            except Exception:
                logger.error("Failed to decrypt token file: %s", file_path)
                return None
        else:
            raw = await asyncio.to_thread(self._read_text, file_path)
            if raw is None:
                return None

        return _deserialize_token_set(raw)

    async def delete(self, key: str) -> None:
        """Delete token file."""
        file_path = self._get_file_path(key)
        if file_path.exists():
            await asyncio.to_thread(file_path.unlink)

    @staticmethod
    def _write_binary(path: Path, content: bytes) -> None:
        """Write binary content with restricted permissions."""
        path.write_bytes(content)
        os.chmod(path, 0o600)

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        """Write text content with restricted permissions."""
        path.write_text(content)
        os.chmod(path, 0o600)

    @staticmethod
    def _read_binary(path: Path) -> bytes | None:
        """Read binary content from file."""
        try:
            return path.read_bytes()
        except OSError:
            return None

    @staticmethod
    def _read_text(path: Path) -> str | None:
        """Read text content from file."""
        try:
            return path.read_text()
        except OSError:
            return None


def _get_machine_id() -> str:
    """Get a machine-specific identifier for key derivation.

    Uses platform-specific methods to find a stable machine identifier.
    Falls back to hostname + platform info if nothing better is available.
    """
    # Try Linux machine-id
    machine_id_path = Path("/etc/machine-id")
    if machine_id_path.exists():
        try:
            return machine_id_path.read_text().strip()
        except OSError:
            pass

    # Try DBus machine-id (another Linux location)
    dbus_path = Path("/var/lib/dbus/machine-id")
    if dbus_path.exists():
        try:
            return dbus_path.read_text().strip()
        except OSError:
            pass

    # Fallback: use hostname + platform node
    return f"{platform.node()}-{platform.machine()}-{os.getlogin()}"


def get_token_storage(storage_dir: Path | None = None) -> TokenStorage:
    """Auto-detect platform and return the appropriate TokenStorage backend.

    Args:
        storage_dir: Optional directory for EncryptedFileStorage (Linux).
                     Ignored on macOS/Windows.

    Returns:
        A platform-appropriate TokenStorage implementation.
    """
    if sys.platform == "darwin":
        return KeychainTokenStorage()
    elif sys.platform == "win32":
        return CredentialManagerStorage()
    else:
        return EncryptedFileStorage(storage_dir=storage_dir)
