import os
import sys


def pytest_configure() -> None:
    """Ensure the ipfs_datasets_py submodule package is importable in tests."""

    repo_root = os.path.dirname(os.path.dirname(__file__))
    submodule_root = os.path.join(repo_root, "ipfs_datasets_py")
    if os.path.isdir(submodule_root) and submodule_root not in sys.path:
        sys.path.insert(0, submodule_root)

    # Vendored dependency layout: ipfs_accelerate_py/ipfs_accelerate_py/
    accelerate_repo_root = os.path.join(submodule_root, "ipfs_accelerate_py")
    if os.path.isdir(accelerate_repo_root) and accelerate_repo_root not in sys.path:
        sys.path.insert(0, accelerate_repo_root)