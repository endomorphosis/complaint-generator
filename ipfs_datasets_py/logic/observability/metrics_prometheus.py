"""
Prometheus-style metrics collector for the complaint-generator MCP stack.

This module provides a pure-Python implementation of Prometheus text-format
metric export.  It deliberately avoids a hard dependency on the ``prometheus_client``
library so that the package can run in any environment.

Key exports
-----------
CircuitBreakerState  — enum mapping state names to their integer gauge values
PrometheusMetricsCollector — collects circuit-breaker and logging metrics;
                              exports Prometheus text format
get_prometheus_collector   — global singleton factory
"""

import math
import statistics
import threading
import time
from enum import Enum
from collections import deque
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------

class CircuitBreakerState(Enum):
    CLOSED = 0
    OPEN = 1
    HALF_OPEN = 2


# ---------------------------------------------------------------------------
# Per-component data
# ---------------------------------------------------------------------------

class _ComponentData:
    """Mutable metrics container for one named component."""

    def __init__(self, max_latency_samples: int = 1000) -> None:
        self._lock = threading.Lock()
        self.max_latency_samples = max_latency_samples

        # Call counters
        self.total_calls: int = 0
        self.successful_calls: int = 0
        self.failed_calls: int = 0

        # Latency samples (capped ring-buffer)
        self._latencies: deque = deque(maxlen=max_latency_samples)

        # State
        self.current_state: Optional[str] = None
        self.last_failure_time: Optional[float] = None

        # Log entries by level
        self.log_entries: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Recording helpers
    # ------------------------------------------------------------------

    def record_call(
        self,
        latency: float,
        success: bool,
        timestamp: Optional[float] = None,
    ) -> None:
        with self._lock:
            self.total_calls += 1
            if success:
                self.successful_calls += 1
            else:
                self.failed_calls += 1
                self.last_failure_time = timestamp if timestamp is not None else time.time()
            self._latencies.append(latency)

    def record_state(self, state: str) -> None:
        with self._lock:
            self.current_state = state

    def record_log_entry(self, level: str) -> None:
        with self._lock:
            self.log_entries[level] = self.log_entries.get(level, 0) + 1

    # ------------------------------------------------------------------
    # Read helpers (copies taken under lock)
    # ------------------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            latencies = list(self._latencies)
            return {
                "total_calls": self.total_calls,
                "successful_calls": self.successful_calls,
                "failed_calls": self.failed_calls,
                "latencies": latencies,
                "current_state": self.current_state,
                "last_failure_time": self.last_failure_time,
                "log_entries": dict(self.log_entries),
            }


# ---------------------------------------------------------------------------
# Metric formatter helpers
# ---------------------------------------------------------------------------

_STATE_NUM = {
    "closed": 0,
    "open": 1,
    "half_open": 2,
}


def _pN(latencies: List[float], pct: int) -> float:
    """Return the *pct*-th percentile of *latencies* (0–100 int)."""
    if not latencies:
        return 0.0
    if len(latencies) == 1:
        return latencies[0]
    sorted_lats = sorted(latencies)
    k = (len(sorted_lats) - 1) * pct / 100.0
    lo = int(k)
    hi = lo + 1
    if hi >= len(sorted_lats):
        return sorted_lats[-1]
    frac = k - lo
    return sorted_lats[lo] + frac * (sorted_lats[hi] - sorted_lats[lo])


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

class PrometheusMetricsCollector:
    """
    Thread-safe Prometheus-style metrics collector.

    Parameters
    ----------
    max_latency_samples:
        Maximum latency samples kept per component (FIFO ring-buffer).
        Defaults to 1 000.
    """

    def __init__(self, max_latency_samples: int = 1000) -> None:
        self._max_latency_samples = max_latency_samples
        self._lock = threading.Lock()
        self._components: Dict[str, _ComponentData] = {}

    # ------------------------------------------------------------------
    # Internal component access
    # ------------------------------------------------------------------

    def _get_or_create(self, component: str) -> _ComponentData:
        with self._lock:
            if component not in self._components:
                self._components[component] = _ComponentData(
                    self._max_latency_samples
                )
            return self._components[component]

    # ------------------------------------------------------------------
    # Recording API
    # ------------------------------------------------------------------

    def record_circuit_breaker_call(
        self,
        component: str,
        latency: float,
        success: bool,
        timestamp: Optional[float] = None,
    ) -> None:
        """Record one circuit-breaker call outcome."""
        data = self._get_or_create(component)
        data.record_call(latency, success, timestamp)

    def record_circuit_breaker_state(
        self,
        component: str,
        state: str,
    ) -> None:
        """Record a circuit-breaker state transition."""
        data = self._get_or_create(component)
        data.record_state(state)

    def record_log_entry(self, component: str, level: str = "info") -> None:
        """Record that one log line was emitted at *level*."""
        data = self._get_or_create(component)
        data.record_log_entry(level)

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_metrics_summary(self, component: str) -> Dict[str, Any]:
        """
        Return a dict summarising all metrics for *component*.

        Keys: total_calls, successful_calls, failed_calls,
              success_rate, failure_rate,
              min_latency, max_latency, avg_latency,
              current_state, last_failure_time,
              latency_percentiles (dict with p50, p95, p99).
        """
        with self._lock:
            data = self._components.get(component)
        if data is None:
            return {
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "success_rate": 0.0,
                "failure_rate": 0.0,
                "min_latency": 0.0,
                "max_latency": 0.0,
                "avg_latency": 0.0,
                "current_state": None,
                "last_failure_time": None,
                "latency_percentiles": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
            }

        snap = data.snapshot()
        total = snap["total_calls"]
        successes = snap["successful_calls"]
        failures = snap["failed_calls"]
        lats = snap["latencies"]

        success_rate = (successes / total * 100.0) if total else 0.0
        failure_rate = (failures / total * 100.0) if total else 0.0
        min_lat = min(lats) if lats else 0.0
        max_lat = max(lats) if lats else 0.0
        avg_lat = sum(lats) / len(lats) if lats else 0.0

        return {
            "total_calls": total,
            "successful_calls": successes,
            "failed_calls": failures,
            "success_rate": round(success_rate, 4),
            "failure_rate": round(failure_rate, 4),
            "min_latency": min_lat,
            "max_latency": max_lat,
            "avg_latency": avg_lat,
            "current_state": snap["current_state"],
            "last_failure_time": snap["last_failure_time"],
            "latency_percentiles": {
                "p50": _pN(lats, 50),
                "p95": _pN(lats, 95),
                "p99": _pN(lats, 99),
            },
        }

    def get_latency_percentiles(
        self,
        component: str,
        percentiles: Sequence[int] = (50, 95, 99),
    ) -> Dict[str, float]:
        """
        Return requested latency percentiles for *component*.

        Returns ``{"p50": 0.0, "p95": 0.0, "p99": 0.0}`` if the component
        has no data.
        """
        with self._lock:
            data = self._components.get(component)
        if data is None:
            return {f"p{p}": 0.0 for p in percentiles}

        snap = data.snapshot()
        lats = snap["latencies"]
        if not lats:
            return {f"p{p}": 0.0 for p in percentiles}
        return {f"p{p}": _pN(lats, p) for p in percentiles}

    def get_components(self) -> List[str]:
        """Return a list of all known component names."""
        with self._lock:
            return list(self._components.keys())

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    def reset_component(self, component: str) -> None:
        """Remove all metrics for *component*."""
        with self._lock:
            self._components.pop(component, None)

    def reset_all(self) -> None:
        """Remove all component metrics."""
        with self._lock:
            self._components.clear()

    # ------------------------------------------------------------------
    # Prometheus text-format export
    # ------------------------------------------------------------------

    def export_prometheus_format(self) -> str:
        """
        Render all metrics in the Prometheus text exposition format.

        Returns an empty string if no components have been registered.
        """
        with self._lock:
            snapshot = {
                name: data.snapshot()
                for name, data in self._components.items()
            }

        if not snapshot:
            return ""

        lines: List[str] = []

        # ---- circuit_breaker_calls_total -----------------------------------
        lines.append("# HELP circuit_breaker_calls_total Total calls through circuit breakers")
        lines.append("# TYPE circuit_breaker_calls_total counter")
        for component, snap in snapshot.items():
            total = snap["total_calls"]
            lines.append(f'circuit_breaker_calls_total{{component="{component}",result="success"}} {snap["successful_calls"]}')
            lines.append(f'circuit_breaker_calls_total{{component="{component}",result="failure"}} {snap["failed_calls"]}')

        # ---- circuit_breaker_state -----------------------------------------
        lines.append("# HELP circuit_breaker_state Current state (0=closed, 1=open, 2=half_open)")
        lines.append("# TYPE circuit_breaker_state gauge")
        for component, snap in snapshot.items():
            state_str = snap.get("current_state") or "closed"
            state_num = _STATE_NUM.get(state_str, 0)
            lines.append(f'circuit_breaker_state{{component="{component}",state="{state_str}"}} {state_num}')

        # ---- circuit_breaker_latency_seconds --------------------------------
        lines.append("# HELP circuit_breaker_latency_seconds Call latency in seconds")
        lines.append("# TYPE circuit_breaker_latency_seconds summary")
        for component, snap in snapshot.items():
            lats = snap["latencies"]
            p50 = _pN(lats, 50)
            p95 = _pN(lats, 95)
            p99 = _pN(lats, 99)
            count = len(lats)
            total = sum(lats)
            lines.append(f'circuit_breaker_latency_seconds{{component="{component}",quantile="0.5"}} {p50}')
            lines.append(f'circuit_breaker_latency_seconds{{component="{component}",quantile="0.95"}} {p95}')
            lines.append(f'circuit_breaker_latency_seconds{{component="{component}",quantile="0.99"}} {p99}')
            lines.append(f'circuit_breaker_latency_seconds_count{{component="{component}"}} {count}')
            lines.append(f'circuit_breaker_latency_seconds_sum{{component="{component}"}} {total}')

        # ---- log_entries_total ---------------------------------------------
        any_logs = any(snap["log_entries"] for snap in snapshot.values())
        if any_logs:
            lines.append("# HELP log_entries_total Total structured log entries emitted")
            lines.append("# TYPE log_entries_total counter")
            for component, snap in snapshot.items():
                for level, count in snap["log_entries"].items():
                    lines.append(f'log_entries_total{{component="{component}",level="{level}"}} {count}')

        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_singleton: Optional[PrometheusMetricsCollector] = None
_singleton_lock = threading.Lock()


def get_prometheus_collector() -> PrometheusMetricsCollector:
    """Return the process-wide singleton ``PrometheusMetricsCollector``."""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = PrometheusMetricsCollector()
        return _singleton
