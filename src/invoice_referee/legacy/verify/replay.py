"""Replay provider for Verify (T11).

``ReplayProviders`` is a ``FakeProviders`` whose documents/registries are loaded
per case AFTER the real case is submitted (so the runner can remap the fixture's
logical evidence ids to the ids the ``Repository`` actually assigned, matched by
role). It returns the frozen OCR/document/registry artifacts — no network — while
the pipeline still runs the real per-document path (validation, active-threshold
re-derivation, ``evaluate``).

Replay never looks up an outcome by case id or filename: the artifacts are keyed
by the evidence ROLE of the case being run.
"""
from __future__ import annotations

from invoice_referee.domain.models import (
    DocumentFacts,
    EvidenceBundle,
    MappingProposal,
    SourceRegistry,
)
from invoice_referee.extraction.providers import FakeProviders

# The replay artifact evidence ids are ROLE NAMES so the runner can map them to
# the real assigned ids by role (which is stable across runs).
PRIMARY = 'PRIMARY_BILL'
RECEIPT = 'GOODS_RECEIPT'


class ReplayProviders(FakeProviders):
    """FakeProviders that the runner populates once the real ids are known."""

    def __init__(self) -> None:
        super().__init__({}, {})
        self._mapping: MappingProposal | None = None

    def load(
        self,
        documents: dict[str, DocumentFacts],
        registries: dict[str, SourceRegistry],
        mapping: MappingProposal | None,
    ) -> None:
        """Install the remapped artifacts for the case about to run."""
        self.documents = dict(documents)
        self.registries = dict(registries)
        self._mapping = mapping
        self.calls = []
        self.identities = []

    def cross_source(self, bundle: EvidenceBundle) -> MappingProposal:
        # Only WORK_PURCHASE reaches here (both docs present + usable).
        self.calls.append('cross_source')
        return self._mapping if self._mapping is not None else super().cross_source(bundle)
