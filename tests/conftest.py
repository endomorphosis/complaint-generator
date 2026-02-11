import os
import sys


def pytest_configure() -> None:
    """Ensure the ipfs_datasets_py submodule package is importable in tests."""

    repo_root = os.path.dirname(os.path.dirname(__file__))
    submodule_root = os.path.join(repo_root, "ipfs_datasets_py")
    if os.path.isdir(submodule_root) and submodule_root not in sys.path:
        sys.path.insert(0, submodule_root)

    # If something imported `ipfs_datasets_py` before we adjusted sys.path, Python may have
    # created a namespace package that points at the submodule repo root (which does not
    # export `llm_router`). Reset it so subsequent imports resolve to the actual package at
    # ipfs_datasets_py/ipfs_datasets_py/.
    mod = sys.modules.get("ipfs_datasets_py")
    if mod is not None and getattr(mod, "__file__", None) is None and hasattr(mod, "__path__"):
        del sys.modules["ipfs_datasets_py"]

    # Vendored dependency layout: ipfs_accelerate_py/ipfs_accelerate_py/
    accelerate_repo_root = os.path.join(submodule_root, "ipfs_accelerate_py")
    if os.path.isdir(accelerate_repo_root) and accelerate_repo_root not in sys.path:
        sys.path.insert(0, accelerate_repo_root)