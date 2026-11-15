# Owner currency siblings

Each row is a sibling module recorded by the owner-currency campaign and the owner it was extracted from. Versioned interfaces use `INTERFACE_SCHEMA` `complaint-generator/module-interface@1` and `INTERFACE_VERSION` `1.0.0`.

| Sibling | Extracted from |
| --- | --- |
| `complaint_phases/denoiser_answer.py` | `complaint_phases/denoiser.py` |
| `integrations/ipfs_datasets/temporal_reasoning.py` | `integrations/ipfs_datasets/logic.py` |
| `mediator/legal_authority_search.py` | `mediator/legal_authority_hooks.py` |
| `complaint_phases/knowledge_graph_build.py` | `complaint_phases/knowledge_graph.py` |
| `integrations/private_storage_legacy.py` | `integrations/private_storage.py` |

Sibling ownership, boundaries, seams, and the current checkout layout stay in the locked maps. This note links those maps and does not copy their tables.

- [Current layout](docs/architecture/current_layout.md)
- [Consolidation modules](docs/architecture/consolidation_modules.md)
- [Module boundaries](docs/architecture/module_boundaries.md)
- [Module seams](docs/architecture/module_seams.md)
