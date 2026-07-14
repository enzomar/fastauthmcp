"""Property-based tests for CircuitBreaker state machine.

Verifies state transition invariants regardless of failure/success sequence.
"""

from __future__ import annotations

import asyncio

from hypothesis import given, strategies as st

from ceramic.resilience import CircuitBreaker, CircuitState


@given(threshold=st.integers(min_value=1, max_value=20))
def test_starts_in_closed_state(threshold: int) -> None:
    """Circuit breaker always starts in CLOSED state."""
    cb = CircuitBreaker(failure_threshold=threshold, cooldown_seconds=1.0)
    assert cb.state == CircuitState.CLOSED


@given(threshold=st.integers(min_value=1, max_value=10))
def test_opens_exactly_at_threshold(threshold: int) -> None:
    """Circuit opens after exactly failure_threshold consecutive failures."""

    async def run():
        cb = CircuitBreaker(failure_threshold=threshold, cooldown_seconds=60.0)

        for i in range(threshold - 1):
            await cb._record_failure()
            assert cb.state == CircuitState.CLOSED, (
                f"Opened too early at failure {i + 1}/{threshold}"
            )

        await cb._record_failure()
        assert cb.state == CircuitState.OPEN, f"Did not open at threshold {threshold}"

    asyncio.run(run())


@given(threshold=st.integers(min_value=1, max_value=10))
def test_success_resets_failure_count(threshold: int) -> None:
    """A success in CLOSED state resets the failure counter to zero."""

    async def run():
        cb = CircuitBreaker(failure_threshold=threshold, cooldown_seconds=60.0)

        # Accumulate failures just below threshold
        for _ in range(threshold - 1):
            await cb._record_failure()

        # One success should reset
        await cb._record_success()

        # Now we should need threshold failures again to open
        for _ in range(threshold - 1):
            await cb._record_failure()
        assert cb.state == CircuitState.CLOSED

        await cb._record_failure()
        assert cb.state == CircuitState.OPEN

    asyncio.run(run())


def test_reset_returns_to_closed() -> None:
    """reset() always returns the breaker to CLOSED state."""

    async def run():
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=60.0)

        # Open the circuit
        await cb._record_failure()
        await cb._record_failure()
        assert cb.state == CircuitState.OPEN

        # Reset
        cb.reset()
        assert cb.state == CircuitState.CLOSED

    asyncio.run(run())


@given(
    failures_before=st.integers(min_value=0, max_value=5),
    successes_between=st.integers(min_value=1, max_value=3),
)
def test_intermittent_failures_dont_open(
    failures_before: int, successes_between: int
) -> None:
    """Non-consecutive failures (interrupted by successes) don't open the circuit."""

    async def run():
        threshold = 5
        cb = CircuitBreaker(failure_threshold=threshold, cooldown_seconds=60.0)

        # Record some failures
        for _ in range(min(failures_before, threshold - 1)):
            await cb._record_failure()

        # Interrupt with successes
        for _ in range(successes_between):
            await cb._record_success()

        # Circuit should still be closed (success resets counter)
        assert cb.state == CircuitState.CLOSED

    asyncio.run(run())
