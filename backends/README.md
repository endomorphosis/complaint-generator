# Backends package

This note is the package entry for `backends`.

## Current entry

The current entry is `backends.interface`. Importing the interface does not import the router implementation.

Its only owner is `backends.llm_router_backend`.

`backends/interface.py` assigns:

- `INTERFACE_SCHEMA` `complaint-generator/module-interface@1`
- `INTERFACE_VERSION` `1.0.0`

Public symbols:

- `LLMRouterBackend`
- `load_terminal_router_backend`
