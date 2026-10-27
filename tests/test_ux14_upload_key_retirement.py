"""Cached upload responses remain subject to the actual case key owner."""
from fastapi.testclient import TestClient
import pytest

from tests.test_cimp_ux_14 import _ready, _upload, _post, _composed_headers, _composed_login, ORIGINAL

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.mark.parametrize("operation", ["status", "complete", "retry"])
@pytest.mark.parametrize("retirement", ["before_request", "after_worker"])
def test_sealed_upload_does_not_disclose_cached_evidence_after_key_lock(tmp_path, monkeypatch, operation, retirement):
    from applications import evidence_workspace_api as api
    world, backend = _ready(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        _, _, sealed = _upload(client, world.case, csrf)
        body = {"tenant_id": world.case.tenant_id, "case_id": world.case.case_id,
            "resource_id": world.case.resource_id, "expected_revision": world.case.revision,
            "upload_id": sealed["upload_id"], "upload_generation": sealed["upload_generation"]}
        def invoke():
            path = "/api/cases/evidence/uploads/" + operation
            if operation == "status":
                return client.get(path, headers=_composed_headers(world.case, csrf), params=body)
            return _post(client, path, world.case, csrf, body)
        visible = invoke()
        assert visible.status_code == 200
        assert visible.json()["evidence"]["original_filename"] == ORIGINAL
        before = dict(backend._blobs)
        if retirement == "before_request":
            assert world.owner_keys.lock()["unlocked"] is False
        else:
            actual = api.run_in_threadpool
            async def retire_after_actual_worker(function, *args, **kwargs):
                result = await actual(function, *args, **kwargs)
                if function.__name__ == "_upload_" + operation or function.__name__ == "_" + operation + "_upload":
                    assert result["evidence"]["original_filename"] == ORIGINAL
                    assert world.owner_keys.lock()["unlocked"] is False
                return result
            monkeypatch.setattr(api, "run_in_threadpool", retire_after_actual_worker)
        denied = invoke()
        assert world.owner_keys.unlocked is False
        assert denied.status_code == 503
        assert denied.json()["error"] == "key_unavailable"
        assert denied.json()["operation_succeeded"] is False
        assert denied.json()["items"] == []
        assert "evidence_id" not in denied.json() and ORIGINAL not in denied.text
        assert backend._blobs == before
