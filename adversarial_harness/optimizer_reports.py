"""Optimizer report types used by the optimizer engine."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"

@dataclass
class OptimizationReport:
    """Report with optimization insights and recommendations."""
    timestamp: str
    num_sessions_analyzed: int
    
    # Aggregate metrics
    average_score: float
    score_trend: str  # improving, declining, stable
    
    # Analysis by component
    question_quality_avg: float
    information_extraction_avg: float
    empathy_avg: float
    efficiency_avg: float
    coverage_avg: float
    
    # Top issues
    common_weaknesses: List[str]
    common_strengths: List[str]
    
    # Recommendations
    recommendations: List[str]
    priority_improvements: List[str]

    # Graph diagnostics (used to steer graph population/reduction improvements)
    kg_sessions_with_data: int = 0
    dg_sessions_with_data: int = 0
    kg_sessions_empty: int = 0
    dg_sessions_empty: int = 0
    kg_avg_total_entities: Optional[float] = None
    kg_avg_total_relationships: Optional[float] = None
    kg_avg_gaps: Optional[float] = None
    dg_avg_total_nodes: Optional[float] = None
    dg_avg_total_dependencies: Optional[float] = None
    dg_avg_satisfaction_rate: Optional[float] = None
    kg_avg_entities_delta_per_iter: Optional[float] = None
    kg_avg_relationships_delta_per_iter: Optional[float] = None
    kg_avg_gaps_delta_per_iter: Optional[float] = None
    kg_sessions_gaps_not_reducing: int = 0
    
    # Detailed insights
    best_session_id: str = None
    worst_session_id: str = None
    best_score: float = 0.0
    worst_score: float = 1.0
    hacc_preset_performance: Dict[str, Dict[str, Any]] | None = None
    anchor_section_performance: Dict[str, Dict[str, Any]] | None = None
    complaint_type_performance: Dict[str, Dict[str, Any]] | None = None
    evidence_modality_performance: Dict[str, Dict[str, Any]] | None = None
    intake_priority_performance: Dict[str, Any] | None = None
    coverage_remediation: Dict[str, Any] | None = None
    recommended_hacc_preset: str | None = None
    workflow_phase_plan: Dict[str, Any] | None = None
    phase_scorecards: Dict[str, Dict[str, Any]] | None = None
    intake_targeting_summary: Dict[str, Any] | None = None
    workflow_targeting_summary: Dict[str, Any] | None = None
    complaint_type_generalization_summary: Dict[str, Any] | None = None
    evidence_modality_generalization_summary: Dict[str, Any] | None = None
    document_handoff_summary: Dict[str, Any] | None = None
    graph_element_targeting_summary: Dict[str, Any] | None = None
    document_evidence_targeting_summary: Dict[str, Any] | None = None
    document_workflow_execution_summary: Dict[str, Any] | None = None
    document_execution_drift_summary: Dict[str, Any] | None = None
    document_grounding_improvement_summary: Dict[str, Any] | None = None
    document_grounding_lane_outcome_summary: Dict[str, Any] | None = None
    document_chronology_reasoning_summary: Dict[str, Any] | None = None
    cross_phase_findings: List[str] | None = None
    workflow_action_queue: List[Dict[str, Any]] | None = None
    document_provenance_summary: Dict[str, Any] | None = None
    intake_question_structure_summary: Dict[str, Any] | None = None
    document_theory_alignment_summary: Dict[str, Any] | None = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'timestamp': self.timestamp,
            'num_sessions_analyzed': self.num_sessions_analyzed,
            'average_score': self.average_score,
            'score_trend': self.score_trend,
            'question_quality_avg': self.question_quality_avg,
            'information_extraction_avg': self.information_extraction_avg,
            'empathy_avg': self.empathy_avg,
            'efficiency_avg': self.efficiency_avg,
            'coverage_avg': self.coverage_avg,
            'common_weaknesses': self.common_weaknesses,
            'common_strengths': self.common_strengths,
            'recommendations': self.recommendations,
            'priority_improvements': self.priority_improvements,
            'kg_sessions_with_data': self.kg_sessions_with_data,
            'dg_sessions_with_data': self.dg_sessions_with_data,
            'kg_sessions_empty': self.kg_sessions_empty,
            'dg_sessions_empty': self.dg_sessions_empty,
            'kg_avg_total_entities': self.kg_avg_total_entities,
            'kg_avg_total_relationships': self.kg_avg_total_relationships,
            'kg_avg_gaps': self.kg_avg_gaps,
            'dg_avg_total_nodes': self.dg_avg_total_nodes,
            'dg_avg_total_dependencies': self.dg_avg_total_dependencies,
            'dg_avg_satisfaction_rate': self.dg_avg_satisfaction_rate,
            'kg_avg_entities_delta_per_iter': self.kg_avg_entities_delta_per_iter,
            'kg_avg_relationships_delta_per_iter': self.kg_avg_relationships_delta_per_iter,
            'kg_avg_gaps_delta_per_iter': self.kg_avg_gaps_delta_per_iter,
            'kg_sessions_gaps_not_reducing': self.kg_sessions_gaps_not_reducing,
            'best_session_id': self.best_session_id,
            'worst_session_id': self.worst_session_id,
            'best_score': self.best_score,
            'worst_score': self.worst_score,
            'hacc_preset_performance': self.hacc_preset_performance or {},
            'anchor_section_performance': self.anchor_section_performance or {},
            'complaint_type_performance': self.complaint_type_performance or {},
            'evidence_modality_performance': self.evidence_modality_performance or {},
            'intake_priority_performance': self.intake_priority_performance or {},
            'coverage_remediation': self.coverage_remediation or {},
            'recommended_hacc_preset': self.recommended_hacc_preset,
            'workflow_phase_plan': self.workflow_phase_plan or {},
            'phase_scorecards': self.phase_scorecards or {},
            'intake_targeting_summary': self.intake_targeting_summary or {},
            'workflow_targeting_summary': self.workflow_targeting_summary or {},
            'complaint_type_generalization_summary': self.complaint_type_generalization_summary or {},
            'evidence_modality_generalization_summary': self.evidence_modality_generalization_summary or {},
            'document_handoff_summary': self.document_handoff_summary or {},
            'graph_element_targeting_summary': self.graph_element_targeting_summary or {},
            'document_evidence_targeting_summary': self.document_evidence_targeting_summary or {},
            'document_provenance_summary': self.document_provenance_summary or {},
            'document_workflow_execution_summary': self.document_workflow_execution_summary or {},
            'document_execution_drift_summary': self.document_execution_drift_summary or {},
            'document_grounding_improvement_summary': self.document_grounding_improvement_summary or {},
            'document_grounding_lane_outcome_summary': self.document_grounding_lane_outcome_summary or {},
            'document_chronology_reasoning_summary': self.document_chronology_reasoning_summary or {},
            'cross_phase_findings': list(self.cross_phase_findings or []),
            'workflow_action_queue': list(self.workflow_action_queue or []),
            'intake_question_structure_summary': self.intake_question_structure_summary or {},
            'document_theory_alignment_summary': self.document_theory_alignment_summary or {},
        }


@dataclass
class WorkflowOptimizationBundle:
    """Serializable optimization bundle spanning the full complaint workflow."""

    timestamp: str
    num_sessions_analyzed: int
    average_score: float
    workflow_phase_plan: Dict[str, Any]
    global_objectives: List[str]
    phase_tasks: List[Dict[str, Any]]
    shared_context: Dict[str, Any]
    phase_scorecards: Dict[str, Dict[str, Any]] | None = None
    cross_phase_findings: List[str] | None = None
    workflow_action_queue: List[Dict[str, Any]] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "num_sessions_analyzed": self.num_sessions_analyzed,
            "average_score": self.average_score,
            "workflow_phase_plan": dict(self.workflow_phase_plan or {}),
            "global_objectives": list(self.global_objectives or []),
            "phase_tasks": list(self.phase_tasks or []),
            "shared_context": dict(self.shared_context or {}),
            "phase_scorecards": dict(self.phase_scorecards or {}),
            "cross_phase_findings": list(self.cross_phase_findings or []),
            "workflow_action_queue": list(self.workflow_action_queue or []),
        }


@dataclass
class UIUXOptimizationBundle:
    """Serializable bundle for screenshot-driven UI/UX optimization work."""

    timestamp: str
    screenshot_dir: str
    output_dir: str
    iterations: int
    pytest_target: str
    target_files: List[str]
    review_runs: List[Dict[str, Any]]
    complaint_output_feedback: Dict[str, Any]
    patch_briefs: List[Dict[str, Any]]
    latest_review_markdown_path: Optional[str] = None
    latest_review_json_path: Optional[str] = None
    task: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "screenshot_dir": self.screenshot_dir,
            "output_dir": self.output_dir,
            "iterations": self.iterations,
            "pytest_target": self.pytest_target,
            "target_files": list(self.target_files or []),
            "review_runs": list(self.review_runs or []),
            "complaint_output_feedback": dict(self.complaint_output_feedback or {}),
            "patch_briefs": list(self.patch_briefs or []),
            "latest_review_markdown_path": self.latest_review_markdown_path,
            "latest_review_json_path": self.latest_review_json_path,
            "task": dict(self.task or {}),
        }


@dataclass
class UIOptimizationBundle:
    """Serializable optimization bundle for screenshot-driven UI/UX review."""

    timestamp: str
    screenshot_dir: str
    screenshot_paths: List[str]
    artifact_count: int
    summary: str
    issues: List[Dict[str, Any]]
    recommended_changes: List[Dict[str, Any]]
    broken_controls: List[Dict[str, Any]]
    complaint_journey: Dict[str, Any]
    actor_plan: Dict[str, Any]
    critic_review: Dict[str, Any]
    playwright_followups: List[str]
    complaint_output_feedback: Dict[str, Any]
    target_files: List[str]
    patch_briefs: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "screenshot_dir": self.screenshot_dir,
            "screenshot_paths": list(self.screenshot_paths or []),
            "artifact_count": self.artifact_count,
            "summary": self.summary,
            "issues": list(self.issues or []),
            "recommended_changes": list(self.recommended_changes or []),
            "broken_controls": list(self.broken_controls or []),
            "complaint_journey": dict(self.complaint_journey or {}),
            "actor_plan": dict(self.actor_plan or {}),
            "critic_review": dict(self.critic_review or {}),
            "playwright_followups": list(self.playwright_followups or []),
            "complaint_output_feedback": dict(self.complaint_output_feedback or {}),
            "target_files": list(self.target_files or []),
            "patch_briefs": list(self.patch_briefs or []),
        }
