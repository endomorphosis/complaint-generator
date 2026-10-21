#!/usr/bin/env python3
"""Run the native Grok-only complaint improvement campaign."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.ipfs_accelerate.improvement_runner import main


if __name__ == "__main__":
    raise SystemExit(main())
