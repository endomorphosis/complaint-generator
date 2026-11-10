"""Lazy public exports for mediator integration adapters."""

import ast
import subprocess
import sys
from pathlib import Path


_MODULE_DOC = "Integration primitives for ipfs_datasets_py enhancements."

_PUBLIC_NAMES = [
    "IPFSDatasetsAdapter",
    "detect_ipfs_datasets_capabilities",
    "CapabilityCatalog",
    "CapabilityStatus",
    "NormalizedRetrievalBundle",
    "NormalizedRetrievalRecord",
    "IntegrationFeatureFlags",
    "RetrievalOrchestrator",
    "ProvenanceRecord",
    "build_provenance_record",
    "TTLCache",
    "VectorRetrievalAugmentor",
    "GraphRetrievalAugmentor",
    "GraphAwareRetrievalReranker",
]

_OWNERS = {
    "IPFSDatasetsAdapter": "adapter",
    "detect_ipfs_datasets_capabilities": "adapter",
    "CapabilityCatalog": "contracts",
    "CapabilityStatus": "contracts",
    "NormalizedRetrievalBundle": "contracts",
    "NormalizedRetrievalRecord": "contracts",
    "IntegrationFeatureFlags": "settings",
    "RetrievalOrchestrator": "retrieval_orchestrator",
    "ProvenanceRecord": "provenance",
    "build_provenance_record": "provenance",
    "TTLCache": "caching",
    "VectorRetrievalAugmentor": "vector_tools",
    "GraphRetrievalAugmentor": "graph_tools",
    "GraphAwareRetrievalReranker": "graph_tools",
}

_UNLOADED = (
    "adapter",
    "retrieval_orchestrator",
    "vector_tools",
    "graph_tools",
)


def _init_path() -> Path:
    return Path(__file__).resolve().parents[1] / "mediator" / "integrations" / "__init__.py"


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
    assert len(exported) == 14
    assert any(isinstance(node, ast.FunctionDef) and node.name == "__getattr__" for node in tree.body)


def test_import_does_not_execute_owners_and_names_match():
    package = "mediator.integrations"
    script = (
        "import sys\n"
        "package = sys.argv[1]\n"
        "names = " + repr(_PUBLIC_NAMES) + "\n"
        "owners = " + repr(_OWNERS) + "\n"
        "unloaded = " + repr(list(_UNLOADED)) + "\n"
        "mod = __import__(package, fromlist=['__all__'])\n"
        "for stem in unloaded:\n"
        "    assert package + '.' + stem not in sys.modules\n"
        "assert list(mod.__all__) == names\n"
        "for name in mod.__all__:\n"
        "    value = getattr(mod, name)\n"
        "    owner = sys.modules[package + '.' + owners[name]]\n"
        "    assert getattr(owner, name) is value\n"
        "adapter = getattr(mod, 'IPFSDatasetsAdapter')\n"
        "assert adapter is sys.modules[package + '.adapter'].IPFSDatasetsAdapter\n"
        "assert isinstance(adapter, type)\n"
        "orchestrator = getattr(mod, 'RetrievalOrchestrator')\n"
        "assert orchestrator is sys.modules[package + '.retrieval_orchestrator'].RetrievalOrchestrator\n"
        "assert isinstance(orchestrator, type)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, package],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
