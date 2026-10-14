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

    def __init__(self, *, root: str | Path) -> None:
        self.root = Path(root)

    def _rel_path(self, *, tenant: str, source_id: str, source_digest: str, version: str) -> Path:
        # Keep the opaque reference relative; never expose an absolute path in
        # SQLite/API payloads. The digest and version make the key stable.
        digest = hashlib.sha256(f"{source_id}:{source_digest}:{version}".encode()).hexdigest()[:16]
        return Path(tenant) / f"{digest}.json"

    def write(
        self,
        *,
        tenant: str,
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
        rel = self._rel_path(
            tenant=tenant, source_id=source_id, source_digest=source_digest, version=version
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
