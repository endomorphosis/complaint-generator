"""Lazy public exports for the mike integration package."""

import ast
import subprocess
import sys
from pathlib import Path


_PUBLIC_NAMES = [
    "apply_mike_llm_router_patch",
    "MIKE_LLM_PATCH_VERSION",
    "load_skill",
    "list_skill_ids",
    "SKILLS_DIR",
]

_OWNERS = {
    "apply_mike_llm_router_patch": "llm_patch",
    "MIKE_LLM_PATCH_VERSION": "llm_patch",
    "load_skill": "skills",
    "list_skill_ids": "skills",
    "SKILLS_DIR": "skills",
}

_MODULE_DOC = (
    "Mike editor integration package.\n"
    "\n"
    "Exposes the LLM router patch, editor adapter utilities, and skill asset loader\n"
    "so the complaint workspace can programmatically reach the Mike frontend/backend\n"
    "layer and enforce its router-ownership policy at every handoff boundary.\n"
)


def _init_path() -> Path:
    return Path(__file__).resolve().parents[1] / "integrations" / "mike" / "__init__.py"


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
    assert any(isinstance(node, ast.FunctionDef) and node.name == "__getattr__" for node in tree.body)


def test_import_does_not_execute_owners_and_names_match():
    package = "integrations.mike"
    script = (
        "import sys\n"
        "package = sys.argv[1]\n"
        "mod = __import__(package, fromlist=['__all__'])\n"
        "assert package + '.llm_patch' not in sys.modules\n"
        "assert package + '.skills' not in sys.modules\n"
        "owners = {\n"
        "    'apply_mike_llm_router_patch': 'llm_patch',\n"
        "    'MIKE_LLM_PATCH_VERSION': 'llm_patch',\n"
        "    'load_skill': 'skills',\n"
        "    'list_skill_ids': 'skills',\n"
        "    'SKILLS_DIR': 'skills',\n"
        "}\n"
        "for name in mod.__all__:\n"
        "    value = getattr(mod, name)\n"
        "    owner = package + '.' + owners[name]\n"
        "    assert getattr(sys.modules[owner], name) is value\n"
        "patch_fn = getattr(mod, 'apply_mike_llm_router_patch')\n"
        "skill_fn = getattr(mod, 'load_skill')\n"
        "assert patch_fn.__module__.endswith('.llm_patch')\n"
        "assert skill_fn.__module__.endswith('.skills')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, package],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
