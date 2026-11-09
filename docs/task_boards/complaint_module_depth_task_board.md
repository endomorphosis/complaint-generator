# Cut the remaining giant modules into versioned module interfaces

<!-- plan_id: baguqeeraj5l77vpyuppxtfwkohv2t5ae3ro6s667r5zthnwmcmyckmfko7aq -->

Implementation tasks begin pending. Completion requires behavioral validation evidence.

## CIMP-DEP-01 Delegate workspace research and interview helpers to a sibling module

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: DEP-extract
- Subgoal: DEP-owners
- Depends on: 
- Outputs: applications/complaint_workspace.py, applications/complaint_workspace_research.py, tests/test_cimp_dep_01.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_01.py
- Acceptance: applications/complaint_workspace_research.py defines the four extracted names and is at least 850 lines. applications/complaint_workspace.py is at most 17600 lines. Each extracted method is one Return of a Call. _dispatch_mcp_tool remains on ComplaintWorkspaceService.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement. The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling. Extract only these ComplaintWorkspaceService methods into applications/complaint_workspace_research.py: get_provider_diagnostics, run_legal_research, _build_workspace_logic_flow, apply_shared_interview. Do not extract _dispatch_mcp_tool, improve_draft, _build_draft, _analyze_complaint_output, sync_mike_final_draft, or build_mike_handoff. Do not edit applications/interface.py or applications/complaint_workspace_drafting.py. The owner file must end at or under 17600 lines. The sibling must be at least 850 lines. The sentinel is _dispatch_mcp_tool.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement.
> The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling.
> Extract only these ComplaintWorkspaceService methods into applications/complaint_workspace_research.py: get_provider_diagnostics, run_legal_research, _build_workspace_logic_flow, apply_shared_interview.
> Do not extract _dispatch_mcp_tool, improve_draft, _build_draft, _analyze_complaint_output, sync_mike_final_draft, or build_mike_handoff. Do not edit applications/interface.py or applications/complaint_workspace_drafting.py.
> The owner file must end at or under 17600 lines. The sibling must be at least 850 lines. The sentinel is _dispatch_mcp_tool.

## CIMP-DEP-02 Delegate mediator follow-up execution to a sibling module

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: DEP-extract
- Subgoal: DEP-owners
- Depends on: 
- Outputs: mediator/mediator.py, mediator/claim_follow_up_flow.py, tests/test_cimp_dep_02.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_02.py
- Acceptance: mediator/claim_follow_up_flow.py defines the four extracted names and is at least 1100 lines. mediator/mediator.py is at most 12600 lines. Each extracted method is one Return of a Call. research_case_automatically remains on Mediator.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement. The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling. Extract only these Mediator methods into mediator/claim_follow_up_flow.py: execute_claim_follow_up_plan, get_three_phase_status, _apply_intake_answer_to_case_file, _build_follow_up_task. Do not extract research_case_automatically or the intake-question methods already moved to mediator/intake_question_flow.py. Do not edit mediator/interface.py or mediator/intake_question_flow.py. Mediator uses tabs. Keep that indentation on the owner shims. The sibling is dedented. The owner file must end at or under 12600 lines. The sibling must be at least 1100 lines. The sentinel is research_case_automatically.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement.
> The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling.
> Extract only these Mediator methods into mediator/claim_follow_up_flow.py: execute_claim_follow_up_plan, get_three_phase_status, _apply_intake_answer_to_case_file, _build_follow_up_task.
> Do not extract research_case_automatically or the intake-question methods already moved to mediator/intake_question_flow.py. Do not edit mediator/interface.py or mediator/intake_question_flow.py.
> Mediator uses tabs. Keep that indentation on the owner shims. The sibling is dedented.
> The owner file must end at or under 12600 lines. The sibling must be at least 1100 lines. The sentinel is research_case_automatically.

## CIMP-DEP-03 Delegate formal-document rendering to a sibling module

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: DEP-extract
- Subgoal: DEP-owners
- Depends on: 
- Outputs: complaint_phases/document_pipeline.py, complaint_phases/document_pipeline_render.py, tests/test_cimp_dep_03.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_03.py
- Acceptance: complaint_phases/document_pipeline_render.py defines the three extracted names and is at least 600 lines. complaint_phases/document_pipeline.py is at most 9600 lines. Each extracted method is one Return of a Call. build_package remains on FormalComplaintDocumentBuilder.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement. The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling. Extract only these FormalComplaintDocumentBuilder methods into complaint_phases/document_pipeline_render.py: _build_runtime_workflow_phase_plan, _render_pdf, _render_docx. Do not extract build_package. Do not edit complaint_phases/document_pipeline_guidance.py, complaint_phases/document_pipeline_readiness.py, or the root document_pipeline.py shim. The owner file must end at or under 9600 lines. The sibling must be at least 600 lines. The sentinel is build_package.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement.
> The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling.
> Extract only these FormalComplaintDocumentBuilder methods into complaint_phases/document_pipeline_render.py: _build_runtime_workflow_phase_plan, _render_pdf, _render_docx.
> Do not extract build_package. Do not edit complaint_phases/document_pipeline_guidance.py, complaint_phases/document_pipeline_readiness.py, or the root document_pipeline.py shim.
> The owner file must end at or under 9600 lines. The sibling must be at least 600 lines. The sentinel is build_package.

## CIMP-DEP-04 Delegate claim-support recommendation builders to a sibling module

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: DEP-extract
- Subgoal: DEP-owners
- Depends on: 
- Outputs: mediator/claim_support_hooks.py, mediator/claim_support_recommendations.py, tests/test_cimp_dep_04.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_04.py
- Acceptance: mediator/claim_support_recommendations.py defines the four extracted names and is at least 700 lines. mediator/claim_support_hooks.py is at most 8900 lines. Each extracted method is one Return of a Call. upsert_support_link remains on ClaimSupportHook.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement. The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling. Extract only these ClaimSupportHook methods into mediator/claim_support_recommendations.py: get_question_recommendations, get_support_paths_for_element, _build_claim_validation, _build_reasoning_predicates. Do not extract upsert_support_link. Do not edit mediator/claim_support_diagnostics.py or mediator/hook_runtime.py. The owner file must end at or under 8900 lines. The sibling must be at least 700 lines. The sentinel is upsert_support_link.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement.
> The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling.
> Extract only these ClaimSupportHook methods into mediator/claim_support_recommendations.py: get_question_recommendations, get_support_paths_for_element, _build_claim_validation, _build_reasoning_predicates.
> Do not extract upsert_support_link. Do not edit mediator/claim_support_diagnostics.py or mediator/hook_runtime.py.
> The owner file must end at or under 8900 lines. The sibling must be at least 700 lines. The sentinel is upsert_support_link.

## CIMP-DEP-05 Delegate denoiser binding and review-question helpers to a sibling module

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: DEP-extract
- Subgoal: DEP-owners
- Depends on: 
- Outputs: complaint_phases/denoiser.py, complaint_phases/denoiser_bindings.py, tests/test_cimp_dep_05.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_05.py
- Acceptance: complaint_phases/denoiser_bindings.py defines the four extracted names and is at least 500 lines. complaint_phases/denoiser.py is at most 7400 lines. Each extracted method is one Return of a Call. process_answer and select_question_candidates remain on ComplaintDenoiser.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement. The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling. Extract only these ComplaintDenoiser methods into complaint_phases/denoiser_bindings.py: _build_claim_element_questions, generate_review_question_recommendations, _bind_unresolved_target, _build_claim_temporal_gap_questions. Do not move process_answer or select_question_candidates. Do not edit complaint_phases/denoiser_questions.py or complaint_phases/interface.py. The owner file must end at or under 7400 lines. The sibling must be at least 500 lines. Both process_answer and select_question_candidates are sentinels and stay on the class with bodies longer than one statement.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement.
> The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling.
> Extract only these ComplaintDenoiser methods into complaint_phases/denoiser_bindings.py: _build_claim_element_questions, generate_review_question_recommendations, _bind_unresolved_target, _build_claim_temporal_gap_questions.
> Do not move process_answer or select_question_candidates. Do not edit complaint_phases/denoiser_questions.py or complaint_phases/interface.py.
> The owner file must end at or under 7400 lines. The sibling must be at least 500 lines. Both process_answer and select_question_candidates are sentinels and stay on the class with bodies longer than one statement.

## CIMP-DEP-06 Move dashboard hub rendering out of dashboard_ui.py

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: DEP-extract
- Subgoal: DEP-owners
- Depends on: 
- Outputs: applications/dashboard_ui.py, applications/dashboard_hub.py, tests/test_cimp_dep_06.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_06.py
- Acceptance: applications/dashboard_hub.py defines _render_dashboard_hub and is at least 4500 lines. applications/dashboard_ui.py is at most 1200 lines, imports _render_dashboard_hub, and still defines create_dashboard_ui_router.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  These are module-level functions. Move them into the sibling module. The owner module must import those names and must not define them again. Leave the named sentinel defined in the owner. The test parses both files with ast. The owner module no longer defines the extracted names. The sentinel is still defined in the owner. The sibling defines the extracted names. Assert the owner line count and the sibling line count. Move the module-level function _render_dashboard_hub from applications/dashboard_ui.py into applications/dashboard_hub.py. The owner imports that name and does not define it again. Leave create_dashboard_ui_router defined in applications/dashboard_ui.py. Do not edit applications/interface.py. The owner file must end at or under 1200 lines. The sibling must be at least 4500 lines. The sentinel is create_dashboard_ui_router.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> These are module-level functions. Move them into the sibling module. The owner module must import those names and must not define them again. Leave the named sentinel defined in the owner.
> The test parses both files with ast. The owner module no longer defines the extracted names. The sentinel is still defined in the owner. The sibling defines the extracted names. Assert the owner line count and the sibling line count.
> Move the module-level function _render_dashboard_hub from applications/dashboard_ui.py into applications/dashboard_hub.py. The owner imports that name and does not define it again.
> Leave create_dashboard_ui_router defined in applications/dashboard_ui.py. Do not edit applications/interface.py.
> The owner file must end at or under 1200 lines. The sibling must be at least 4500 lines. The sentinel is create_dashboard_ui_router.

## CIMP-DEP-07 Delegate optimizer fallback construction to a sibling module

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: DEP-extract
- Subgoal: DEP-owners
- Depends on: 
- Outputs: adversarial_harness/optimizer.py, adversarial_harness/optimizer_fallback.py, tests/test_cimp_dep_07.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_07.py
- Acceptance: adversarial_harness/optimizer_fallback.py defines _fallback_agentic_optimizer_components and is at least 700 lines. adversarial_harness/optimizer.py is at most 5900 lines. The extracted method is one Return of a Call. analyze remains on Optimizer.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement. The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling. Extract only Optimizer._fallback_agentic_optimizer_components into adversarial_harness/optimizer_fallback.py. Do not extract analyze. Do not edit adversarial_harness/harness.py. The owner file must end at or under 5900 lines. The sibling must be at least 700 lines. The sentinel is analyze.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement.
> The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling.
> Extract only Optimizer._fallback_agentic_optimizer_components into adversarial_harness/optimizer_fallback.py.
> Do not extract analyze. Do not edit adversarial_harness/harness.py.
> The owner file must end at or under 5900 lines. The sibling must be at least 700 lines. The sentinel is analyze.

## CIMP-DEP-08 Delegate knowledge-graph extraction to a sibling module

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: DEP-extract
- Subgoal: DEP-owners
- Depends on: 
- Outputs: complaint_phases/knowledge_graph.py, complaint_phases/knowledge_graph_extraction.py, tests/test_cimp_dep_08.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_08.py
- Acceptance: complaint_phases/knowledge_graph_extraction.py defines the two extracted names and is at least 900 lines. complaint_phases/knowledge_graph.py is at most 3900 lines. Each extracted method is one Return of a Call. find_gaps remains on KnowledgeGraph.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement. The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling. Extract only these KnowledgeGraphBuilder methods into complaint_phases/knowledge_graph_extraction.py: _extract_entities, _extract_relationships. Do not extract KnowledgeGraph.find_gaps. Do not edit complaint_phases/interface.py. The owner file must end at or under 3900 lines. The sibling must be at least 900 lines. The sentinel is find_gaps on class KnowledgeGraph.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement.
> The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling.
> Extract only these KnowledgeGraphBuilder methods into complaint_phases/knowledge_graph_extraction.py: _extract_entities, _extract_relationships.
> Do not extract KnowledgeGraph.find_gaps. Do not edit complaint_phases/interface.py.
> The owner file must end at or under 3900 lines. The sibling must be at least 900 lines. The sentinel is find_gaps on class KnowledgeGraph.

## CIMP-DEP-09 Delegate intake open-item builders to a sibling module

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: DEP-extract
- Subgoal: DEP-owners
- Depends on: 
- Outputs: complaint_phases/intake_case_file.py, complaint_phases/intake_case_open_items.py, tests/test_cimp_dep_09.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_09.py
- Acceptance: complaint_phases/intake_case_open_items.py defines the four extracted names and is at least 950 lines. complaint_phases/intake_case_file.py is at most 3700 lines, imports those names, and still defines refresh_intake_case_file.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  These are module-level functions. Move them into the sibling module. The owner module must import those names and must not define them again. Leave the named sentinel defined in the owner. The test parses both files with ast. The owner module no longer defines the extracted names. The sentinel is still defined in the owner. The sibling defines the extracted names. Assert the owner line count and the sibling line count. Move these module-level functions from complaint_phases/intake_case_file.py into complaint_phases/intake_case_open_items.py: build_open_items, build_blocker_follow_up_summary, build_temporal_issue_registry, build_claim_temporal_graphs. The owner imports those names and does not define them again. Leave refresh_intake_case_file defined in the owner. Do not edit complaint_phases/interface.py. The owner file must end at or under 3700 lines. The sibling must be at least 950 lines. The sentinel is refresh_intake_case_file.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> These are module-level functions. Move them into the sibling module. The owner module must import those names and must not define them again. Leave the named sentinel defined in the owner.
> The test parses both files with ast. The owner module no longer defines the extracted names. The sentinel is still defined in the owner. The sibling defines the extracted names. Assert the owner line count and the sibling line count.
> Move these module-level functions from complaint_phases/intake_case_file.py into complaint_phases/intake_case_open_items.py: build_open_items, build_blocker_follow_up_summary, build_temporal_issue_registry, build_claim_temporal_graphs.
> The owner imports those names and does not define them again. Leave refresh_intake_case_file defined in the owner. Do not edit complaint_phases/interface.py.
> The owner file must end at or under 3700 lines. The sibling must be at least 950 lines. The sentinel is refresh_intake_case_file.

## CIMP-DEP-10 Delegate document-optimization support context to a sibling module

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: DEP-extract
- Subgoal: DEP-owners
- Depends on: 
- Outputs: complaint_phases/document_optimization.py, complaint_phases/document_optimization_support.py, tests/test_cimp_dep_10.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_10.py
- Acceptance: complaint_phases/document_optimization_support.py defines _build_support_context and is at least 550 lines. complaint_phases/document_optimization.py is at most 3600 lines. The extracted method is one Return of a Call. optimize_draft remains on AgenticDocumentOptimizer.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement. The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling. Extract only AgenticDocumentOptimizer._build_support_context into complaint_phases/document_optimization_support.py. Do not extract optimize_draft. Do not edit complaint_phases/document_optimization_summaries.py or the root document_optimization.py shim. The owner file must end at or under 3600 lines. The sibling must be at least 550 lines. The sentinel is optimize_draft.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement.
> The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling.
> Extract only AgenticDocumentOptimizer._build_support_context into complaint_phases/document_optimization_support.py.
> Do not extract optimize_draft. Do not edit complaint_phases/document_optimization_summaries.py or the root document_optimization.py shim.
> The owner file must end at or under 3600 lines. The sibling must be at least 550 lines. The sentinel is optimize_draft.

## CIMP-DEP-11 Delegate claim-support follow-up summaries to a sibling module

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: DEP-extract
- Subgoal: DEP-owners
- Depends on: 
- Outputs: mediator/claim_support_review.py, mediator/claim_support_review_followups.py, tests/test_cimp_dep_11.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_11.py
- Acceptance: mediator/claim_support_review_followups.py defines the two extracted names and is at least 600 lines. mediator/claim_support_review.py is at most 4000 lines, imports those names, and still defines _summarize_claim_coverage_claim.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  These are module-level functions. Move them into the sibling module. The owner module must import those names and must not define them again. Leave the named sentinel defined in the owner. The test parses both files with ast. The owner module no longer defines the extracted names. The sentinel is still defined in the owner. The sibling defines the extracted names. Assert the owner line count and the sibling line count. Move these module-level functions from mediator/claim_support_review.py into mediator/claim_support_review_followups.py: summarize_follow_up_history_claim, _summarize_follow_up_execution_claim. The owner imports those names and does not define them again. Leave _summarize_claim_coverage_claim defined in the owner. Do not edit mediator/claim_support_review_sections.py or the root claim_support_review.py shim. The owner file must end at or under 4000 lines. The sibling must be at least 600 lines. The sentinel is _summarize_claim_coverage_claim.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> These are module-level functions. Move them into the sibling module. The owner module must import those names and must not define them again. Leave the named sentinel defined in the owner.
> The test parses both files with ast. The owner module no longer defines the extracted names. The sentinel is still defined in the owner. The sibling defines the extracted names. Assert the owner line count and the sibling line count.
> Move these module-level functions from mediator/claim_support_review.py into mediator/claim_support_review_followups.py: summarize_follow_up_history_claim, _summarize_follow_up_execution_claim.
> The owner imports those names and does not define them again. Leave _summarize_claim_coverage_claim defined in the owner. Do not edit mediator/claim_support_review_sections.py or the root claim_support_review.py shim.
> The owner file must end at or under 4000 lines. The sibling must be at least 600 lines. The sentinel is _summarize_claim_coverage_claim.

## CIMP-DEP-12 Delegate hook-runtime effect dispatch to a sibling module

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: DEP-extract
- Subgoal: DEP-owners
- Depends on: 
- Outputs: mediator/hook_runtime.py, mediator/hook_runtime_dispatch.py, tests/test_cimp_dep_12.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_12.py
- Acceptance: mediator/hook_runtime_dispatch.py defines the two extracted names and is at least 500 lines. mediator/hook_runtime.py is at most 4000 lines, imports those names, and still defines dispatch_registered_hook_operation.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  These are module-level functions. Move them into the sibling module. The owner module must import those names and must not define them again. Leave the named sentinel defined in the owner. The test parses both files with ast. The owner module no longer defines the extracted names. The sentinel is still defined in the owner. The sibling defines the extracted names. Assert the owner line count and the sibling line count. Move these module-level functions from mediator/hook_runtime.py into mediator/hook_runtime_dispatch.py: dispatch_observed_hook_purpose, accept_bound_hook_effect. The owner imports those names and does not define them again. Leave dispatch_registered_hook_operation defined in the owner. Do not edit mediator/claim_support_hooks.py or mediator/interface.py. The owner file must end at or under 4000 lines. The sibling must be at least 500 lines. The sentinel is dispatch_registered_hook_operation.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> These are module-level functions. Move them into the sibling module. The owner module must import those names and must not define them again. Leave the named sentinel defined in the owner.
> The test parses both files with ast. The owner module no longer defines the extracted names. The sentinel is still defined in the owner. The sibling defines the extracted names. Assert the owner line count and the sibling line count.
> Move these module-level functions from mediator/hook_runtime.py into mediator/hook_runtime_dispatch.py: dispatch_observed_hook_purpose, accept_bound_hook_effect.
> The owner imports those names and does not define them again. Leave dispatch_registered_hook_operation defined in the owner. Do not edit mediator/claim_support_hooks.py or mediator/interface.py.
> The owner file must end at or under 4000 lines. The sibling must be at least 500 lines. The sentinel is dispatch_registered_hook_operation.

## CIMP-DEP-13 Delegate legal-authority storage setup to a sibling module

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: DEP-extract
- Subgoal: DEP-owners
- Depends on: 
- Outputs: mediator/legal_authority_hooks.py, mediator/legal_authority_storage.py, tests/test_cimp_dep_13.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_13.py
- Acceptance: mediator/legal_authority_storage.py defines the three extracted names and is at least 500 lines. mediator/legal_authority_hooks.py is at most 3700 lines. Each extracted method is one Return of a Call. build_search_programs remains on LegalAuthoritySearchHook.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement. The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling. Extract only these LegalAuthorityStorageHook methods into mediator/legal_authority_storage.py: upsert_authority, _initialize_schema, _extract_rule_candidates. Do not extract LegalAuthoritySearchHook.build_search_programs. Do not edit mediator/interface.py. The owner file must end at or under 3700 lines. The sibling must be at least 500 lines. The sentinel is build_search_programs on LegalAuthoritySearchHook.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> On each named class method, replace the body with exactly one Return of a Call to a function of the same name in the sibling module. The sibling function keeps the old body and takes self as its first parameter. Leave the named sentinel defined on its original class with a body longer than one statement.
> The test parses both files with ast. Each extracted method has exactly one statement and it is a Return of a Call. The sentinel remains and is not defined in the sibling. Assert the owner line count and the sibling line count. Assert each extracted name is defined in the sibling.
> Extract only these LegalAuthorityStorageHook methods into mediator/legal_authority_storage.py: upsert_authority, _initialize_schema, _extract_rule_candidates.
> Do not extract LegalAuthoritySearchHook.build_search_programs. Do not edit mediator/interface.py.
> The owner file must end at or under 3700 lines. The sibling must be at least 500 lines. The sentinel is build_search_programs on LegalAuthoritySearchHook.

## CIMP-DEP-14 Add a versioned interface for the adversarial harness

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: DEP-facade
- Subgoal: DEP-public
- Depends on: 
- Outputs: adversarial_harness/interface.py, tests/test_cimp_dep_14.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_14.py
- Acceptance: adversarial_harness.interface defines the module-interface schema and version and does not import the optimizer module at import time. AdversarialHarness, Optimizer, and AdversarialSession are lazy exports of the owner classes.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  Create adversarial_harness/interface.py. Set INTERFACE_SCHEMA to complaint-generator/module-interface@1 and INTERFACE_VERSION to 1.0.0. Record owner modules adversarial_harness.harness, adversarial_harness.optimizer, and adversarial_harness.session. Lazy-export AdversarialHarness from adversarial_harness.harness, Optimizer from adversarial_harness.optimizer, and AdversarialSession from adversarial_harness.session. Importing adversarial_harness.interface must not import those owner modules. The first access of each name loads the owner object. Do not move optimizer.py in this task. tests/test_cimp_dep_14.py loads the interface, asserts the schema and version, asserts the three owner modules are not in sys.modules before attribute access, then asserts each lazy name is the owner class.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> Create adversarial_harness/interface.py. Set INTERFACE_SCHEMA to complaint-generator/module-interface@1 and INTERFACE_VERSION to 1.0.0.
> Record owner modules adversarial_harness.harness, adversarial_harness.optimizer, and adversarial_harness.session.
> Lazy-export AdversarialHarness from adversarial_harness.harness, Optimizer from adversarial_harness.optimizer, and AdversarialSession from adversarial_harness.session.
> Importing adversarial_harness.interface must not import those owner modules. The first access of each name loads the owner object.
> Do not move optimizer.py in this task.
> tests/test_cimp_dep_14.py loads the interface, asserts the schema and version, asserts the three owner modules are not in sys.modules before attribute access, then asserts each lazy name is the owner class.

## CIMP-DEP-15 Add a versioned interface for complaint analysis

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: DEP-facade
- Subgoal: DEP-public
- Depends on: 
- Outputs: complaint_analysis/interface.py, tests/test_cimp_dep_15.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_15.py
- Acceptance: complaint_analysis.interface defines the module-interface schema and version and does not import the analyzer module at import time. ComplaintAnalyzer, LegalPatternExtractor, and ResponseParserFactory are lazy exports of the owner classes.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  Create complaint_analysis/interface.py. Set INTERFACE_SCHEMA to complaint-generator/module-interface@1 and INTERFACE_VERSION to 1.0.0. Record owner modules complaint_analysis.analyzer, complaint_analysis.legal_patterns, and complaint_analysis.response_parsers. Lazy-export ComplaintAnalyzer from complaint_analysis.analyzer, LegalPatternExtractor from complaint_analysis.legal_patterns, and ResponseParserFactory from complaint_analysis.response_parsers. Importing complaint_analysis.interface must not import those owner modules. Do not split analyzer.py in this task. tests/test_cimp_dep_15.py asserts the schema and version, asserts the owner modules are absent from sys.modules before attribute access, then asserts each lazy name is the owner class.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> Create complaint_analysis/interface.py. Set INTERFACE_SCHEMA to complaint-generator/module-interface@1 and INTERFACE_VERSION to 1.0.0.
> Record owner modules complaint_analysis.analyzer, complaint_analysis.legal_patterns, and complaint_analysis.response_parsers.
> Lazy-export ComplaintAnalyzer from complaint_analysis.analyzer, LegalPatternExtractor from complaint_analysis.legal_patterns, and ResponseParserFactory from complaint_analysis.response_parsers.
> Importing complaint_analysis.interface must not import those owner modules.
> Do not split analyzer.py in this task.
> tests/test_cimp_dep_15.py asserts the schema and version, asserts the owner modules are absent from sys.modules before attribute access, then asserts each lazy name is the owner class.

## CIMP-DEP-16 Add a versioned interface for router backends

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: DEP-facade
- Subgoal: DEP-public
- Depends on: 
- Outputs: backends/interface.py, tests/test_cimp_dep_16.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_16.py
- Acceptance: backends.interface defines the module-interface schema and version and does not import the router implementation at import time. LLMRouterBackend and load_terminal_router_backend are lazy exports of backends.llm_router_backend.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  Create backends/interface.py. Set INTERFACE_SCHEMA to complaint-generator/module-interface@1 and INTERFACE_VERSION to 1.0.0. Record owner module backends.llm_router_backend. Lazy-export LLMRouterBackend and load_terminal_router_backend from that module. Importing backends.interface must not import backends.llm_router_backend and must not import the provider backend modules. Do not edit backends/llm_router_backend.py. tests/test_cimp_dep_16.py asserts the schema and version and the lazy identity of both names. Build any banned provider module name by concatenation inside the test. A test source that contains a contiguous provider name is skipped and fails this task.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> Create backends/interface.py. Set INTERFACE_SCHEMA to complaint-generator/module-interface@1 and INTERFACE_VERSION to 1.0.0.
> Record owner module backends.llm_router_backend.
> Lazy-export LLMRouterBackend and load_terminal_router_backend from that module.
> Importing backends.interface must not import backends.llm_router_backend and must not import the provider backend modules.
> Do not edit backends/llm_router_backend.py.
> tests/test_cimp_dep_16.py asserts the schema and version and the lazy identity of both names. Build any banned provider module name by concatenation inside the test. A test source that contains a contiguous provider name is skipped and fails this task.

## CIMP-DEP-17 Add a package interface over the three integration facades

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: DEP-facade
- Subgoal: DEP-public
- Depends on: 
- Outputs: integrations/interface.py, tests/test_cimp_dep_17.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_17.py
- Acceptance: integrations.interface defines the module-interface schema and version and names the three existing integration interface modules. Importing integrations.interface does not import integrations.private_storage or integrations.ipfs_datasets.logic.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  Create integrations/interface.py. Set INTERFACE_SCHEMA to complaint-generator/module-interface@1 and INTERFACE_VERSION to 1.0.0. OWNER_MODULES is exactly the three existing facade modules: integrations.ipfs_datasets.interface, integrations.mike.interface, and the accelerate facade interface module. Do not import integrations.private_storage or integrations.ipfs_datasets.logic from this module. Do not move private_storage.py or logic.py. Private key storage and datasets legal logic stay in their current modules. tests/test_cimp_dep_17.py parses or imports the interface, asserts the schema, version, and three owner module names, and asserts private_storage and ipfs_datasets.logic are not imported as a side effect of importing the interface. Do not write the contiguous letters accelerate in the test file. Identify the third owner by an AST or suffix check.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> Create integrations/interface.py. Set INTERFACE_SCHEMA to complaint-generator/module-interface@1 and INTERFACE_VERSION to 1.0.0.
> OWNER_MODULES is exactly the three existing facade modules: integrations.ipfs_datasets.interface, integrations.mike.interface, and the accelerate facade interface module. Do not import integrations.private_storage or integrations.ipfs_datasets.logic from this module.
> Do not move private_storage.py or logic.py. Private key storage and datasets legal logic stay in their current modules.
> tests/test_cimp_dep_17.py parses or imports the interface, asserts the schema, version, and three owner module names, and asserts private_storage and ipfs_datasets.logic are not imported as a side effect of importing the interface. Do not write the contiguous letters accelerate in the test file. Identify the third owner by an AST or suffix check.

## CIMP-DEP-18 Retarget the sixteen current docs whose relative links do not resolve

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: DEP-docs
- Subgoal: DEP-links
- Depends on: 
- Outputs: docs/OBSERVABILITY_INDEX.md, docs/IPFS_DATASETS_PY_INTEGRATION.md, docs/REFINEMENT_STRATEGY_GUIDE.md, docs/PERFORMANCE_TUNING.md, docs/GRAPHRAG_REFACTORING_ROADMAP.md, docs/migration/LOGGING_MIGRATION_GUIDE.md, docs/optimizers/API_TYPE_CONTRACTS.md, docs/optimizers/PERFORMANCE_TUNING_GUIDE.md, docs/integration/CIRCUIT_BREAKER_GUIDE.md, docs/PRODUCTION_DEPLOYMENT_GUIDE.md, docs/metrics/PROMETHEUS_GUIDE.md, docs/tracing/OTEL_GUIDE.md, docs/optimizers/TROUBLESHOOTING_GUIDE.md, docs/COMPLAINT_ANALYSIS_EXAMPLES.md, docs/optimizers/DISTRIBUTED_ONTOLOGY_REFINEMENT.md, docs/optimizers/INTEGRATION_EXAMPLES.md, tests/test_cimp_dep_18.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_18.py
- Acceptance: Each of the sixteen docs still exists at its current path. Every relative markdown link in those docs resolves to an existing file, and no doc has fewer relative links than it has now.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  Repair relative markdown links in only these sixteen docs. Do not delete a doc and do not move it into docs/archive. Current relative-link counts that the test must keep as minimums: docs/OBSERVABILITY_INDEX.md 65, docs/IPFS_DATASETS_PY_INTEGRATION.md 9, docs/REFINEMENT_STRATEGY_GUIDE.md 7, docs/PERFORMANCE_TUNING.md 6, docs/GRAPHRAG_REFACTORING_ROADMAP.md 8, docs/migration/LOGGING_MIGRATION_GUIDE.md 5, docs/optimizers/API_TYPE_CONTRACTS.md 5, docs/optimizers/PERFORMANCE_TUNING_GUIDE.md 5, docs/integration/CIRCUIT_BREAKER_GUIDE.md 4, docs/PRODUCTION_DEPLOYMENT_GUIDE.md 3, docs/metrics/PROMETHEUS_GUIDE.md 3, docs/tracing/OTEL_GUIDE.md 3, docs/optimizers/TROUBLESHOOTING_GUIDE.md 5, docs/COMPLAINT_ANALYSIS_EXAMPLES.md 1, docs/optimizers/DISTRIBUTED_ONTOLOGY_REFINEMENT.md 2, docs/optimizers/INTEGRATION_EXAMPLES.md 8. Retarget a broken link to the existing file with the same basename when that file exists. Session summaries live under docs/archive/sessions. Datasets implementation files live under external/ipfs_datasets_py. Guides in this repository use their real filenames, including docs/metrics/PROMETHEUS_GUIDE.md and docs/tracing/OTEL_GUIDE.md. A link whose basename does not exist must point at the existing guide or module it was trying to name, not at a new stub file. tests/test_cimp_dep_18.py hard-codes the sixteen paths and the minimum link counts. It resolves every relative markdown link and fails when a target is missing or a count drops. It does not import a helper from an earlier CIMP test. It does not treat an archived copy as a reason to delete the current doc.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> Repair relative markdown links in only these sixteen docs. Do not delete a doc and do not move it into docs/archive.
> Current relative-link counts that the test must keep as minimums: docs/OBSERVABILITY_INDEX.md 65, docs/IPFS_DATASETS_PY_INTEGRATION.md 9, docs/REFINEMENT_STRATEGY_GUIDE.md 7, docs/PERFORMANCE_TUNING.md 6, docs/GRAPHRAG_REFACTORING_ROADMAP.md 8, docs/migration/LOGGING_MIGRATION_GUIDE.md 5, docs/optimizers/API_TYPE_CONTRACTS.md 5, docs/optimizers/PERFORMANCE_TUNING_GUIDE.md 5, docs/integration/CIRCUIT_BREAKER_GUIDE.md 4, docs/PRODUCTION_DEPLOYMENT_GUIDE.md 3, docs/metrics/PROMETHEUS_GUIDE.md 3, docs/tracing/OTEL_GUIDE.md 3, docs/optimizers/TROUBLESHOOTING_GUIDE.md 5, docs/COMPLAINT_ANALYSIS_EXAMPLES.md 1, docs/optimizers/DISTRIBUTED_ONTOLOGY_REFINEMENT.md 2, docs/optimizers/INTEGRATION_EXAMPLES.md 8.
> Retarget a broken link to the existing file with the same basename when that file exists. Session summaries live under docs/archive/sessions. Datasets implementation files live under external/ipfs_datasets_py. Guides in this repository use their real filenames, including docs/metrics/PROMETHEUS_GUIDE.md and docs/tracing/OTEL_GUIDE.md. A link whose basename does not exist must point at the existing guide or module it was trying to name, not at a new stub file.
> tests/test_cimp_dep_18.py hard-codes the sixteen paths and the minimum link counts. It resolves every relative markdown link and fails when a target is missing or a count drops. It does not import a helper from an earlier CIMP test. It does not treat an archived copy as a reason to delete the current doc.

## CIMP-DEP-19 Name the new sibling modules in the consolidation map and root docs

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: DEP-docs
- Subgoal: DEP-map
- Depends on: CIMP-DEP-01, CIMP-DEP-02, CIMP-DEP-03, CIMP-DEP-04, CIMP-DEP-05, CIMP-DEP-06, CIMP-DEP-07, CIMP-DEP-08, CIMP-DEP-09, CIMP-DEP-10, CIMP-DEP-11, CIMP-DEP-12, CIMP-DEP-13
- Outputs: docs/architecture/consolidation_modules.md, README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, tests/test_cimp_dep_19.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_19.py
- Acceptance: docs/architecture/consolidation_modules.md names every previously extracted sibling and every sibling added by this campaign, with the owner it came from. The four root docs still name the archive directories, the claim-support review path, and the module-interface schema and version.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  Update docs/architecture/consolidation_modules.md so it still names the thirteen siblings from the consolidation campaign and also names the thirteen siblings added here: applications/complaint_workspace_research.py, mediator/claim_follow_up_flow.py, complaint_phases/document_pipeline_render.py, mediator/claim_support_recommendations.py, complaint_phases/denoiser_bindings.py, applications/dashboard_hub.py, adversarial_harness/optimizer_fallback.py, complaint_phases/knowledge_graph_extraction.py, complaint_phases/intake_case_open_items.py, complaint_phases/document_optimization_support.py, mediator/claim_support_review_followups.py, mediator/hook_runtime_dispatch.py, mediator/legal_authority_storage.py. Each row names the owner file it was extracted from. Keep these phrases in README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, and TESTING.md: docs/archive/sessions, docs/archive/reports, mediator/claim_support_review.py, complaint-generator/module-interface@1, 1.0.0, and a link to docs/architecture/consolidation_modules.md. tests/test_cimp_dep_19.py fails if any of those sibling paths or the required phrases is absent. It resolves the consolidation map link from each root doc. It does not contain a URL scheme.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> Update docs/architecture/consolidation_modules.md so it still names the thirteen siblings from the consolidation campaign and also names the thirteen siblings added here: applications/complaint_workspace_research.py, mediator/claim_follow_up_flow.py, complaint_phases/document_pipeline_render.py, mediator/claim_support_recommendations.py, complaint_phases/denoiser_bindings.py, applications/dashboard_hub.py, adversarial_harness/optimizer_fallback.py, complaint_phases/knowledge_graph_extraction.py, complaint_phases/intake_case_open_items.py, complaint_phases/document_optimization_support.py, mediator/claim_support_review_followups.py, mediator/hook_runtime_dispatch.py, mediator/legal_authority_storage.py. Each row names the owner file it was extracted from.
> Keep these phrases in README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, and TESTING.md: docs/archive/sessions, docs/archive/reports, mediator/claim_support_review.py, complaint-generator/module-interface@1, 1.0.0, and a link to docs/architecture/consolidation_modules.md.
> tests/test_cimp_dep_19.py fails if any of those sibling paths or the required phrases is absent. It resolves the consolidation map link from each root doc. It does not contain a URL scheme.

## CIMP-DEP-20 Enforce the module-depth ratchet independently of earlier helpers

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: DEP-closure
- Subgoal: DEP-ratchet
- Depends on: CIMP-DEP-14, CIMP-DEP-15, CIMP-DEP-16, CIMP-DEP-17, CIMP-DEP-18, CIMP-DEP-19
- Outputs: tests/test_cimp_dep_20.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_dep_20.py
- Acceptance: Owner modules are at or under the new line floors and the new sibling modules are at or over their minimums. The four new interfaces export the owner objects, the sixteen repaired docs still resolve, and the five root markdown files are unchanged as a set.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task. Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules. Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters. Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt. Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py. Do not restart the completed consolidation campaign or the completed repository-reorganization campaign. Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider. When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task. Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.  Write tests/test_cimp_dep_20.py as a standalone ratchet. Do not import helpers from tests/test_cimp_con_26.py, tests/test_cimp_mod_19.py, or earlier CIMP-DEP tests. Hard-code the names and floors below. If the tree fails a check, fix the tree. Do not relax the check. Root markdown must be exactly README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, TODO.md. Line floors, owner <= N and sibling >= M: applications/complaint_workspace.py <= 17600 and complaint_workspace_research.py >= 850; mediator/mediator.py <= 12600 and claim_follow_up_flow.py >= 1100; complaint_phases/document_pipeline.py <= 9600 and document_pipeline_render.py >= 600; mediator/claim_support_hooks.py <= 8900 and claim_support_recommendations.py >= 700; complaint_phases/denoiser.py <= 7400 and denoiser_bindings.py >= 500; applications/dashboard_ui.py <= 1200 and dashboard_hub.py >= 4500; adversarial_harness/optimizer.py <= 5900 and optimizer_fallback.py >= 700; complaint_phases/knowledge_graph.py <= 3900 and knowledge_graph_extraction.py >= 900; complaint_phases/intake_case_file.py <= 3700 and intake_case_open_items.py >= 950; complaint_phases/document_optimization.py <= 3600 and document_optimization_support.py >= 550; mediator/claim_support_review.py <= 4000 and claim_support_review_followups.py >= 600; mediator/hook_runtime.py <= 4000 and hook_runtime_dispatch.py >= 500; mediator/legal_authority_hooks.py <= 3700 and legal_authority_storage.py >= 500. Also keep the previous consolidation floors from getting worse: applications/complaint_workspace_drafting.py >= 1250, mediator/intake_question_flow.py >= 1450, complaint_phases/document_pipeline_readiness.py >= 950, complaint_phases/document_pipeline_guidance.py >= 800, complaint_phases/document_optimization_summaries.py >= 650, mediator/claim_support_review_sections.py >= 1600, complaint_phases/denoiser_questions.py >= 1000, mediator/claim_support_diagnostics.py >= 1050. Root shims intake_status.py, workflow_phase_guidance.py, document_pipeline.py, document_optimization.py, and claim_support_review.py stay at most 30 lines and define no function or class. Assert adversarial_harness.interface.AdversarialHarness, complaint_analysis.interface.ComplaintAnalyzer, backends.interface.LLMRouterBackend, and the integrations interface schema are the owner surfaces. Re-check that the sixteen docs from CIMP-DEP-18 still have resolving relative links at the recorded minimum counts. This task grants no completion authority and must not edit external/.

Implementation instructions:

> Preserve behavior. Move or expose only the named code. A catalog, an index, or a test that allows the old definition to remain is a failed task.
> Do not edit external/, gitlinks, or dependency pins. Do not run git submodule update and do not initialize nested submodules.
> Do not touch campaign state, DuckDB, launcher files, quarantines, other task boards, or attempt counters.
> Do not weaken tests, skip them, or xfail them. Do not lower a line-count floor in this prompt.
> Do not edit docs/task_boards/complaint_repository_consolidation_task_board.md or tests/test_cimp_con_26.py.
> Do not restart the completed consolidation campaign or the completed repository-reorganization campaign.
> Write the declared target files. Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> When an interface module is created, set INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0".
> The new test file must not contain the contiguous substrings https://, http://, urllib, openai, accelerate, torch, playwright, or socket. A skipped test is a failed task.
> Use the repository line count from splitlines(). Do not satisfy a floor by deleting comments or docstrings from functions you did not move.
> 
> Write tests/test_cimp_dep_20.py as a standalone ratchet. Do not import helpers from tests/test_cimp_con_26.py, tests/test_cimp_mod_19.py, or earlier CIMP-DEP tests. Hard-code the names and floors below. If the tree fails a check, fix the tree. Do not relax the check.
> Root markdown must be exactly README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, TODO.md.
> Line floors, owner <= N and sibling >= M: applications/complaint_workspace.py <= 17600 and complaint_workspace_research.py >= 850; mediator/mediator.py <= 12600 and claim_follow_up_flow.py >= 1100; complaint_phases/document_pipeline.py <= 9600 and document_pipeline_render.py >= 600; mediator/claim_support_hooks.py <= 8900 and claim_support_recommendations.py >= 700; complaint_phases/denoiser.py <= 7400 and denoiser_bindings.py >= 500; applications/dashboard_ui.py <= 1200 and dashboard_hub.py >= 4500; adversarial_harness/optimizer.py <= 5900 and optimizer_fallback.py >= 700; complaint_phases/knowledge_graph.py <= 3900 and knowledge_graph_extraction.py >= 900; complaint_phases/intake_case_file.py <= 3700 and intake_case_open_items.py >= 950; complaint_phases/document_optimization.py <= 3600 and document_optimization_support.py >= 550; mediator/claim_support_review.py <= 4000 and claim_support_review_followups.py >= 600; mediator/hook_runtime.py <= 4000 and hook_runtime_dispatch.py >= 500; mediator/legal_authority_hooks.py <= 3700 and legal_authority_storage.py >= 500.
> Also keep the previous consolidation floors from getting worse: applications/complaint_workspace_drafting.py >= 1250, mediator/intake_question_flow.py >= 1450, complaint_phases/document_pipeline_readiness.py >= 950, complaint_phases/document_pipeline_guidance.py >= 800, complaint_phases/document_optimization_summaries.py >= 650, mediator/claim_support_review_sections.py >= 1600, complaint_phases/denoiser_questions.py >= 1000, mediator/claim_support_diagnostics.py >= 1050. Root shims intake_status.py, workflow_phase_guidance.py, document_pipeline.py, document_optimization.py, and claim_support_review.py stay at most 30 lines and define no function or class.
> Assert adversarial_harness.interface.AdversarialHarness, complaint_analysis.interface.ComplaintAnalyzer, backends.interface.LLMRouterBackend, and the integrations interface schema are the owner surfaces. Re-check that the sixteen docs from CIMP-DEP-18 still have resolving relative links at the recorded minimum counts. This task grants no completion authority and must not edit external/.
