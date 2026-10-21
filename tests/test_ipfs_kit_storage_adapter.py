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


def test_pseudo_cid_is_not_network_pinned(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPLAINT_GENERATOR_IPFS_CACHE_DIR", str(tmp_path / "ipfs-cache"))
    with patch("integrations.ipfs_datasets.storage._load_optional_kit_backend", return_value=None):
        with patch("integrations.ipfs_datasets.storage.add_bytes", None):
            stored = store_bytes(b"local evidence", pin_content=True)
    assert stored["cid_kind"] == "pseudo_cid"
    assert stored["stored_local"] is True
    assert stored["pinned"] is False
    assert stored["uploaded"] is False
    assert stored["network_durable"] is False
    assert stored["replicated"] is False


def test_pin_failure_is_not_reported_as_pinned():
    class _PinFails:
        measurement_label = "measured-hermetic"

        def __init__(self):
            self.blobs = {}

        def add_bytes(self, data, pin=True):
            del pin
            self.blobs["bafymeasuredhermeticvalue"] = bytes(data)
            return {"success": True, "cid": "bafymeasuredhermeticvalue", "pinned": False}

        def cat(self, cid):
            return self.blobs[cid]

        def pin(self, cid):
            raise RuntimeError(f"pin rejected {cid}")

    stored = store_bytes(b"evidence bytes", backend=_PinFails(), backend_name="kit")
    assert stored["cid"] == "bafymeasuredhermeticvalue"
    assert stored["pinned"] is False
    assert stored["verified"] is True
    assert stored["measurement"] == "measured-hermetic"
    assert stored["network_durable"] is False
    assert stored["status"] == "available"


def test_readback_mismatch_is_not_verified():
    class _Mismatch:
        measurement_label = "measured-hermetic"

        def add_bytes(self, data, pin=True):
            del data, pin
            return {"success": True, "cid": "bafymismatchcid", "pinned": True}

        def cat(self, cid):
            del cid
            return b"other-bytes"

    stored = store_bytes(b"evidence bytes", backend=_Mismatch(), backend_name="kit")
    assert stored["verified"] is False
    assert stored["verification"]["matched"] is False
    assert stored["network_durable"] is False
    assert stored["pinned"] is True


def test_malformed_and_offline_results_stay_unpinned():
    class _Malformed:
        measurement_label = "measured-hermetic"

        def add_bytes(self, data, pin=True):
            del data, pin
            return 5

    malformed = store_bytes(b"evidence bytes", backend=_Malformed(), backend_name="kit")
    assert malformed["status"] == "error"
    assert malformed["pinned"] is False
    assert malformed["network_durable"] is False

    class _Offline:
        def add_bytes(self, data, pin=True):
            del data, pin
            raise ConnectionError("ipfs daemon offline")

    offline = store_bytes(b"evidence bytes", backend=_Offline(), backend_name="kit")
    assert offline["status"] == "error"
    assert offline["pinned"] is False
    assert offline["uploaded"] is False


def test_service_router_uses_declared_operations_not_add_bytes():
    class _Definition:
        def __init__(self, operation_id):
            self.operation_id = operation_id
            self.aliases = ()

    class _Registry:
        def __init__(self):
            self._ops = (
                _Definition("storage.ipfs.add"),
                _Definition("storage.ipfs.cat"),
            )

        def operations(self):
            return self._ops

    class _Router:
        measurement_label = "measured-hermetic"

        def __init__(self):
            self.registry = _Registry()
            self.blobs = {}
            self.calls = []

        def dispatch(self, operation, request, context=None):
            del context
            self.calls.append(operation)
            if operation == "storage.ipfs.add":
                cid = "bafyroutercid"
                self.blobs[cid] = bytes(request["data"])
                return {"success": True, "cid": cid, "pinned": False}
            if operation == "storage.ipfs.cat":
                return self.blobs[request["cid"]]
            raise AssertionError(operation)

    router = _Router()
    stored = store_bytes(b"routed", backend=router, backend_name="kit", pin_content=True)
    assert stored["calls"] if False else stored["cid"] == "bafyroutercid"
    assert stored["pinned"] is False
    assert stored["verified"] is True
    assert stored["receipt"]["pin_evidence"] == "pin_call_failed"
    assert "storage.ipfs.add" in router.calls
    assert "storage.ipfs.pin" not in router.calls
    assert all(call in {"storage.ipfs.add", "storage.ipfs.cat"} for call in router.calls)


def test_execute_protocol_is_not_called_as_byte_api():
    class _Protocol:
        def execute(self, operation, request, context):
            raise AssertionError("execute must go through ServiceRouter.dispatch")

    stored = store_bytes(b"nope", backend=_Protocol(), backend_name="kit")
    assert stored["pinned"] is False
    assert stored["status"] in {"error", "deferred"}
    assert "ServiceRouter" in stored["error"]


def test_import_and_probe_do_not_construct_kit(monkeypatch):
    import integrations.ipfs_datasets.storage as storage

    monkeypatch.delenv("COMPLAINT_GENERATOR_ENABLE_IPFS_KIT", raising=False)
    calls = []

    def _explode(*_args, **_kwargs):
        calls.append("import")
        raise AssertionError("kit import during disabled probe")

    monkeypatch.setattr(storage, "import_attr_optional", _explode)
    assert storage._load_optional_kit_backend() is None
    assert calls == []


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
