"""Bounded private storage for raw OCR provider responses (contracts §12.1).

Raw OCR is private derived data: it lives under `uploads_dir.parent/"artifacts"`,
scoped by tenant/root/source digest, written atomically, and shares the source's
deletion lifetime. A failed or oversized write is a technical unresolved result,
never a silent truncation into apparent success.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

MAX_ARTIFACT_BYTES_PER_SOURCE = 20 * 1024 * 1024  # lead-chosen, plan E2
MAX_ARTIFACT_BYTES_PER_ROOT = 40 * 1024 * 1024


class ArtifactWriteError(RuntimeError):
    """A raw artifact could not be persisted (disk/size/atomic-write failure)."""


class ArtifactStore:
    """Writes raw provider JSON under a tenant/root/source-digest key."""

    def __init__(
        self,
        *,
        root: str | Path,
        max_root_bytes: int = MAX_ARTIFACT_BYTES_PER_ROOT,
    ) -> None:
        self.root = Path(root)
        self.max_root_bytes = max_root_bytes

    def _rel_path(
        self, *, tenant: str, root_id: str, source_id: str, source_digest: str, version: str
    ) -> Path:
        # Keep the opaque reference relative; never expose an absolute path in
        # SQLite/API payloads. tenant/root/source-digest scope the artifact.
        safe_root = root_id.replace("/", "_").replace(":", "_")
        digest = hashlib.sha256(f"{source_id}:{source_digest}:{version}".encode()).hexdigest()[:16]
        return Path(tenant) / safe_root / f"{digest}.json"

    def _root_bytes(self, tenant: str, root_id: str) -> int:
        safe_root = root_id.replace("/", "_").replace(":", "_")
        directory = self.root / tenant / safe_root
        if not directory.is_dir():
            return 0
        return sum(p.stat().st_size for p in directory.glob("*.json"))

    def write(
        self,
        *,
        tenant: str,
        root_id: str,
        source_id: str,
        source_digest: str,
        version: str,
        payload: dict,
    ) -> str:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(encoded) > MAX_ARTIFACT_BYTES_PER_SOURCE:
            raise ArtifactWriteError(
                f"raw OCR artifact {len(encoded)} bytes exceeds "
                f"{MAX_ARTIFACT_BYTES_PER_SOURCE} per source"
            )
        if self._root_bytes(tenant, root_id) + len(encoded) > self.max_root_bytes:
            raise ArtifactWriteError(
                f"root {root_id} artifact bytes exceed {self.max_root_bytes}"
            )
        rel = self._rel_path(
            tenant=tenant, root_id=root_id, source_id=source_id,
            source_digest=source_digest, version=version,
        )
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: a temp file in the same directory, then os.replace.
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
            os.replace(tmp_name, target)
        except OSError as error:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise ArtifactWriteError(str(error)) from error
        return rel.as_posix()

    def path_for(self, ref: str) -> Path:
        """Resolve an opaque artifact reference to a local path."""
        return self.root / ref
