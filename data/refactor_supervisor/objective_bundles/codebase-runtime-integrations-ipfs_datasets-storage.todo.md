# Codebase Bundle: codebase/runtime/integrations-ipfs_datasets-storage

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-132 Review swallowed exception path in integrations/ipfs_datasets/storage.py:218

- Status: todo
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, integrations/ipfs_datasets/storage.py
- Validation: python3 -m py_compile integrations/ipfs_datasets/storage.py
- Bundle: codebase/runtime/integrations-ipfs_datasets-storage
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-integrations-ipfs_datasets-storage.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/integrations-ipfs_datasets-storage
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: integrations/ipfs_datasets/storage.py
- AST symbols: __future__, __future__.annotations, __init__, _blob_path, _cid_for_bytes, _discover_repo_local_ipfs_path, _discover_repo_local_kubo_cmd, _ensure_local_kubo_environment, _pin_path, _repo_local_ipfs_kit_root, _runtime_backend_probe, add bytes, add path, add_bytes, add_path, blob path, block get, block put, block_get, block_put, cat, cid for bytes, clear ipfs backend router caches, clear_ipfs_backend_router_caches, dag export, dag_export, discover repo local ipfs path, discover repo local kubo cmd, ensure ipfs backend, ensure local kubo environment, ensure_ipfs_backend, future, future annotations, get ipfs backend, get to path, get_ipfs_backend, get_to_path, hashlib, init, loader, loader import attr optional, loader.import_attr_optional, localcacheipfsbackend, localcacheipfsbackend add bytes, localcacheipfsbackend add path, localcacheipfsbackend blob path, localcacheipfsbackend block get, localcacheipfsbackend block put, localcacheipfsbackend cat, localcacheipfsbackend cid for bytes, localcacheipfsbackend dag export, localcacheipfsbackend get to path, localcacheipfsbackend init, localcacheipfsbackend ls, localcacheipfsbackend pin, localcacheipfsbackend pin path, localcacheipfsbackend unpin, localcacheipfsbackend.__init__, localcacheipfsbackend._blob_path, localcacheipfsbackend._cid_for_bytes, localcacheipfsbackend._pin_path, localcacheipfsbackend.add_bytes, localcacheipfsbackend.add_path, localcacheipfsbackend.block_get, localcacheipfsbackend.block_put, localcacheipfsbackend.cat, localcacheipfsbackend.dag_export, localcacheipfsbackend.get_to_path, localcacheipfsbackend.ls, localcacheipfsbackend.pin, localcacheipfsbackend.unpin, ls, os, pathlib, pathlib path, pathlib.path, pin, pin cid, pin path, pin_cid
- AST symbol scope: file
- Goal id: codebase/runtime/integrations-ipfs_datasets-storage
- Missing evidence: Review swallowed exception path in integrations/ipfs_datasets/storage.py:218
- Merge key: codebase/runtime/integrations-ipfs_datasets-storage
- Merge family: integrations/ipfs_datasets/storage.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 3f2581f03aaa928b
- Acceptance: Codebase scan filed this finding from integrations/ipfs_datasets/storage.py:218. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-132-codebase-scan-3f2581f03aaa.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
