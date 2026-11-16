# Root release keepers

This note records the root files that stay in the release checkout and the generated root paths that are not product modules. `INTERFACE_SCHEMA` is `complaint-generator/module-interface@1` and `INTERFACE_VERSION` is `1.0.0`.

## Root markdown keepers

These five root markdown files are keepers. No other root markdown file is a keeper.

- `README.md`
- `DOCUMENTATION_INDEX.md`
- `CONTRIBUTING.md`
- `TESTING.md`
- `TODO.md`

## Root shims

These five root shims are keepers.

- `intake_status.py`
- `workflow_phase_guidance.py`
- `document_pipeline.py`
- `document_optimization.py`
- `claim_support_review.py`

## Root config files

These eight root config JSON files stay because the CLI defaults use those paths. They are keepers.

- `config.adversarial_autopatch_demo.json`
- `config.adversarial_autopatch_live.json`
- `config.adversarial_autopatch_live_batch.json`
- `config.adversarial_autopatch_live_multibackend.json`
- `config.huggingface_router.json`
- `config.llm_router.json`
- `config.review_surface.huggingface_router.json`
- `config.review_surface.json`

## Compatibility entrypoints

`main.py` and `run.py` are compatibility entrypoints and are keepers.

## Generated files

`drift_report_mcp.json`, `complaint_generator.egg-info`, and `.tmp-demo-output-sessions` are generated and are not product modules.

## Linked layout

The current layout, owner currency, cohesive moves, consolidation modules, module boundaries, and module seams stay in their own notes. This note links those maps and does not copy their tables.

- [Current layout](docs/architecture/current_layout.md)
- [Owner currency](docs/architecture/owner_currency.md)
- [Cohesive moves](docs/architecture/cohesive_moves.md)
- [Consolidation modules](docs/architecture/consolidation_modules.md)
- [Module boundaries](docs/architecture/module_boundaries.md)
- [Module seams](docs/architecture/module_seams.md)
