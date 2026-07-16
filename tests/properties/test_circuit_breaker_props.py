"""Property-based tests for CircuitBreaker state machine invariants.

Uses Hypothesis to generate arbitrary sequences of success/failure outcomes
and verifies the state machine never reaches an invalid state.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import httpx
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from fastauthmcp.resilience import CircuitBreaker, CircuitState

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# An outcome is either success (True) or failure (False)
outcome_sequences = st.lists(st.booleans(), min_size=1, max_size=50)

# Reasonable thresholds for the circuit breaker
thresholds = st.integers(min_value=1, max_value=10)
cooldowns = st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_success_coro():
    """Create a coroutine factory that succeeds."""

    async def _coro():
        return "ok"

    return _coro


def _make_failure_coro():
    """Create a coroutine factory that raises a 500 error."""

    async def _coro():
        resp = MagicMock()
        resp.status_code = 500
        raise httpx.HTTPStatusError("Server Error", request=MagicMock(), response=resp)

    return _coro


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


class TestCircuitBreakerProperties:
    """State machine invariants for the circuit breaker."""

    @given(outcomes=outcome_sequences, threshold=thresholds)
    @settings(max_examples=200)
    def test_failure_count_never_negative(self, outcomes, threshold):
        """The internal failure counter should never go below zero."""
        cb = CircuitBreaker(failure_threshold=threshold, cooldown_seconds=1000)

        for success in outcomes:
            try:
                if success:
                    asyncio.run(cb.execute(_make_success_coro()))
                else:
                    asyncio.run(cb.execute(_make_failure_coro()))
            except (httpx.HTTPStatusError, Exception):
                pass  # Expected for failures or open circuit

            assert cb._failure_count >= 0

    @given(outcomes=outcome_sequences, threshold=thresholds)
    @settings(max_examples=200)
    def test_state_is_always_valid(self, outcomes, threshold):
        """The circuit breaker state is always one of the valid states."""
        cb = CircuitBreaker(failure_threshold=threshold, cooldown_seconds=1000)

        valid_states = {CircuitState.CLOSED, CircuitState.OPEN, CircuitState.HALF_OPEN}

        for success in outcomes:
            try:
                if success:
                    asyncio.run(cb.execute(_make_success_coro()))
                else:
                    asyncio.run(cb.execute(_make_failure_coro()))
            except (httpx.HTTPStatusError, Exception):
                pass

            assert cb.state in valid_states

    @given(outcomes=outcome_sequences, threshold=thresholds)
    @settings(max_examples=200)
    def test_opens_at_threshold(self, outcomes, threshold):
        """Circuit opens if and only if consecutive failures reach threshold."""
        cb = CircuitBreaker(failure_threshold=threshold, cooldown_seconds=1000)
        consecutive_failures = 0

        for success in outcomes:
            if cb.state == CircuitState.OPEN:
                # Once open with long cooldown, it stays open
                break

            try:
                if success:
                    asyncio.run(cb.execute(_make_success_coro()))
                    consecutive_failures = 0
                else:
                    asyncio.run(cb.execute(_make_failure_coro()))
            except httpx.HTTPStatusError:
                consecutive_failures += 1
            except Exception:
                pass

            if consecutive_failures >= threshold:
                assert cb._state == CircuitState.OPEN

    @given(threshold=thresholds)
    @settings(max_examples=50)
    def test_success_resets_failure_count(self, threshold):
        """A successful call always resets the failure count to zero."""
        cb = CircuitBreaker(failure_threshold=threshold, cooldown_seconds=1000)

        # Accumulate some failures (but don't trip the breaker)
        failures_to_add = min(threshold - 1, 3)
        for _ in range(failures_to_add):
            try:
                asyncio.run(cb.execute(_make_failure_coro()))
            except (httpx.HTTPStatusError, Exception):
                pass

        assume(cb._state == CircuitState.CLOSED)

        # A success should reset
        asyncio.run(cb.execute(_make_success_coro()))
        assert cb._failure_count == 0

    @given(threshold=thresholds)
    @settings(max_examples=50)
    def test_failure_count_bounded_by_threshold(self, threshold):
        """Failure count should never exceed the threshold (circuit opens at threshold)."""
        cb = CircuitBreaker(failure_threshold=threshold, cooldown_seconds=1000)

        # Feed more failures than the threshold
        for _ in range(threshold + 5):
            try:
                asyncio.run(cb.execute(_make_failure_coro()))
            except (httpx.HTTPStatusError, Exception):
                pass

        # Count should be <= threshold (at threshold it opens and stops counting)
        assert cb._failure_count <= threshold
