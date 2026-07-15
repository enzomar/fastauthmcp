"""Unit tests for the middleware pipeline executor."""

from __future__ import annotations

import pytest

from fastauthmcp.middleware.pipeline import (
    MiddlewarePipeline,
    RequestContext,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_tracking_middleware(name: str, call_log: list[str]):
    """Create an async middleware that logs its name before and after calling next."""

    async def middleware(ctx: RequestContext, next):
        call_log.append(f"{name}:before")
        result = await next()
        call_log.append(f"{name}:after")
        return result

    return middleware


def make_short_circuit_middleware(name: str, response: object, call_log: list[str]):
    """Create a middleware that returns a response without calling next."""

    async def middleware(ctx: RequestContext, next):
        call_log.append(f"{name}:short-circuit")
        return response

    return middleware


def make_raising_middleware(name: str, exc: Exception, call_log: list[str]):
    """Create a middleware that raises an exception."""

    async def middleware(ctx: RequestContext, next):
        call_log.append(f"{name}:raising")
        raise exc

    return middleware


# ---------------------------------------------------------------------------
# Tests: Execution Order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_before_hooks_execute_in_registration_order():
    """Before-hooks run first-registered-first."""
    pipeline = MiddlewarePipeline()
    log: list[str] = []

    pipeline.add_before(make_tracking_middleware("A", log))
    pipeline.add_before(make_tracking_middleware("B", log))
    pipeline.add_before(make_tracking_middleware("C", log))

    async def handler():
        log.append("handler")
        return "result"

    ctx = RequestContext()
    result = await pipeline.execute(ctx, handler)

    assert result == "result"
    assert log == [
        "A:before",
        "B:before",
        "C:before",
        "handler",
        "C:after",
        "B:after",
        "A:after",
    ]


@pytest.mark.asyncio
async def test_after_hooks_execute_in_reverse_registration_order():
    """After-hooks run last-registered-first (reverse order)."""
    pipeline = MiddlewarePipeline()
    log: list[str] = []

    async def after_A(ctx, next):
        log.append("after_A")
        result = await next()
        return result

    async def after_B(ctx, next):
        log.append("after_B")
        result = await next()
        return result

    async def after_C(ctx, next):
        log.append("after_C")
        result = await next()
        return result

    pipeline.add_after(after_A)
    pipeline.add_after(after_B)
    pipeline.add_after(after_C)

    async def handler():
        log.append("handler")
        return "result"

    ctx = RequestContext()
    result = await pipeline.execute(ctx, handler)

    assert result == "result"
    # After-hooks in reverse: C first, then B, then A
    assert log == ["handler", "after_C", "after_B", "after_A"]


@pytest.mark.asyncio
async def test_empty_pipeline_calls_handler_directly():
    """With no middleware, the handler is invoked directly."""
    pipeline = MiddlewarePipeline()

    async def handler():
        return "direct"

    ctx = RequestContext()
    result = await pipeline.execute(ctx, handler)
    assert result == "direct"


# ---------------------------------------------------------------------------
# Tests: Short-Circuit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_short_circuit_prevents_subsequent_middleware_and_handler():
    """A middleware that returns without calling next short-circuits the chain."""
    pipeline = MiddlewarePipeline()
    log: list[str] = []

    pipeline.add_before(make_tracking_middleware("A", log))
    pipeline.add_before(make_short_circuit_middleware("B", "short", log))
    pipeline.add_before(make_tracking_middleware("C", log))

    handler_called = False

    async def handler():
        nonlocal handler_called
        handler_called = True
        return "should not reach"

    ctx = RequestContext()
    result = await pipeline.execute(ctx, handler)

    assert result == "short"
    assert not handler_called
    # A wraps B; B short-circuits before C or handler run.
    # A's before ran, B short-circuited, A's after ran (because B returned).
    assert "C:before" not in log
    assert "B:short-circuit" in log


@pytest.mark.asyncio
async def test_short_circuit_response_is_returned_to_caller():
    """The short-circuit value is the final response."""
    pipeline = MiddlewarePipeline()
    log: list[str] = []

    sentinel = {"status": "denied", "reason": "unauthorized"}
    pipeline.add_before(make_short_circuit_middleware("authz", sentinel, log))

    async def handler():
        return "ok"

    ctx = RequestContext()
    result = await pipeline.execute(ctx, handler)
    assert result is sentinel


# ---------------------------------------------------------------------------
# Tests: Exception Routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exception_routes_to_on_exception_handler():
    """Unhandled exceptions in before-middleware route to on_exception handlers."""
    pipeline = MiddlewarePipeline()
    log: list[str] = []
    caught_exc = None

    async def boom(ctx, next):
        raise ValueError("something broke")

    async def exc_handler(ctx, next):
        nonlocal caught_exc
        caught_exc = ctx.metadata.get("exception")
        log.append("exc_handler")
        return {"error": "handled", "detail": str(caught_exc)}

    pipeline.add_before(boom)
    pipeline.add_exception_handler(exc_handler)

    async def handler():
        return "ok"

    ctx = RequestContext()
    result = await pipeline.execute(ctx, handler)

    assert result == {"error": "handled", "detail": "something broke"}
    assert "exc_handler" in log
    assert isinstance(caught_exc, ValueError)


@pytest.mark.asyncio
async def test_exception_never_propagates_to_caller():
    """Even without on_exception handlers, exceptions do not propagate."""
    pipeline = MiddlewarePipeline()

    async def boom(ctx, next):
        raise RuntimeError("kaboom")

    pipeline.add_before(boom)

    async def handler():
        return "ok"

    ctx = RequestContext()
    # Should NOT raise — returns generic error instead.
    result = await pipeline.execute(ctx, handler)
    assert result["error"] == "internal_error"


@pytest.mark.asyncio
async def test_secondary_exception_in_on_exception_returns_generic_error():
    """If on_exception handler raises, return generic error (never propagate)."""
    pipeline = MiddlewarePipeline()

    async def boom(ctx, next):
        raise ValueError("primary")

    async def bad_handler(ctx, next):
        raise RuntimeError("secondary failure in handler")

    pipeline.add_before(boom)
    pipeline.add_exception_handler(bad_handler)

    async def handler():
        return "ok"

    ctx = RequestContext()
    result = await pipeline.execute(ctx, handler)

    assert result["error"] == "internal_error"
    assert "internal error" in result["message"].lower()


@pytest.mark.asyncio
async def test_handler_exception_routes_to_on_exception():
    """Exceptions raised by the final handler also route through on_exception."""
    pipeline = MiddlewarePipeline()
    caught_exc = None

    async def exc_handler(ctx, next):
        nonlocal caught_exc
        caught_exc = ctx.metadata.get("exception")
        return {"error": "caught_handler_exc"}

    pipeline.add_exception_handler(exc_handler)

    async def handler():
        raise TypeError("handler failed")

    ctx = RequestContext()
    result = await pipeline.execute(ctx, handler)

    assert result == {"error": "caught_handler_exc"}
    assert isinstance(caught_exc, TypeError)


# ---------------------------------------------------------------------------
# Tests: RequestContext
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_context_default_values():
    """RequestContext provides sensible defaults."""
    ctx = RequestContext()
    assert ctx.identity is None
    assert ctx.session is None
    assert ctx.request_id  # non-empty UUID string
    assert ctx.tool_name is None
    assert ctx.metadata == {}


@pytest.mark.asyncio
async def test_request_context_custom_values():
    """RequestContext accepts custom values."""
    ctx = RequestContext(
        request_id="req-123",
        tool_name="my_tool",
        metadata={"key": "value"},
    )
    assert ctx.request_id == "req-123"
    assert ctx.tool_name == "my_tool"
    assert ctx.metadata == {"key": "value"}


@pytest.mark.asyncio
async def test_middleware_can_mutate_context():
    """Middleware can modify the RequestContext for downstream consumers."""
    pipeline = MiddlewarePipeline()

    async def mutating_mw(ctx: RequestContext, next):
        ctx.metadata["injected"] = True
        ctx.tool_name = "overridden"
        return await next()

    pipeline.add_before(mutating_mw)

    captured_ctx = None

    async def handler():
        nonlocal captured_ctx
        captured_ctx = True
        return "ok"

    ctx = RequestContext(tool_name="original")
    await pipeline.execute(ctx, handler)

    assert ctx.metadata["injected"] is True
    assert ctx.tool_name == "overridden"
