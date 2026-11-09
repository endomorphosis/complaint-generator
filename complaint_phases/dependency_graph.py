"""
Dependency Graph Builder

Tracks dependencies between claims, evidence, and legal requirements.
Used to ensure all elements of a claim are properly supported.
"""

import json
import logging
import re
from copy import deepcopy
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from enum import Enum
from .intake_claim_registry import normalize_claim_type

logger = logging.getLogger(__name__)

_NAME_PATTERN = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
_CONFIRMATION_PLACEHOLDER_PATTERN = re.compile(
    r"\b(?:needs?\s+confirmation|to\s+be\s+confirmed|confirm(?:ed|ation)?\s+pending|tbd|unknown|not\s+sure|unclear|pending)\b",
    flags=re.IGNORECASE,
)
_DATE_TOKEN_PATTERN = re.compile(
    r"(?:\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+\d{1,2}(?:,\s*\d{4})?\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b|\b(?:19|20)\d{2}\b)",
    flags=re.IGNORECASE,
)
_ACTOR_CRITIC_PHASE_FOCUS_ORDER = ("graph_analysis", "document_generation", "intake_questioning")
_ACTOR_CRITIC_PRIORITY = 70
_ACTOR_CRITIC_FOCUS_METRICS = {
    "empathy": 0.22,
    "question_quality": 0.58,
    "information_extraction": 0.72,
    "coverage": 0.69,
    "patchability": 0.74,
}
_ACTOR_CRITIC_WEAK_CLAIM_TYPES = {"housing_discrimination", "hacc_research_engine"}
_ACTOR_CRITIC_WEAK_EVIDENCE_MODALITIES = {"policy_document", "file_evidence"}
_FACTUAL_CLARIFICATION_CLASS = "factual_clarification"
_LEGALLY_SOURCED_CLASS = "legally_sourced_requirement"
_LEGAL_SOURCE_GAP_CLASS = "legal_source_gap"
_UNRESOLVED_LEGAL_CLASS = "unresolved_legal_requirement"
_HEURISTIC_LAW_ORIGINS = {"heuristic", "heuristic_graph", "law_derived", "law-derived"}
_UNVERIFIED_REQUIREMENT_STATUSES = {"unverified_template", "unverified", "heuristic", "candidate"}
_VERIFIED_REQUIREMENT_STATUSES = {"verified", "source_bound", "applicable"}
_FACTUAL_CLARIFICATION_KEYS_BY_NAME = {
    "Timeline of events": ("timeline",),
    "Actor-by-actor decision timeline": ("decision_timeline", "actor", "timeline"),
    "Responsible party": ("actor", "responsible_party"),
    "Protected activity facts": ("protected_activity",),
    "Adverse action facts": ("adverse_action",),
    "Retaliation causation chronology": ("causation", "timeline"),
    "Retaliation causation link facts": ("causation",),
    "Written notice date": ("notice", "timeline"),
    "Hearing request date": ("hearing", "timeline"),
}


def _utc_now_isoformat() -> str:
    return datetime.now(UTC).isoformat()


class NodeType(Enum):
    """Types of nodes in the dependency graph."""
    CLAIM = "claim"
    EVIDENCE = "evidence"
    REQUIREMENT = "requirement"
    FACT = "fact"
    LEGAL_ELEMENT = "legal_element"


class DependencyType(Enum):
    """Types of dependencies between nodes."""
    REQUIRES = "requires"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    IMPLIES = "implies"
    DEPENDS_ON = "depends_on"
    BEFORE = "before"
    SAME_TIME = "same_time"
    OVERLAPS = "overlaps"


@dataclass
class DependencyNode:
    """Represents a node in the dependency graph."""
    id: str
    node_type: NodeType
    name: str
    description: str = ""
    satisfied: bool = False
    confidence: float = 0.0
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        data = asdict(self)
        data['node_type'] = self.node_type.value
        return data


@dataclass
class Dependency:
    """Represents a dependency edge in the graph."""
    id: str
    source_id: str
    target_id: str
    dependency_type: DependencyType
    required: bool = True
    strength: float = 1.0  # 0.0 to 1.0
    
    def to_dict(self) -> dict:
        data = asdict(self)
        data['dependency_type'] = self.dependency_type.value
        return data


class DependencyGraph:
    """
    Dependency graph for tracking claim requirements and evidence.
    
    This graph tracks what each claim requires (legal elements, facts, evidence)
    and whether those requirements are satisfied.
    """
    
    def __init__(self):
        self.nodes: Dict[str, DependencyNode] = {}
        self.dependencies: Dict[str, Dependency] = {}
        self.metadata = {
            'created_at': _utc_now_isoformat(),
            'last_updated': _utc_now_isoformat(),
            'version': '1.0'
        }
    
    def add_node(self, node: DependencyNode) -> str:
        """Add a node to the graph."""
        self.nodes[node.id] = node
        self._update_metadata()
        return node.id
    
    def add_dependency(self, dependency: Dependency) -> str:
        """Add a dependency to the graph."""
        if dependency.source_id not in self.nodes:
            raise ValueError(f"Source node {dependency.source_id} not found")
        if dependency.target_id not in self.nodes:
            raise ValueError(f"Target node {dependency.target_id} not found")
        
        self.dependencies[dependency.id] = dependency
        self._update_metadata()
        return dependency.id
    
    def get_node(self, node_id: str) -> Optional[DependencyNode]:
        """Get a node by ID."""
        return self.nodes.get(node_id)
    
    def get_dependencies_for_node(self, node_id: str, 
                                   direction: str = 'both') -> List[Dependency]:
        """
        Get dependencies for a node.
        
        Args:
            node_id: Node ID
            direction: 'incoming', 'outgoing', or 'both'
        """
        deps = []
        for dep in self.dependencies.values():
            if direction in ['incoming', 'both'] and dep.target_id == node_id:
                deps.append(dep)
            if direction in ['outgoing', 'both'] and dep.source_id == node_id:
                deps.append(dep)
        return deps
    
    def get_nodes_by_type(self, node_type: NodeType) -> List[DependencyNode]:
        """Get all nodes of a specific type."""
        return [n for n in self.nodes.values() if n.node_type == node_type]
    
    def check_satisfaction(self, node_id: str) -> Dict[str, Any]:
        """
        Check if a node's requirements are satisfied.
        
        Returns information about satisfaction status and missing dependencies.
        """
        node = self.get_node(node_id)
        if not node:
            return {'error': 'Node not found'}
        
        # Get all requirements (incoming dependencies)
        requirements = self.get_dependencies_for_node(node_id, direction='incoming')
        required_deps = [d for d in requirements if d.required]
        
        satisfied_count = 0
        missing = []
        
        for dep in required_deps:
            source_node = self.get_node(dep.source_id)
            if source_node and source_node.satisfied:
                satisfied_count += 1
            else:
                missing.append({
                    'dependency_id': dep.id,
                    'source_node_id': dep.source_id,
                    'source_name': source_node.name if source_node else 'Unknown',
                    'dependency_type': dep.dependency_type.value
                })
        
        total_required = len(required_deps)
        satisfaction_ratio = satisfied_count / total_required if total_required > 0 else 1.0
        
        return {
            'node_id': node_id,
            'node_name': node.name,
            'satisfied': satisfaction_ratio >= 1.0,
            'satisfaction_ratio': satisfaction_ratio,
            'satisfied_count': satisfied_count,
            'total_required': total_required,
            'missing_dependencies': missing
        }
    
    def find_unsatisfied_requirements(self) -> List[Dict[str, Any]]:
        """Find all nodes with unsatisfied requirements."""
        unsatisfied = []
        
        for node in self.nodes.values():
            check = self.check_satisfaction(node.id)
            if not check.get('satisfied', False) and check.get('total_required', 0) > 0:
                if self.metadata.get('legal_requirement_mode') == 'verified_sources':
                    # The denoiser has a finite per-claim question budget. Keep
                    # current sourced obligations visible before generic facts.
                    def sourced_obligation(dependency):
                        source = self.get_node(dependency['source_node_id'])
                        return bool(source is not None
                            and source.attributes.get('dependency_class') == _LEGALLY_SOURCED_CLASS
                            and source.attributes.get('source_available') is True
                            and source.attributes.get('dependency_scope', {}).get('claim_id') == node.id)
                    check['missing_dependencies'].sort(key=lambda dependency: not sourced_obligation(dependency))
                unsatisfied.append(check)
        
        return unsatisfied
    
    def get_claim_readiness(self) -> Dict[str, Any]:
        return dependency_graph_readiness.get_claim_readiness(
            self,
        )
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            'metadata': self.metadata,
            'nodes': {nid: n.to_dict() for nid, n in self.nodes.items()},
            'dependencies': {did: d.to_dict() for did, d in self.dependencies.items()}
        }
    
    def to_json(self, filepath: str):
        """Save to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Dependency graph saved to {filepath}")
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DependencyGraph':
        """Deserialize without changing the caller's versioned projection."""
        data = deepcopy(data)
        graph = cls()
        graph.metadata = data['metadata']
        
        for nid, ndata in data['nodes'].items():
            ndata['node_type'] = NodeType(ndata['node_type'])
            node = DependencyNode(**ndata)
            graph.nodes[nid] = node
        
        for did, ddata in data['dependencies'].items():
            ddata['dependency_type'] = DependencyType(ddata['dependency_type'])
            dep = Dependency(**ddata)
            graph.dependencies[did] = dep
        
        return graph
    
    @classmethod
    def from_json(cls, filepath: str) -> 'DependencyGraph':
        """Load from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        logger.info(f"Dependency graph loaded from {filepath}")
        return cls.from_dict(data)
    
    def _update_metadata(self):
        """Update last_updated timestamp."""
        self.metadata['last_updated'] = _utc_now_isoformat()
    
    def summary(self) -> Dict[str, Any]:
        """Get a summary of the dependency graph."""
        node_counts = {}
        for node in self.nodes.values():
            node_type_str = node.node_type.value
            node_counts[node_type_str] = node_counts.get(node_type_str, 0) + 1
        
        dep_counts = {}
        for dep in self.dependencies.values():
            dep_type_str = dep.dependency_type.value
            dep_counts[dep_type_str] = dep_counts.get(dep_type_str, 0) + 1
        
        satisfied_nodes = sum(1 for n in self.nodes.values() if n.satisfied)
        
        return {
            'total_nodes': len(self.nodes),
            'total_dependencies': len(self.dependencies),
            'node_types': node_counts,
            'dependency_types': dep_counts,
            'satisfied_nodes': satisfied_nodes,
            'satisfaction_rate': satisfied_nodes / len(self.nodes) if self.nodes else 0.0
        }

    def get_temporal_dependencies(self) -> List[Dependency]:
        """Return temporal ordering dependencies present in the graph."""
        temporal_types = {
            DependencyType.BEFORE,
            DependencyType.SAME_TIME,
            DependencyType.OVERLAPS,
        }
        return [
            dep for dep in self.dependencies.values()
            if dep.dependency_type in temporal_types
        ]

    def detect_temporal_cycles(self) -> List[List[str]]:
        """Detect cycles among BEFORE dependencies and return node-id cycles."""
        adjacency: Dict[str, List[str]] = {}
        for dep in self.dependencies.values():
            if dep.dependency_type != DependencyType.BEFORE:
                continue
            adjacency.setdefault(dep.source_id, []).append(dep.target_id)

        cycles: List[List[str]] = []
        seen_cycle_keys = set()

        def _canonical_cycle_key(path: List[str]) -> tuple[str, ...]:
            core = path[:-1] if len(path) > 1 and path[0] == path[-1] else path
            if not core:
                return tuple()
            rotations = [tuple(core[index:] + core[:index]) for index in range(len(core))]
            reversed_core = list(reversed(core))
            rotations.extend(tuple(reversed_core[index:] + reversed_core[:index]) for index in range(len(reversed_core)))
            return min(rotations)

        def _visit(node_id: str, stack: List[str], visiting: set[str]) -> None:
            visiting.add(node_id)
            stack.append(node_id)
            for neighbor_id in adjacency.get(node_id, []):
                if neighbor_id in visiting:
                    cycle_start = stack.index(neighbor_id)
                    cycle_path = stack[cycle_start:] + [neighbor_id]
                    cycle_key = _canonical_cycle_key(cycle_path)
                    if cycle_key and cycle_key not in seen_cycle_keys:
                        seen_cycle_keys.add(cycle_key)
                        cycles.append(cycle_path)
                    continue
                if neighbor_id in stack:
                    continue
                _visit(neighbor_id, stack, visiting)
            stack.pop()
            visiting.remove(node_id)

        for node_id in list(adjacency.keys()):
            _visit(node_id, [], set())

        return cycles

    def get_temporal_inconsistency_issues(self) -> List[Dict[str, Any]]:
        """Return temporal inconsistency diagnostics derived from temporal edges."""
        issues: List[Dict[str, Any]] = []
        pair_type_map: Dict[tuple[str, str], set[str]] = {}
        directional_before_pairs = set()

        for dep in self.get_temporal_dependencies():
            source_id = str(dep.source_id)
            target_id = str(dep.target_id)
            relation_type = dep.dependency_type.value
            pair_key = tuple(sorted((source_id, target_id)))
            pair_type_map.setdefault(pair_key, set()).add(relation_type)
            if dep.dependency_type == DependencyType.BEFORE:
                directional_before_pairs.add((source_id, target_id))

        for cycle_index, cycle in enumerate(self.detect_temporal_cycles(), start=1):
            node_names = [self.get_node(node_id).name if self.get_node(node_id) else node_id for node_id in cycle[:-1]]
            summary = f"Temporal cycle detected: {' -> '.join(node_names + [node_names[0]])}"
            issues.append({
                'issue_id': f'temporal_cycle_{cycle_index:03d}',
                'issue_type': 'temporal_cycle',
                'summary': summary,
                'severity': 'blocking',
                'recommended_resolution_lane': 'request_document',
                'current_resolution_status': 'open',
                'external_corroboration_required': True,
                'node_ids': cycle[:-1],
                'node_names': node_names,
            })

        for pair_index, (pair_key, relation_types) in enumerate(sorted(pair_type_map.items()), start=1):
            left_id, right_id = pair_key
            left_node = self.get_node(left_id)
            right_node = self.get_node(right_id)
            left_name = left_node.name if left_node else left_id
            right_name = right_node.name if right_node else right_id

            if 'before' in relation_types and 'same_time' in relation_types:
                issues.append({
                    'issue_id': f'temporal_conflict_{pair_index:03d}',
                    'issue_type': 'temporal_relation_conflict',
                    'summary': f'Temporal relation conflict: {left_name} cannot be both before and simultaneous with {right_name}',
                    'severity': 'blocking',
                    'recommended_resolution_lane': 'request_document',
                    'current_resolution_status': 'open',
                    'external_corroboration_required': True,
                    'left_node_id': left_id,
                    'right_node_id': right_id,
                    'left_node_name': left_name,
                    'right_node_name': right_name,
                    'relation_types': sorted(relation_types),
                })

            if (left_id, right_id) in directional_before_pairs and (right_id, left_id) in directional_before_pairs:
                issues.append({
                    'issue_id': f'temporal_reverse_before_{pair_index:03d}',
                    'issue_type': 'temporal_reverse_before',
                    'summary': f'Temporal ordering conflict: {left_name} is marked before {right_name} and {right_name} is marked before {left_name}',
                    'severity': 'blocking',
                    'recommended_resolution_lane': 'request_document',
                    'current_resolution_status': 'open',
                    'external_corroboration_required': True,
                    'left_node_id': left_id,
                    'right_node_id': right_id,
                    'left_node_name': left_name,
                    'right_node_name': right_name,
                    'relation_types': ['before'],
                })

        return issues

    def get_blocker_follow_up_issues(self) -> List[Dict[str, Any]]:
        return dependency_graph_readiness.get_blocker_follow_up_issues(
            self,
        )

    def _node_rich_text(self, node: DependencyNode) -> str:
        """Build searchable text including node attributes for blocker diagnostics."""
        values = [str(node.name or ""), str(node.description or "")]
        attrs = node.attributes if isinstance(node.attributes, dict) else {}
        for value in attrs.values():
            if isinstance(value, (str, int, float, bool)):
                values.append(str(value))
            elif isinstance(value, list):
                values.extend(str(item) for item in value if isinstance(item, (str, int, float, bool)))
            elif isinstance(value, dict):
                values.extend(
                    str(item)
                    for item in value.values()
                    if isinstance(item, (str, int, float, bool))
                )
        return " ".join(item for item in values if item).strip()

    def _nodes_with_confirmation_placeholders(
        self,
        node_rich_text_by_id: Dict[str, str],
    ) -> List[DependencyNode]:
        """Identify nodes that still contain 'needs confirmation'-style placeholders."""
        placeholder_nodes: List[DependencyNode] = []
        for node_id, text_value in node_rich_text_by_id.items():
            if not text_value:
                continue
            if _CONFIRMATION_PLACEHOLDER_PATTERN.search(text_value):
                node = self.get_node(node_id)
                if node is not None:
                    placeholder_nodes.append(node)
        return placeholder_nodes

    def _contains_date_anchor(self, text_value: str) -> bool:
        """Return whether text includes an explicit or parseable date anchor."""
        if not text_value:
            return False
        return bool(_DATE_TOKEN_PATTERN.search(text_value))

    def _contains_document_precision_marker(self, text_value: str) -> bool:
        """Return whether text includes document-level precision markers."""
        if not text_value:
            return False
        lowered = text_value.lower()
        precision_tokens = (
            "subject line",
            "sender",
            "recipient",
            "from:",
            "to:",
            "reference number",
            "case number",
            "tracking number",
            "message id",
            "document id",
            "attachment",
        )
        return any(token in lowered for token in precision_tokens)

    def _phase_focus_rank_for_actor_critic(self, workflow_phase: str) -> int:
        phase = str(workflow_phase or "").strip().lower()
        if phase in _ACTOR_CRITIC_PHASE_FOCUS_ORDER:
            return _ACTOR_CRITIC_PHASE_FOCUS_ORDER.index(phase)
        return len(_ACTOR_CRITIC_PHASE_FOCUS_ORDER)

    def _dedupe_preserve_order(self, values: List[str]) -> List[str]:
        deduped: List[str] = []
        seen = set()
        for value in values:
            token = str(value or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            deduped.append(token)
        return deduped

    def _optimize_issue_question_text(
        self,
        *,
        question_text: str,
        question_type: str,
        extraction_targets: List[str],
    ) -> str:
        base = str(question_text or "").strip()
        qtype = str(question_type or "").strip().lower()
        targets = [str(item or "").strip().lower() for item in extraction_targets if str(item or "").strip()]
        lower = base.lower()

        empathy_prefix = "To make sure I understand, "
        if qtype in {"timeline", "responsible_party"}:
            empathy_prefix = "I know this may be stressful, and this helps keep your record accurate: "
        elif qtype in {"evidence"}:
            empathy_prefix = "So we can support your claim clearly, "

        if not lower.startswith((
            "to make sure i understand",
            "i know this may be stressful",
            "so we can support your claim",
        )):
            if base:
                first = base[0].lower() + base[1:] if len(base) > 1 else base.lower()
            else:
                first = "can you share the missing details"
            base = f"{empathy_prefix}{first}"
            lower = base.lower()

        quality_prompts: List[str] = []
        if any(item in targets for item in {"exact_dates", "event_order"}) and not any(
            token in lower for token in ("exact date", "on what date", "what date", "when")
        ):
            quality_prompts.append("the exact date for each step")
        if "response_timing" in targets and not any(
            token in lower for token in ("response", "responded", "reply", "how long", "time between", "delay")
        ):
            quality_prompts.append("how long each response took after the prior event")
        if any(item in targets for item in {"actor_name", "actor_role", "decision_maker"}) and not any(
            token in lower for token in ("who", "full name", "title", "role")
        ):
            quality_prompts.append("who took each action (full name and title)")
        if "adverse_action" in targets and not any(
            token in lower for token in ("adverse action", "terminated", "fired", "disciplined", "evicted", "suspended", "what exactly")
        ):
            quality_prompts.append("what exact adverse action occurred at each step")
        if any(item in targets for item in {"document_type", "document_date", "document_owner"}) and not any(
            token in lower for token in ("document", "notice", "letter", "email", "record", "message")
        ):
            quality_prompts.append("which document or message supports each point")
        if any(item in targets for item in {"document_sender", "document_recipient", "document_subject", "document_identifier"}) and not any(
            token in lower for token in ("sender", "recipient", "subject", "reference", "case number", "document id")
        ):
            quality_prompts.append("the document sender, recipient, subject line, and any case/document ID")
        if "causation_link" in targets and not any(token in lower for token in ("because", "after", "before", "led to")):
            quality_prompts.append("how each step led to the next")

        if quality_prompts:
            detail_clause = " Please include " + "; ".join(self._dedupe_preserve_order(quality_prompts))
            if not base.endswith((".", "?", "!")):
                base = f"{base}."
            base = f"{base}{detail_clause}"

        cleaned = base.rstrip(" .!?")
        if not cleaned:
            cleaned = "To make sure I understand, can you share the missing details"
        optimized = f"{cleaned}?"
        if len(optimized) > 280:
            optimized = optimized[:277].rstrip(" ,;:.!?") + "?"
        return optimized

    def _optimize_blocker_issues_for_actor_critic(
        self,
        issues: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        optimized: List[Dict[str, Any]] = []
        objective_map = {
            "timeline": "establish_chronology",
            "responsible_party": "identify_responsible_party",
            "evidence": "identify_supporting_evidence",
            "clarification": "clarify_low_confidence_fact",
            "requirement": "satisfy_claim_requirement",
        }

        for issue in issues:
            if not isinstance(issue, dict):
                continue
            enriched = dict(issue)
            workflow_phase = str(enriched.get("workflow_phase") or "graph_analysis").strip().lower()
            question_type = str(enriched.get("question_type") or "timeline").strip().lower()
            severity = str(enriched.get("severity") or "").strip().lower()
            extraction_targets = self._dedupe_preserve_order([
                str(target).strip()
                for target in (enriched.get("extraction_targets") or [])
                if str(target).strip()
            ])
            patchability_markers = self._dedupe_preserve_order([
                str(marker).strip()
                for marker in (enriched.get("patchability_markers") or [])
                if str(marker).strip()
            ])

            if question_type == "timeline":
                extraction_targets = self._dedupe_preserve_order(
                    extraction_targets + ["exact_dates", "event_order", "response_timing"]
                )
                patchability_markers = self._dedupe_preserve_order(
                    patchability_markers + ["chronology_patch_anchor"]
                )
            elif question_type == "responsible_party":
                extraction_targets = self._dedupe_preserve_order(
                    extraction_targets + ["actor_name", "actor_role", "decision_maker"]
                )
                patchability_markers = self._dedupe_preserve_order(
                    patchability_markers + ["actor_link_patch_anchor", "decision_actor_patch_anchor"]
                )
            elif question_type == "evidence":
                extraction_targets = self._dedupe_preserve_order(
                    extraction_targets
                    + ["document_type", "document_date", "document_owner", "document_sender", "document_recipient"]
                )
                patchability_markers = self._dedupe_preserve_order(
                    patchability_markers + ["support_patch_anchor", "notice_chain_patch_anchor"]
                )

            enriched["workflow_phase"] = workflow_phase
            enriched["workflow_phase_rank"] = self._phase_focus_rank_for_actor_critic(workflow_phase)
            enriched["extraction_targets"] = extraction_targets
            enriched["patchability_markers"] = patchability_markers
            enriched.setdefault("question_objective", objective_map.get(question_type, "general_intake_clarification"))
            enriched.setdefault("expected_proof_gain", "high" if severity == "blocking" else "medium")
            enriched.setdefault("router_backed_question_quality", True)
            enriched.setdefault("actor_critic_priority", _ACTOR_CRITIC_PRIORITY)
            enriched.setdefault("phase_focus_order", list(_ACTOR_CRITIC_PHASE_FOCUS_ORDER))
            enriched.setdefault("actor_critic_focus_metrics", dict(_ACTOR_CRITIC_FOCUS_METRICS))
            enriched.setdefault(
                "actor_critic_quality_dimensions",
                {
                    "chronology_closure": bool(
                        any(target in {"exact_dates", "event_order", "response_timing"} for target in extraction_targets)
                    ),
                    "decision_precision": bool(
                        any(target in {"decision_maker", "actor_name", "actor_role"} for target in extraction_targets)
                    ),
                    "document_precision": bool(
                        any(
                            target in {
                                "document_type",
                                "document_date",
                                "document_owner",
                                "document_sender",
                                "document_recipient",
                                "document_subject",
                                "document_identifier",
                            }
                            for target in extraction_targets
                        )
                    ),
                    "patchability_coverage": len(patchability_markers),
                },
            )
            enriched["suggested_question"] = self._optimize_issue_question_text(
                question_text=str(enriched.get("suggested_question") or ""),
                question_type=question_type,
                extraction_targets=extraction_targets,
            )
            optimized.append(enriched)
        return optimized


    # ------------------------------------------------------------------ #
    # Batch 209: Dependency graph analysis and statistics methods        #
    # ------------------------------------------------------------------ #

    def total_nodes(self) -> int:
        """Return total number of nodes in the graph.

        Returns:
            Count of nodes.
        """
        return len(self.nodes)

    def total_dependencies(self) -> int:
        """Return total number of dependencies in the graph.

        Returns:
            Count of dependencies.
        """
        return len(self.dependencies)

    def node_type_distribution(self) -> dict:
        """Calculate frequency distribution of node types.

        Returns:
            Dict mapping node type names to counts.
        """
        type_counts: dict = {}
        for node in self.nodes.values():
            ntype = node.node_type.value  # Get enum value (string)
            type_counts[ntype] = type_counts.get(ntype, 0) + 1
        return type_counts

    def dependency_type_distribution(self) -> dict:
        """Calculate frequency distribution of dependency types.

        Returns:
            Dict mapping dependency type names to counts.
        """
        type_counts: dict = {}
        for dep in self.dependencies.values():
            dtype = dep.dependency_type.value  # Get enum value (string)
            type_counts[dtype] = type_counts.get(dtype, 0) + 1
        return type_counts

    def satisfied_node_count(self) -> int:
        """Count nodes marked as satisfied.

        Returns:
            Number of satisfied nodes.
        """
        return sum(1 for node in self.nodes.values() if node.satisfied)

    def unsatisfied_node_count(self) -> int:
        """Count nodes not marked as satisfied.

        Returns:
            Number of unsatisfied nodes.
        """
        return sum(1 for node in self.nodes.values() if not node.satisfied)

    def average_confidence(self) -> float:
        """Calculate average confidence across all nodes.

        Returns:
            Mean confidence score, or 0.0 if no nodes.
        """
        if not self.nodes:
            return 0.0
        return sum(n.confidence for n in self.nodes.values()) / len(self.nodes)

    def required_dependency_count(self) -> int:
        """Count dependencies marked as required.

        Returns:
            Number of required dependencies.
        """
        return sum(1 for dep in self.dependencies.values() if dep.required)

    def average_dependencies_per_node(self) -> float:
        """Calculate average number of dependencies per node.

        Returns:
            Mean dependency count, or 0.0 if no nodes.
        """
        if not self.nodes:
            return 0.0
        total_connections = sum(
            len(self.get_dependencies_for_node(nid))
            for nid in self.nodes.keys()
        )
        # Each dependency is counted twice (source and target), so divide by 2
        return (total_connections / 2) / len(self.nodes)

    def most_dependent_node(self) -> str:
        """Find node ID with the most dependencies.

        Returns:
            Node ID with most dependencies, or 'none' if no nodes.
        """
        if not self.nodes:
            return 'none'
        
        dependency_counts: dict = {}
        for node_id in self.nodes.keys():
            dependency_counts[node_id] = len(self.get_dependencies_for_node(node_id))
        
        if not dependency_counts:
            return 'none'
        
        return max(dependency_counts.items(), key=lambda x: x[1])[0]


    # ------------------------------------------------------------------ #
    # Batch 223: Dependency graph analysis and statistics methods        #
    # ------------------------------------------------------------------ #

    def node_type_set(self) -> List[str]:
        """Return sorted list of unique node types.

        Returns:
            Sorted list of node type strings.
        """
        return sorted({node.node_type.value for node in self.nodes.values()})

    def dependency_type_set(self) -> List[str]:
        """Return sorted list of unique dependency types.

        Returns:
            Sorted list of dependency type strings.
        """
        return sorted({dep.dependency_type.value for dep in self.dependencies.values()})

    def nodes_with_attributes_count(self) -> int:
        """Count nodes with non-empty attributes.

        Returns:
            Number of nodes with attributes.
        """
        return sum(1 for node in self.nodes.values() if node.attributes)

    def nodes_with_description_count(self) -> int:
        """Count nodes with non-empty description.

        Returns:
            Number of nodes with descriptions.
        """
        return sum(1 for node in self.nodes.values() if node.description)

    def nodes_missing_description_count(self) -> int:
        """Count nodes missing a description.

        Returns:
            Number of nodes with empty description fields.
        """
        return sum(1 for node in self.nodes.values() if not node.description)

    def nodes_by_satisfaction(self, satisfied: bool = True) -> List[DependencyNode]:
        """Get nodes filtered by satisfaction flag.

        Args:
            satisfied: Whether to return satisfied or unsatisfied nodes

        Returns:
            List of dependency nodes matching the flag.
        """
        return [node for node in self.nodes.values() if node.satisfied == satisfied]

    def dependency_count_for_node(self, node_id: str) -> int:
        """Count dependencies involving a specific node.

        Args:
            node_id: Node identifier

        Returns:
            Number of dependencies involving the node.
        """
        return len(self.get_dependencies_for_node(node_id))

    def dependencies_required_ratio(self) -> float:
        """Calculate ratio of required dependencies.

        Returns:
            Ratio of required dependencies (0.0 to 1.0).
        """
        if not self.dependencies:
            return 0.0
        required = sum(1 for dep in self.dependencies.values() if dep.required)
        return required / len(self.dependencies)

    def dependency_strength_stats(self) -> Dict[str, float]:
        """Calculate average, min, and max dependency strengths.

        Returns:
            Dict with avg, min, and max strength values.
        """
        if not self.dependencies:
            return {"avg": 0.0, "min": 0.0, "max": 0.0}
        strengths = [dep.strength for dep in self.dependencies.values()]
        return {
            "avg": sum(strengths) / len(strengths),
            "min": min(strengths),
            "max": max(strengths),
        }

    def average_required_dependencies_per_node(self) -> float:
        """Calculate average required dependencies per node.

        Returns:
            Mean required dependency count, or 0.0 if no nodes.
        """
        if not self.nodes:
            return 0.0
        required_connections = sum(
            len([dep for dep in self.get_dependencies_for_node(nid) if dep.required])
            for nid in self.nodes.keys()
        )
        return (required_connections / 2) / len(self.nodes)


    # ------------------------------------------------------------------ #
    # Batch 224: Dependency graph analysis and statistics methods        #
    # ------------------------------------------------------------------ #

    def node_confidence_min(self) -> float:
        """Get minimum confidence across nodes.

        Returns:
            Minimum confidence, or 0.0 if no nodes.
        """
        if not self.nodes:
            return 0.0
        return min(node.confidence for node in self.nodes.values())

    def node_confidence_max(self) -> float:
        """Get maximum confidence across nodes.

        Returns:
            Maximum confidence, or 0.0 if no nodes.
        """
        if not self.nodes:
            return 0.0
        return max(node.confidence for node in self.nodes.values())

    def node_confidence_range(self) -> float:
        """Get range of confidence values across nodes.

        Returns:
            Max minus min confidence, or 0.0 if no nodes.
        """
        if not self.nodes:
            return 0.0
        return self.node_confidence_max() - self.node_confidence_min()

    def average_satisfied_confidence(self) -> float:
        """Calculate average confidence for satisfied nodes.

        Returns:
            Mean confidence for satisfied nodes, or 0.0 if none.
        """
        satisfied = [node.confidence for node in self.nodes.values() if node.satisfied]
        if not satisfied:
            return 0.0
        return sum(satisfied) / len(satisfied)

    def average_unsatisfied_confidence(self) -> float:
        """Calculate average confidence for unsatisfied nodes.

        Returns:
            Mean confidence for unsatisfied nodes, or 0.0 if none.
        """
        unsatisfied = [node.confidence for node in self.nodes.values() if not node.satisfied]
        if not unsatisfied:
            return 0.0
        return sum(unsatisfied) / len(unsatisfied)

    def optional_dependency_count(self) -> int:
        """Count dependencies marked as optional.

        Returns:
            Number of optional dependencies.
        """
        return sum(1 for dep in self.dependencies.values() if not dep.required)

    def required_dependency_count_for_node(self, node_id: str) -> int:
        """Count required dependencies involving a node.

        Args:
            node_id: Node identifier

        Returns:
            Number of required dependencies involving the node.
        """
        return len([dep for dep in self.get_dependencies_for_node(node_id) if dep.required])

    def nodes_without_dependencies_count(self) -> int:
        """Count nodes that have no dependencies.

        Returns:
            Number of nodes with zero dependencies.
        """
        return sum(1 for node_id in self.nodes.keys() if not self.get_dependencies_for_node(node_id))

    def dependency_strength_average_required(self) -> float:
        """Calculate average strength of required dependencies.

        Returns:
            Mean strength of required dependencies, or 0.0 if none.
        """
        strengths = [dep.strength for dep in self.dependencies.values() if dep.required]
        if not strengths:
            return 0.0
        return sum(strengths) / len(strengths)

    def dependency_strength_average_optional(self) -> float:
        """Calculate average strength of optional dependencies.

        Returns:
            Mean strength of optional dependencies, or 0.0 if none.
        """
        strengths = [dep.strength for dep in self.dependencies.values() if not dep.required]
        if not strengths:
            return 0.0
        return sum(strengths) / len(strengths)


    # ------------------------------------------------------------------ #
    # Batch 227: Dependency graph analysis and statistics methods        #
    # ------------------------------------------------------------------ #

    def node_ids(self) -> List[str]:
        """Return sorted list of node IDs.

        Returns:
            Sorted list of node identifiers.
        """
        return sorted(self.nodes.keys())

    def dependency_ids(self) -> List[str]:
        """Return sorted list of dependency IDs.

        Returns:
            Sorted list of dependency identifiers.
        """
        return sorted(self.dependencies.keys())

    def satisfied_node_ratio(self) -> float:
        """Calculate ratio of satisfied nodes.

        Returns:
            Ratio of satisfied nodes, or 0.0 if no nodes.
        """
        if not self.nodes:
            return 0.0
        return self.satisfied_node_count() / len(self.nodes)

    def dependency_density(self) -> float:
        """Calculate dependency density for directed graph.

        Returns:
            Density ratio (0.0 to 1.0), or 0.0 if fewer than 2 nodes.
        """
        n = len(self.nodes)
        if n < 2:
            return 0.0
        max_possible = n * (n - 1)
        return len(self.dependencies) / max_possible

    def average_dependencies_per_satisfied_node(self) -> float:
        """Calculate average dependencies per satisfied node.

        Returns:
            Mean dependency count, or 0.0 if no satisfied nodes.
        """
        satisfied_nodes = [node_id for node_id, node in self.nodes.items() if node.satisfied]
        if not satisfied_nodes:
            return 0.0
        total = sum(len(self.get_dependencies_for_node(node_id)) for node_id in satisfied_nodes)
        return total / len(satisfied_nodes)

    def average_dependencies_per_unsatisfied_node(self) -> float:
        """Calculate average dependencies per unsatisfied node.

        Returns:
            Mean dependency count, or 0.0 if no unsatisfied nodes.
        """
        unsatisfied_nodes = [node_id for node_id, node in self.nodes.items() if not node.satisfied]
        if not unsatisfied_nodes:
            return 0.0
        total = sum(len(self.get_dependencies_for_node(node_id)) for node_id in unsatisfied_nodes)
        return total / len(unsatisfied_nodes)

    def dependency_strength_min_required(self) -> float:
        """Get minimum strength among required dependencies.

        Returns:
            Minimum strength, or 0.0 if none.
        """
        strengths = [dep.strength for dep in self.dependencies.values() if dep.required]
        if not strengths:
            return 0.0
        return min(strengths)

    def dependency_strength_max_required(self) -> float:
        """Get maximum strength among required dependencies.

        Returns:
            Maximum strength, or 0.0 if none.
        """
        strengths = [dep.strength for dep in self.dependencies.values() if dep.required]
        if not strengths:
            return 0.0
        return max(strengths)

    def dependency_strength_min_optional(self) -> float:
        """Get minimum strength among optional dependencies.

        Returns:
            Minimum strength, or 0.0 if none.
        """
        strengths = [dep.strength for dep in self.dependencies.values() if not dep.required]
        if not strengths:
            return 0.0
        return min(strengths)

    def dependency_strength_max_optional(self) -> float:
        """Get maximum strength among optional dependencies.

        Returns:
            Maximum strength, or 0.0 if none.
        """
        strengths = [dep.strength for dep in self.dependencies.values() if not dep.required]
        if not strengths:
            return 0.0
        return max(strengths)


    # ------------------------------------------------------------------ #
    # Batch 228: Dependency graph analysis and statistics methods        #
    # ------------------------------------------------------------------ #

    def nodes_with_confidence_above(self, threshold: float) -> int:
        """Count nodes with confidence above a threshold.

        Args:
            threshold: Confidence threshold

        Returns:
            Number of nodes with confidence above threshold.
        """
        return sum(1 for node in self.nodes.values() if node.confidence > threshold)

    def nodes_with_confidence_below(self, threshold: float) -> int:
        """Count nodes with confidence below a threshold.

        Args:
            threshold: Confidence threshold

        Returns:
            Number of nodes with confidence below threshold.
        """
        return sum(1 for node in self.nodes.values() if node.confidence < threshold)

    def dependency_strength_range(self) -> float:
        """Calculate range of dependency strengths.

        Returns:
            Max minus min strength, or 0.0 if no dependencies.
        """
        if not self.dependencies:
            return 0.0
        strengths = [dep.strength for dep in self.dependencies.values()]
        return max(strengths) - min(strengths)

    def dependency_strength_range_required(self) -> float:
        """Calculate range of strengths for required dependencies.

        Returns:
            Max minus min strength, or 0.0 if none.
        """
        strengths = [dep.strength for dep in self.dependencies.values() if dep.required]
        if not strengths:
            return 0.0
        return max(strengths) - min(strengths)

    def dependency_strength_range_optional(self) -> float:
        """Calculate range of strengths for optional dependencies.

        Returns:
            Max minus min strength, or 0.0 if none.
        """
        strengths = [dep.strength for dep in self.dependencies.values() if not dep.required]
        if not strengths:
            return 0.0
        return max(strengths) - min(strengths)

    def average_dependencies_per_claim_node(self) -> float:
        """Calculate average dependencies per claim node.

        Returns:
            Mean dependency count for claim nodes, or 0.0 if none.
        """
        claim_nodes = [node.id for node in self.get_nodes_by_type(NodeType.CLAIM)]
        if not claim_nodes:
            return 0.0
        total = sum(len(self.get_dependencies_for_node(node_id)) for node_id in claim_nodes)
        return total / len(claim_nodes)

    def average_dependencies_per_evidence_node(self) -> float:
        """Calculate average dependencies per evidence node.

        Returns:
            Mean dependency count for evidence nodes, or 0.0 if none.
        """
        evidence_nodes = [node.id for node in self.get_nodes_by_type(NodeType.EVIDENCE)]
        if not evidence_nodes:
            return 0.0
        total = sum(len(self.get_dependencies_for_node(node_id)) for node_id in evidence_nodes)
        return total / len(evidence_nodes)

    def average_dependencies_per_requirement_node(self) -> float:
        """Calculate average dependencies per requirement node.

        Returns:
            Mean dependency count for requirement nodes, or 0.0 if none.
        """
        requirement_nodes = [node.id for node in self.get_nodes_by_type(NodeType.REQUIREMENT)]
        if not requirement_nodes:
            return 0.0
        total = sum(len(self.get_dependencies_for_node(node_id)) for node_id in requirement_nodes)
        return total / len(requirement_nodes)

    def node_type_distribution_for_satisfaction(self, satisfied: bool = True) -> Dict[str, int]:
        """Get node type distribution for satisfied or unsatisfied nodes.

        Args:
            satisfied: Whether to count satisfied or unsatisfied nodes

        Returns:
            Dict mapping node types to counts.
        """
        counts: Dict[str, int] = {}
        for node in self.nodes.values():
            if node.satisfied != satisfied:
                continue
            ntype = node.node_type.value
            counts[ntype] = counts.get(ntype, 0) + 1
        return counts

    def dependency_strength_median(self) -> float:
        """Calculate median dependency strength.

        Returns:
            Median strength, or 0.0 if no dependencies.
        """
        if not self.dependencies:
            return 0.0
        strengths = sorted(dep.strength for dep in self.dependencies.values())
        mid = len(strengths) // 2
        if len(strengths) % 2 == 1:
            return strengths[mid]
        return (strengths[mid - 1] + strengths[mid]) / 2


class DependencyGraphBuilder:
    """
    Builds dependency graphs from claims and requirements.
    
    This builder creates the dependency structure showing what each claim
    requires and tracks satisfaction as evidence is gathered.
    """
    
    def __init__(self, mediator=None):
        self.mediator = mediator
        self.node_counter = 0
        self.dependency_counter = 0
    
    def build_from_claims(self, claims: List[Dict[str, Any]], 
                          legal_requirements: Optional[Dict[str, Any]] = None,
                          *,
                          require_verified_legal_sources: bool = False) -> DependencyGraph:
        return dependency_graph_readiness.build_from_claims(
            self,
            claims,
            legal_requirements,
            require_verified_legal_sources=require_verified_legal_sources,
        )

    def build_grounded_hook_graph(
        self,
        claims: List[Dict[str, Any]],
        legal_requirements: Optional[Dict[str, Any]] = None,
        *,
        model_text: str = "",
        taxonomy_names: Optional[List[str]] = None,
        legal_context: Optional[Dict[str, Any]] = None,
    ) -> DependencyGraph:
        """Build a graph whose legal nodes come only from verified source entries.

        Model prose and default claim-taxonomy names are recorded as unresolved.
        They do not become legal elements. Factual clarification nodes stay
        labeled as complainant facts.
        """
        from integrations.ipfs_datasets.legal import adapt_sourced_legal_requirements

        supplied = legal_requirements if isinstance(legal_requirements, dict) else {}
        adapted = adapt_sourced_legal_requirements(supplied, legal_context=legal_context)
        blocked = {str(model_text).strip()} if str(model_text or "").strip() else set()
        blocked.update(str(name).strip() for name in (taxonomy_names or []) if str(name).strip())
        for claim_type, entries in list(adapted.items()):
            rewritten = []
            for entry in entries:
                if not isinstance(entry, dict):
                    rewritten.append(entry)
                    continue
                name = str(entry.get("name") or "").strip()
                description = str(entry.get("description") or "").strip()
                if (
                    name in blocked
                    or description in blocked
                    or entry.get("legacy_template") is True
                    or entry.get("template_kind") == "claim_keyword_template"
                ):
                    entry = dict(entry)
                    entry["intake_requirement_status"] = "unresolved"
                    entry["proof_status"] = "not_authoritative"
                    entry["derivation_status"] = "unresolved"
                    entry["unresolved_reason"] = "model_or_taxonomy_text_is_not_law"
                    entry["law_derived"] = False
                rewritten.append(entry)
            adapted[claim_type] = rewritten
        graph = self.build_from_claims(claims, adapted, require_verified_legal_sources=True)
        factual = []
        legal = []
        for node in graph.nodes.values():
            kind = str((node.attributes or {}).get("record_kind") or node.node_type.value)
            bucket = factual if node.node_type == NodeType.FACT or (node.attributes or {}).get("about_complainant") else legal
            bucket.append({
                "id": node.id,
                "name": node.name,
                "node_type": node.node_type.value,
                "record_kind": kind,
                "law_derived": bool((node.attributes or {}).get("law_derived")),
            })
        graph.metadata["factual_nodes"] = factual
        graph.metadata["legal_nodes"] = legal
        graph.metadata["model_text_created_law"] = False
        graph.metadata["default_taxonomy_created_law"] = False
        graph.metadata["factual_legal_separated"] = True
        return graph

    def _mark_factual_clarifications(self, graph: DependencyGraph) -> None:
        """Label complainant clarification nodes so they stay distinct from legal requirements."""
        for node in graph.get_nodes_by_type(NodeType.FACT):
            attributes = node.attributes if isinstance(node.attributes, dict) else {}
            if attributes.get("timeline_fact_node") or attributes.get("record_kind") == "factual_assertion":
                continue
            if attributes.get("dependency_class"):
                continue
            keys = list(_FACTUAL_CLARIFICATION_KEYS_BY_NAME.get(node.name, ("clarification",)))
            attributes.update({
                "record_kind": _FACTUAL_CLARIFICATION_CLASS,
                "dependency_class": _FACTUAL_CLARIFICATION_CLASS,
                "law_derived": False,
                "about_complainant": True,
                "clarification_keys": keys,
                "dependency_scope": {
                    "clarification_keys": list(keys),
                    "fact_ids": [str(item) for item in (attributes.get("fact_ids") or [])],
                },
                "satisfaction_revision": int(attributes.get("satisfaction_revision") or 0),
            })
            node.attributes = attributes

    @staticmethod
    def _bounded_source_record(record: Any) -> bool:
        """Bound the serialized source proof before the parser copies it."""
        remaining, characters = 8192, 262144
        def bounded(value, depth=0):
            nonlocal remaining, characters
            remaining -= 1
            if remaining < 0 or depth > 8:
                return False
            if isinstance(value, str):
                characters -= len(value)
                return len(value) <= 65536 and characters >= 0
            if value is None or type(value) in (bool, int, float):
                return True
            if isinstance(value, dict):
                return len(value) <= 128 and all(isinstance(key, str) and len(key) <= 128
                    and bounded(item, depth + 1) for key, item in value.items())
            if isinstance(value, list):
                return len(value) <= 256 and all(bounded(item, depth + 1) for item in value)
            return False
        return isinstance(record, dict) and bounded(record)

    @classmethod
    def _is_verified_legal_requirement(cls, requirement: Any) -> bool:
        """Re-derive source admission; serialized verification booleans are not proof."""
        if not isinstance(requirement, dict):
            return False
        source = requirement.get("source_record")
        if not cls._bounded_source_record(source):
            return False
        try:
            from integrations.ipfs_datasets.logic import extract_source_bound_rule_candidates
            admitted = extract_source_bound_rule_candidates(source).get("promoted_requirements", [])
        except Exception:
            return False
        keys = ("rule_text", "source_span", "source_hash", "span_sha256",
                "authority_text_sha256", "authority_id", "authority_version",
                "jurisdiction", "applicable_date", "temporal_applicability",
                "treatment_edges", "blocking_treatments")
        for candidate in admitted:
            if (candidate.get("applicable") is True and candidate.get("support_eligible") is True
                    and not candidate.get("treatment_blocks_support")
                    and all(requirement.get(key) == candidate.get(key) for key in keys)
                    and requirement.get("description") == candidate.get("rule_text")):
                return True
        return False

    def _heuristic_graph_law_derived(self, *args: Any, **kwargs: Any) -> None:
        """Heuristic law text is not a retrieved legal source."""
        raise RuntimeError("heuristic graph law-derived requirements are not a legal source")

    def _rule_identity(self, requirement: Dict[str, Any]) -> str:
        provenance = requirement.get("provenance") if isinstance(requirement.get("provenance"), dict) else {}
        return str(
            requirement.get("rule_id")
            or requirement.get("authority_id")
            or provenance.get("rule_id")
            or provenance.get("source_id")
            or requirement.get("name")
            or ""
        ).strip()

    @staticmethod
    def _is_user_law_assertion(requirement: Dict[str, Any]) -> bool:
        if requirement.get("user_asserted") is True:
            return True
        origin = str(requirement.get("origin") or requirement.get("source_kind") or "").strip().lower()
        if origin in {"user", "user_assertion", "complainant"}:
            return True
        return str(requirement.get("derivation_status") or "").strip().lower() == "user_assertion"

    def _add_unresolved_legal_requirement(
        self,
        graph: DependencyGraph,
        claim_node: DependencyNode,
        reason: str,
        req_data: Optional[Dict[str, Any]] = None,
    ) -> DependencyNode:
        """Record that authority was not selected. This node is not a legal rule."""
        payload = req_data if isinstance(req_data, dict) else {}
        jurisdiction = str(payload.get("jurisdiction") or graph.metadata.get("legal_context_jurisdiction") or "unknown")
        if not jurisdiction.strip():
            jurisdiction = "unknown"
        claim_type = str(claim_node.attributes.get("claim_type") or payload.get("claim_type") or "unknown")
        node = DependencyNode(
            id=self._get_namespaced_node_id("legal_requirement", {
                "gap": "unresolved_legal_requirement",
                "claim_type": claim_type,
                "claim_id": claim_node.id,
                "reason": reason,
                "authority_locator": str(payload.get("authority_locator") or ""),
            }),
            node_type=NodeType.REQUIREMENT,
            name="Unresolved legal requirement",
            description=(
                "No sourced legal requirement was selected. "
                "Missing or ambiguous authority was not replaced with an invented rule."
            ),
            satisfied=False,
            attributes={
                "record_kind": _UNRESOLVED_LEGAL_CLASS,
                "dependency_class": _UNRESOLVED_LEGAL_CLASS,
                "claim_type": claim_type,
                "jurisdiction": jurisdiction,
                "authority_locator": "",
                "source_locator": "",
                "authority_source_locator": "",
                "effective_date": "",
                "authority_version": "",
                "derivation_status": str(payload.get("derivation_status") or "unresolved"),
                "proof_status": "not_authoritative" if self._is_user_law_assertion(payload) or payload.get("proof_status") == "not_authoritative" else "unresolved",
                "unresolved_reason": reason,
                "asserted_text": str(payload.get("asserted_text") or "")[:500],
                "law_derived": False,
                "heuristic_law_derived": False,
                "source_available": False,
                "about_complainant": False,
                "user_assertion_is_not_law": True,
                "dependency_scope": {"claim_type": claim_type, "rule_id": "", "fact_ids": []},
            },
        )
        graph.add_node(node)
        graph.add_dependency(Dependency(
            id=self._get_dependency_id(),
            source_id=node.id,
            target_id=claim_node.id,
            dependency_type=DependencyType.REQUIRES,
            required=True,
        ))
        graph.metadata.setdefault("unresolved_legal_requirements", []).append({
            "claim_type": claim_type,
            "claim_id": claim_node.id,
            "node_id": node.id,
            "jurisdiction": jurisdiction,
            "reason": reason,
            "derivation_status": node.attributes["derivation_status"],
            "proof_status": node.attributes["proof_status"],
        })
        return node

    def _add_legal_requirement_node(
        self,
        graph: DependencyGraph,
        claim_node: DependencyNode,
        req_data: Dict[str, Any],
    ) -> DependencyNode:
        requirement_provenance = req_data.get("provenance") if isinstance(req_data.get("provenance"), dict) else {}
        claim_type = claim_node.attributes.get("claim_type")
        rule_id = self._rule_identity(req_data)
        req_node = DependencyNode(
            id=self._get_namespaced_node_id("legal_requirement", {
                "claim_type": claim_type,
                "claim_id": claim_node.id,
                "requirement": req_data,
            }),
            node_type=NodeType.LEGAL_ELEMENT,
            name=req_data.get("name", "Unnamed Requirement"),
            description=req_data.get("description", ""),
            satisfied=False,
            attributes={
                **deepcopy(req_data),
                "record_kind": "legal_requirement",
                "dependency_class": _LEGALLY_SOURCED_CLASS,
                "source_available": True,
                "source_fact_ids": list(req_data.get("fact_ids") or []),
                "law_derived": False,
                "about_complainant": False,
                "provenance": dict(requirement_provenance),
                "rule_id": rule_id,
                "verification_status": req_data.get("verification_status"),
                "source_bound": req_data.get("source_bound"),
                "dependency_scope": {
                    "claim_type": claim_type,
                    "claim_id": claim_node.id,
                    "rule_id": rule_id,
                    "jurisdiction": str(req_data.get("jurisdiction") or ""),
                    "fact_ids": [str(item) for item in (req_data.get("fact_ids") or []) if str(item).strip()],
                    "date_sensitive": True,
                },
                "satisfaction_revision": 0,
                "satisfaction_state": "unsatisfied",
            },
        )
        self._recompute_support_proof_and_question_targets(req_node)
        graph.add_node(req_node)
        graph.add_dependency(Dependency(
            id=self._get_dependency_id(),
            source_id=req_node.id,
            target_id=claim_node.id,
            dependency_type=DependencyType.REQUIRES,
            required=True,
        ))
        return req_node

    def _add_legal_source_gaps(self, graph: DependencyGraph, claim_nodes: List[DependencyNode]) -> None:
        """Record an explicit source gap when a claim has no retrieved verified requirement."""
        for claim_node in claim_nodes:
            if self._claim_has_sourced_requirement(graph, claim_node.id):
                continue
            claim_type = str(claim_node.attributes.get("claim_type") or "")
            gap = DependencyNode(
                id=self._get_namespaced_node_id("legal_requirement", {
                    "gap": "legal_context_source_gap",
                    "claim_type": claim_type,
                    "claim_id": claim_node.id,
                }),
                node_type=NodeType.REQUIREMENT,
                name="Legal context or source gap",
                description=(
                    "No retrieved verified legal requirement is available for this claim. "
                    "Heuristic law-derived elements were not substituted."
                ),
                satisfied=False,
                attributes={
                    "record_kind": _LEGAL_SOURCE_GAP_CLASS,
                    "dependency_class": _LEGAL_SOURCE_GAP_CLASS,
                    "gap_kind": "legal_context_source_gap",
                    "reason": "no_retrieved_requirements",
                    "law_derived": False,
                    "heuristic_law_derived": False,
                    "about_complainant": False,
                    "claim_type": claim_type,
                    "dependency_scope": {"claim_type": claim_type, "rule_id": "", "fact_ids": []},
                },
            )
            graph.add_node(gap)
            graph.add_dependency(Dependency(
                id=self._get_dependency_id(),
                source_id=gap.id,
                target_id=claim_node.id,
                dependency_type=DependencyType.REQUIRES,
                required=True,
            ))
            graph.metadata.setdefault("legal_source_gaps", []).append({
                "claim_type": claim_type,
                "claim_id": claim_node.id,
                "node_id": gap.id,
                "gap_kind": "legal_context_source_gap",
                "reason": "no_retrieved_requirements",
            })

    def _claim_has_sourced_requirement(self, graph: DependencyGraph, claim_id: str) -> bool:
        for dependency in graph.dependencies.values():
            if dependency.target_id != claim_id:
                continue
            source = graph.nodes.get(dependency.source_id)
            if source is None or not isinstance(source.attributes, dict):
                continue
            if (source.attributes.get("dependency_class") == _LEGALLY_SOURCED_CLASS
                    and source.attributes.get("source_available") is not False
                    and self._is_verified_legal_requirement(source.attributes)):
                return True
        return False

    def reconcile_verified_requirements(self, graph: DependencyGraph, grouped: Dict[str, Any]) -> Dict[str, Any]:
        """Keep unchanged source nodes; retire removed or changed source admissions."""
        claims = graph.get_nodes_by_type(NodeType.CLAIM)
        desired = {}
        for claim in claims:
            for requirement in grouped.get(claim.attributes.get("claim_type"), []) or []:
                if self._is_verified_legal_requirement(requirement):
                    key = self._get_namespaced_node_id("legal_requirement", {
                        "claim_type": claim.attributes.get("claim_type"),
                        "claim_id": claim.id, "requirement": requirement,
                    })
                    desired[key] = (claim, requirement)
        affected, added = [], []
        for node in list(graph.nodes.values()):
            if node.attributes.get("dependency_class") != _LEGALLY_SOURCED_CLASS:
                continue
            if node.id in desired and node.attributes.get("source_available") is not False:
                desired.pop(node.id)
                continue
            if node.attributes.get("source_available") is False:
                if node.satisfied:
                    affected.append(node.id)
                node.satisfied = False
                node.attributes.update(stale_satisfaction=True, satisfaction_state="invalidated")
                continue
            node.attributes["invalidated_satisfaction"] = {"satisfied": bool(node.satisfied), "confidence": node.confidence}
            node.satisfied = False
            node.attributes.update(source_available=False, stale_satisfaction=True,
                                   satisfaction_state="invalidated")
            retired = [edge for edge in graph.dependencies.values()
                       if edge.source_id == node.id or edge.target_id == node.id]
            node.attributes["retired_dependency_edges"] = [
                {"id": edge.id, "source_id": edge.source_id, "target_id": edge.target_id,
                 "dependency_type": edge.dependency_type.value, "required": edge.required}
                for edge in retired]
            graph.dependencies = {key: edge for key, edge in graph.dependencies.items()
                                  if edge.source_id != node.id and edge.target_id != node.id}
            node.attributes["satisfaction_revision"] = int(node.attributes.get("satisfaction_revision") or 0) + 1
            affected.append(node.id)
        for key, (claim, requirement) in desired.items():
            node = self._add_legal_requirement_node(graph, claim, requirement)
            node.attributes.update(stale_satisfaction=True, satisfaction_state="invalidated")
            added.append(node.id)
        self._refresh_legal_source_gaps(graph, claims)
        return {"affected_node_ids": affected + added, "added_node_ids": added,
                "preserved_node_ids": [key for key in graph.nodes if key not in set(affected + added)]}

    def apply_derived_dependency_requirements(self, graph: DependencyGraph, derivation: Dict[str, Any]) -> Dict[str, Any]:
        """Install SDK-derived requirements and visible unresolved research.

        Earlier nodes from this derivation are replaced. Fact support is stored
        on the requirement and does not change its rule text. Other graph
        nodes stay in place.
        """
        if not isinstance(derivation, dict):
            raise ValueError("derivation_invalid")
        task_id = "CIMP-UX-26"
        removed = []
        for node in list(graph.nodes.values()):
            attributes = node.attributes if isinstance(node.attributes, dict) else {}
            if attributes.get("derivation_task") == task_id:
                removed.append(node.id)
                graph.nodes.pop(node.id, None)
        if removed:
            removed_ids = set(removed)
            graph.dependencies = {key: edge for key, edge in graph.dependencies.items()
                                  if edge.source_id not in removed_ids and edge.target_id not in removed_ids}
        claims = graph.get_nodes_by_type(NodeType.CLAIM)
        installed = []
        for requirement in derivation.get("requirements") or []:
            if not isinstance(requirement, dict) or requirement.get("rule_text") != requirement.get("description"):
                continue
            node = self._add_legal_requirement_node(graph, claims[0] if claims else DependencyNode(
                id="case", node_type=NodeType.CLAIM, name="case", attributes={"claim_type": "unspecified"}), requirement)
            if not claims:
                graph.dependencies = {key: edge for key, edge in graph.dependencies.items() if edge.target_id != "case"}
                graph.nodes.pop("case", None)
            node.attributes["derivation_task"] = task_id
            node.attributes["derivation_lineage"] = deepcopy(requirement.get("derivation_lineage") or {})
            node.attributes["fact_support"] = list(requirement.get("fact_support") or [])
            node.attributes["support_state"] = requirement.get("support_state") or "unsupported"
            node.attributes["effective_date"] = requirement.get("effective_date") or ""
            node.attributes["authority_version"] = requirement.get("authority_version") or ""
            node.attributes["jurisdiction"] = requirement.get("jurisdiction") or ""
            node.attributes["admitted_law"] = True
            node.attributes["proof"] = False
            node.description = str(requirement.get("rule_text") or "")
            node.satisfied = False
            installed.append(node.id)
            for fact in node.attributes["fact_support"]:
                fact_node = next((item for item in graph.nodes.values()
                                  if item.node_type == NodeType.FACT and fact.get("fact_id") in {item.id, item.name}), None)
                if fact_node is None:
                    continue
                graph.add_dependency(Dependency(
                    id=self._get_dependency_id(), source_id=fact_node.id, target_id=node.id,
                    dependency_type=DependencyType.SUPPORTS, required=False,
                ))
        unresolved_ids = []
        for item in derivation.get("unresolved_research") or []:
            if not isinstance(item, dict):
                continue
            reason = str(item.get("reason") or "unresolved")
            node = DependencyNode(
                id=self._get_namespaced_node_id("legal_requirement", {"gap": "unresolved_research", "reason": reason,
                    "passage_id": str(item.get("passage_id") or ""), "task": task_id}),
                node_type=NodeType.REQUIREMENT,
                name="Unresolved legal research",
                description="Admitted authority did not yield a current requirement. No generic element was substituted.",
                satisfied=False,
                attributes={
                    "record_kind": "unresolved_research",
                    "dependency_class": "unresolved_research",
                    "derivation_task": task_id,
                    "unresolved_reason": reason,
                    "visible": True,
                    "law_derived": False,
                    "admitted_law": False,
                    "proof": False,
                    "review_reasons": list(item.get("review_reasons") or []),
                    "passage_id": str(item.get("passage_id") or ""),
                    "passage_ids": list(item.get("passage_ids") or []),
                },
            )
            graph.add_node(node)
            unresolved_ids.append(node.id)
            for claim in claims:
                graph.add_dependency(Dependency(
                    id=self._get_dependency_id(), source_id=node.id, target_id=claim.id,
                    dependency_type=DependencyType.REQUIRES, required=True,
                ))
        graph.metadata["derived_dependency_requirements"] = {
            "task_id": task_id,
            "status": derivation.get("status"),
            "requirement_ids": installed,
            "unresolved_ids": unresolved_ids,
            "hardcoded_elements_used": False,
        }
        return graph.metadata["derived_dependency_requirements"]

    def _refresh_legal_source_gaps(self, graph, claims=None):
        gap_ids = {node.id for node in graph.nodes.values()
                   if node.attributes.get("dependency_class") == _LEGAL_SOURCE_GAP_CLASS}
        for key in gap_ids:
            graph.nodes.pop(key, None)
        graph.dependencies = {key: edge for key, edge in graph.dependencies.items()
                              if edge.source_id not in gap_ids and edge.target_id not in gap_ids}
        graph.metadata["legal_source_gaps"] = []
        self._add_legal_source_gaps(graph, claims if claims is not None else graph.get_nodes_by_type(NodeType.CLAIM))

    def refresh_affected_dependencies(
        self,
        graph: DependencyGraph,
        change: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return dependency_graph_readiness.refresh_affected_dependencies(
            self,
            graph,
            change,
        )

    def _dependency_change_affects(
        self,
        node: DependencyNode,
        clarification_keys: set,
        fact_ids: set,
        rule_ids: set,
        jurisdiction_changed: bool,
        date_changed: bool,
        fact_change: bool,
        version_changed: bool = False,
        treatment_changed: bool = False,
        source_outage: bool = False,
        definition_changed: bool = False,
        definition_identity: Any = None,
        premise_identity: Any = None,
        adverse_treatment_identity: Any = None,
        forum_changed: bool = False,
        applicability_changed: bool = False,
        context_changed: bool = False,
    ) -> bool:
        attributes = node.attributes if isinstance(node.attributes, dict) else {}
        dependency_class = attributes.get("dependency_class")
        scope = attributes.get("dependency_scope") if isinstance(attributes.get("dependency_scope"), dict) else {}
        if dependency_class == _FACTUAL_CLARIFICATION_CLASS and fact_change:
            node_keys = {str(item) for item in (attributes.get("clarification_keys") or scope.get("clarification_keys") or [])}
            node_facts = {str(item) for item in (scope.get("fact_ids") or [])}
            if clarification_keys and node_keys & clarification_keys:
                return True
            if fact_ids and node_facts & fact_ids:
                return True
            return False
        if dependency_class != _LEGALLY_SOURCED_CLASS:
            return False
        node_rule = str(scope.get("rule_id") or attributes.get("rule_id") or "")
        node_facts = {str(item) for item in (scope.get("fact_ids") or [])}
        if rule_ids and node_rule in rule_ids:
            return True
        if fact_ids and node_facts & fact_ids:
            return True
        if (jurisdiction_changed or date_changed or context_changed or forum_changed or applicability_changed
                or version_changed or treatment_changed or source_outage or definition_changed):
            return True
        if definition_identity is not None and attributes.get("definition_identity") not in (None, definition_identity):
            return True
        if premise_identity is not None and attributes.get("premise_identity") not in (None, premise_identity):
            return True
        if adverse_treatment_identity is not None and attributes.get("adverse_treatment_identity") not in (None, adverse_treatment_identity):
            return True
        return False

    @staticmethod
    def _recompute_support_proof_and_question_targets(node: DependencyNode) -> None:
        """Mint new support, proof, and question identities for one affected requirement."""
        import hashlib

        attributes = node.attributes if isinstance(node.attributes, dict) else {}
        scope = attributes.get("dependency_scope") if isinstance(attributes.get("dependency_scope"), dict) else {}
        basis = json.dumps({
            "authority_id": attributes.get("authority_id"),
            "authority_version": attributes.get("authority_version"),
            "jurisdiction": scope.get("jurisdiction") or attributes.get("jurisdiction"),
            "reason": attributes.get("invalidation_reason"),
            "rule_id": scope.get("rule_id") or attributes.get("rule_id"),
            "satisfaction_revision": attributes.get("satisfaction_revision"),
            "source_hash": attributes.get("source_hash"),
        }, sort_keys=True, default=str)
        digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()
        previous_support = str(attributes.get("support_identity") or "")
        if previous_support and previous_support != digest:
            attributes["rejected_support_identity"] = previous_support
        attributes["support_identity"] = digest
        previous_proof = str(attributes.get("proof_identity") or attributes.get("proof_cache_identity") or "")
        if previous_proof:
            attributes["rejected_proof_identity"] = previous_proof
        attributes["proof_identity"] = ""
        attributes["proof_cache_reusable"] = False
        targets = attributes.get("inquiry_targets")
        if isinstance(targets, list):
            for inquiry in targets:
                if not isinstance(inquiry, dict):
                    continue
                inquiry["status"] = "reopened"
                inquiry["target_revision"] = digest[:16]
                inquiry["invalidation_reason"] = attributes.get("invalidation_reason") or "dependency_refresh"
        previous_target = str(attributes.get("question_target_id") or "")
        new_target = "qt_" + digest[:24]
        if previous_target and previous_target != new_target:
            attributes["rejected_question_target_id"] = previous_target
        attributes["question_target_id"] = new_target
        attributes["question_target_revision"] = digest[:16]
        node.attributes = attributes

    def _replace_changed_rules(
        self,
        graph: DependencyGraph,
        rule_ids: set,
        updated_requirements: Dict[str, Any],
    ) -> List[str]:
        """Replace only the sourced requirements whose rule identity changed."""
        removed = []
        claim_nodes = {
            node.id: node
            for node in graph.get_nodes_by_type(NodeType.CLAIM)
            if isinstance(node.attributes, dict)
        }
        for node in list(graph.nodes.values()):
            attributes = node.attributes if isinstance(node.attributes, dict) else {}
            if (attributes.get("dependency_class") != _LEGALLY_SOURCED_CLASS
                    or attributes.get("source_available") is False):
                continue
            scope = attributes.get("dependency_scope") if isinstance(attributes.get("dependency_scope"), dict) else {}
            rule_id = str(scope.get("rule_id") or attributes.get("rule_id") or "")
            if rule_id not in rule_ids:
                continue
            prior = {
                "satisfied": bool(node.satisfied),
                "confidence": node.confidence,
                "satisfaction_state": attributes.get("satisfaction_state"),
            }
            graph.dependencies = {
                dep_id: dep for dep_id, dep in graph.dependencies.items()
                if dep.source_id != node.id and dep.target_id != node.id
            }
            graph.nodes.pop(node.id, None)
            removed.append(rule_id)
            claim_node = claim_nodes.get(str(scope.get("claim_id") or ""))
            replacement = None
            for requirements in [updated_requirements.get(str(scope.get("claim_type") or ""), [])]:
                if not isinstance(requirements, list):
                    continue
                for requirement in requirements:
                    if isinstance(requirement, dict) and self._rule_identity(requirement) == rule_id:
                        replacement = requirement
                        break
            if claim_node is not None and isinstance(replacement, dict) and self._is_verified_legal_requirement(replacement):
                added = self._add_legal_requirement_node(graph, claim_node, replacement)
                added.attributes["stale_satisfaction"] = True
                added.attributes["satisfaction_state"] = "invalidated"
                added.attributes["invalidated_satisfaction"] = prior
                added.satisfied = False
        return removed

    def sync_intake_timeline_to_graph(
        self,
        graph: DependencyGraph,
        intake_case_file: Optional[Dict[str, Any]],
    ) -> DependencyGraph:
        """Synchronize structured intake timeline facts and temporal edges into a dependency graph."""
        if not isinstance(graph, DependencyGraph):
            return graph

        case_file = intake_case_file if isinstance(intake_case_file, dict) else {}
        canonical_facts = case_file.get('canonical_facts') if isinstance(case_file.get('canonical_facts'), list) else []
        timeline_relations = case_file.get('timeline_relations') if isinstance(case_file.get('timeline_relations'), list) else []

        temporal_node_ids = [
            node_id
            for node_id, node in graph.nodes.items()
            if isinstance(node.attributes, dict) and node.attributes.get('timeline_fact_node')
        ]
        if temporal_node_ids:
            temporal_node_id_set = set(temporal_node_ids)
            graph.dependencies = {
                dep_id: dep
                for dep_id, dep in graph.dependencies.items()
                if dep.source_id not in temporal_node_id_set and dep.target_id not in temporal_node_id_set
            }
            for node_id in temporal_node_ids:
                graph.nodes.pop(node_id, None)

        claim_nodes = graph.get_nodes_by_type(NodeType.CLAIM)
        claim_nodes_by_type = {
            str(node.attributes.get('claim_type') or '').strip(): node
            for node in claim_nodes
            if isinstance(node.attributes, dict)
        }
        timeline_node_ids_by_fact_id: Dict[str, str] = {}

        for fact in canonical_facts:
            if not isinstance(fact, dict):
                continue
            temporal_context = fact.get('temporal_context') if isinstance(fact.get('temporal_context'), dict) else {}
            if (
                str(fact.get('fact_type') or '').strip().lower() != 'timeline'
                and not temporal_context.get('start_date')
                and not temporal_context.get('relative_markers')
            ):
                continue

            fact_id = str(fact.get('fact_id') or '').strip()
            if not fact_id:
                continue
            node_id = self._get_node_id()
            timeline_node = DependencyNode(
                id=node_id,
                node_type=NodeType.FACT,
                name=str(fact.get('text') or fact_id),
                description=str(fact.get('event_date_or_range') or fact.get('text') or ''),
                satisfied=bool(
                    temporal_context.get('start_date')
                    or temporal_context.get('relative_markers')
                    or fact.get('event_date_or_range')
                ),
                confidence=float(fact.get('confidence', 0.0) or 0.0),
                attributes={
                    'timeline_fact_node': True,
                    'source_fact_id': fact_id,
                    'fact_type': fact.get('fact_type'),
                    'event_date_or_range': fact.get('event_date_or_range'),
                    'temporal_context': temporal_context,
                    'claim_types': list(fact.get('claim_types') or []),
                    'element_tags': list(fact.get('element_tags') or []),
                },
            )
            graph.add_node(timeline_node)
            timeline_node_ids_by_fact_id[fact_id] = node_id

            target_claim_nodes = []
            claim_types = [str(item).strip() for item in (fact.get('claim_types') or []) if str(item).strip()]
            for claim_type in claim_types:
                claim_node = claim_nodes_by_type.get(claim_type)
                if claim_node is not None:
                    target_claim_nodes.append(claim_node)
            if not target_claim_nodes:
                target_claim_nodes = claim_nodes

            for claim_node in target_claim_nodes:
                graph.add_dependency(
                    Dependency(
                        id=self._get_dependency_id(),
                        source_id=timeline_node.id,
                        target_id=claim_node.id,
                        dependency_type=DependencyType.SUPPORTS,
                        required=False,
                        strength=max(0.1, min(1.0, float(fact.get('confidence', 0.0) or 0.0))),
                    )
                )

        relation_type_map = {
            'before': DependencyType.BEFORE,
            'same_time': DependencyType.SAME_TIME,
            'overlaps': DependencyType.OVERLAPS,
        }
        for relation in timeline_relations:
            if not isinstance(relation, dict):
                continue
            source_fact_id = str(relation.get('source_fact_id') or '').strip()
            target_fact_id = str(relation.get('target_fact_id') or '').strip()
            dependency_type = relation_type_map.get(str(relation.get('relation_type') or '').strip())
            source_node_id = timeline_node_ids_by_fact_id.get(source_fact_id)
            target_node_id = timeline_node_ids_by_fact_id.get(target_fact_id)
            if not dependency_type or not source_node_id or not target_node_id:
                continue
            confidence = str(relation.get('confidence') or '').strip().lower()
            strength = 0.7 if confidence == 'high' else 0.55 if confidence == 'medium' else 0.4
            graph.add_dependency(
                Dependency(
                    id=self._get_dependency_id(),
                    source_id=source_node_id,
                    target_id=target_node_id,
                    dependency_type=dependency_type,
                    required=False,
                    strength=strength,
                )
            )

        graph._update_metadata()
        return graph
    
    def invalidate_factual_dependents(
        self,
        graph: DependencyGraph,
        fact_id: str,
        *,
        reason: str,
        event_id: str = "",
    ) -> Dict[str, Any]:
        """Drop proof caches and satisfaction only where this fact is a support input.

        Legal requirement text, source identity, and unrelated node ids stay.
        Contradiction edges remain. Affected inquiry targets are reopened.
        """
        if not isinstance(graph, DependencyGraph) or not fact_id:
            return {"invalidated_node_ids": [], "reopened_inquiry_ids": [], "preserved_node_ids": []}
        invalidated = []
        reopened = []
        for node in graph.nodes.values():
            attributes = node.attributes if isinstance(node.attributes, dict) else {}
            if not self._node_depends_on_fact(node, fact_id):
                continue
            if node.id == fact_id:
                continue
            preserved_text = {
                "name": node.name,
                "description": node.description,
                "rule_id": attributes.get("rule_id"),
                "authority_id": attributes.get("authority_id"),
                "source_hash": attributes.get("source_hash"),
                "source_span": deepcopy(attributes.get("source_span")) if isinstance(attributes.get("source_span"), dict) else attributes.get("source_span"),
                "provenance": deepcopy(attributes.get("provenance")) if isinstance(attributes.get("provenance"), dict) else attributes.get("provenance"),
            }
            if node.satisfied or attributes.get("satisfaction_state") == "satisfied" or attributes.get("proof_cache_identity") or isinstance(attributes.get("proof_cache"), dict):
                attributes["invalidated_satisfaction"] = {
                    "satisfied": bool(node.satisfied),
                    "confidence": node.confidence,
                    "satisfaction_state": attributes.get("satisfaction_state"),
                    "proof_cache_identity": attributes.get("proof_cache_identity"),
                }
                node.satisfied = False
                attributes["satisfaction_state"] = "invalidated"
                attributes["stale_satisfaction"] = True
            if attributes.get("proof_cache_identity"):
                attributes["rejected_proof_cache_identity"] = attributes.get("proof_cache_identity")
            attributes["proof_cache_reusable"] = False
            if isinstance(attributes.get("proof_cache"), dict):
                attributes["proof_cache"] = dict(attributes["proof_cache"])
                attributes["proof_cache"]["reusable"] = False
                attributes["proof_cache"]["satisfied"] = False
                attributes["proof_cache"]["invalidation_reason"] = reason
                attributes["proof_cache"]["invalidated_entity_id"] = fact_id
            attributes["invalidation_reason"] = reason
            attributes["invalidated_entity_id"] = fact_id
            for inquiry in attributes.get("inquiry_targets") or []:
                if not isinstance(inquiry, dict):
                    continue
                target = str(inquiry.get("entity_id") or inquiry.get("fact_id") or "")
                if target != fact_id:
                    continue
                inquiry["status"] = "reopened"
                inquiry["invalidation_reason"] = reason
                inquiry["event_id"] = event_id
                reopened.append(inquiry.get("inquiry_id"))
            node.name = preserved_text["name"]
            node.description = preserved_text["description"]
            attributes["rule_id"] = preserved_text["rule_id"]
            attributes["authority_id"] = preserved_text["authority_id"]
            attributes["source_hash"] = preserved_text["source_hash"]
            attributes["source_span"] = preserved_text["source_span"]
            attributes["provenance"] = preserved_text["provenance"]
            node.attributes = attributes
            invalidated.append(node.id)
        for dependency in graph.dependencies.values():
            if dependency.dependency_type == DependencyType.CONTRADICTS:
                continue
            if dependency.dependency_type != DependencyType.SUPPORTS:
                continue
            if fact_id not in {dependency.source_id, dependency.target_id}:
                continue
            graph.metadata.setdefault("invalidated_support_refs", [])
            ref = {
                "dependency_id": dependency.id,
                "source_id": dependency.source_id,
                "target_id": dependency.target_id,
                "fact_id": fact_id,
                "reason": reason,
                "event_id": event_id,
            }
            if ref not in graph.metadata["invalidated_support_refs"]:
                graph.metadata["invalidated_support_refs"].append(ref)
        graph._update_metadata()
        preserved = [node_id for node_id in graph.nodes if node_id not in set(invalidated)]
        return {
            "invalidated_node_ids": invalidated,
            "reopened_inquiry_ids": reopened,
            "preserved_node_ids": preserved,
        }

    @staticmethod
    def _node_depends_on_fact(node: DependencyNode, fact_id: str) -> bool:
        attributes = node.attributes if isinstance(node.attributes, dict) else {}
        scope = attributes.get("dependency_scope") if isinstance(attributes.get("dependency_scope"), dict) else {}
        listed = {str(item) for item in (scope.get("fact_ids") or []) if str(item).strip()}
        listed.update(str(item) for item in (attributes.get("source_fact_ids") or []) if str(item).strip())
        listed.update(str(item) for item in (attributes.get("support_fact_ids") or []) if str(item).strip())
        if attributes.get("support_fact_id"):
            listed.add(str(attributes.get("support_fact_id")))
        cache = attributes.get("proof_cache") if isinstance(attributes.get("proof_cache"), dict) else {}
        listed.update(str(item) for item in (cache.get("fact_ids") or []) if str(item).strip())
        if cache.get("fact_id"):
            listed.add(str(cache.get("fact_id")))
        for inquiry in attributes.get("inquiry_targets") or []:
            if isinstance(inquiry, dict) and str(inquiry.get("fact_id") or inquiry.get("entity_id") or "") == fact_id:
                listed.add(fact_id)
        return fact_id in listed

    def apply_retrieval_nomination(
        self,
        graph: DependencyGraph,
        payload: Dict[str, Any],
        *,
        claim_id: str = "",
        requirement_id: str = "",
        source_span: Optional[Dict[str, Any]] = None,
        allegation_id: str = "",
    ) -> Dict[str, Any]:
        """Admit retrieval output as a nomination until exact binding is rechecked.

        A bound nomination may support a factual allegation. It does not rewrite
        or satisfy the governing legal requirement.
        """
        from mediator.integrations.graph_tools import GraphRetrievalAugmentor

        if not isinstance(graph, DependencyGraph):
            return {"admitted": False, "reason": "dependency_graph_unavailable", "bound_support": False}
        augmentor = GraphRetrievalAugmentor()
        if claim_id or requirement_id or source_span is not None:
            checked = augmentor.recheck_support_binding(
                payload,
                claim_id=claim_id,
                requirement_id=requirement_id,
                source_span=source_span,
            )
        else:
            checked = dict(payload)
            checked["bound_support"] = False
            checked["support_status"] = checked.get("support_status") or "candidate_nomination"
            checked["satisfied_legal_requirement"] = False
        legal = graph.nodes.get(requirement_id) if requirement_id else None
        legal_before = None
        if legal is not None:
            legal_before = {
                "id": legal.id,
                "name": legal.name,
                "description": legal.description,
                "satisfied": legal.satisfied,
                "rule_id": (legal.attributes or {}).get("rule_id"),
                "authority_id": (legal.attributes or {}).get("authority_id"),
                "source_hash": (legal.attributes or {}).get("source_hash"),
                "source_span": deepcopy((legal.attributes or {}).get("source_span")),
                "provenance": deepcopy((legal.attributes or {}).get("provenance")),
            }
        record_id = str(checked.get("id") or "").strip()
        if record_id and graph.get_node(record_id) is None:
            graph.add_node(DependencyNode(
                id=record_id,
                node_type=NodeType.EVIDENCE,
                name=str(checked.get("name") or "Evidence"),
                description=str(checked.get("description") or ""),
                satisfied=False,
                confidence=float(checked.get("retrieval_confidence", checked.get("confidence", 0.0)) or 0.0),
                attributes={
                    "support_status": checked.get("support_status"),
                    "binding_status": checked.get("binding_status"),
                    "bound_support": bool(checked.get("bound_support")),
                    "retrieval_confidence": checked.get("retrieval_confidence", checked.get("confidence")),
                    "confidence_role": "retrieval_candidate",
                    "satisfied_legal_requirement": False,
                    "supports_claims": list(checked.get("supports_claims") or []),
                    "source_type": checked.get("source_type"),
                },
            ))
        if checked.get("bound_support") and allegation_id and allegation_id in graph.nodes and record_id in graph.nodes:
            dependency_id = f"supports:{record_id}:{allegation_id}"
            if dependency_id not in graph.dependencies:
                graph.add_dependency(Dependency(
                    id=dependency_id,
                    source_id=record_id,
                    target_id=allegation_id,
                    dependency_type=DependencyType.SUPPORTS,
                    required=False,
                    strength=0.0,
                ))
            allegation = graph.nodes[allegation_id]
            allegation_attributes = dict(allegation.attributes or {})
            refs = list(allegation_attributes.get("evidence_support_refs") or [])
            if record_id not in refs:
                refs.append(record_id)
            allegation_attributes["evidence_support_refs"] = refs
            allegation.attributes = allegation_attributes
        if legal is not None and legal_before is not None:
            legal.id = legal_before["id"]
            legal.name = legal_before["name"]
            legal.description = legal_before["description"]
            legal.satisfied = False if not legal_before["satisfied"] else legal_before["satisfied"]
            attributes = dict(legal.attributes or {})
            attributes["rule_id"] = legal_before["rule_id"]
            attributes["authority_id"] = legal_before["authority_id"]
            attributes["source_hash"] = legal_before["source_hash"]
            attributes["source_span"] = legal_before["source_span"]
            attributes["provenance"] = legal_before["provenance"]
            attributes["satisfied_by_retrieval"] = False
            legal.attributes = attributes
        graph._update_metadata()
        return {
            "admitted": bool(checked.get("bound_support")),
            "bound_support": bool(checked.get("bound_support")),
            "support_status": checked.get("support_status"),
            "binding_status": checked.get("binding_status"),
            "binding_reason": checked.get("binding_reason"),
            "satisfied_legal_requirement": False,
            "retrieval_confidence": checked.get("retrieval_confidence", checked.get("confidence")),
            "legal_requirement": legal_before,
        }

    def support_factual_allegation(
        self,
        graph: DependencyGraph,
        *,
        evidence_id: str,
        allegation_id: str,
        legal_requirement_id: str,
    ) -> Dict[str, Any]:
        """Let evidence support an allegation without editing the legal requirement."""
        evidence = graph.nodes.get(evidence_id)
        allegation = graph.nodes.get(allegation_id)
        legal = graph.nodes.get(legal_requirement_id)
        if evidence is None or allegation is None or legal is None:
            return {"supported": False, "reason": "endpoint_unavailable"}
        before = {
            "id": legal.id,
            "name": legal.name,
            "description": legal.description,
            "rule_id": (legal.attributes or {}).get("rule_id"),
            "authority_id": (legal.attributes or {}).get("authority_id"),
            "source_hash": (legal.attributes or {}).get("source_hash"),
            "source_span": deepcopy((legal.attributes or {}).get("source_span")),
            "provenance": deepcopy((legal.attributes or {}).get("provenance")),
            "satisfied": bool(legal.satisfied),
        }
        dependency_id = f"supports:{evidence_id}:{allegation_id}"
        if dependency_id not in graph.dependencies:
            graph.add_dependency(Dependency(
                id=dependency_id,
                source_id=evidence_id,
                target_id=allegation_id,
                dependency_type=DependencyType.SUPPORTS,
                required=False,
                strength=1.0,
            ))
        attributes = dict(allegation.attributes or {})
        refs = list(attributes.get("evidence_support_refs") or [])
        if evidence_id not in refs:
            refs.append(evidence_id)
        attributes["evidence_support_refs"] = refs
        attributes["epistemic_class"] = attributes.get("epistemic_class") or "allegation"
        allegation.attributes = attributes
        legal.name = before["name"]
        legal.description = before["description"]
        legal.satisfied = before["satisfied"]
        legal_attributes = dict(legal.attributes or {})
        legal_attributes["rule_id"] = before["rule_id"]
        legal_attributes["authority_id"] = before["authority_id"]
        legal_attributes["source_hash"] = before["source_hash"]
        legal_attributes["source_span"] = before["source_span"]
        legal_attributes["provenance"] = before["provenance"]
        legal.attributes = legal_attributes
        graph._update_metadata()
        return {"supported": True, "legal_requirement": before, "allegation_id": allegation_id}

    def record_visible_contradiction(
        self,
        graph: DependencyGraph,
        *,
        left_fact_id: str,
        right_fact_id: str,
        legal_requirement_id: str,
    ) -> Dict[str, Any]:
        """Keep both facts visible. Neither contradiction becomes a satisfied legal requirement."""
        left = graph.nodes.get(left_fact_id)
        right = graph.nodes.get(right_fact_id)
        legal = graph.nodes.get(legal_requirement_id)
        if left is None or right is None or legal is None:
            return {"visible": False, "reason": "endpoint_unavailable"}
        before = {
            "id": legal.id,
            "name": legal.name,
            "description": legal.description,
            "rule_id": (legal.attributes or {}).get("rule_id"),
            "source_hash": (legal.attributes or {}).get("source_hash"),
            "provenance": deepcopy((legal.attributes or {}).get("provenance")),
        }
        dependency_id = f"contradicts:{left_fact_id}:{right_fact_id}"
        if dependency_id not in graph.dependencies:
            graph.add_dependency(Dependency(
                id=dependency_id,
                source_id=left_fact_id,
                target_id=right_fact_id,
                dependency_type=DependencyType.CONTRADICTS,
                required=False,
                strength=1.0,
            ))
        legal.satisfied = False
        attributes = dict(legal.attributes or {})
        attributes["satisfaction_state"] = "unsatisfied"
        attributes["satisfied_by_contradiction"] = False
        attributes["rule_id"] = before["rule_id"]
        attributes["source_hash"] = before["source_hash"]
        attributes["provenance"] = before["provenance"]
        legal.attributes = attributes
        legal.name = before["name"]
        legal.description = before["description"]
        graph._update_metadata()
        return {
            "visible": left_fact_id in graph.nodes and right_fact_id in graph.nodes,
            "legal_requirement_satisfied": bool(legal.satisfied),
            "dependency_id": dependency_id,
            "legal_text": legal.name,
            "legal_source_hash": attributes.get("source_hash"),
        }

    def add_evidence_to_graph(self, graph: DependencyGraph, 
                             evidence_data: Dict[str, Any],
                             supports_claim_id: str) -> str:
        """
        Add evidence to the dependency graph.
        
        Args:
            graph: The dependency graph to update
            evidence_data: Evidence information
            supports_claim_id: ID of claim this evidence supports
            
        Returns:
            The ID of the created evidence node
        """
        nomination = str(evidence_data.get("support_status") or "") == "candidate_nomination" or evidence_data.get("binding_status") == "unbound"
        evidence_node = DependencyNode(
            id=self._get_node_id(),
            node_type=NodeType.EVIDENCE,
            name=evidence_data.get('name', 'Unnamed Evidence'),
            description=evidence_data.get('description', ''),
            satisfied=not nomination,
            confidence=evidence_data.get('confidence', 0.8),
            attributes=evidence_data.get('attributes', {})
        )
        if nomination:
            evidence_node.attributes = dict(evidence_node.attributes or {})
            evidence_node.attributes["support_status"] = "candidate_nomination"
            evidence_node.attributes["satisfied_legal_requirement"] = False
            evidence_node.satisfied = False
        graph.add_node(evidence_node)

        if nomination and not evidence_data.get("bound_support"):
            graph._update_metadata()
            return evidence_node.id

        # Create support relationship
        dep = Dependency(
            id=self._get_dependency_id(),
            source_id=evidence_node.id,
            target_id=supports_claim_id,
            dependency_type=DependencyType.SUPPORTS,
            required=False,
            strength=evidence_data.get('strength', 0.7)
        )
        graph.add_dependency(dep)
        
        return evidence_node.id
    
    def _get_node_id(self) -> str:
        """Generate unique node ID."""
        self.node_counter += 1
        return f"node_{self.node_counter}"

    def _get_namespaced_node_id(self, kind: str, identity: Optional[Dict[str, Any]] = None) -> str:
        """Mint a node id that cannot collide with fact, claim, or link ids."""
        from integrations.ipfs_datasets.graphs import mint_graph_record_id

        self.node_counter += 1
        if identity is not None:
            return mint_graph_record_id(kind, json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
        return mint_graph_record_id(kind, kind, str(self.node_counter))
    
    def _get_dependency_id(self) -> str:
        """Generate unique dependency ID."""
        self.dependency_counter += 1
        return f"dep_{self.dependency_counter}"

    def apply_element_proof_cache(
        self,
        graph: DependencyGraph,
        node_id: str,
        evaluation: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Bind a versioned element proof. A new identity drops the prior satisfied result."""

        node = graph.nodes.get(node_id)
        if node is None or not isinstance(node.attributes, dict):
            raise KeyError(node_id)
        from integrations.ipfs_datasets.logic import verify_element_proof_evaluation
        admission = verify_element_proof_evaluation(evaluation)
        admitted = bool(admission.get('verified'))
        observed = admission.get('evaluation') if admitted else {}
        evaluation = observed if isinstance(observed, dict) else {}
        identity = str(evaluation.get("cache_identity") or "")
        previous = str(node.attributes.get("proof_cache_identity") or "")
        if previous and previous != identity:
            node.attributes["rejected_proof_cache_identity"] = previous
            node.attributes["proof_cache_reusable"] = False
            if node.satisfied or node.attributes.get("satisfaction_state") == "satisfied":
                node.attributes["invalidated_satisfaction"] = {
                    "satisfied": bool(node.satisfied),
                    "confidence": node.confidence,
                    "satisfaction_state": node.attributes.get("satisfaction_state"),
                    "proof_cache_identity": previous,
                }
            node.satisfied = False
        # A current, issued evaluation remains nonsubstantive until an actual
        # checked kernel proof contract is configured and verified by the adapter.
        satisfied = admitted and admission.get('satisfied') is True
        node.attributes['proof_evaluation_verified'] = admitted
        node.attributes['proof_evaluation_reason'] = admission.get('reason')
        node.attributes["proof_cache_identity"] = identity
        node.attributes["proof_cache"] = {
            "cache_identity": identity,
            "satisfied": satisfied,
            "status": evaluation.get("status") or 'unknown',
            "reason": evaluation.get("reason") or admission.get('reason'),
            "reusable": satisfied,
            "result": deepcopy(evaluation.get("result")),
        }
        node.attributes["recommended_follow_ups"] = list(evaluation.get("recommended_follow_ups") or [])
        if satisfied:
            node.satisfied = True
            node.attributes["satisfaction_state"] = "satisfied"
            node.attributes["proof_cache_reusable"] = True
            node.attributes["stale_satisfaction"] = False
        else:
            node.satisfied = False
            node.attributes["satisfaction_state"] = str(evaluation.get("status") or "uncertain")
            node.attributes["proof_cache_reusable"] = False
            node.attributes["stale_satisfaction"] = True
        graph._update_metadata()
        return deepcopy(node.attributes)

    def add_fact_rule_link(
        self,
        graph: DependencyGraph,
        *,
        factual_assertion_id: str,
        rule_id: str,
        relation: str = "supports",
        factual_provenance: Optional[Dict[str, Any]] = None,
        rule_provenance: Optional[Dict[str, Any]] = None,
        factual_name: str = "",
        rule_name: str = "",
    ) -> Dict[str, Any]:
        """Record a support or contradiction edge across factual and rule namespaces.

        Each side keeps its own provenance chain. The link id is neither a fact
        id nor a rule id.
        """
        from integrations.ipfs_datasets.graphs import (
            FACTUAL_ASSERTION_KIND,
            build_namespaced_support_link,
            record_kind_from_id,
        )

        link = build_namespaced_support_link(
            factual_assertion_id=factual_assertion_id,
            rule_id=rule_id,
            relation=relation,
            factual_provenance=factual_provenance,
            rule_provenance=rule_provenance,
        )
        fact_chain = dict(link["provenance_chains"][FACTUAL_ASSERTION_KIND])
        rule_chain = dict(link["provenance_chains"]["rule"])
        fact_text = factual_name or factual_assertion_id
        if link["assertion_verified"]:
            # The flag verifies only the immutable assertion's content. A local
            # alias or caller display label cannot introduce another assertion.
            from integrations.ipfs_datasets.types import user_assertion_from_mapping
            asserted_text = user_assertion_from_mapping(fact_chain["user_assertion"]).source_span_text
            if factual_name and " ".join(factual_name.split()) != " ".join(asserted_text.split()):
                raise ValueError("factual label differs from the verified assertion span")
            fact_text = asserted_text
        fact_ref = link["factual_assertion_id"]
        rule_kind = record_kind_from_id(rule_id)
        # Validate both endpoints and any replay BEFORE mutating the graph.
        for endpoint, expected_type, expected_kind, chain in (
            (fact_ref, NodeType.FACT, FACTUAL_ASSERTION_KIND, fact_chain),
            (rule_id, NodeType.LEGAL_ELEMENT, rule_kind, rule_chain),
        ):
            node = graph.nodes.get(endpoint)
            if node is None:
                continue
            if node.id != endpoint or node.node_type != expected_type or node.attributes.get("record_kind") != expected_kind:
                raise ValueError("cross-graph endpoint has a conflicting type or namespace")
            if node.attributes.get("provenance", {}) != chain:
                raise ValueError("cross-graph endpoint has conflicting source provenance")
            if expected_type == NodeType.FACT and link["assertion_verified"] and (
                not isinstance(node.name, str) or " ".join(node.name.split()) != " ".join(fact_text.split())
            ):
                raise ValueError("stored factual text differs from its verified assertion span")
        if fact_ref != factual_assertion_id and factual_assertion_id in graph.nodes:
            node = graph.nodes[factual_assertion_id]
            if node.id != factual_assertion_id or node.node_type != NodeType.FACT or node.attributes.get("provenance", {}) != fact_chain:
                raise ValueError("local factual endpoint is ambiguous or has conflicting provenance")
            if link["assertion_verified"] and (
                not isinstance(node.name, str) or " ".join(node.name.split()) != " ".join(fact_text.split())
            ):
                raise ValueError("local factual text differs from its verified assertion span")
        dependency_type = (
            DependencyType.CONTRADICTS if link["link_type"] == "contradiction_link" else DependencyType.SUPPORTS
        )
        existing_dependency = graph.dependencies.get(link["link_id"])
        if existing_dependency is not None and (
            existing_dependency.id != link["link_id"]
            or existing_dependency.source_id != fact_ref or existing_dependency.target_id != rule_id
            or existing_dependency.dependency_type != dependency_type
            or existing_dependency.required or existing_dependency.strength != 1.0
        ):
            raise ValueError("cross-graph link identity conflicts with an existing dependency")
        existing_links = graph.metadata.get("cross_graph_links", [])
        if not isinstance(existing_links, list):
            raise ValueError("invalid cross-graph link registry")
        previous = [item for item in existing_links if isinstance(item, dict) and item.get("link_id") == link["link_id"]]
        if any(item != link for item in previous):
            raise ValueError("cross-graph link replay changed provenance")
        if fact_ref not in graph.nodes:
            graph.add_node(DependencyNode(
                id=fact_ref,
                node_type=NodeType.FACT,
                name=fact_text,
                attributes={
                    "record_kind": FACTUAL_ASSERTION_KIND,
                    "source_entity_id": factual_assertion_id,
                    "assertion_verified": link["assertion_verified"],
                    "provenance": deepcopy(fact_chain),
                },
            ))
        if rule_id not in graph.nodes:
            graph.add_node(DependencyNode(
                id=rule_id,
                node_type=NodeType.LEGAL_ELEMENT,
                name=rule_name or rule_id,
                attributes={
                    "record_kind": rule_kind,
                    "about_complainant": False,
                    "provenance": deepcopy(rule_chain),
                },
            ))
        graph.add_dependency(Dependency(
            id=link["link_id"],
            source_id=fact_ref,
            target_id=rule_id,
            dependency_type=dependency_type,
            required=False,
            strength=1.0,
        ))
        if not previous:
            graph.metadata.setdefault("cross_graph_links", []).append(deepcopy(link))
        return deepcopy(link)

from . import dependency_graph_readiness
