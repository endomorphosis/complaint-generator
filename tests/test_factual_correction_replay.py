"""Client reopen keeps graph revisions, and private graphs stay sealed."""

from __future__ import annotations

import hashlib
import os

import pytest

from applications.complaint_workspace import WorkspaceAccess
from integrations.ipfs_datasets import graphs
from integrations.private_storage import ENVELOPE_MAGIC


pytestmark = pytest.mark.usefixtures("reset_graph_client")


@pytest.fixture
def reset_graph_client(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPLAINT_GENERATOR_GRAPH_CATALOG", str(tmp_path))
    monkeypatch.setattr(graphs, "_GRAPH_CLIENT", None)
    monkeypatch.setattr(graphs, "_GRAPH_CLIENT_VERSIONS", {})
    monkeypatch.setattr(graphs, "_GRAPH_SNAPSHOT_REGISTRY", {})
    yield
    client = graphs._GRAPH_CLIENT
    if client is not None:
        client.close()
        graphs._GRAPH_CLIENT = None


def _payload(name: str) -> dict:
    return {
        "source_id": "statement-1",
        "entities": [
            {
                "id": "fact-1",
                "type": "person",
                "name": name,
                "provenance": {"source_id": "statement-1", "statement": name},
            },
            {"id": "rule-1", "type": "legal_requirement", "name": "Element A"},
        ],
        "relationships": [
            {
                "id": "link-1",
                "type": "support_link",
                "link_type": "support_link",
                "from": "fact-1",
                "to": "rule-1",
                "factual_assertion_id": "fact-1",
                "rule_id": "rule-1",
                "provenance": {"source_id": "statement-1", "chain": "fact-to-rule"},
            }
        ],
    }


def _reopen(monkeypatch, tmp_path):
    client = graphs._GRAPH_CLIENT
    if client is not None:
        client.close()
    monkeypatch.setattr(graphs, "_GRAPH_CLIENT", None)
    monkeypatch.setattr(graphs, "_GRAPH_SNAPSHOT_REGISTRY", {})
    os.environ["COMPLAINT_GENERATOR_GRAPH_CATALOG"] = str(tmp_path)


def test_client_reopen_keeps_same_count_change_and_idempotent_retry(monkeypatch, tmp_path):
    graph_id = "graph:factual-replay"
    first = graphs.persist_graph_snapshot(_payload("Original worker"), graph_id=graph_id)
    assert first["metadata"]["client_write_ok"] is True
    second = graphs.persist_graph_snapshot(_payload("Updated worker"), graph_id=graph_id)
    assert second["metadata"]["client_write_ok"] is True
    assert second["node_count"] == first["node_count"] == 2
    retry = graphs.persist_graph_snapshot(_payload("Updated worker"), graph_id=graph_id)
    assert retry["metadata"]["client_write_ok"] is True
    assert retry["metadata"]["idempotent_retry"] is True

    module_client = graphs._GRAPH_CLIENT
    client_id = "graph-" + hashlib.sha256(graph_id.encode()).hexdigest()[:48]
    target = module_client._service.catalog.get_graph("complaint-generator", client_id)
    assert target.graph_id == client_id
    _reopen(monkeypatch, tmp_path)
    from integrations.ipfs_datasets.loader import import_module_optional

    module, error = import_module_optional("ipfs_datasets_py.knowledge_graphs")
    assert module is not None and error is None
    with module.Client.open(tmp_path / "catalog", storage_path=tmp_path / "store") as reopened:
        queried = reopened.query(
            module.GraphTarget(tenant="complaint-generator", graph_id=client_id, branch="main"),
            params={"language": "scan"},
        )
    assert queried.ok, getattr(queried, "error", None)
    rows = {tuple(row[:3]) for row in queried.result["rows"]}
    assert ("fact-1", "person", "Updated worker") in rows
    assert ("rule-1", "legal_requirement", "Element A") in rows
    assert len(queried.result["rows"]) == 2

    resumed = graphs.resume_graph_revisions(graph_id)
    assert resumed["revision_count"] >= 2
    assert any(item.get("name") == "Original worker" for item in resumed["superseded_facts"])
    assert any(item.get("statement") == "Updated worker" for item in resumed["provenance"])
    assert any(item.get("chain") == "fact-to-rule" for item in resumed["provenance"])
    assert any(item.get("rule_id") == "rule-1" for item in resumed["cross_graph_links"])
    assert resumed["plaintext_publication"] is False


def test_claim_hook_resume_matches_client_revisions(monkeypatch, tmp_path):
    from mediator.claim_support_hooks import ClaimSupportHook

    class _Mediator:
        def log(self, *args, **kwargs):
            return None

    graph_id = "graph:hook-replay"
    graphs.persist_graph_snapshot(_payload("First fact"), graph_id=graph_id)
    graphs.persist_graph_snapshot(_payload("Corrected fact"), graph_id=graph_id)
    _reopen(monkeypatch, tmp_path)
    hook = ClaimSupportHook(_Mediator(), db_path=str(tmp_path / "unused.duckdb"))
    resumed = hook.resume_factual_graph(graph_id)
    assert resumed["available"] is True
    assert resumed["revision_count"] >= 2
    assert any(item.get("name") == "First fact" for item in resumed["superseded_facts"])
    assert resumed["cross_graph_links"]
    assert resumed["plaintext_publication"] is False


class _HermeticBytes:
    measurement_label = "measured-hermetic"

    def __init__(self):
        self.blobs = {}
        self.seen = []

    def add_bytes(self, data, pin=True):
        del pin
        blob = bytes(data)
        self.seen.append(blob)
        cid = "bafyhermetic" + hashlib.sha256(blob).hexdigest()[:16]
        self.blobs[cid] = blob
        return {"success": True, "cid": cid, "pinned": False}

    def cat(self, cid):
        return self.blobs[cid]

    def pin(self, cid):
        return {"success": True, "cid": cid, "pinned": True}


def test_private_graph_materials_are_sealed_before_replication():
    from mediator.claim_support_hooks import ClaimSupportHook

    class _Mediator:
        def log(self, *args, **kwargs):
            return None

    replicated = []
    backend = _HermeticBytes()
    sentinel_source = "SENTINEL-SOURCE-fact05"
    sentinel_embedding = "SENTINEL-EMBEDDING-fact05"
    sentinel_index = "SENTINEL-INDEX-fact05"
    payload = {
        "entities": [{"id": "fact-1", "name": "Synthetic worker"}],
        "relationships": [],
        "source_text": sentinel_source,
        "embeddings": [{"vector": [0.1, 0.2], "text": sentinel_embedding}],
        "indexes": {"posts": [sentinel_index]},
    }
    context = {
        "access": WorkspaceAccess.authenticated("tenant-a", case_id="case-a"),
        "tenant_id": "tenant-a",
        "case_id": "case-a",
        "principal_id": "tenant-a",
        "key": bytes(range(32)),
        "key_id": "case-key-a",
        "backend": backend,
        "backend_name": "measured-hermetic",
        "pin_content": True,
        "replicate": replicated.append,
        "publish_plaintext": True,
    }
    hook = ClaimSupportHook(_Mediator(), db_path=":memory:")
    result = hook.persist_private_factual_graph(payload, context, graph_id="graph:private")
    assert result["persisted"] is True
    assert result["plaintext_publication"] is False
    assert result["plaintext_catalog"] is False
    assert replicated, "replication must observe sealed envelopes"
    for blob in replicated:
        assert blob.startswith(ENVELOPE_MAGIC)
        assert sentinel_source.encode() not in blob
        assert sentinel_embedding.encode() not in blob
        assert sentinel_index.encode() not in blob
    for blob in backend.seen:
        assert sentinel_source.encode() not in blob
        assert sentinel_embedding.encode() not in blob
        assert sentinel_index.encode() not in blob
