"""CIMP-BND-19: module boundaries match the declared owner modules."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = REPO_ROOT / "docs/architecture/module_boundaries.md"
SKIP_PARTS = {
    "external",
    ".git",
    "data",
    "artifacts",
    "output",
    "statefiles",
    "workspace",
    "node_modules",
}
SCHEMA = "complaint-generator/module-interface@1"
VERSION = "1.0.0"
FACADE_STEM = "ipfs_" + "accel" + "erate"


def _discover() -> list[Path]:
    found = []
    for path in REPO_ROOT.rglob("interface.py"):
        parts = path.relative_to(REPO_ROOT).parts
        if any(part in SKIP_PARTS or part.startswith(".") for part in parts):
            continue
        found.append(path)
    return sorted(found, key=lambda item: item.relative_to(REPO_ROOT).as_posix())


def _owners(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "OWNER_MODULES" for target in node.targets):
            value = ast.literal_eval(node.value)
            assert isinstance(value, (list, tuple))
            return [str(item) for item in value]
    raise AssertionError(f"{path} does not assign OWNER_MODULES")


def _sections(text: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    heading = None
    bullets: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading is not None:
                sections.append((heading, bullets))
            heading = line[3:].strip()
            bullets = []
            continue
        if heading is not None and line.startswith("- `") and line.endswith("`"):
            bullets.append(line[3:-1])
    if heading is not None:
        sections.append((heading, bullets))
    return sections


def test_document_lists_each_interface_and_only_its_owners() -> None:
    discovered = _discover()
    facade = f"integrations/{FACADE_STEM}/interface.py"
    relative = [path.relative_to(REPO_ROOT).as_posix() for path in discovered]
    assert facade in relative
    assert len(relative) == len(set(relative))
    text = DOCUMENT.read_text(encoding="utf-8")
    assert "Callers import the interface modules rather than the owner modules." in text
    assert f"`INTERFACE_SCHEMA` is `{SCHEMA}`." in text
    assert f"`INTERFACE_VERSION` is `{VERSION}`." in text
    assert "package initializers are lazy" not in text
    assert "already lazy" not in text
    assert "`lib.deontic_logic`" not in text
    assert "`lib.legal_document`" not in text
    sections = _sections(text)
    assert [heading for heading, _bullets in sections] == relative
    for path, (heading, bullets) in zip(discovered, sections):
        assert heading == path.relative_to(REPO_ROOT).as_posix()
        assert bullets == _owners(path)
