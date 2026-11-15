# Current repository layout

This note records the layout that the checkout uses now. Historical plan, backlog, and tasklist documents are not the current architecture. Read them as archive context only.

## Root markdown set

The root markdown set is README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, and TODO.md.

## Root shims

These root modules stay shims. Each stays a shim of at most 40 lines and re-exports the sibling body named in the consolidation map:

- intake_status.py
- workflow_phase_guidance.py
- document_pipeline.py
- document_optimization.py
- claim_support_review.py

## Root configs

These configuration files stay at the root:

- config.adversarial_autopatch_demo.json
- config.adversarial_autopatch_live.json
- config.adversarial_autopatch_live_batch.json
- config.adversarial_autopatch_live_multibackend.json
- config.huggingface_router.json
- config.llm_router.json
- config.review_surface.huggingface_router.json
- config.review_surface.json

## Published interface

Published module interfaces use INTERFACE_SCHEMA `complaint-generator/module-interface@1` and INTERFACE_VERSION `1.0.0`.

## Architecture maps

Sibling ownership, boundaries, and seams stay in the locked maps. This note links those maps and does not copy their tables.

- [Consolidation modules](docs/architecture/consolidation_modules.md)
- [Module boundaries](docs/architecture/module_boundaries.md)
- [Module seams](docs/architecture/module_seams.md)

## Plan compiler

The plan compiler file is `improvement_plan.py` under the accelerate facade directory `integrations/ipfs_accelerate/`.
