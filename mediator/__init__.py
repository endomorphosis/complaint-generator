from importlib import import_module

_LAZY_EXPORTS = {
    'Mediator': ('.mediator', 'Mediator'),
    'MODULE_OWNERSHIP': ('.mediator', 'MODULE_OWNERSHIP'),
    'RUNTIME_ENTRYPOINT_ROLE': ('.mediator', 'RUNTIME_ENTRYPOINT_ROLE'),
    'ALIGNMENT_TASK_UPDATE_HISTORY_LIMIT': ('.mediator', 'ALIGNMENT_TASK_UPDATE_HISTORY_LIMIT'),
    'FOLLOW_UP_REVIEWABLE_ESCALATION_STATUSES': ('.mediator', 'FOLLOW_UP_REVIEWABLE_ESCALATION_STATUSES'),
    'WorkflowActionService': ('.workflow_service', 'WorkflowActionService'),
    'WorkflowService': ('.workflow_service', 'WorkflowService'),
    'LegalClassificationHook': ('.legal_hooks', 'LegalClassificationHook'),
    'StatuteRetrievalHook': ('.legal_hooks', 'StatuteRetrievalHook'),
    'SummaryJudgmentHook': ('.legal_hooks', 'SummaryJudgmentHook'),
    'QuestionGenerationHook': ('.legal_hooks', 'QuestionGenerationHook'),
    'EvidenceStorageHook': ('.evidence_hooks', 'EvidenceStorageHook'),
    'EvidenceStateHook': ('.evidence_hooks', 'EvidenceStateHook'),
    'EvidenceAnalysisHook': ('.evidence_hooks', 'EvidenceAnalysisHook'),
    'LegalAuthoritySearchHook': ('.legal_authority_hooks', 'LegalAuthoritySearchHook'),
    'LegalAuthorityStorageHook': ('.legal_authority_hooks', 'LegalAuthorityStorageHook'),
    'LegalAuthorityAnalysisHook': ('.legal_authority_hooks', 'LegalAuthorityAnalysisHook'),
    'WebEvidenceSearchHook': ('.web_evidence_hooks', 'WebEvidenceSearchHook'),
    'WebEvidenceIntegrationHook': ('.web_evidence_hooks', 'WebEvidenceIntegrationHook'),
    'ClaimSupportHook': ('.claim_support_hooks', 'ClaimSupportHook'),
    'ComplaintDocumentBuilder': ('.formal_document', 'ComplaintDocumentBuilder'),
    'LegalCorpusRAGHook': ('.legal_corpus_hooks', 'LegalCorpusRAGHook'),
}

__all__ = [
    'Mediator',
    'MODULE_OWNERSHIP',
    'RUNTIME_ENTRYPOINT_ROLE',
    'ALIGNMENT_TASK_UPDATE_HISTORY_LIMIT',
    'FOLLOW_UP_REVIEWABLE_ESCALATION_STATUSES',
    'WorkflowActionService',
    'WorkflowService',
    'LegalClassificationHook',
    'StatuteRetrievalHook',
    'SummaryJudgmentHook',
    'QuestionGenerationHook',
    'EvidenceStorageHook',
    'EvidenceStateHook',
    'EvidenceAnalysisHook',
    'LegalAuthoritySearchHook',
    'LegalAuthorityStorageHook',
    'LegalAuthorityAnalysisHook',
    'WebEvidenceSearchHook',
    'WebEvidenceIntegrationHook',
    'ClaimSupportHook',
    'ComplaintDocumentBuilder',
    'LegalCorpusRAGHook',
]


def __getattr__(name: str):
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(module_name, __name__)
    value = module if attribute_name is None else getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
