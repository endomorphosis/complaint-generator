"""Durable private evidence, annotations, classification revisions, and links.

Records are sealed with the caller's case key and Kit authenticated encryption.
A content hash is not ciphertext. A queued or local write is not remote
durability. Missing keys and failed readback stay failures.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from integrations.private_collaboration import commit_linkage_record
from integrations.private_storage import (
    BoundPrivateRecordError,
    PrivateArtifactBinding,
    commit_private_bound_record,
    open_private_bound_record,
    recover_private_bound_records,
    stage_interrupted_bound_record,
)


class EvidenceAnnotationStore:
    """Case-scoped store for the four private evidence record kinds."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def put_evidence(
        self,
        *,
        record_id: str,
        plaintext: bytes,
        binding: PrivateArtifactBinding,
        key: bytes,
        key_id: str,
        remote_backend: Any | None = None,
    ) -> dict[str, Any]:
        self._require_kind(binding, "evidence")
        return commit_private_bound_record(
            self._root,
            record_id=record_id,
            kind="evidence",
            plaintext=plaintext,
            binding=binding,
            key=key,
            key_id=key_id,
            remote_backend=remote_backend,
        )

    def put_annotation(
        self,
        *,
        record_id: str,
        evidence_id: str,
        note: str,
        binding: PrivateArtifactBinding,
        key: bytes,
        key_id: str,
        remote_backend: Any | None = None,
    ) -> dict[str, Any]:
        self._require_kind(binding, "annotation")
        self._label(evidence_id, "evidence_id_rejected")
        if not isinstance(note, str) or not note.strip() or len(note) > 4000:
            raise BoundPrivateRecordError("annotation_rejected")
        body = json.dumps(
            {"kind": "annotation", "evidence_id": evidence_id, "note": note},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return commit_private_bound_record(
            self._root,
            record_id=record_id,
            kind="annotation",
            plaintext=body,
            binding=binding,
            key=key,
            key_id=key_id,
            remote_backend=remote_backend,
        )

    def revise_classification(
        self,
        *,
        record_id: str,
        label: str,
        previous_revision: str,
        binding: PrivateArtifactBinding,
        key: bytes,
        key_id: str,
        remote_backend: Any | None = None,
    ) -> dict[str, Any]:
        self._require_kind(binding, "classification_revision")
        self._label(label, "classification_rejected")
        self._label(previous_revision, "classification_rejected")
        if previous_revision == binding.revision:
            raise BoundPrivateRecordError("classification_revision_unchanged")
        body = json.dumps(
            {
                "kind": "classification_revision",
                "label": label,
                "previous_revision": previous_revision,
                "revision": binding.revision,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return commit_private_bound_record(
            self._root,
            record_id=record_id,
            kind="classification_revision",
            plaintext=body,
            binding=binding,
            key=key,
            key_id=key_id,
            remote_backend=remote_backend,
        )

    def link(
        self,
        *,
        record_id: str,
        actor_principal_id: str,
        evidence_id: str,
        annotation_id: str,
        binding: PrivateArtifactBinding,
        key: bytes,
        key_id: str,
        remote_backend: Any | None = None,
    ) -> dict[str, Any]:
        return commit_linkage_record(
            self._root,
            actor_principal_id=actor_principal_id,
            evidence_id=evidence_id,
            annotation_id=annotation_id,
            binding=binding,
            key=key,
            key_id=key_id,
            record_id=record_id,
            remote_backend=remote_backend,
        )

    def read(self, *, record_id: str, binding: PrivateArtifactBinding, key: bytes) -> bytes:
        return open_private_bound_record(self._root, record_id=record_id, binding=binding, key=key)

    def stage_evidence(
        self,
        *,
        record_id: str,
        plaintext: bytes,
        binding: PrivateArtifactBinding,
        key: bytes,
        key_id: str,
    ) -> dict[str, Any]:
        self._require_kind(binding, "evidence")
        return stage_interrupted_bound_record(
            self._root,
            record_id=record_id,
            kind="evidence",
            plaintext=plaintext,
            binding=binding,
            key=key,
            key_id=key_id,
        )

    def recover(
        self,
        *,
        key: bytes,
        bindings: Mapping[str, PrivateArtifactBinding],
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        return recover_private_bound_records(
            self._root,
            key=key,
            bindings=bindings,
            max_attempts=max_attempts,
        )

    @staticmethod
    def _require_kind(binding: PrivateArtifactBinding, kind: str) -> None:
        if not isinstance(binding, PrivateArtifactBinding) or binding.artifact_kind != kind:
            raise BoundPrivateRecordError("binding_kind_mismatch")

    @staticmethod
    def _label(value: str, code: str) -> None:
        if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > 80:
            raise BoundPrivateRecordError(code)
