"""Evaluation packet DTOs (contracts §7, §11).

A packet is three separate layers so the app can never read the answer:

- input/  : raw sources + organization.json + submission.json — what the app sees.
- gold/   : latent.json + observable.json + allowed.json — scorer-only.
- manifest.json: digests, root/economic identity, family/split/profile.

`PacketInput` is what `EvaluationRunner.run` accepts; `GoldPacket` is loaded by
the scorer afterwards and never enters the application or a model prompt.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from invoice_referee.domain.common import Id, StrictModel, UtcDatetime

Split = Literal["development", "calibration", "validation", "holdout"]
Strata = Literal["routine", "FACT", "POLICY", "AUTHORITY", "TECHNICAL"]


class PacketSource(StrictModel):
    """One raw source file inside input/ (path relative to the packet root)."""

    filename: str = Field(min_length=1)
    media: Literal["PDF", "PNG", "JPEG"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class OrganizationContext(StrictModel):
    """Genuine simulated observable ledger/context — never the expected E/S."""

    tenant: Id
    profile: str
    # Simulated observable records only; no `expected`/`forced` routing fields.
    records: tuple[str, ...] = ()


class Submission(StrictModel):
    """The employee's declaration. An estimate is not a verified payment."""

    employee: Id
    activity: Id
    declared_purpose: str
    notes: str | None = None


class PacketInput(StrictModel):
    """Everything the application may read for one packet."""

    root_id: Id
    profile: str
    sources: tuple[PacketSource, ...] = ()
    organization: OrganizationContext
    submission: Submission


class LatentGold(StrictModel):
    """Truth not visible in the sources (e.g. the real payer), scorer-only."""

    facts: dict[str, str | int] = {}


class ObservableGold(StrictModel):
    """What a correct reader should observe from the sources themselves."""

    facts: dict[str, str | int] = {}


class AllowedGold(StrictModel):
    """The acceptable outcome(s): route, amounts, owner, question."""

    route: Literal["AUTO", "FACT", "POLICY", "AUTHORITY", "TECHNICAL", "UNSUPPORTED"]
    expected_amounts: dict[str, int] = {}
    owner: str | None = None
    question_required: bool = False


class GoldPacket(StrictModel):
    """The hidden oracle. Loaded by the scorer only (contracts §7)."""

    latent: LatentGold
    observable: ObservableGold
    allowed: AllowedGold


class ManifestEntry(StrictModel):
    """One root's placement in the dataset (contracts §7, §11 grouping axes)."""

    root_id: Id
    split: Split
    strata: Strata
    profile: str
    economic_key: str
    # Grouping axes: roots sharing a family/template/layout/issuer must not
    # straddle a split boundary (a shared font/A4 alone is not leakage).
    family: str
    template: str
    layout: str
    issuer: str
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    gold_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class InventoryReport(StrictModel):
    """Result of validating a manifest against the grouping rules (§11).

    `problems` are hard failures (cross-split leakage, duplicate roots);
    `disclosures` are within-split group sharing that must be reported but does
    not by itself invalidate the dataset.
    """

    total: int
    by_split: dict[str, int] = {}
    by_strata: dict[str, int] = {}
    problems: tuple[str, ...] = ()
    disclosures: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.problems


class PacketMetadata(StrictModel):
    """manifest.json shape: dataset-level metadata plus one entry per root."""

    dataset: str
    frozen_at: UtcDatetime
    entries: tuple[ManifestEntry, ...] = ()
