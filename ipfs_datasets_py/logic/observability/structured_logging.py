"""
Structured JSON logging for the complaint-generator MCP stack.

Key exports
-----------
LogField      — field-name constants
EventType     — enum of known event-type strings
LogContext    — thread-local context manager that injects extra fields
JSONLogFormatter  — logging.Formatter that emits one JSON line per record
get_logger    — factory for a logger with JSONLogFormatter attached
log_event     — convenience wrapper for EventType-keyed log lines
log_error     — convenience wrapper for error events
log_performance — convenience wrapper for performance events
log_mcp_tool  — convenience wrapper for MCP tool invocation events
LogPerformance — context manager that times and logs an operation
parse_json_log_file — read a log file and return parsed entries
filter_logs   — filter a list of log-entry dicts by field values
"""

import json
import logging
import threading
import time
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional


# ---------------------------------------------------------------------------
# Field name constants
# ---------------------------------------------------------------------------

class LogField:
    TIMESTAMP = "timestamp"
    LEVEL = "level"
    MESSAGE = "message"
    EVENT_TYPE = "event_type"
    TOOL_NAME = "tool_name"
    DURATION_MS = "duration_ms"
    REQUEST_ID = "request_id"
    SESSION_ID = "session_id"
    USER_ID = "user_id"


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    TOOL_INVOKED = "mcp.tool.invoked"
    TOOL_COMPLETED = "mcp.tool.completed"
    TOOL_ERROR = "mcp.tool.error"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker.open"
    CIRCUIT_BREAKER_CLOSE = "circuit_breaker.close"
    CIRCUIT_BREAKER_CALL = "circuit_breaker.call"
    CIRCUIT_BREAKER_STATE_CHANGE = "circuit_breaker.state_change"
    PERFORMANCE = "performance"
    ERROR = "error"
    ERROR_OCCURRED = "error.occurred"
    ENTITY_EXTRACTED = "entity.extracted"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# Thread-local context
# ---------------------------------------------------------------------------

_context_local = threading.local()


def _get_context_stack() -> List[Dict[str, Any]]:
    if not hasattr(_context_local, "stack"):
        _context_local.stack = []
    return _context_local.stack


def _merged_context() -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for frame in _get_context_stack():
        merged.update(frame)
    return merged


class LogContext:
    """
    Thread-local context manager that injects extra fields into every log
    record emitted within the ``with`` block.

    Usage::

        with LogContext(request_id="req-123", user_id="u-456"):
            logger.info("Handled request")
    """

    def __init__(self, **fields: Any) -> None:
        self._fields = fields

    def __enter__(self) -> "LogContext":
        _get_context_stack().append(self._fields)
        return self

    def __exit__(self, *_: Any) -> None:
        _get_context_stack().pop()


# ---------------------------------------------------------------------------
# JSON log formatter
# ---------------------------------------------------------------------------

class JSONLogFormatter(logging.Formatter):
    """
    Formats each log record as a single line of JSON.

    Standard fields always present: timestamp, level, message.
    Extra fields (set via ``logger.info("msg", extra={...})``) are merged in.
    Thread-local LogContext fields are also merged in.
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        entry: Dict[str, Any] = {
            "timestamp": self.formatTime(record, datefmt=None),
            "level": record.levelname,
            "message": record.getMessage(),
        }

        # Inject thread-local context fields
        entry.update(_merged_context())

        # Inject any extra= fields passed by the caller
        skip = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs",
            "pathname", "process", "processName", "relativeCreated",
            "stack_info", "thread", "threadName", "exc_info", "exc_text",
            "message",
        }
        for key, value in record.__dict__.items():
            if key not in skip and not key.startswith("_"):
                entry[key] = value

        return json.dumps(entry, default=str)


# ---------------------------------------------------------------------------
# Logger factory
# ---------------------------------------------------------------------------

def get_logger(
    name: str,
    handlers: Optional[List[logging.Handler]] = None,
) -> logging.Logger:
    """
    Return a logger named *name* with a JSONLogFormatter attached.

    If *handlers* is given those handlers are used; otherwise a
    StreamHandler writing to stderr is created automatically.
    """
    logger = logging.getLogger(name)
    logger.handlers.clear()

    if handlers is None:
        handler: logging.Handler = logging.StreamHandler()
        handlers = [handler]

    formatter = JSONLogFormatter()
    for h in handlers:
        h.setFormatter(formatter)
        logger.addHandler(h)

    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    return logger


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def log_event(
    event_type: str,
    logger: Optional[logging.Logger] = None,
    **kwargs: Any,
) -> None:
    """Log a structured event line."""
    _log = logger or get_logger("mcp.events")
    extra = {"event_type": event_type, **kwargs}
    _log.info(f"Event: {event_type}", extra=extra)


def log_error(
    message: str,
    logger: Optional[logging.Logger] = None,
    **kwargs: Any,
) -> None:
    """Log an error event."""
    _log = logger or get_logger("mcp.errors")
    extra = {"event_type": EventType.ERROR.value, **kwargs}
    _log.error(message, extra=extra)


def log_performance(
    operation: str,
    duration_ms: float,
    logger: Optional[logging.Logger] = None,
    **kwargs: Any,
) -> None:
    """Log a performance measurement."""
    _log = logger or get_logger("mcp.performance")
    extra = {
        "event_type": EventType.PERFORMANCE.value,
        "operation": operation,
        "duration_ms": duration_ms,
        **kwargs,
    }
    _log.info(f"Performance: {operation}", extra=extra)


def log_mcp_tool(
    tool_name: str,
    status: str,
    duration_ms: float,
    logger: Optional[logging.Logger] = None,
    params: Optional[Dict[str, Any]] = None,
    result: Optional[Any] = None,
    **kwargs: Any,
) -> None:
    """Log an MCP tool invocation with inputs and outputs."""
    _log = logger or get_logger("mcp.tool")
    event_type = f"mcp.tool.{status}"
    extra: Dict[str, Any] = {
        "event_type": event_type,
        "tool_name": tool_name,
        "duration_ms": duration_ms,
        **kwargs,
    }
    if params is not None:
        extra["params"] = params
    if result is not None:
        extra["result"] = result
    _log.info(f"MCP tool {tool_name} {status}", extra=extra)


# ---------------------------------------------------------------------------
# LogPerformance context manager
# ---------------------------------------------------------------------------

class LogPerformance:
    """
    Context manager that times the enclosed block and logs its duration.

    Usage::

        with LogPerformance("my_operation", logger=my_logger):
            do_work()
    """

    def __init__(
        self,
        operation: str,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.operation = operation
        self._logger = logger or get_logger("mcp.performance")
        self._start: float = 0.0

    def __enter__(self) -> "LogPerformance":
        self._start = time.monotonic()
        return self

    def __exit__(self, *_: Any) -> None:
        duration_ms = (time.monotonic() - self._start) * 1000
        extra = {
            "event_type": EventType.PERFORMANCE.value,
            "operation": self.operation,
            "duration_ms": duration_ms,
            **_merged_context(),
        }
        self._logger.info(f"Performance: {self.operation}", extra=extra)


# ---------------------------------------------------------------------------
# Log file parsing / filtering
# ---------------------------------------------------------------------------

def parse_json_log_file(path: Any) -> List[Dict[str, Any]]:
    """
    Read a log file written by JSONLogFormatter and return parsed entries.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.

    Blank lines and malformed JSON lines are silently skipped.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Log file not found: {file_path}")
    entries: List[Dict[str, Any]] = []
    for raw_line in file_path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return entries


def filter_logs(
    entries: List[Dict[str, Any]],
    **criteria: Any,
) -> List[Dict[str, Any]]:
    """
    Filter *entries* by exact field-value matches.

    Example::

        filter_logs(entries, event_type="mcp.tool.invoked")
    """
    result = []
    for entry in entries:
        if all(entry.get(k) == v for k, v in criteria.items()):
            result.append(entry)
    return result
