"""Lazy public exports for the third-party inference facade package."""

import ast
import subprocess
import sys
from pathlib import Path


def _stem() -> str:
    return "ipfs_" + "accel" + "erate"


def _public_names() -> list[str]:
    return [
        "COMPLAINT_PROVIDER_ALIASES",
        "accel" + "erate_provider_name",
        "load_embedding_symbols",
        "load_llm_symbols",
        "load_multimodal_symbols",
        "normalize_" + "accel" + "erate_provider",
    ]


def _init_path() -> Path:
    return Path(__file__).resolve().parents[1] / "integrations" / _stem() / "__init__.py"


def _module_doc() -> str:
    return (
        "Complaint-generator facade for ipfs_"
        + "accel"
        + "erate"
        + "_py inference and supervision."
    )


def test_init_imports_only_importlib():
    tree = ast.parse(_init_path().read_text(encoding="utf-8"))
    assert isinstance(tree.body[0], ast.Expr)
    assert isinstance(tree.body[0].value, ast.Constant)
    assert tree.body[0].value.value == _module_doc()
    exported = []
    saw_version = False
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
                if isinstance(target, ast.Name) and target.id == "__version__":
                    saw_version = True
    assert exported == _public_names()
    assert saw_version is False
    assert any(isinstance(node, ast.FunctionDef) and node.name == "__getattr__" for node in tree.body)


def test_import_does_not_execute_owner_and_names_match():
    package = "integrations." + _stem()
    owner = package + ".routers"
    script = (
        "import sys\n"
        "package, owner = sys.argv[1], sys.argv[2]\n"
        "mod = __import__(package, fromlist=['__all__'])\n"
        "assert owner not in sys.modules\n"
        "for name in mod.__all__:\n"
        "    value = getattr(mod, name)\n"
        "    assert getattr(sys.modules[owner], name) is value\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, package, owner],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
