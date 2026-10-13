"""Sources, evidence units, observations and relations (contracts §2).

Read states are observations, never Fact.KNOWN: a page that was not read,
could not be read, or failed is not the same as a page that is absent.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from invoice_referee.domain.common import EvidenceRef, Id, StrictModel, UtcDatetime
from invoice_referee.domain.issues import ProcessingProblem

Media = Literal["PDF", "PNG", "JPEG"]
EvidenceRole = Literal[
    "REQUEST",
    "INVOICE",
    "PAYMENT",
    "RECEIVED",
    "ADVANCE",
    "LEDGER",
    "DECLARATION",
    "OTHER",
]
ReadState = Literal["CLEAR", "MISSING", "UNREADABLE", "NOT_READ", "ERROR"]
RelationState = Literal["SUPPORTED", "DISPROVED", "UNKNOWN", "CONFLICT"]


class SourceRef(StrictModel):
    """An immutable source revision. The digest fixes which bytes were read."""

    id: Id
    digest: str = Field(min_length=1)
    tenant: Id
    media: Media
    storage_key: str = Field(min_length=1)


class EvidenceUnit(StrictModel):
    """A page range of one source in one role; a PDF may hold several roles."""

    source: Id
    page_range: tuple[int, int]
    role: EvidenceRole

    @model_validator(mode="after")
    def _ordered_page_range(self) -> EvidenceUnit:
        start, end = self.page_range
        if start < 1 or end < start:
            raise ValueError("page_range must be 1-based and ordered (start <= end)")
        return self


class Observation(StrictModel):
    field: str
    raw: str | None = None
    normalized: str | int | None = None
    read_state: ReadState
    ref: EvidenceRef


class Relation(StrictModel):
    kind: str
    from_id: Id
    to_id: Id
    state: RelationState
    refs: tuple[EvidenceRef, ...] = ()


class Confirmation(StrictModel):
    """A scoped business confirmation by a responsible actor (contracts §3)."""

    fact_key: str
    value: str | int
    actor: Id
    scope: str
    refs: tuple[EvidenceRef, ...] = ()
    reason: str
    observed_at: UtcDatetime


class ReadResult(StrictModel):
    """What one read pass produced. Proposals only: no financial effect."""

    units: tuple[EvidenceUnit, ...] = ()
    observations: tuple[Observation, ...] = ()
    relations: tuple[Relation, ...] = ()
    page_coverage: tuple[int, ...] = ()
    problems: tuple[ProcessingProblem, ...] = ()
    trace_refs: tuple[str, ...] = ()
