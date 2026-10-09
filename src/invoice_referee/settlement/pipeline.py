"""Settlement pipeline (W02): orchestrate read → match → evaluate → report.

The Reader protocol is the seam between deterministic orchestration and
provider-backed reading (W03). This module also carries the W02 fake reader:
``StructuredLedgerReader`` parses a documented synthetic text format, so unit,
API and UI tests exercise the same core path with data-driven sources — never
test IDs. Its mode label ``FAKE_OR_REPLAY`` is recorded on runs and reports.

Structured ledger v1 (UTF-8 text, one directive per line, ``#`` comments):

    fact <fact_id> <key> <value>          # value: integer or word
    unclear <fact_id> <key> <raw text>   # field exists but cannot be read
    rel <rel_id> <KIND> <from> <to> [portion <int>]

Relations are surfaced by ``read`` as observations with key ``relation`` and a
dict value; ``match`` converts them to Relation records.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import (
    Observation,
    Relation,
    Report,
    RunBudget,
    RunInput,
    SourceRecord,
)
from invoice_referee.settlement.rules import evaluate

REQUIRED_KEYS = {
    "B7": ["expense.", "payment.", "history.", "budget.", "relation"],
    "B3": ["advance.request", "forecast.", "history.advance.", "budget."],
}


class Reader(Protocol):
    """Reads facts from one source and proposes links between them."""

    mode: str

    def read(self, source: SourceRecord, keys: list[str],
             budget: RunBudget) -> list[Observation]: ...

    def match(self, run_input: RunInput, candidates: list[Observation],
              budget: RunBudget) -> list[Relation]: ...


class StructuredLedgerReader:
    """Fake/offline reader for the documented synthetic ledger format."""

    mode = "FAKE_OR_REPLAY"

    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = Path(artifact_root)

    def read(self, source: SourceRecord, keys: list[str],
             budget: RunBudget) -> list[Observation]:
        budget.reserve_call()  # một lần đọc nguồn = một call trong budget
        path = self.artifact_root / source.original_path
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as error:
            raise DomainError(
                "SOURCE_UNREADABLE",
                f"Không đọc được nguồn {source.id}: {error}",
            ) from error
        observations: list[Observation] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            observation = self._parse_line(stripped, source.id, line_number)
            if observation is not None and self._wanted(observation.key, keys):
                observations.append(observation)
        return observations

    @staticmethod
    def _wanted(key: str, keys: list[str]) -> bool:
        if not keys:
            return True
        return any(key == prefix or key.startswith(prefix) for prefix in keys)

    @staticmethod
    def _parse_line(line: str, source_id: str, line_number: int) -> Observation | None:
        parts = line.split()
        locator = f"line {line_number}"
        if parts[0] == "fact" and len(parts) >= 4:
            fact_id, key, raw_value = parts[1], parts[2], " ".join(parts[3:])
            value: int | str
            try:
                value = int(raw_value)
            except ValueError:
                value = raw_value
            return Observation(
                fact_id=fact_id, key=key, raw=raw_value, read_state="READ",
                value=value, source_id=source_id, row=line_number, locator=locator,
                basis=f"structured ledger {source_id} {locator}",
            )
        if parts[0] == "unclear" and len(parts) >= 4:
            fact_id, key = parts[1], parts[2]
            raw_text = " ".join(parts[3:])
            return Observation(
                fact_id=fact_id, key=key, raw=raw_text, read_state="UNCLEAR",
                value=None, source_id=source_id, row=line_number, locator=locator,
                basis=f"structured ledger {source_id} {locator}: không đọc được",
                usability="UNUSABLE",
            )
        if parts[0] == "rel" and len(parts) >= 5:
            relation_id, kind, from_id, to_id = parts[1], parts[2], parts[3], parts[4]
            portion: int | None = None
            if "portion" in parts:
                index = parts.index("portion")
                if index + 1 < len(parts):
                    portion = int(parts[index + 1])
            return Observation(
                fact_id=relation_id, key="relation",
                raw=line, read_state="READ",
                value={"kind": kind, "from": from_id, "to": to_id,
                       "portion_vnd": portion},
                source_id=source_id, row=line_number, locator=locator,
                basis=f"structured ledger {source_id} {locator}",
            )
        raise DomainError(
            "LEDGER_LINE_INVALID",
            f"Dòng ledger không hợp lệ tại {source_id} {locator}: {line}",
        )

    def match(self, run_input: RunInput, candidates: list[Observation],
              budget: RunBudget) -> list[Relation]:
        relations: list[Relation] = []
        for observation in candidates:
            if observation.key != "relation" or observation.read_state != "READ":
                continue
            if not isinstance(observation.value, dict):
                continue
            payload = observation.value
            relations.append(Relation(
                relation_id=observation.fact_id,
                kind=payload["kind"],  # type: ignore[arg-type]
                from_id=payload["from"], to_id=payload["to"],
                portion_vnd=payload.get("portion_vnd"),
                supporting_refs=[observation.source_id],
                status="ESTABLISHED",
                reason=f"structured ledger ghép trực tiếp ({observation.locator})",
            ))
        return relations


def process(run_input: RunInput, reader: Reader, budget: RunBudget,
            checkpoint, run_id: str = "R-PIPELINE") -> Report:
    """Run one job over the snapshot; checkpoint guards Stop/revision/epoch."""
    keys = REQUIRED_KEYS.get(run_input.submission.job, [])
    checkpoint("reading")
    observations: list[Observation] = []
    for source in sorted(run_input.sources, key=lambda s: s.id):
        observations.extend(reader.read(source, keys, budget))
    checkpoint("matching")
    relations = reader.match(run_input, observations, budget)
    checkpoint("evaluating")
    report = evaluate(run_input, observations, relations, run_id=run_id,
                      mode=reader.mode)
    checkpoint("publishing")
    return report
