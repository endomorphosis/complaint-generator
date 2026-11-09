"""CIMP-DEP-18: sixteen current docs keep resolving relative links."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MINIMUMS = {
    "docs/OBSERVABILITY_INDEX.md": 65,
    "docs/IPFS_DATASETS_PY_INTEGRATION.md": 9,
    "docs/REFINEMENT_STRATEGY_GUIDE.md": 7,
    "docs/PERFORMANCE_TUNING.md": 6,
    "docs/GRAPHRAG_REFACTORING_ROADMAP.md": 8,
    "docs/migration/LOGGING_MIGRATION_GUIDE.md": 5,
    "docs/optimizers/API_TYPE_CONTRACTS.md": 5,
    "docs/optimizers/PERFORMANCE_TUNING_GUIDE.md": 5,
    "docs/integration/CIRCUIT_BREAKER_GUIDE.md": 4,
    "docs/PRODUCTION_DEPLOYMENT_GUIDE.md": 3,
    "docs/metrics/PROMETHEUS_GUIDE.md": 3,
    "docs/tracing/OTEL_GUIDE.md": 3,
    "docs/optimizers/TROUBLESHOOTING_GUIDE.md": 5,
    "docs/COMPLAINT_ANALYSIS_EXAMPLES.md": 1,
    "docs/optimizers/DISTRIBUTED_ONTOLOGY_REFINEMENT.md": 2,
    "docs/optimizers/INTEGRATION_EXAMPLES.md": 8,
}
_INLINE = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
_DEFINITION = re.compile(r"(?m)^\s{0,3}\[[^\]\n]+\]:[ \t]+(\S+)")
_AUTOLINK = re.compile(r"(?<![A-Za-z0-9_])<([^>\s]+)>")


def _percent_decode(text: str) -> str:
    parts = text.split("%")
    decoded = [parts[0]]
    for part in parts[1:]:
        if len(part) >= 2:
            try:
                decoded.append(bytes.fromhex(part[:2]).decode("utf-8") + part[2:])
                continue
            except ValueError:
                pass
        decoded.append("%" + part)
    return "".join(decoded)


def _destination(raw: str) -> str | None:
    text = raw.strip()
    if text.startswith("<") and ">" in text:
        text = text[1 : text.find(">")].strip()
    elif " " in text:
        text = text.split()[0]
    if not text or text.startswith("#") or "://" in text or text.startswith("mailto:"):
        return None
    text = _percent_decode(text.split("#", 1)[0].split("?", 1)[0].strip())
    return text or None


def _targets(text: str) -> list[str]:
    raws = [match.group(1) for match in _INLINE.finditer(text)]
    raws.extend(match.group(1) for match in _DEFINITION.finditer(text))
    for match in _AUTOLINK.finditer(text):
        candidate = match.group(1)
        if "://" in candidate or "@" in candidate:
            continue
        if "/" in candidate or candidate.endswith((".md", ".py", ".json", ".yml")):
            raws.append(candidate)
    return [target for raw in raws if (target := _destination(raw)) is not None]


def test_sixteen_docs_keep_their_links_and_every_link_resolves() -> None:
    for relative, minimum in MINIMUMS.items():
        document = REPO_ROOT / relative
        assert document.is_file(), relative
        assert "docs/archive" not in relative
        targets = _targets(document.read_text(encoding="utf-8"))
        assert len(targets) >= minimum, f"{relative} has {len(targets)} relative links"
        missing = [
            target
            for target in targets
            if not (document.parent / target).resolve().exists()
        ]
        assert missing == [], f"{relative} -> {missing}"
