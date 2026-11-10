"""Lazy public exports for the document render package."""

import ast
import subprocess
import sys
from pathlib import Path


_PUBLIC_NAMES = [
    "HAS_REPORTLAB",
    "build_case_caption_table",
    "build_case_caption_text_lines",
    "build_caption_party_block_html",
    "build_caption_party_block_lines",
    "build_case_detail_lines",
    "make_page_footer_renderer",
]

_OWNER = "reportlab_helpers"
_MODULE_DOC = "Reusable document-render helpers for complaint-generator."


def _init_path() -> Path:
    return Path(__file__).resolve().parents[1] / "lib" / "document_render" / "__init__.py"


def test_init_imports_only_importlib():
    tree = ast.parse(_init_path().read_text(encoding="utf-8"))
    assert isinstance(tree.body[0], ast.Expr)
    assert isinstance(tree.body[0].value, ast.Constant)
    assert tree.body[0].value.value == _MODULE_DOC
    exported = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name == "importlib"
        elif isinstance(node, ast.ImportFrom):
            assert node.module == "importlib"
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    assert isinstance(node.value, ast.List)
                    exported = [
                        element.value
                        for element in node.value.elts
                        if isinstance(element, ast.Constant)
                    ]
    assert exported == _PUBLIC_NAMES
    assert len(exported) == 7
    assert any(isinstance(node, ast.FunctionDef) and node.name == "__getattr__" for node in tree.body)


def test_import_does_not_execute_owners_and_names_match():
    package = "lib.document_render"
    owner = _OWNER
    names_literal = repr(_PUBLIC_NAMES)
    script = (
        "import sys\n"
        "package = sys.argv[1]\n"
        "owner_name = sys.argv[2]\n"
        "names = " + names_literal + "\n"
        "mod = __import__(package, fromlist=['__all__'])\n"
        "owner = package + '.' + owner_name\n"
        "assert owner not in sys.modules\n"
        "assert list(mod.__all__) == names\n"
        "for name in mod.__all__:\n"
        "    value = getattr(mod, name)\n"
        "    assert getattr(sys.modules[owner], name) is value\n"
        "helper = getattr(mod, 'build_case_caption_text_lines')\n"
        "assert helper is sys.modules[owner].build_case_caption_text_lines\n"
        "assert callable(helper)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, package, owner],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
