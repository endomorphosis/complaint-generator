# Seam sibling modules

Each row is a sibling module extracted by the module-seams campaign and the owner it was extracted from. Versioned interfaces use `INTERFACE_SCHEMA` `complaint-generator/module-interface@1` and `INTERFACE_VERSION` `1.0.0`.

| Sibling | Extracted from |
| --- | --- |
| `applications/complaint_workspace_mike.py` | `applications/complaint_workspace.py` |
| `mediator/mediator_follow_up_queries.py` | `mediator/mediator.py` |
| `complaint_phases/document_pipeline_email.py` | `complaint_phases/document_pipeline.py` |
| `mediator/claim_support_testimony.py` | `mediator/claim_support_hooks.py` |
| `complaint_phases/denoiser_question_disposition.py` | `complaint_phases/denoiser.py` |
| `adversarial_harness/optimizer_ui_feedback.py` | `adversarial_harness/optimizer.py` |
| `mediator/evidence_scraper_queue.py` | `mediator/evidence_hooks.py` |
| `adversarial_harness/session_document_fallback.py` | `adversarial_harness/session.py` |
| `integrations/ipfs_datasets/canonical_legal_ir.py` | `integrations/ipfs_datasets/logic.py` |
| `integrations/ipfs_datasets/legal_corpus.py` | `integrations/ipfs_datasets/legal.py` |
| `mediator/hook_runtime_remote.py` | `mediator/hook_runtime.py` |
| `mediator/formal_document_chronology.py` | `mediator/formal_document.py` |
| `integrations/private_workspace_transfer.py` | `integrations/private_storage.py` |

Session reports live in `docs/archive/sessions`. Plans and profiles live in `docs/archive/reports`.
