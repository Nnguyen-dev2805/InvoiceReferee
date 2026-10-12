"""Source-mapped replay reader for B7 Verify (plan Task 2).

``SourcedReplayReader`` implements the existing ``Reader`` protocol over
prepared observations/relations sidecars. It binds each sidecar entry to the
**uploaded source bytes by sha256** (never filename, case id or expected) and
re-emits ``Observation``/``Relation`` through the same pipeline. It opens no
network and never reads the packet's expected files.

Discipline (plan Task 2 interfaces):

- A sidecar entry whose ``source_sha256`` matches no uploaded source is a
  per-source technical failure, not a silent drop.
- ``basis`` is ``SOURCE_QUOTE`` (raw text must be found in the source) or
  ``DERIVED_WITH_POLICY`` (zero/history totals derived from reviewed coverage,
  carrying ``derivation_refs``). No fabricated confidence.
- ``mode = POLICY_REPLAY`` so the honest metrics never call it AI extraction.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from invoice_referee.shared.errors import DomainError
from invoice_referee.settlement.models import (
    CallTrace,
    Observation,
    Relation,
    RunBudget,
    RunInput,
    SourceRecord,
)

MODE = "POLICY_REPLAY"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SourcedReplayReader:
    """Reader over prepared sidecars, bound to sources by bytes hash."""

    mode = MODE

    def __init__(self, artifact_root: Path, observations_path: Path,
                 relations_path: Path) -> None:
        self.artifact_root = Path(artifact_root)
        self.observations_path = Path(observations_path)
        self.relations_path = Path(relations_path)
        self._trace: list[CallTrace] = []
        self._observations = self._load(self.observations_path)
        self._relations = self._load(self.relations_path)

    @staticmethod
    def _load(path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            raise DomainError(
                "REPLAY_SIDECAR_MISSING",
                f"Thiếu replay sidecar {path}; không thể chạy POLICY_REPLAY.",
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise DomainError(
                "REPLAY_SIDECAR_INVALID",
                f"Replay sidecar {path.name} phải là danh sách.",
            )
        return data

    # --- Reader protocol ------------------------------------------------------

    def reset_trace(self) -> None:
        self._trace = []

    def trace_entries(self) -> list[CallTrace]:
        return list(self._trace)

    def read(self, source: SourceRecord, keys: list[str],
             budget: RunBudget) -> list[Observation]:
        """Emit the sidecar observations bound to this uploaded source."""
        data = self._read_bytes(source)
        sha = _sha256_bytes(data)
        matched = [o for o in self._observations
                   if o.get("source_sha256") == sha]
        if not matched:
            # No prepared facts for this uploaded bytes: a per-source technical
            # gap, never a silent drop or a fabricated NOT_FOUND.
            raise DomainError(
                "REPLAY_SOURCE_UNMATCHED",
                f"Replay sidecar không có fact cho source {source.id} "
                f"(sha256 {sha[:12]}…); không suy NOT_FOUND.",
            )
        observations: list[Observation] = []
        for entry in matched:
            observations.append(self._to_observation(entry, source))
        return observations

    def match(self, run_input: RunInput, candidates: list[Observation],
              budget: RunBudget) -> list[Relation]:
        """Emit the sidecar relations (source-mapped), not a live matcher."""
        relations: list[Relation] = []
        for entry in self._relations:
            relations.append(Relation(
                relation_id=str(entry["relation_id"]),
                kind=entry["kind"],  # type: ignore[arg-type]
                from_id=str(entry["from_id"]), to_id=str(entry["to_id"]),
                portion_vnd=entry.get("portion_vnd"),
                supporting_refs=list(entry.get("supporting_refs") or []),
                status=entry.get("status", "ESTABLISHED"),  # type: ignore[arg-type]
                reason=str(entry.get("reason", "replay sidecar")),
            ))
        return relations

    # --- internals ------------------------------------------------------------

    def _read_bytes(self, source: SourceRecord) -> bytes:
        path = self.artifact_root / source.original_path
        try:
            return path.read_bytes()
        except OSError as error:
            raise DomainError(
                "SOURCE_UNREADABLE",
                f"Không đọc được source {source.id}: {error}",
            ) from error

    def _to_observation(self, entry: dict[str, Any],
                        source: SourceRecord) -> Observation:
        basis = str(entry.get("basis", "SOURCE_QUOTE"))
        if basis == "SOURCE_QUOTE":
            raw = entry.get("raw")
            text = self._source_text(source)
            if isinstance(raw, str) and raw and not _quote_present(raw, text):
                raise DomainError(
                    "REPLAY_QUOTE_NOT_FOUND",
                    f"Quote {raw!r} của {entry.get('key')} không có trong "
                    f"source {source.id}; không bịa confidence.",
                )
        note = basis
        derivation = entry.get("derivation_refs") or []
        if derivation:
            note = f"{basis}: {', '.join(str(d) for d in derivation)}"
        return Observation(
            fact_id=str(entry["fact_id"]), key=str(entry["key"]),
            raw=entry.get("raw"), read_state=entry.get("read_state", "READ"),
            value=entry.get("value"), source_id=source.id,
            page=entry.get("page"), locator=entry.get("locator"),
            basis=note, usability=entry.get("usability", "USABLE"),
        )

    def _source_text(self, source: SourceRecord) -> str:
        data = self._read_bytes(source)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="ignore")


def _quote_present(raw: str, text: str) -> bool:
    """Is ``raw`` grounded in ``text``?

    Literal containment first; then a separator-insensitive digit check so a
    normalized VND value (``3000000``) is found in ``3.000.000``. This is not a
    number parser — it only removes ``.``/``,``/whitespace before comparing.
    """
    if raw in text:
        return True
    digits_raw = "".join(ch for ch in raw if ch.isdigit())
    if not digits_raw:
        return False
    digits_text = "".join(ch for ch in text if ch.isdigit())
    return digits_raw in digits_text
