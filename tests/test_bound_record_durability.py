"""Private record durability comes from the actual Kit storage producer."""
from __future__ import annotations

import pytest

from applications.evidence_annotation_store import EvidenceAnnotationStore
from tests.test_cimp_ux_57 import KEY, SECRET, _binding

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


class _VolatileEchoBackend:
    """Adversarial byte echo, deliberately without a durable storage producer."""
    provider_id = "memory-only"
    failure_domain = "same-process"

    def __init__(self):
        self.objects = {}
        self.calls = 0

    def put(self, name, payload):
        self.calls += 1
        self.objects[name] = bytes(payload)
        return {"state": "queued"}

    def get(self, name):
        self.calls += 1
        return self.objects[name]


def test_queued_memory_echo_cannot_qualify_remote_durability(tmp_path):
    backend = _VolatileEchoBackend()
    store = EvidenceAnnotationStore(tmp_path / "records")
    receipt = store.put_evidence(record_id="echo-record", plaintext=SECRET,
        binding=_binding("evidence"), key=KEY, key_id="key-echo", remote_backend=backend)
    assert receipt["local_durable"] is True
    assert receipt["remote_durable"] is False
    assert receipt["counts_toward_desired"] is False
    assert store.read(record_id="echo-record", binding=_binding("evidence"), key=KEY) == SECRET
