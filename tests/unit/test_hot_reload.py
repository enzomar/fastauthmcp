"""Unit tests for ConfigLoader hot-reload watcher (task 12.1).

Tests cover:
- watch() starts a daemon thread and detects file changes
- On valid change: callback is invoked with merged config (reloadable sections updated)
- On invalid change: previous config retained, warning logged
- auth and sessions sections are never reloaded
- INFO log emitted on successful reload
- stop_watching() stops the background thread
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from ceramic.config import (
    CeramicConfig,
)
from ceramic.config_loader import ConfigLoader


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """Create a minimal ceramic.yaml config file with hot_reload enabled."""
    config_data = {
        "observability": {
            "enabled": True,
            "log_level": "info",
        },
        "hot_reload": {
            "enabled": True,
            "watch_interval": 1,
            "reloadable_sections": ["observability"],
        },
    }
    config_path = tmp_path / "ceramic.yaml"
    config_path.write_text(yaml.dump(config_data), encoding="utf-8")
    return config_path


@pytest.fixture
def full_config_file(tmp_path: Path) -> Path:
    """Create a ceramic.yaml with auth and sessions (non-reloadable)."""
    config_data = {
        "auth": {
            "provider": "oidc",
            "issuer": "https://idp.example.com",
            "client_id": "test-client",
            "client_secret": "secret123",
        },
        "sessions": {
            "enabled": True,
            "ttl": 3600,
            "backend": "memory",
        },
        "observability": {
            "enabled": True,
            "log_level": "info",
        },
        "hot_reload": {
            "enabled": True,
            "watch_interval": 1,
            "reloadable_sections": ["observability"],
        },
    }
    config_path = tmp_path / "ceramic.yaml"
    config_path.write_text(yaml.dump(config_data), encoding="utf-8")
    return config_path


class TestWatchDetectsChanges:
    """Test that watch() detects file modifications and calls the callback."""

    def test_callback_invoked_on_valid_change(self, config_file: Path):
        """watch() calls callback when config file is modified with valid YAML."""
        loader = ConfigLoader()
        callback = MagicMock()

        loader.watch(callback, config_path=config_file, interval=1)
        try:
            # Modify the config file
            time.sleep(0.5)
            new_config = {
                "observability": {
                    "enabled": True,
                    "log_level": "debug",
                },
                "hot_reload": {
                    "enabled": True,
                    "watch_interval": 1,
                    "reloadable_sections": ["observability"],
                },
            }
            config_file.write_text(yaml.dump(new_config), encoding="utf-8")

            # Wait for the watcher to pick up the change
            time.sleep(2.5)

            assert callback.call_count >= 1
            reloaded_config = callback.call_args[0][0]
            assert isinstance(reloaded_config, CeramicConfig)
            assert reloaded_config.observability is not None
            assert reloaded_config.observability.log_level == "debug"
        finally:
            loader.stop_watching()

    def test_no_callback_when_file_unchanged(self, config_file: Path):
        """watch() does not call callback when file hasn't changed."""
        loader = ConfigLoader()
        callback = MagicMock()

        loader.watch(callback, config_path=config_file, interval=1)
        try:
            time.sleep(2.5)
            assert callback.call_count == 0
        finally:
            loader.stop_watching()


class TestInvalidConfigRetainsPrevious:
    """Test that invalid config changes don't trigger callback."""

    def test_invalid_yaml_retains_previous(self, config_file: Path, caplog):
        """Invalid YAML keeps previous config and logs warning."""
        loader = ConfigLoader()
        callback = MagicMock()

        loader.watch(callback, config_path=config_file, interval=1)
        try:
            time.sleep(0.5)
            # Write invalid YAML
            config_file.write_text("{{{{invalid yaml!!", encoding="utf-8")
            time.sleep(2.5)

            # Callback should NOT have been called
            assert callback.call_count == 0
        finally:
            loader.stop_watching()

    def test_invalid_config_values_retains_previous(self, config_file: Path, caplog):
        """Config with invalid values keeps previous config and logs warning."""
        loader = ConfigLoader()
        callback = MagicMock()

        loader.watch(callback, config_path=config_file, interval=1)
        try:
            time.sleep(0.5)
            # Write config with unknown top-level key (extra='forbid')
            invalid_config = {
                "unknown_section": {"foo": "bar"},
                "observability": {"enabled": True},
            }
            config_file.write_text(yaml.dump(invalid_config), encoding="utf-8")
            time.sleep(2.5)

            assert callback.call_count == 0
        finally:
            loader.stop_watching()


class TestNonReloadableSectionsBlocked:
    """Test that auth and sessions sections are never hot-reloaded."""

    def test_auth_section_not_reloaded(self, full_config_file: Path):
        """Changes to auth section are blocked during hot-reload."""
        loader = ConfigLoader()
        callback = MagicMock()

        loader.watch(callback, config_path=full_config_file, interval=1)
        try:
            time.sleep(0.5)

            # Change auth client_id AND observability log_level
            new_config = {
                "auth": {
                    "provider": "oidc",
                    "issuer": "https://idp.example.com",
                    "client_id": "changed-client",
                    "client_secret": "secret123",
                },
                "sessions": {
                    "enabled": True,
                    "ttl": 3600,
                    "backend": "memory",
                },
                "observability": {
                    "enabled": True,
                    "log_level": "debug",
                },
                "hot_reload": {
                    "enabled": True,
                    "watch_interval": 1,
                    "reloadable_sections": ["observability"],
                },
            }
            full_config_file.write_text(yaml.dump(new_config), encoding="utf-8")
            time.sleep(2.5)

            assert callback.call_count >= 1
            reloaded_config = callback.call_args[0][0]
            # Observability should be updated (reloadable)
            assert reloaded_config.observability.log_level == "debug"
            # Auth should NOT be updated (blocked)
            assert reloaded_config.auth.client_id == "test-client"
        finally:
            loader.stop_watching()

    def test_sessions_section_not_reloaded(self, full_config_file: Path):
        """Changes to sessions section are blocked during hot-reload."""
        loader = ConfigLoader()
        callback = MagicMock()

        loader.watch(callback, config_path=full_config_file, interval=1)
        try:
            time.sleep(0.5)

            # Change sessions TTL and observability
            new_config = {
                "auth": {
                    "provider": "oidc",
                    "issuer": "https://idp.example.com",
                    "client_id": "test-client",
                    "client_secret": "secret123",
                },
                "sessions": {
                    "enabled": True,
                    "ttl": 7200,
                    "backend": "memory",
                },
                "observability": {
                    "enabled": True,
                    "log_level": "warning",
                },
                "hot_reload": {
                    "enabled": True,
                    "watch_interval": 1,
                    "reloadable_sections": ["observability"],
                },
            }
            full_config_file.write_text(yaml.dump(new_config), encoding="utf-8")
            time.sleep(2.5)

            assert callback.call_count >= 1
            reloaded_config = callback.call_args[0][0]
            # Observability should be updated
            assert reloaded_config.observability.log_level == "warning"
            # Sessions should NOT be updated
            assert reloaded_config.sessions.ttl == 3600
        finally:
            loader.stop_watching()


class TestLogging:
    """Test that appropriate log messages are emitted."""

    def test_info_log_on_successful_reload(self, config_file: Path, caplog):
        """INFO log is emitted when config is successfully reloaded."""
        loader = ConfigLoader()
        callback = MagicMock()

        with caplog.at_level(logging.INFO, logger="ceramic.config_loader"):
            loader.watch(callback, config_path=config_file, interval=1)
            try:
                time.sleep(0.5)
                new_config = {
                    "observability": {
                        "enabled": True,
                        "log_level": "debug",
                    },
                    "hot_reload": {
                        "enabled": True,
                        "watch_interval": 1,
                        "reloadable_sections": ["observability"],
                    },
                }
                config_file.write_text(yaml.dump(new_config), encoding="utf-8")
                time.sleep(2.5)

                assert any(
                    "Configuration reloaded successfully" in record.message
                    for record in caplog.records
                )
            finally:
                loader.stop_watching()

    def test_warning_log_on_invalid_reload(self, config_file: Path, caplog):
        """WARNING log is emitted when config reload fails."""
        loader = ConfigLoader()
        callback = MagicMock()

        with caplog.at_level(logging.WARNING, logger="ceramic.config_loader"):
            loader.watch(callback, config_path=config_file, interval=1)
            try:
                time.sleep(0.5)
                config_file.write_text("not: {valid: [config", encoding="utf-8")
                time.sleep(2.5)

                assert any(
                    "Configuration reload failed" in record.message
                    for record in caplog.records
                )
            finally:
                loader.stop_watching()


class TestStopWatching:
    """Test that stop_watching() properly terminates the watch thread."""

    def test_stop_watching_terminates_thread(self, config_file: Path):
        """stop_watching() stops the background polling thread."""
        loader = ConfigLoader()
        callback = MagicMock()

        loader.watch(callback, config_path=config_file, interval=1)
        assert loader._watch_thread is not None
        assert loader._watch_thread.is_alive()

        loader.stop_watching()
        assert loader._watch_thread is None

    def test_watch_thread_is_daemon(self, config_file: Path):
        """The watch thread is daemonic (doesn't prevent process exit)."""
        loader = ConfigLoader()
        callback = MagicMock()

        loader.watch(callback, config_path=config_file, interval=1)
        try:
            assert loader._watch_thread.daemon is True
        finally:
            loader.stop_watching()

    def test_stop_watching_without_start(self):
        """stop_watching() is safe to call when no watcher is running."""
        loader = ConfigLoader()
        # Should not raise
        loader.stop_watching()
