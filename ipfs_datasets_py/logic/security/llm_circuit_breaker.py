"""
LLM Circuit Breaker — guards downstream LLM API calls.

Implements the classic circuit-breaker pattern:
  CLOSED  → normal operation
  OPEN    → all calls rejected immediately
  HALF_OPEN → one probe call allowed; success → CLOSED, failure → OPEN
"""

import time
import threading
import functools
from enum import Enum
from typing import Any, Callable, Dict, Optional


# ---------------------------------------------------------------------------
# State Enum
# ---------------------------------------------------------------------------

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CircuitBreakerOpenError(Exception):
    """Raised when a call is rejected because the circuit is OPEN."""


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class CircuitBreakerMetrics:
    """Thread-safe counters and latency samples for a single circuit breaker."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.success_count: int = 0
        self.failure_count: int = 0
        self.state_transitions: int = 0
        self.latencies: list = []

    @property
    def total_calls(self) -> int:
        """Total calls recorded (successes + failures)."""
        return self.success_count + self.failure_count

    def record_success(self, latency: float) -> None:
        with self._lock:
            self.success_count += 1
            self.latencies.append(latency)

    def record_failure(self, latency: float) -> None:
        with self._lock:
            self.failure_count += 1
            self.latencies.append(latency)

    def record_state_transition(self) -> None:
        with self._lock:
            self.state_transitions += 1

    def reset(self) -> None:
        with self._lock:
            self.success_count = 0
            self.failure_count = 0
            self.state_transitions = 0
            self.latencies = []


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class LLMCircuitBreaker:
    """
    Circuit breaker for LLM/API calls.

    Parameters
    ----------
    failure_threshold:
        Number of consecutive failures required to open the circuit.
    timeout_seconds:
        Seconds the circuit stays OPEN before transitioning to HALF_OPEN.
    success_threshold:
        Consecutive successes in HALF_OPEN required to close the circuit.
    name:
        Identifier used in error messages.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        timeout_seconds: float = 60.0,
        success_threshold: int = 1,
        name: str = "llm_circuit_breaker",
    ) -> None:
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.success_threshold = success_threshold
        self.name = name

        self._state = CircuitState.CLOSED
        self._lock = threading.Lock()
        self._open_time: Optional[float] = None
        self._half_open_successes: int = 0
        self.metrics = CircuitBreakerMetrics()

    # ------------------------------------------------------------------
    # Public state property
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        return self._state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_half_open_transition(self) -> None:
        """Transition from OPEN → HALF_OPEN if the timeout has elapsed."""
        if (
            self._state == CircuitState.OPEN
            and self._open_time is not None
            and time.time() - self._open_time >= self.timeout_seconds
        ):
            self._state = CircuitState.HALF_OPEN
            self._half_open_successes = 0

    def _on_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_successes += 1
            if self._half_open_successes >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._open_time = None
                self._half_open_successes = 0
                self.metrics.record_state_transition()
        # In CLOSED state nothing changes; metrics are updated by the caller.

    def _on_failure(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            # A failure in HALF_OPEN reopens immediately.
            self._state = CircuitState.OPEN
            self._open_time = time.time()
            self.metrics.record_state_transition()
        elif self._state == CircuitState.CLOSED:
            if self.metrics.failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._open_time = time.time()
                self.metrics.record_state_transition()

    # ------------------------------------------------------------------
    # Main call interface
    # ------------------------------------------------------------------

    def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Execute *func* through the circuit breaker.

        Raises
        ------
        CircuitBreakerOpenError
            If the circuit is OPEN and the timeout has not elapsed.
        Any exception raised by *func*
            Propagated after recording the failure.
        """
        with self._lock:
            self._check_half_open_transition()
            if self._state == CircuitState.OPEN:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is OPEN"
                )

        start = time.monotonic()
        try:
            result = func(*args, **kwargs)
        except Exception:
            latency = time.monotonic() - start
            self.metrics.record_failure(latency)
            with self._lock:
                self._on_failure()
            raise
        else:
            latency = time.monotonic() - start
            self.metrics.record_success(latency)
            with self._lock:
                self._on_success()
            return result

    # ------------------------------------------------------------------
    # Decorator interface
    # ------------------------------------------------------------------

    def protected(self, func: Callable) -> Callable:
        """Decorator that wraps *func* with this circuit breaker."""
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return self.call(func, *args, **kwargs)
        return wrapper

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset metrics. State is preserved (set to CLOSED)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._open_time = None
            self._half_open_successes = 0
        self.metrics.reset()

    def refresh_state(self) -> None:
        """
        Explicitly trigger state-machine evaluation.

        Useful for testing: call after sleeping past ``timeout_seconds`` to
        force the OPEN→HALF_OPEN transition without waiting for the next
        ``call()``.
        """
        with self._lock:
            prev = self._state
            self._check_half_open_transition()
            if self._state != prev:
                self.metrics.record_state_transition()


# ---------------------------------------------------------------------------
# Global registry
# ---------------------------------------------------------------------------

_registry: Dict[str, LLMCircuitBreaker] = {}
_registry_lock = threading.Lock()


def get_circuit_breaker(name: str, **kwargs: Any) -> LLMCircuitBreaker:
    """
    Return the singleton circuit breaker for *name*, creating it if needed.

    Keyword arguments are forwarded to ``LLMCircuitBreaker.__init__`` only
    on first creation.
    """
    with _registry_lock:
        if name not in _registry:
            _registry[name] = LLMCircuitBreaker(name=name, **kwargs)
        return _registry[name]
