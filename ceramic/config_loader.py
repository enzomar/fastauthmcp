"""Configuration loader for the Ceramic framework.

Handles YAML parsing, environment variable overrides, and configuration
resolution from multiple sources (path argument, CERAMIC_CONFIG env var,
or CWD ceramic.yaml).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import ValidationError

from ceramic.config import CeramicConfig
from ceramic.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Loads and validates Ceramic configuration from YAML files and env vars.

    Configuration Resolution Order:
        1. If `path` argument is provided, use it directly
        2. If CERAMIC_CONFIG env var is set, use that path
        3. Otherwise, look for ceramic.yaml in CWD
        4. If no config found anywhere, return empty CeramicConfig (passthrough)
    """

    def load(self, path: Path | None = None) -> CeramicConfig:
        """Load and validate configuration from a YAML file.

        Args:
            path: Explicit path to a ceramic.yaml file. If None, resolution
                  order is applied (env var, then CWD).

        Returns:
            A validated CeramicConfig instance.

        Raises:
            ConfigurationError: If the config file is missing (when CERAMIC_CONFIG
                is set), contains invalid YAML, or has unknown top-level keys.
        """
        resolved_path = self._resolve_path(path)

        if resolved_path is None:
            # No config found anywhere — passthrough mode
            return CeramicConfig()

        raw_data = self._read_yaml(resolved_path)
        config = self._validate(raw_data)
        config = self.apply_env_overrides(config)
        return config

    def apply_env_overrides(self, config: CeramicConfig) -> CeramicConfig:
        """Apply CERAMIC_-prefixed environment variable overrides to config.

        Converts env var names to config dot-paths:
            CERAMIC_AUTH_PROVIDER → auth.provider

        Only scalar values (str, int, bool) are overridden. If the target
        path resolves to a list or object in the current config, the override
        is skipped.

        Args:
            config: The current configuration to apply overrides to.

        Returns:
            A new CeramicConfig with env var overrides applied.
        """
        config_dict = config.model_dump(mode="json", exclude_none=True)
        overrides_applied = False

        for key, value in os.environ.items():
            if not key.startswith("CERAMIC_"):
                continue

            # Skip the CERAMIC_CONFIG env var — it's for path resolution
            if key == "CERAMIC_CONFIG":
                continue

            # Convert CERAMIC_AUTH_PROVIDER → ["auth", "provider"]
            parts = key[len("CERAMIC_") :].lower().split("_")
            dot_path = parts

            # Try to apply the override
            if self._apply_scalar_override(config_dict, dot_path, value):
                overrides_applied = True

        if not overrides_applied:
            return config

        # Rebuild config from the modified dict
        try:
            return CeramicConfig.model_validate(config_dict)
        except ValidationError as exc:
            msg = f"Configuration error after applying env overrides: {exc}"
            print(msg, file=sys.stderr)
            raise ConfigurationError(msg) from exc

    def watch(
        self,
        callback: Callable[[CeramicConfig], None],
        config_path: Path | None = None,
        interval: int = 5,
    ) -> None:
        """Start watching the configuration file for changes.

        Starts a daemonic background thread that polls the config file's
        modification time at the specified interval. When a change is detected:
        - Re-reads and validates the YAML
        - If valid: atomically swaps only reloadable sections (observability,
          authorization), retaining auth and sessions from the previous config
        - If invalid: logs WARNING and retains the previous config

        Args:
            callback: Function called with the new CeramicConfig on successful reload.
            config_path: Path to the config file to watch. If None, uses resolution order.
            interval: Seconds between file modification time checks.
        """
        resolved_path = self._resolve_path(config_path)
        if resolved_path is None:
            logger.warning("No configuration file found to watch")
            return

        self._watch_stop_event = threading.Event()
        self._current_config = self.load(config_path)
        self._last_mtime = os.path.getmtime(resolved_path)

        def _poll_loop() -> None:
            while not self._watch_stop_event.is_set():
                self._watch_stop_event.wait(timeout=interval)
                if self._watch_stop_event.is_set():
                    break

                try:
                    current_mtime = os.path.getmtime(resolved_path)
                except OSError:
                    continue

                if current_mtime == self._last_mtime:
                    continue

                self._last_mtime = current_mtime

                # Re-read and validate
                try:
                    raw_data = self._read_yaml(resolved_path)
                    new_config = self._validate(raw_data)
                    new_config = self.apply_env_overrides(new_config)
                except (ConfigurationError, ValidationError) as exc:
                    logger.warning("Configuration reload failed: %s", exc)
                    continue

                # Determine reloadable sections from the hot_reload config
                reloadable = {"observability", "authorization"}
                if new_config.hot_reload:
                    reloadable = set(new_config.hot_reload.reloadable_sections)

                # Block reload of auth and sessions — keep from previous config
                merged_data = new_config.model_dump(mode="json", exclude_none=True)
                prev_data = self._current_config.model_dump(
                    mode="json", exclude_none=True
                )

                # For non-reloadable sections, retain previous values
                non_reloadable = {"auth", "sessions"}
                for section in non_reloadable:
                    if section in prev_data:
                        merged_data[section] = prev_data[section]
                    elif section in merged_data:
                        del merged_data[section]

                # Also preserve any other sections not in reloadable set
                all_sections = set(merged_data.keys()) | set(prev_data.keys())
                for section in all_sections:
                    if section in non_reloadable:
                        continue
                    if section in reloadable:
                        continue
                    # Non-reloadable, non-explicitly-blocked: keep previous
                    if section in prev_data:
                        merged_data[section] = prev_data[section]
                    elif section in merged_data:
                        del merged_data[section]

                try:
                    merged_config = CeramicConfig.model_validate(merged_data)
                except ValidationError as exc:
                    logger.warning("Configuration reload failed during merge: %s", exc)
                    continue

                self._current_config = merged_config
                logger.info("Configuration reloaded successfully")
                callback(merged_config)

        self._watch_thread = threading.Thread(
            target=_poll_loop, name="ceramic-config-watcher", daemon=True
        )
        self._watch_thread.start()

    def stop_watching(self) -> None:
        """Stop the file watcher background thread."""
        if hasattr(self, "_watch_stop_event") and self._watch_stop_event is not None:
            self._watch_stop_event.set()
        if hasattr(self, "_watch_thread") and self._watch_thread is not None:
            self._watch_thread.join(timeout=5)
            self._watch_thread = None

    def _resolve_path(self, path: Path | None) -> Path | None:
        """Resolve the configuration file path using resolution order.

        Returns:
            The resolved Path, or None if no config file is found.

        Raises:
            ConfigurationError: If CERAMIC_CONFIG is set but file doesn't exist.
        """
        # 1. Explicit path argument
        if path is not None:
            if not path.exists():
                msg = f"Configuration file not found: {path}"
                print(msg, file=sys.stderr)
                raise ConfigurationError(msg)
            return path

        # 2. CERAMIC_CONFIG env var
        env_path = os.environ.get("CERAMIC_CONFIG")
        if env_path is not None:
            p = Path(env_path)
            if not p.exists():
                msg = f"Configuration file not found: {p}"
                print(msg, file=sys.stderr)
                raise ConfigurationError(msg)
            return p

        # 3. CWD ceramic.yaml
        cwd_path = Path.cwd() / "ceramic.yaml"
        if cwd_path.exists():
            return cwd_path

        # 4. No config found — passthrough mode
        return None

    def _read_yaml(self, path: Path) -> dict[str, Any]:
        """Read and parse a YAML file.

        Returns:
            The parsed YAML content as a dict.

        Raises:
            ConfigurationError: If the YAML is invalid.
        """
        try:
            content = path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            msg = f"Invalid YAML in {path}: {exc}"
            print(msg, file=sys.stderr)
            raise ConfigurationError(msg) from exc

        # Handle empty YAML file
        if data is None:
            return {}

        if not isinstance(data, dict):
            msg = f"Invalid YAML in {path}: expected a mapping at top level"
            print(msg, file=sys.stderr)
            raise ConfigurationError(msg)

        return data

    def _validate(self, data: dict[str, Any]) -> CeramicConfig:
        """Validate parsed YAML data against the CeramicConfig model.

        Raises:
            ConfigurationError: If validation fails (e.g., unknown top-level keys).
        """
        try:
            return CeramicConfig.model_validate(data)
        except ValidationError as exc:
            msg = f"Configuration validation error: {exc}"
            print(msg, file=sys.stderr)
            raise ConfigurationError(msg) from exc

    def _apply_scalar_override(
        self, data: dict[str, Any], path_parts: list[str], value: str
    ) -> bool:
        """Attempt to apply a scalar override at the given path.

        Walks the config dict following path_parts. If the final value is a
        scalar (or the path doesn't exist yet but the parent is a dict), applies
        the override.

        For paths with more segments than two levels, we try greedy matching:
        e.g., CERAMIC_AUTH_CALLBACK_TIMEOUT → try auth.callback_timeout first,
        then auth.callback.timeout, etc.

        Returns:
            True if an override was applied, False otherwise.
        """
        # Try all possible segmentations of path_parts into a nested key path
        # E.g., ["auth", "callback", "timeout"] could be:
        #   auth → callback_timeout (2 segments: key=auth, field=callback_timeout)
        #   auth → callback → timeout (3 segments — unlikely in flat pydantic models)
        return self._try_override_recursive(data, path_parts, 0, value)

    def _try_override_recursive(
        self, data: dict[str, Any], parts: list[str], start: int, value: str
    ) -> bool:
        """Recursively try to match path segments to dict keys.

        For each position, try joining remaining parts as underscore-separated
        keys at each nesting level.
        """
        if start >= len(parts):
            return False

        # Try increasingly longer prefixes at this level
        for end in range(start + 1, len(parts) + 1):
            key = "_".join(parts[start:end])

            if key not in data:
                continue

            if end == len(parts):
                # We've consumed all parts — this is the target
                current_value = data[key]
                if self._is_scalar(current_value):
                    data[key] = self._parse_env_value(value)
                    return True
                # Target is non-scalar (list/dict) — skip
                return False

            # There are more parts — descend into nested dict
            if isinstance(data[key], dict):
                if self._try_override_recursive(data[key], parts, end, value):
                    return True

        return False

    @staticmethod
    def _is_scalar(value: Any) -> bool:
        """Check if a value is a scalar (not a list or dict)."""
        return not isinstance(value, (list, dict))

    @staticmethod
    def _parse_env_value(value: str) -> str | int | bool:
        """Parse an environment variable value into a Python type.

        Boolean parsing: "true"/"1" → True, "false"/"0" → False
        Int parsing: attempt int() for numeric strings
        Otherwise: return as string
        """
        lower = value.lower()
        if lower in ("true", "1"):
            return True
        if lower in ("false", "0"):
            return False

        try:
            return int(value)
        except ValueError:
            pass

        return value
