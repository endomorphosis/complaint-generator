"""CIMP-CUR-13: the deployment guide drops the fictional home prefix."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT_PATH = REPO_ROOT / "docs" / "DEPLOYMENT.md"
FICTIONAL_HOME = "/home/" + "complaint-app"
ROUTER_CONFIG = "config.llm_router.json"
REVIEW_CONFIG = "config.review_surface.json"
ROUTER_COMMAND = "python run.py --config " + ROUTER_CONFIG
REVIEW_COMMAND = "python run.py --config " + REVIEW_CONFIG


def deployment_lines() -> list[str]:
    """Return deployment guide lines using splitlines()."""
    return DEPLOYMENT_PATH.read_text(encoding="utf-8").splitlines()


def test_deployment_guide_drops_fictional_home() -> None:
    lines = deployment_lines()
    text = "\n".join(lines)
    assert lines
    assert len(lines) == len(DEPLOYMENT_PATH.read_text(encoding="utf-8").splitlines())
    assert FICTIONAL_HOME not in text
    assert ROUTER_CONFIG in text
    assert REVIEW_CONFIG in text
    assert ROUTER_COMMAND in text
    assert REVIEW_COMMAND in text
