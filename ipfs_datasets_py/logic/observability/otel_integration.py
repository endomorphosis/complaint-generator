"""
OpenTelemetry-style distributed tracing for the complaint-generator MCP stack.

Provides a pure-Python tracer that produces traces / spans compatible with
Jaeger JSON export format.  No hard dependency on ``opentelemetry-sdk``.

Key exports
-----------
SpanStatus   — enum: OK, ERROR
EventType    — enum of known span-event types
SpanEvent    — immutable event attached to a span
Span         — mutable, thread-safe span object
Trace        — collection of spans sharing a trace_id
OTelTracer   — tracer factory and registry
get_otel_tracer   — global singleton factory
setup_otel_tracer — configure the global singleton
"""

import json
import threading
import time
import uuid
from contextlib import contextmanager
from enum import Enum
from typing import Any, Dict, Generator, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SpanStatus(Enum):
    OK = "OK"
    ERROR = "ERROR"
    UNSET = "UNSET"


class EventType(Enum):
    CIRCUIT_BREAKER_CALL = "circuit_breaker.call"
    CIRCUIT_BREAKER_STATE_CHANGE = "circuit_breaker.state_change"
    LOG_EMITTED = "log.emitted"
    TOOL_INVOKED = "mcp.tool.invoked"
    TOOL_COMPLETED = "mcp.tool.completed"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Span event
# ---------------------------------------------------------------------------

class SpanEvent:
    """An immutable event recorded within a span."""

    __slots__ = ("name", "timestamp", "attributes")

    def __init__(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        self.name = name
        self.timestamp = timestamp if timestamp is not None else time.time()
        self.attributes: Dict[str, Any] = dict(attributes or {})


# ---------------------------------------------------------------------------
# Span
# ---------------------------------------------------------------------------

class Span:
    """
    A single unit of work within a distributed trace.

    Thread-safe attribute access is provided through a lock.
    """

    def __init__(
        self,
        name: str,
        trace_id: str,
        span_id: str,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._lock = threading.Lock()
        self.name = name
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_span_id = parent_span_id

        self.start_time: float = time.time()
        self.end_time: Optional[float] = None
        self.status: SpanStatus = SpanStatus.UNSET
        self.attributes: Dict[str, Any] = dict(attributes or {})
        self.events: List[SpanEvent] = []

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    def is_active(self) -> bool:
        return self.end_time is None

    def duration_ms(self) -> float:
        if self.end_time is None:
            return (time.time() - self.start_time) * 1000.0
        return (self.end_time - self.start_time) * 1000.0

    # ------------------------------------------------------------------
    # Thread-safe mutators
    # ------------------------------------------------------------------

    def set_attribute(self, key: str, value: Any) -> None:
        with self._lock:
            self.attributes[key] = value

    def add_event(self, event: SpanEvent) -> None:
        with self._lock:
            self.events.append(event)

    def _end(self, status: SpanStatus = SpanStatus.OK) -> None:
        with self._lock:
            self.end_time = time.time()
            if self.status == SpanStatus.UNSET:
                self.status = status

    # ------------------------------------------------------------------
    # Jaeger helpers
    # ------------------------------------------------------------------

    def to_jaeger_dict(self) -> Dict[str, Any]:
        tags = [
            {"key": k, "type": "string", "value": str(v)}
            for k, v in self.attributes.items()
        ]
        if self.status == SpanStatus.ERROR:
            tags.append({"key": "error", "type": "bool", "value": True})

        logs = []
        for ev in self.events:
            fields = [{"key": k, "value": str(v)} for k, v in ev.attributes.items()]
            fields.insert(0, {"key": "event", "value": ev.name})
            logs.append({"timestamp": int(ev.timestamp * 1_000_000), "fields": fields})

        start_us = int(self.start_time * 1_000_000)
        duration_us = int(self.duration_ms() * 1_000)

        d: Dict[str, Any] = {
            "traceID": self.trace_id,
            "spanID": self.span_id,
            "operationName": self.name,
            "startTime": start_us,
            "duration": duration_us,
            "tags": tags,
            "logs": logs,
            "references": [],
        }
        if self.parent_span_id:
            d["references"].append({
                "refType": "CHILD_OF",
                "traceID": self.trace_id,
                "spanID": self.parent_span_id,
            })
        return d


# ---------------------------------------------------------------------------
# Trace
# ---------------------------------------------------------------------------

class Trace:
    """A collection of spans sharing the same trace_id."""

    def __init__(self, trace_id: str) -> None:
        self.trace_id = trace_id
        self._lock = threading.Lock()
        self.spans: List[Span] = []

    def add_span(self, span: Span) -> None:
        with self._lock:
            self.spans.append(span)

    def is_complete(self) -> bool:
        with self._lock:
            if not self.spans:
                return False
            return all(not s.is_active() for s in self.spans)

    def to_jaeger_dict(self, service_name: str) -> Dict[str, Any]:
        with self._lock:
            spans_copy = list(self.spans)
        return {
            "traceID": self.trace_id,
            "spans": [s.to_jaeger_dict() for s in spans_copy],
            "processes": {
                "p1": {"serviceName": service_name, "tags": []}
            },
        }


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------

_MAX_COMPLETED_TRACES = 100

# Thread-local stack for implicit parent tracking
_span_stack_local = threading.local()


def _get_span_stack() -> List[Span]:
    if not hasattr(_span_stack_local, "stack"):
        _span_stack_local.stack = []
    return _span_stack_local.stack


class OTelTracer:
    """
    Minimal OpenTelemetry-compatible tracer.

    Maintains active traces and a bounded buffer of completed traces.
    """

    def __init__(self, service_name: str = "complaint-generator") -> None:
        self.service_name = service_name
        self._lock = threading.Lock()
        self._active_traces: Dict[str, Trace] = {}
        self._completed_traces: List[Trace] = []

    # ------------------------------------------------------------------
    # Span lifecycle
    # ------------------------------------------------------------------

    def start_span(
        self,
        name: str,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Span:
        """
        Start and return a new span.

        If *parent_span_id* is ``None`` and a span is already active in the
        current thread, that span becomes the implicit parent (same trace).
        Otherwise a new trace is created.
        """
        stack = _get_span_stack()

        # Determine trace membership
        if parent_span_id is not None:
            # Caller supplied explicit parent → find its trace
            with self._lock:
                parent_trace = next(
                    (t for t in self._active_traces.values()
                     if any(s.span_id == parent_span_id for s in t.spans)),
                    None,
                )
            if parent_trace is not None:
                trace = parent_trace
            else:
                trace = Trace(str(uuid.uuid4()).replace("-", ""))
                with self._lock:
                    self._active_traces[trace.trace_id] = trace
        elif stack:
            # Implicit parent: current top of thread-local stack, but only
            # if this tracer actually owns that trace (avoids cross-test
            # contamination when spans from other tracer instances remain on
            # the thread-local stack).
            implicit_parent = stack[-1]
            with self._lock:
                trace = self._active_traces.get(implicit_parent.trace_id)
            if trace is not None:
                parent_span_id = implicit_parent.span_id
            else:
                # Stale span from another tracer — start a fresh root trace
                trace = Trace(str(uuid.uuid4()).replace("-", ""))
                with self._lock:
                    self._active_traces[trace.trace_id] = trace
        else:
            # Root span: new trace
            trace = Trace(str(uuid.uuid4()).replace("-", ""))
            with self._lock:
                self._active_traces[trace.trace_id] = trace

        span = Span(
            name=name,
            trace_id=trace.trace_id,
            span_id=str(uuid.uuid4()).replace("-", ""),
            parent_span_id=parent_span_id,
            attributes=attributes,
        )
        trace.add_span(span)
        stack.append(span)
        return span

    def end_span(
        self,
        span: Span,
        status: SpanStatus = SpanStatus.OK,
    ) -> None:
        """End *span* and, if its trace is complete, move it to completed."""
        span._end(status)

        # Pop from thread-local stack if it is on top
        stack = _get_span_stack()
        if stack and stack[-1].span_id == span.span_id:
            stack.pop()

        # Check if trace is complete
        with self._lock:
            trace = self._active_traces.get(span.trace_id)
        if trace is not None and trace.is_complete():
            with self._lock:
                self._active_traces.pop(span.trace_id, None)
                self._completed_traces.append(trace)
                # Trim to max
                if len(self._completed_traces) > _MAX_COMPLETED_TRACES:
                    self._completed_traces = self._completed_traces[-_MAX_COMPLETED_TRACES:]

    def get_active_span(self) -> Optional[Span]:
        """Return the innermost active span in the current thread."""
        stack = _get_span_stack()
        return stack[-1] if stack else None

    # ------------------------------------------------------------------
    # Attribute / event helpers
    # ------------------------------------------------------------------

    def set_span_attribute(self, span: Span, key: str, value: Any) -> None:
        span.set_attribute(key, value)

    def record_event(
        self,
        span: Span,
        event_type: EventType,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> SpanEvent:
        """Record a named event on *span* and return it."""
        event = SpanEvent(event_type.value, attributes)
        span.add_event(event)
        return event

    def record_error(
        self,
        span: Span,
        message: str,
        error_type: Optional[str] = None,
        extra_attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an error event and mark the span as ERROR."""
        attrs: Dict[str, Any] = {"error.message": message}
        if error_type is not None:
            attrs["error.type"] = error_type
        if extra_attributes:
            attrs.update(extra_attributes)
        event = SpanEvent(EventType.ERROR.value, attrs)
        span.add_event(event)
        with span._lock:
            span.status = SpanStatus.ERROR

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    @contextmanager
    def span_context(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Generator[Span, None, None]:
        """Context manager that starts a span and ends it on exit."""
        span = self.start_span(name, attributes=attributes)
        try:
            yield span
        except Exception as exc:
            self.record_error(span, str(exc), error_type=type(exc).__name__)
            self.end_span(span, status=SpanStatus.ERROR)
            raise
        else:
            self.end_span(span, status=SpanStatus.OK)

    # ------------------------------------------------------------------
    # Trace retrieval
    # ------------------------------------------------------------------

    def get_trace(self, trace_id: str) -> Optional[Trace]:
        """Return an *active* trace by ID, or ``None``."""
        with self._lock:
            return self._active_traces.get(trace_id)

    def get_completed_traces(self) -> List[Trace]:
        """Return a copy of the completed-traces buffer."""
        with self._lock:
            return list(self._completed_traces)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_jaeger_format(self) -> str:
        """Export all completed traces as a Jaeger-compatible JSON string."""
        with self._lock:
            traces_copy = list(self._completed_traces)
        data = [t.to_jaeger_dict(self.service_name) for t in traces_copy]
        return json.dumps({"data": data}, default=str)


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_singleton: Optional[OTelTracer] = None
_singleton_lock = threading.Lock()


def get_otel_tracer() -> OTelTracer:
    """Return the process-wide singleton ``OTelTracer``."""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = OTelTracer()
        return _singleton


def setup_otel_tracer(service_name: str) -> OTelTracer:
    """
    Configure (or re-configure) the global singleton with *service_name*.

    Returns the singleton instance.
    """
    global _singleton
    with _singleton_lock:
        _singleton = OTelTracer(service_name=service_name)
        return _singleton
