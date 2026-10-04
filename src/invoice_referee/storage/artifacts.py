"""Backend-owned artifact storage (T04, System §10).

The backend — never the client — assigns artifact IDs/paths. ``put_artifact``
writes original bytes under ``root/case_id/run_id/`` with an exclusive, atomic
temp-file + ``os.replace`` so a crash never leaves a half-written artifact. The
logical name is sanitized to a basename (no traversal, no separators), and the
SHA256 is taken over the original bytes by the caller.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def safe_name(name: str) -> str:
    """Return ``name`` only when it is a plain basename; otherwise raise.

    Rejects empty names, ``.``/``..``, any path component (``a/b``), and any
    backslash so a Windows-style path cannot smuggle a traversal.
    """
    if not name or name in {'.', '..'} or Path(name).name != name or '\\' in name:
        raise ValueError('Artifact name must be a basename')
    return name


def put_artifact(root: Path, case_id: str, run_id: str, name: str, content: bytes) -> Path:
    """Atomically store ``content`` and return the backend-owned absolute path.

    ``case_id``/``run_id`` are opaque backend IDs (validated to a single path
    segment); ``name`` is sanitized by :func:`safe_name`.
    """
    for part, label in ((case_id, 'case_id'), (run_id, 'run_id')):
        if not part or part in {'.', '..'} or Path(part).name != part or '\\' in part:
            raise ValueError(f'Artifact {label} must be a single path segment')
    clean = safe_name(name)

    directory = Path(root) / case_id / run_id
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / clean

    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix='.tmp-', suffix='.part')
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except BaseException:
        # Only clean up the temp file we created; never touch other artifacts.
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise
    return target
