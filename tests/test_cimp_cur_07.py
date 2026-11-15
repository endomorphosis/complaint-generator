"""Root operator config names in the configuration guide match the repository root."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "CONFIGURATION.md"
HEADING = "Root operator configs"
NAME_RE = re.compile(r"`(config[^`\s]+\.json)`")


def _section_lines(text: str) -> list[str]:
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip() == f"## {HEADING}"]
    assert len(starts) == 1
    body = []
    for line in lines[starts[0] + 1 :]:
        if line.startswith("## "):
            break
        body.append(line)
    return body


def test_root_operator_configs_match_repository_root():
    body = _section_lines(GUIDE.read_text(encoding="utf-8"))
    named = set()
    for line in body:
        named.update(NAME_RE.findall(line))
    on_disk = {
        path.name
        for path in ROOT.iterdir()
        if path.is_file() and path.name.startswith("config") and path.name.endswith(".json")
    }
    assert named == on_disk
    assert len(named) == 8
    for name in sorted(named):
        assert (ROOT / name).is_file()
    prose = " ".join(body)
    assert "stay at the repository root because the CLI defaults use those paths" in prose
