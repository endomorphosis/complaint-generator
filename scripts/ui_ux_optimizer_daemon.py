#!/usr/bin/env python3
from complaint_generator.ui_optimizer_daemon import (
    _run_daemon,
    _start_daemon,
    _status_payload,
    _stop_daemon,
    build_parser,
    main,
)

__all__ = [
    "build_parser",
    "main",
    "_run_daemon",
    "_start_daemon",
    "_status_payload",
    "_stop_daemon",
]


if __name__ == "__main__":
    raise SystemExit(main())
