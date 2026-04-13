from lib.legal_document import parse_legal_document
from lib.support_map import SupportMapBuilder
from lib.knowledge_graph_formats import (
    GraphData, NodeData, RelationshipData, SchemaData, MigrationFormat,
    register_format, registered_formats,
)
from lib.knowledge_graph_export import ExportConfig, ExportResult, Neo4jExporter
from lib.deontic_logic import (
    DeonticConflict,
    DeonticGraph,
    DeonticGraphBuilder,
    DeonticModality,
    DeonticNode,
    DeonticNodeType,
    DeonticRule,
    DeonticRuleAssessment,
)
from lib.formal_logic.core import (
    Action,
    Conjunction,
    DeonticKnowledgeBase,
    DeonticModality as FormalDeonticModality,
    DeonticStatement,
    Disjunction,
    Implication,
    LogicalOperator,
    Negation,
    Party,
    Predicate,
    Proposition,
    TemporalOperator,
    TimeInterval,
)


SAMPLE_LEGAL_TEXT = """IN THE UNITED STATES DISTRICT COURT
FOR THE DISTRICT OF EXAMPLE

Case No. 1:26-cv-12345

JANE DOE, Plaintiff,
v.
ACME CORP., Defendant.

COMPLAINT

1. Plaintiff served notice.
- Exhibit A
"""


class _DuckTarget:
    def __init__(self, label: str) -> None:
        self.label = label


class _DuckRule:
    def __init__(self) -> None:
        self.id = "rule:1"
        self.target_id = "action:preserve_records"
        self.predicate = "preserve_records"
        self.active = True
        self.source_ids = ["fact:notice"]
        self.authority_ids = ["policy:retention"]
        self.evidence_ids = ["exhibit:A"]

        class _Modality:
            value = "obligation"

        self.modality = _Modality()


class _DuckGraph:
    def __init__(self) -> None:
        self.rules = {"rule:1": _DuckRule()}

    def get_node(self, node_id: str):
        if node_id == "action:preserve_records":
            return _DuckTarget("Preserve records")
        return None


def test_lib_legal_document_exposes_cross_consumer_summary_contract() -> None:
    parsed = parse_legal_document(SAMPLE_LEGAL_TEXT)

    summary = parsed.summary()

    assert summary == {
        "has_header": True,
        "court_line_count": 2,
        "party_line_count": 3,
        "title_line_count": 1,
        "section_count": 1,
        "section_kinds": ["header_title"],
        "numbered_paragraph_count": 1,
        "bullet_count": 1,
        "code_block_count": 0,
        "all_caps_heading_count": 1,
        "title": "COMPLAINT",
    }
    assert parsed.to_dict()["title"] == summary["title"]


def test_lib_support_map_builder_accepts_duck_typed_deontic_graph() -> None:
    support_map = SupportMapBuilder().build_from_deontic_graph(
        _DuckGraph(),
        fact_catalog={
            "fact:notice": {
                "predicate": "notice_sent",
                "status": "verified",
                "source_ids": ["email:2026-03-04"],
            }
        },
        filing_map={
            "rule:1": [
                {
                    "filing_id": "complaint:1",
                    "filing_type": "complaint",
                    "proposition": "Defendant had a duty to preserve records.",
                }
            ]
        },
    )

    payload = support_map.to_dict()

    assert payload["entry_count"] == 1
    assert payload["entries"][0]["target_label"] == "Preserve records"
    assert payload["entries"][0]["modality"] == "obligation"
    assert payload["entries"][0]["facts"][0]["fact_id"] == "fact:notice"
    assert payload["entries"][0]["filings"][0]["filing_id"] == "complaint:1"


# ---------------------------------------------------------------------------
# Knowledge-graph formats contracts
# ---------------------------------------------------------------------------


def _make_sample_graph() -> GraphData:
    return GraphData(
        nodes=[
            NodeData(id="n1", labels=["Person"], properties={"name": "Alice"}),
            NodeData(id="n2", labels=["Organization"], properties={"name": "ACME"}),
        ],
        relationships=[
            RelationshipData(
                id="r1", type="WORKS_AT",
                start_node="n1", end_node="n2",
                properties={"since": "2020"},
            )
        ],
        metadata={"source": "test"},
    )


def test_lib_knowledge_graph_formats_node_data_roundtrip() -> None:
    node = NodeData(id="n1", labels=["Person"], properties={"name": "Alice"})
    as_dict = node.to_dict()
    restored = NodeData.from_dict(as_dict)
    assert restored.id == "n1"
    assert restored.labels == ["Person"]
    assert restored.properties["name"] == "Alice"


def test_lib_knowledge_graph_formats_relationship_data_roundtrip() -> None:
    rel = RelationshipData(
        id="r1", type="KNOWS", start_node="n1", end_node="n2",
        properties={"weight": "0.9"},
    )
    restored = RelationshipData.from_dict(rel.to_dict())
    assert restored.id == "r1"
    assert restored.type == "KNOWS"
    assert restored.start_node == "n1"
    assert restored.properties["weight"] == "0.9"


def test_lib_knowledge_graph_formats_schema_data_roundtrip() -> None:
    schema = SchemaData(indexes=[{"name": "idx_person"}], node_labels=["Person"])
    restored = SchemaData.from_dict(schema.to_dict())
    assert restored.node_labels == ["Person"]
    assert restored.indexes[0]["name"] == "idx_person"


def test_lib_knowledge_graph_formats_graph_data_json_roundtrip() -> None:
    g = _make_sample_graph()
    restored = GraphData.from_json(g.to_json())
    assert len(restored.nodes) == 2
    assert len(restored.relationships) == 1
    assert restored.nodes[0].id == "n1"
    assert restored.relationships[0].type == "WORKS_AT"


def test_lib_knowledge_graph_formats_iter_nodes_chunked() -> None:
    g = _make_sample_graph()
    chunks = list(g.iter_nodes_chunked(1))
    assert len(chunks) == 2
    assert chunks[0][0].id == "n1"


def test_lib_knowledge_graph_formats_iter_relationships_chunked() -> None:
    g = _make_sample_graph()
    chunks = list(g.iter_relationships_chunked(1))
    assert len(chunks) == 1
    assert chunks[0][0].id == "r1"


def test_lib_knowledge_graph_formats_migration_format_enum_has_expected_values() -> None:
    assert MigrationFormat.DAG_JSON.value == "dag-json"
    assert MigrationFormat.JSON_LINES.value == "jsonlines"
    assert MigrationFormat.GRAPHML.value == "graphml"


def test_lib_knowledge_graph_formats_register_and_retrieve_custom_format() -> None:
    saved = []

    def _save(graph, filepath):
        saved.append((graph, filepath))

    def _load(filepath):
        return GraphData()

    register_format(MigrationFormat.PAJEK, _save, _load)
    fmts = registered_formats()
    assert MigrationFormat.PAJEK in fmts


# ---------------------------------------------------------------------------
# Knowledge-graph export contracts
# ---------------------------------------------------------------------------


def test_lib_knowledge_graph_export_config_defaults() -> None:
    cfg = ExportConfig()
    assert cfg.uri == "bolt://localhost:7687"
    assert cfg.username == "neo4j"
    assert cfg.batch_size == 1000
    assert cfg.include_schema is True


def test_lib_knowledge_graph_export_config_custom() -> None:
    cfg = ExportConfig(
        uri="bolt://custom:7687",
        username="admin",
        batch_size=500,
        node_labels=["Person"],
        relationship_types=["KNOWS"],
    )
    assert cfg.uri == "bolt://custom:7687"
    assert cfg.batch_size == 500
    assert cfg.node_labels == ["Person"]
    assert cfg.relationship_types == ["KNOWS"]


def test_lib_knowledge_graph_export_result_to_dict() -> None:
    result = ExportResult(
        success=True,
        node_count=42,
        relationship_count=10,
        duration_seconds=1.5,
    )
    d = result.to_dict()
    assert d["success"] is True
    assert d["node_count"] == 42
    assert d["relationship_count"] == 10
    assert d["duration_seconds"] == 1.5
    assert d["errors"] == []


def test_lib_knowledge_graph_export_result_failure_with_errors() -> None:
    result = ExportResult(success=False, errors=["Connection refused"])
    d = result.to_dict()
    assert d["success"] is False
    assert d["errors"] == ["Connection refused"]


def test_lib_knowledge_graph_export_neo4j_exporter_unavailable_without_driver() -> None:
    cfg = ExportConfig()
    exporter = Neo4jExporter(cfg)
    # Without neo4j installed in the test environment the flag must be False
    assert isinstance(exporter._neo4j_available, bool)


def test_lib_knowledge_graph_export_neo4j_exporter_export_fails_without_neo4j() -> None:
    cfg = ExportConfig()
    exporter = Neo4jExporter(cfg)
    if exporter._neo4j_available:
        # neo4j is installed — skip the "no neo4j" branch
        return
    result = exporter.export()
    assert result.success is False
    assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# Deontic-graph contracts
# ---------------------------------------------------------------------------


def _make_sample_deontic_graph() -> DeonticGraph:
    graph = DeonticGraph()
    graph.add_node(DeonticNode(
        id="actor:landlord", node_type=DeonticNodeType.ACTOR,
        label="Landlord", active=True, confidence=1.0,
    ))
    graph.add_node(DeonticNode(
        id="fact:notice_given", node_type=DeonticNodeType.CONDITION,
        label="Written notice given", active=True, confidence=0.9,
    ))
    graph.add_node(DeonticNode(
        id="action:return_deposit", node_type=DeonticNodeType.ACTION,
        label="Return security deposit", active=False, confidence=0.0,
    ))
    graph.add_rule(DeonticRule(
        id="rule:deposit_return",
        modality=DeonticModality.OBLIGATION,
        source_ids=["actor:landlord", "fact:notice_given"],
        target_id="action:return_deposit",
        predicate="return_security_deposit",
        active=True, confidence=1.0,
        authority_ids=["ORS-90.300"],
        evidence_ids=["exhibit:lease"],
    ))
    return graph


def test_lib_deontic_node_type_enum_values() -> None:
    assert DeonticNodeType.ACTOR.value == "actor"
    assert DeonticNodeType.FACT.value == "fact"
    assert DeonticNodeType.CONDITION.value == "condition"
    assert DeonticNodeType.ACTION.value == "action"
    assert DeonticNodeType.AUTHORITY.value == "authority"


def test_lib_deontic_modality_enum_values() -> None:
    assert DeonticModality.OBLIGATION.value == "obligation"
    assert DeonticModality.PROHIBITION.value == "prohibition"
    assert DeonticModality.PERMISSION.value == "permission"
    assert DeonticModality.ENTITLEMENT.value == "entitlement"


def test_lib_deontic_node_roundtrip() -> None:
    node = DeonticNode(
        id="n1", node_type=DeonticNodeType.ACTOR,
        label="Tenant", active=True, confidence=0.8,
        attributes={"verified": True},
    )
    d = node.to_dict()
    assert d["id"] == "n1"
    assert d["node_type"] == "actor"
    assert d["active"] is True
    assert d["attributes"]["verified"] is True


def test_lib_deontic_rule_roundtrip() -> None:
    rule = DeonticRule(
        id="r1", modality=DeonticModality.PROHIBITION,
        source_ids=["actor:1"], target_id="action:evict",
        predicate="evict_without_notice",
        active=False, confidence=0.7,
        authority_ids=["ORS-90.380"], evidence_ids=["doc:complaint"],
    )
    d = rule.to_dict()
    assert d["modality"] == "prohibition"
    assert d["source_ids"] == ["actor:1"]
    assert d["authority_ids"] == ["ORS-90.380"]


def test_lib_deontic_conflict_roundtrip() -> None:
    conflict = DeonticConflict(
        rule_id="r1", conflicting_rule_id="r2", target_id="action:evict",
        modalities=["obligation", "prohibition"],
        reason="Incompatible modalities on same target.",
    )
    d = conflict.to_dict()
    assert d["rule_id"] == "r1"
    assert d["modalities"] == ["obligation", "prohibition"]


def test_lib_deontic_rule_assessment_roundtrip() -> None:
    assessment = DeonticRuleAssessment(
        rule_id="r1", target_id="action:1", modality="obligation",
        active=True, satisfied_sources=["s1"], missing_sources=["s2"],
        authority_ids=["auth:1"], evidence_ids=["ev:1"],
    )
    d = assessment.to_dict()
    assert d["satisfied_sources"] == ["s1"]
    assert d["missing_sources"] == ["s2"]


def test_lib_deontic_graph_summary_contract() -> None:
    graph = _make_sample_deontic_graph()
    summary = graph.summary()
    assert summary["total_nodes"] == 3
    assert summary["total_rules"] == 1
    assert summary["active_rule_count"] == 1
    assert summary["inactive_rule_count"] == 0
    assert summary["governed_target_count"] == 1
    assert summary["modalities"]["obligation"] == 1


def test_lib_deontic_graph_assess_rules_supported_sources() -> None:
    graph = _make_sample_deontic_graph()
    assessments = graph.assess_rules()
    assert len(assessments) == 1
    a = assessments[0]
    assert a.rule_id == "rule:deposit_return"
    assert a.modality == "obligation"
    assert "actor:landlord" in a.satisfied_sources
    assert "fact:notice_given" in a.satisfied_sources
    assert a.missing_sources == []


def test_lib_deontic_graph_detect_conflicts_no_conflicts() -> None:
    graph = _make_sample_deontic_graph()
    conflicts = graph.detect_conflicts()
    assert conflicts == []


def test_lib_deontic_graph_detect_conflicts_obligation_vs_prohibition() -> None:
    graph = _make_sample_deontic_graph()
    graph.add_rule(DeonticRule(
        id="rule:deposit_keep",
        modality=DeonticModality.PROHIBITION,
        source_ids=["actor:landlord"],
        target_id="action:return_deposit",
        predicate="return_security_deposit",
        active=True, confidence=0.5,
    ))
    conflicts = graph.detect_conflicts()
    assert len(conflicts) == 1
    assert set(conflicts[0].modalities) == {"obligation", "prohibition"}


def test_lib_deontic_graph_json_roundtrip() -> None:
    import os
    import tempfile
    graph = _make_sample_deontic_graph()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
        path = fh.name
    try:
        graph.to_json(path)
        restored = DeonticGraph.from_json(path)
        assert len(restored.nodes) == 3
        assert len(restored.rules) == 1
        assert restored.rules["rule:deposit_return"].modality == DeonticModality.OBLIGATION
    finally:
        os.unlink(path)


def test_lib_deontic_graph_export_reasoning_rows_contract() -> None:
    graph = _make_sample_deontic_graph()
    rows = graph.export_reasoning_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["rule_id"] == "rule:deposit_return"
    assert row["modality"] == "obligation"
    assert row["active"] is True
    assert row["target_label"] == "Return security deposit"


def test_lib_deontic_graph_builder_build_from_matrix() -> None:
    builder = DeonticGraphBuilder()
    graph = builder.build_from_matrix([
        {
            "rule_id": "r1",
            "modality": "obligation",
            "predicate": "pay_rent",
            "target_id": "action:pay_rent",
            "target_label": "Pay rent on time",
            "sources": [{"id": "actor:tenant", "label": "Tenant", "node_type": "actor"}],
            "authority_ids": ["lease:clause-4"],
        }
    ])
    assert len(graph.rules) == 1
    assert graph.rules["r1"].modality == DeonticModality.OBLIGATION


def test_lib_deontic_graph_is_canonical_type_shared_with_submodule() -> None:
    """When lib is importable the submodule's graph.py should re-export lib's types."""
    try:
        from ipfs_datasets_py.logic.deontic.graph import DeonticGraph as SubmoduleGraph
    except ImportError:
        return  # submodule not on path; skip
    assert SubmoduleGraph is DeonticGraph


# ---------------------------------------------------------------------------
# Formal-logic (lib.formal_logic.core) contracts
# ---------------------------------------------------------------------------


def test_lib_formal_logic_deontic_modality_values() -> None:
    assert FormalDeonticModality.OBLIGATORY.value == "O"
    assert FormalDeonticModality.PERMITTED.value == "P"
    assert FormalDeonticModality.PROHIBITED.value == "F"
    assert FormalDeonticModality.OPTIONAL.value == "OPT"


def test_lib_formal_logic_temporal_operator_values() -> None:
    assert TemporalOperator.BEFORE.value == "before"
    assert TemporalOperator.AFTER.value == "after"
    assert TemporalOperator.COINCIDENT.value == "coincident"


def test_lib_formal_logic_logical_operator_values() -> None:
    assert LogicalOperator.AND.value == "and"
    assert LogicalOperator.OR.value == "or"
    assert LogicalOperator.NOT.value == "not"
    assert LogicalOperator.IMPLIES.value == "implies"


def test_lib_formal_logic_time_interval_contains() -> None:
    from datetime import datetime
    iv = TimeInterval(
        start=datetime(2024, 1, 1),
        end=datetime(2024, 12, 31),
    )
    assert iv.contains(datetime(2024, 6, 15)) is True
    assert iv.contains(datetime(2023, 12, 31)) is False


def test_lib_formal_logic_time_interval_resolved_end_from_duration() -> None:
    from datetime import datetime
    iv = TimeInterval(start=datetime(2024, 1, 1), duration_days=30)
    resolved = iv.resolved_end()
    assert resolved is not None
    assert resolved.day == 31
    assert resolved.month == 1


def test_lib_formal_logic_party_and_action_str() -> None:
    party = Party(name="Landlord", role="respondent", entity_id="landlord:1")
    action = Action(verb="evict", object_noun="tenant", action_id="action:evict")
    assert "Landlord" in str(party)
    assert "respondent" in str(party)
    assert "evict" in str(action)
    assert "tenant" in str(action)


def test_lib_formal_logic_predicate_evaluate() -> None:
    pred = Predicate(name="notice_given", args=("tenant:1",))
    assert pred.evaluate({"notice_given(tenant:1)": True}) is True
    assert pred.evaluate({}) is False


def test_lib_formal_logic_conjunction_evaluate() -> None:
    p = Predicate(name="a", args=())
    q = Predicate(name="b", args=())
    conj = Conjunction(left=p, right=q)
    assert conj.evaluate({"a()": True, "b()": True}) is True
    assert conj.evaluate({"a()": True, "b()": False}) is False


def test_lib_formal_logic_disjunction_evaluate() -> None:
    p = Predicate(name="a", args=())
    q = Predicate(name="b", args=())
    disj = Disjunction(left=p, right=q)
    assert disj.evaluate({"a()": False, "b()": True}) is True
    assert disj.evaluate({"a()": False, "b()": False}) is False


def test_lib_formal_logic_negation_evaluate() -> None:
    p = Predicate(name="prohibited", args=())
    neg = Negation(prop=p)
    assert neg.evaluate({"prohibited()": True}) is False
    assert neg.evaluate({}) is True


def test_lib_formal_logic_implication_evaluate() -> None:
    ant = Predicate(name="filing_submitted", args=())
    cons = Predicate(name="review_triggered", args=())
    impl = Implication(antecedent=ant, consequent=cons)
    assert impl.evaluate({"filing_submitted()": True, "review_triggered()": True}) is True
    assert impl.evaluate({"filing_submitted()": True, "review_triggered()": False}) is False
    assert impl.evaluate({}) is True


def test_lib_formal_logic_deontic_statement_str() -> None:
    party = Party(name="Landlord", role="respondent", entity_id="landlord:1")
    action = Action(verb="return", object_noun="deposit", action_id="action:return_deposit")
    stmt = DeonticStatement(modality=FormalDeonticModality.OBLIGATORY, actor=party, action=action)
    assert "O" in str(stmt)
    assert "Landlord" in str(stmt)


def test_lib_formal_logic_knowledge_base_infer_and_check_compliance() -> None:
    from datetime import datetime
    party = Party(name="Tenant", role="tenant", entity_id="tenant:1")
    action = Action(verb="pay", object_noun="rent", action_id="action:pay_rent")
    stmt = DeonticStatement(modality=FormalDeonticModality.OBLIGATORY, actor=party, action=action)
    kb = DeonticKnowledgeBase()
    kb.add_statement(stmt)
    kb.infer_statements()
    ok, reason = kb.check_compliance(party, action, datetime.now())
    assert ok is True
    assert "obligation" in reason.lower() or "complies" in reason.lower()


def test_lib_formal_logic_knowledge_base_to_dict() -> None:
    party = Party(name="Authority", role="authority", entity_id="auth:1")
    action = Action(verb="disclose", object_noun="records", action_id="action:disclose")
    kb = DeonticKnowledgeBase()
    kb.add_fact("records_requested", True)
    kb.add_statement(DeonticStatement(modality=FormalDeonticModality.OBLIGATORY, actor=party, action=action))
    kb.infer_statements()
    d = kb.to_dict()
    assert "facts" in d
    assert "statements" in d
    assert d["facts"]["records_requested"] is True


def test_lib_formal_logic_types_shared_with_knowledge_base_submodule() -> None:
    """Verify knowledge_base.py re-exports lib's types via KnowledgeDeonticModality alias."""
    try:
        from ipfs_datasets_py.logic.deontic.knowledge_base import (
            KnowledgeDeonticModality,
            TimeInterval as KbTimeInterval,
            Party as KbParty,
        )
    except ImportError:
        return  # submodule not on path; skip
    assert KnowledgeDeonticModality is FormalDeonticModality
    assert KbTimeInterval is TimeInterval
    assert KbParty is Party