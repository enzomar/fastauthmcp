"""Audit logging: structured, immutable records of security-relevant events.

Status: Planned — not yet wired into the middleware pipeline.

Captures authentication, authorization, token exchange, and tool invocation
events with full context for compliance and forensics.

Usage in fastauthmcp.yaml:

    audit:
      enabled: true
      sink: structured_log    # structured_log | file | webhook
      file_path: /var/log/fastauthmcp/audit.jsonl
      include_tool_args: false
      include_identity: true
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger("fastauthmcp.audit")


class AuditEventType(str, Enum):
    """Types of auditable events."""

    AUTH_SUCCESS = "auth.success"
    AUTH_FAILURE = "auth.failure"
    AUTH_REFRESH = "auth.refresh"
    AUTHZ_GRANTED = "authz.granted"
    AUTHZ_DENIED = "authz.denied"
    TOKEN_EXCHANGE = "token.exchange"
    TOKEN_EXCHANGE_FAILURE = "token.exchange.failure"
    TOOL_INVOKED = "tool.invoked"
    TOOL_ERROR = "tool.error"
    SESSION_CREATED = "session.created"
    SESSION_EXPIRED = "session.expired"
    CONFIG_RELOAD = "config.reload"


@dataclass
class AuditEvent:
    """A single audit log entry."""

    event_type: AuditEventType
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    request_id: str | None = None
    subject: str | None = None
    email: str | None = None
    tool_name: str | None = None
    client_ip: str | None = None
    outcome: str = "success"  # success | failure | denied
    details: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None


class AuditLogger:
    """Emits structured audit events.

    Supports multiple sinks:
    - structured_log: Python logging with JSON serialization
    - file: Append to a JSONL file
    - webhook: POST to an external endpoint (future)
    """

    def __init__(
        self,
        enabled: bool = True,
        sink: str = "structured_log",
        file_path: str | None = None,
        include_tool_args: bool = False,
        include_identity: bool = True,
    ) -> None:
        self._enabled = enabled
        self._sink = sink
        self._file_path = file_path
        self._include_tool_args = include_tool_args
        self._include_identity = include_identity

    def emit(self, event: AuditEvent) -> None:
        """Emit an audit event to the configured sink."""
        if not self._enabled:
            return

        record = self._serialize(event)

        if self._sink == "structured_log":
            logger.info(json.dumps(record, default=str))
        elif self._sink == "file" and self._file_path:
            try:
                with open(self._file_path, "a") as f:
                    f.write(json.dumps(record, default=str) + "\n")
            except OSError as exc:
                logger.error("Failed to write audit event to file: %s", exc)

    def auth_success(self, request_id: str | None, subject: str | None, email: str | None) -> None:
        """Record a successful authentication."""
        self.emit(
            AuditEvent(
                event_type=AuditEventType.AUTH_SUCCESS,
                request_id=request_id,
                subject=subject,
                email=email,
            )
        )

    def auth_failure(self, request_id: str | None, reason: str) -> None:
        """Record a failed authentication attempt."""
        self.emit(
            AuditEvent(
                event_type=AuditEventType.AUTH_FAILURE,
                request_id=request_id,
                outcome="failure",
                details={"reason": reason},
            )
        )

    def authz_denied(
        self,
        request_id: str | None,
        subject: str | None,
        tool_name: str | None,
        required: str,
    ) -> None:
        """Record an authorization denial."""
        self.emit(
            AuditEvent(
                event_type=AuditEventType.AUTHZ_DENIED,
                request_id=request_id,
                subject=subject,
                tool_name=tool_name,
                outcome="denied",
                details={"required": required},
            )
        )

    def tool_invoked(
        self,
        request_id: str | None,
        subject: str | None,
        tool_name: str | None,
        duration_ms: float | None = None,
    ) -> None:
        """Record a tool invocation."""
        self.emit(
            AuditEvent(
                event_type=AuditEventType.TOOL_INVOKED,
                request_id=request_id,
                subject=subject,
                tool_name=tool_name,
                duration_ms=duration_ms,
            )
        )

    def _serialize(self, event: AuditEvent) -> dict[str, Any]:
        """Convert an audit event to a JSON-serializable dict."""
        record = asdict(event)
        record["event_type"] = event.event_type.value
        # Remove None values for cleaner output
        return {k: v for k, v in record.items() if v is not None}
