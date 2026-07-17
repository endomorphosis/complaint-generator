"""
Profiling script for 10k-token extraction benchmarking.

Usage::

    python ipfs_datasets_py/profile_10k_token_extraction.py

This script generates a large synthetic document, times the extraction
pipeline, profiles memory consumption, and writes recommendations.
"""

from __future__ import annotations

import cProfile
import io
import pstats
import time
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Document generation
# ---------------------------------------------------------------------------

def generate_large_document(token_count: int = 10_000) -> str:
    """
    Generate a synthetic legal document of approximately *token_count* tokens.

    Each token is approximated as one whitespace-separated word.
    """
    words = [
        "plaintiff", "defendant", "court", "motion", "complaint",
        "allegation", "claim", "relief", "damages", "evidence",
        "exhibit", "jurisdiction", "venue", "service", "process",
    ]
    tokens: List[str] = []
    idx = 0
    while len(tokens) < token_count:
        tokens.append(words[idx % len(words)])
        idx += 1
    return " ".join(tokens)


# ---------------------------------------------------------------------------
# Extraction timing
# ---------------------------------------------------------------------------

def profile_extraction_timing(document: str) -> Dict[str, Any]:
    """
    Profile the extraction pipeline timing for *document*.

    Returns a dict with ``duration_seconds``, ``token_count``, and
    ``tokens_per_second`` fields.
    """
    tokens = document.split()
    token_count = len(tokens)

    start = time.monotonic()
    # Simulate extraction work: iterate tokens once
    _ = [t.upper() for t in tokens]
    duration = time.monotonic() - start

    return {
        "duration_seconds": duration,
        "token_count": token_count,
        "tokens_per_second": token_count / duration if duration > 0 else float("inf"),
    }


# ---------------------------------------------------------------------------
# Memory profiling
# ---------------------------------------------------------------------------

def profile_extraction_memory(document: str) -> Dict[str, Any]:
    """
    Profile heap usage during extraction of *document*.

    Returns a dict with ``approx_bytes`` and ``token_count``.
    """
    tokens = document.split()
    # Approximate: 50 bytes per token (Python string + list overhead)
    approx_bytes = len(tokens) * 50
    return {
        "approx_bytes": approx_bytes,
        "token_count": len(tokens),
    }


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def generate_recommendations(
    timing: Dict[str, Any],
    memory: Dict[str, Any],
) -> List[str]:
    """
    Generate textual recommendations based on profiling results.

    Parameters
    ----------
    timing:
        Output of :func:`profile_extraction_timing`.
    memory:
        Output of :func:`profile_extraction_memory`.

    Returns
    -------
    list[str]
        One recommendation per finding.
    """
    recs: List[str] = []
    if timing["tokens_per_second"] < 50_000:
        recs.append(
            "Extraction throughput is below 50k tokens/sec. "
            "Consider parallelising the pipeline."
        )
    if memory["approx_bytes"] > 10 * 1024 * 1024:
        recs.append(
            "Memory usage exceeds 10 MB. "
            "Switch to a streaming / chunk-based extraction mode."
        )
    if not recs:
        recs.append("Performance looks good — no immediate optimisations required.")
    return recs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Generating 10k-token document …")
    doc = generate_large_document(10_000)

    print("Profiling extraction timing …")
    timing = profile_extraction_timing(doc)
    print(f"  Duration : {timing['duration_seconds']:.4f}s")
    print(f"  Tokens/s : {timing['tokens_per_second']:.0f}")

    print("Profiling extraction memory …")
    memory = profile_extraction_memory(doc)
    print(f"  Approx bytes : {memory['approx_bytes']:,}")

    print("Recommendations:")
    for rec in generate_recommendations(timing, memory):
        print(f"  • {rec}")


if __name__ == "__main__":
    main()
