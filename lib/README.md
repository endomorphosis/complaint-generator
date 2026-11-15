# Lib package

Shared helpers for logging, formal logic, and knowledge-graph export.

## Current entry

New code imports `lib.interface`. That module is the versioned public surface for the lib package. It records owner modules and symbol names without importing those owners.

The interface owners are:

- `lib.log`
- `lib.formal_logic`
- `lib.knowledge_graph_export`

`lib/interface.py` assigns:

- `INTERFACE_SCHEMA` `complaint-generator/module-interface@1`
- `INTERFACE_VERSION` `1.0.0`

The module name is `lib.interface`. `INTERFACE_VERSION` is `1.0.0`. Importing `lib.interface` records `lib.log`, `lib.formal_logic`, and `lib.knowledge_graph_export` and their public symbol names. That import does not import those owners, start a server, or read a private workspace path.
