# Cohesive-move siblings

Each row is a sibling module extracted by the cohesive-moves campaign and the owner it was extracted from. Versioned interfaces use `INTERFACE_SCHEMA` `complaint-generator/module-interface@1` and `INTERFACE_VERSION` `1.0.0`.

| Sibling | Extracted from |
| --- | --- |
| `complaint_phases/document_pipeline_chronology.py` | `complaint_phases/document_pipeline.py` |
| `adversarial_harness/optimizer_workflow.py` | `adversarial_harness/optimizer.py` |
| `mediator/claim_support_retrieval.py` | `mediator/claim_support_hooks.py` |
| `complaint_phases/intake_case_temporal.py` | `complaint_phases/intake_case_file.py` |
| `integrations/ipfs_datasets/canonical_formalization.py` | `integrations/ipfs_datasets/logic.py` |
| `complaint_phases/document_optimization_guidance.py` | `complaint_phases/document_optimization.py` |

The current checkout layout, owner currency, and the three locked architecture documents stay in their own notes. This note links those maps and does not copy their tables.

- [Current layout](docs/architecture/current_layout.md)
- [Owner currency](docs/architecture/owner_currency.md)
- [Consolidation modules](docs/architecture/consolidation_modules.md)
- [Module boundaries](docs/architecture/module_boundaries.md)
- [Module seams](docs/architecture/module_seams.md)
