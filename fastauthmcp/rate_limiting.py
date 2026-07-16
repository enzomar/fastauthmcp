"""Rate limiting middleware for MCP tool calls.

Status: Planned — not yet wired into the middleware pipeline.

Supports per-tool and per-user rate limiting with configurable windows
and burst allowances using the token bucket algorithm.

Usage in fastauthmcp.yaml:

    rate_limiting:
      enabled: true
      default_rpm: 60            # Requests per minute (default)
      default_burst: 10          # Burst allowance above steady rate
      per_tool:
        expensive_tool: 5        # Only 5 rpm for this tool
      per_user: true             # Apply limits per-user (vs global)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from fastauthmcp.middleware.pipeline import RequestContext

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""

    enabled: bool = True
    default_rpm: int = 60
    default_burst: int = 10
    per_tool: dict[str, int] = field(default_factory=dict)
    per_user: bool = True


class TokenBucket:
    """Token bucket rate limiter.

    Allows steady-state requests at `rate` per second with bursts up to `capacity`.
    """

    def __init__(self, rate: float, capacity: int) -> None:
        self._rate = rate  # tokens per second
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if allowed, False if rate-limited."""
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    @property
    def remaining(self) -> int:
        """Current available tokens."""
        self._refill()
        return int(self._tokens)

    @property
    def retry_after(self) -> float:
        """Seconds until the next token is available."""
        if self._tokens >= 1:
            return 0.0
        return (1 - self._tokens) / self._rate

    def _refill(self) -> None:
        """Add tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now


class RateLimiter:
    """Per-tool and per-user rate limiter.

    Maintains a bucket per (tool_name, user_subject) pair when per_user=True,
    or per tool_name when per_user=False.
    """

    def __init__(self, config: RateLimitConfig) -> None:
        self._config = config
        self._buckets: dict[str, TokenBucket] = {}

    def check(self, tool_name: str, subject: str | None = None) -> tuple[bool, float]:
        """Check if a request is allowed.

        Returns:
            (allowed, retry_after_seconds)
        """
        if not self._config.enabled:
            return True, 0.0

        key = self._bucket_key(tool_name, subject)
        bucket = self._buckets.get(key)

        if bucket is None:
            rpm = self._config.per_tool.get(tool_name, self._config.default_rpm)
            rate = rpm / 60.0  # Convert to per-second
            capacity = self._config.default_burst
            bucket = TokenBucket(rate=rate, capacity=capacity)
            self._buckets[key] = bucket

        allowed = bucket.consume()
        return allowed, bucket.retry_after

    def _bucket_key(self, tool_name: str, subject: str | None) -> str:
        """Generate the bucket key."""
        if self._config.per_user and subject:
            return f"{tool_name}:{subject}"
        return tool_name


class RateLimitingMiddleware:
    """Middleware that enforces rate limits on tool calls."""

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self._limiter = RateLimiter(config or RateLimitConfig())

    async def __call__(self, ctx: RequestContext, next: Callable[[], Awaitable[Any]]) -> Any:
        tool_name = ctx.tool_name
        if not tool_name:
            return await next()

        subject = ctx.identity.subject if ctx.identity else None
        allowed, retry_after = self._limiter.check(tool_name, subject)

        if not allowed:
            logger.warning(
                "Rate limit exceeded for tool '%s' (subject=%s, retry_after=%.1fs)",
                tool_name,
                subject,
                retry_after,
            )
            return {
                "error": "rate_limit_exceeded",
                "message": f"Rate limit exceeded for tool '{tool_name}'. Try again in {retry_after:.1f}s.",
                "retry_after": retry_after,
            }

        return await next()
