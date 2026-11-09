"""Optional integrations, initialized when explicitly requested."""

from importlib import import_module
from importlib.util import module_from_spec, spec_from_file_location


__all__ = ["ipfs_datasets", "mike", "ipfs_accelerate"]


def _load_interface(stem: str):
    parent = __file__.rsplit("/", 1)[0]
    path = parent + "/" + stem + "/interface.py"
    spec = spec_from_file_location(f"_boundary_{stem}_interface", path)
    if spec is None or spec.loader is None:
        raise AttributeError(stem)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def __getattr__(name: str):
    if name == "ipfs_datasets":
        value = import_module("integrations.ipfs_datasets")
    elif name in {"mike", "ipfs_accelerate"}:
        value = _load_interface(name)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
