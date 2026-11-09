# Module boundaries

Callers import the interface modules rather than the owner modules.

`INTERFACE_SCHEMA` is `complaint-generator/module-interface@1`. `INTERFACE_VERSION` is `1.0.0`.

## adversarial_harness/interface.py

- `adversarial_harness.harness`
- `adversarial_harness.optimizer`
- `adversarial_harness.session`

## applications/interface.py

- `applications.server`
- `applications.case_routes`
- `applications.launcher`

## backends/interface.py

- `backends.llm_router_backend`

## complaint_analysis/interface.py

- `complaint_analysis.analyzer`
- `complaint_analysis.legal_patterns`
- `complaint_analysis.response_parsers`

## complaint_generator/interface.py

- `complaint_generator.entrypoints`
- `complaint_generator.workspace`
- `complaint_generator.mcp`

## complaint_phases/interface.py

- `complaint_phases.phase_manager`
- `complaint_phases.knowledge_graph`
- `complaint_phases.intake_case_file`

## integrations/interface.py

- `integrations.ipfs_datasets.interface`
- `integrations.mike.interface`
- `integrations.ipfs_accelerate.interface`

## integrations/ipfs_accelerate/interface.py

- `integrations.ipfs_accelerate.campaign`
- `integrations.ipfs_accelerate.improvement_plan`

## integrations/ipfs_datasets/interface.py

- `integrations.ipfs_datasets.loader`
- `integrations.ipfs_datasets.documents`

## integrations/mike/interface.py

- `integrations.mike`
- `integrations.mike.llm_patch`
- `integrations.mike.skills`

## lib/interface.py

- `lib.log`
- `lib.formal_logic`
- `lib.knowledge_graph_export`

## mediator/interface.py

- `mediator.workflow_service`
- `mediator.hook_runtime`
- `mediator.state`
