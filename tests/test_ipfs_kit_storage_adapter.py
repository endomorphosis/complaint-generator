from unittest.mock import patch

from integrations.ipfs_datasets.storage import pin_cid, retrieve_bytes, store_bytes, translate_kit_operation_result


class _FakeKit:
    def __init__(self):
        self.blobs = {}

    def add_bytes(self, data, pin=True):
        cid = "bafykit"
        self.blobs[cid] = bytes(data)
        return {"success": True, "resulting_content_cid": cid, "pinned": pin}

    def cat(self, cid):
        return self.blobs[cid]

    def pin(self, cid):
        return {"success": True, "cid": cid}


def test_translate_kit_operation_result_reads_resulting_content_cid():
    translated = translate_kit_operation_result(
        {"success": True, "resulting_content_cid": "bafykit"},
        backend_name="kit",
    )
    assert translated["status"] == "available"
    assert translated["cid"] == "bafykit"
    assert translated["backend_name"] == "kit"


def test_store_retrieve_and_pin_roundtrip_on_fake_kit():
    backend = _FakeKit()
    stored = store_bytes(b"evidence bytes", backend=backend, backend_name="kit")
    assert stored["status"] == "available"
    assert stored["backend_name"] == "kit"
    assert stored["cid"] == "bafykit"
    retrieved = retrieve_bytes("bafykit", backend=backend, backend_name="kit")
    assert retrieved["data"] == b"evidence bytes"
    pinned = pin_cid("bafykit", backend=backend, backend_name="kit")
    assert pinned["backend_name"] == "kit"
    assert pinned["pinned"] is True


def test_store_bytes_uses_local_cache_when_kit_and_datasets_router_are_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPLAINT_GENERATOR_IPFS_CACHE_DIR", str(tmp_path / "ipfs-cache"))
    with patch("integrations.ipfs_datasets.storage._load_optional_kit_backend", return_value=None):
        with patch("integrations.ipfs_datasets.storage.add_bytes", None):
            stored = store_bytes(b"local evidence")
    assert stored["backend_name"] == "local_cache"
    assert stored["status"] == "degraded"
    assert stored["cid"]
    with patch("integrations.ipfs_datasets.storage._load_optional_kit_backend", return_value=None):
        with patch("integrations.ipfs_datasets.storage.cat", None):
            retrieved = retrieve_bytes(stored["cid"])
    assert retrieved["backend_name"] == "local_cache"
    assert retrieved["data"] == b"local evidence"
