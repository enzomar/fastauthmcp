"""Graceful degradation: continue serving when auth infrastructure is unavailable.

Status: Planned — not yet wired into the middleware pipeline.

When the identity provider is down (circuit breaker open), FastAuthMCP can
optionally degrade gracefully rather than rejecting all requests:

1. Allow previously-authenticated sessions to continue (stale identity)
2. Allow specific tools marked as "public" to execute without auth
3. Return degraded-mode indicators so tools can adjust behavior

Usage in fastauthmcp.yaml:

    auth:
      graceful_degradation:
        enabled: true
        allow_stale_sessions: true      # Trust existing sessions during outage
        public_tools: ["health", "status"]  # These never require auth
        max_stale_age: 600              # Max seconds to trust stale identity
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DegradationConfig:
    """Graceful degradation configuration."""

    enabled: bool = False
    allow_stale_sessions: bool = True
    public_tools: list[str] = field(default_factory=list)
    max_stale_age: int = 600  # seconds


class DegradationState:
    """Tracks whether the system is in degraded mode.

    Toggled by the circuit breaker when the IdP becomes unavailable.
    """

    def __init__(self, config: DegradationConfig) -> None:
        self._config = config
        self._degraded_since: float | None = None
        self._public_tools: frozenset[str] = frozenset(config.public_tools)

    @property
    def is_degraded(self) -> bool:
        """Whether the system is currently in degraded mode."""
        return self._degraded_since is not None

    @property
    def degraded_duration(self) -> float:
        """Seconds spent in degraded mode (0 if not degraded)."""
        if self._degraded_since is None:
            return 0.0
        return time.monotonic() - self._degraded_since

    def enter_degraded_mode(self) -> None:
        """Enter degraded mode (called when circuit breaker opens)."""
        if self._degraded_since is None:
            self._degraded_since = time.monotonic()
            logger.warning(
                "Entering graceful degradation mode — IdP unavailable, using cached identities"
            )

    def exit_degraded_mode(self) -> None:
        """Exit degraded mode (called when circuit breaker closes)."""
        if self._degraded_since is not None:
            duration = time.monotonic() - self._degraded_since
            self._degraded_since = None
            logger.info("Exiting graceful degradation mode after %.1fs", duration)

    def is_public_tool(self, tool_name: str) -> bool:
        """Check if a tool is marked as public (always allowed)."""
        return tool_name in self._public_tools

    def should_allow_stale(self, identity_age: float) -> bool:
        """Check if a stale identity should be trusted during degradation.

        Args:
            identity_age: Seconds since the identity was last validated.

        Returns:
            True if the stale identity should be accepted.
        """
        if not self._config.enabled:
            return False
        if not self._config.allow_stale_sessions:
            return False
        return identity_age <= self._config.max_stale_age
