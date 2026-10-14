"""EvidenceReader: sources -> observations, units, relations (contracts §5, §9).

The reader is read-only: it produces `ReadResult` proposals and has no path to
record money, grant authority or commit an action. A page that was not read or
timed out is NOT_READ (never MISSING); two representations that disagree are
kept side by side as a CONFLICT, not resolved by model confidence.
"""

from __future__ import annotations

from typing import Protocol

from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import OcrSourceResult
from invoice_referee.domain.evidence import (
    EvidenceUnit,
    Observation,
    Relation,
    ReadResult,
    SourceRef,
)
from invoice_referee.domain.issues import ProcessingProblem
from invoice_referee.evidence.artifacts import ArtifactStore
from invoice_referee.evidence.trace import ProviderMode, RunBudget

# Cheap, observable role cues. These are routing hints, not monetary truth.
_ROLE_CUES: tuple[tuple[str, str], ...] = (
    ("ĐỀ NGHỊ THANH TOÁN", "REQUEST"),
    ("ĐỀ NGHỊ", "REQUEST"),
    ("BIÊN NHẬN THANH TOÁN", "PAYMENT"),
    ("THANH TOÁN", "PAYMENT"),
    ("ĐÃ NHẬN TIỀN", "RECEIVED"),
    ("NHẬN TIỀN", "RECEIVED"),
)


class OcrClient(Protocol):
    async def ocr_page(self, source: SourceRef, page: int) -> str: ...


class EvidenceReader:
    """Bounded, read-only reader over the current root's sources."""

    def __init__(
        self,
        *,
        mode: ProviderMode,
        mistral: object | None = None,
        native_text: dict[str, dict[int, str]] | None = None,
        side_effect_spy: object | None = None,
    ) -> None:
        self.mode = mode
        self.mistral = mistral
        self.native_text = native_text or {}
        self.side_effect_spy = side_effect_spy

    async def read(
        self,
        source: SourceRef,
        requested_fields: tuple[str, ...],
        budget: RunBudget,
        *,
        pages: tuple[int, ...] = (1,),
    ) -> ReadResult:
        units: list[EvidenceUnit] = []
        observations: list[Observation] = []
        problems: list[ProcessingProblem] = []

        native = self.native_text.get(source.id, {})

        for page in pages:
            ocr_text = await self._read_page(source, page, budget)
            native_page = native.get(page, "")

            if ocr_text is None:
                # Timeout / not read: an observation, never MISSING.
                observations.append(
                    Observation(
                        field="page",
                        raw=None,
                        normalized=None,
                        read_state="NOT_READ",
                        ref=self._ref(source, page, "page not read"),
                    )
                )
                continue

            role = self._classify_role(native_page or ocr_text)
            units.append(
                EvidenceUnit(source=source.id, page_range=(page, page), role=role)
            )

            # Keep both representations; a disagreement is a CONFLICT, not a guess.
            for field in requested_fields:
                native_value, native_quote = self._extract(native_page, field)
                ocr_value, ocr_quote = self._extract(ocr_text, field)
                if native_value is not None:
                    observations.append(
                        Observation(
                            field=field,
                            raw=native_quote,
                            normalized=native_value,
                            read_state="CLEAR",
                            ref=self._ref(source, page, native_quote),
                        )
                    )
                if ocr_value is not None and ocr_value != native_value:
                    observations.append(
                        Observation(
                            field=field,
                            raw=ocr_quote,
                            normalized=ocr_value,
                            read_state="CLEAR",
                            ref=self._ref(source, page, ocr_quote),
                        )
                    )

        if not observations:
            observations.append(
                Observation(
                    field="page",
                    raw=None,
                    normalized=None,
                    read_state="NOT_READ",
                    ref=self._ref(source, 1, "no readable page"),
                )
            )

        return ReadResult(
            units=tuple(units),
            observations=tuple(observations),
            relations=(),
            page_coverage=tuple(pages),
            problems=tuple(problems),
            trace_refs=(),
        )

    async def _read_page(
        self, source: SourceRef, page: int, budget: RunBudget
    ) -> str | None:
        # A read client (real Mistral, a RECORDED_REPLAY reader, or a STUB
        # hand-transcription fake) provides the page text. Its absence or a
        # timeout is NOT_READ, never MISSING.
        if self.mistral is None:
            native = self.native_text.get(source.id, {})
            return native.get(page, "") if page in native else None
        try:
            return await self.mistral.ocr_page(source, page)  # type: ignore[attr-defined]
        except TimeoutError:
            return None

    @staticmethod
    def _classify_role(text: str) -> str:
        for cue, role in _ROLE_CUES:
            if cue in text:
                return role
        return "OTHER"

    @staticmethod
    def _extract(text: str, field: str) -> tuple[int | None, str]:
        """A literal, bounded amount extractor for the demo (no model).

        Returns the parsed integer and the exact source text that produced it,
        so an EvidenceRef's `exact_quote` is a real quote, never a bare number.
        """
        import re

        match = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)", text)
        if match is None:
            return None, text
        quote = match.group(1)
        try:
            return int(quote.replace(".", "")), quote
        except ValueError:
            return None, quote

    @staticmethod
    def _ref(source: SourceRef, page: int, quote: str) -> EvidenceRef:
        return EvidenceRef(
            source_id=source.id,
            source_sha256=source.digest,
            page=page,
            exact_quote=quote or "page",
        )


def relations_for(result: ReadResult) -> tuple[Relation, ...]:
    """No relations are asserted by a read alone (contracts §3)."""
    return result.relations


class FileOcrReader:
    """File-level OCR reader (contracts §12.1, plan E2).

    Every accepted page of one file goes to OCR; native PDF text is not used to
    skip the provider. Raw provider JSON is persisted through the artifact
    store. This is the shape E7 wires into the pipeline; the legacy per-page
    `EvidenceReader.read` stays until E7 removes it.
    """

    def __init__(self, *, provider: object) -> None:
        self.provider = provider

    async def read_source(
        self,
        source: SourceRef,
        *,
        budget: RunBudget,
        artifacts: ArtifactStore,
        source_bytes: bytes,
        expected_pages: int | None = None,
    ) -> OcrSourceResult:
        return await self.provider.ocr_file(  # type: ignore[attr-defined]
            source,
            budget=budget,
            artifacts=artifacts,
            source_bytes=source_bytes,
            expected_pages=expected_pages,
        )
