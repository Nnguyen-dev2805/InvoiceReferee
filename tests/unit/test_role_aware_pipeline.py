"""Role-aware pipeline: paper/evidence extraction, no standalone classification (16/10/2026)."""

from __future__ import annotations

from decimal import Decimal

from tests.factories import clear_ocr_page

from invoice_referee.domain.documents import OcrSourceResult
from invoice_referee.domain.evidence import SourceRef
from invoice_referee.evidence.artifacts import ArtifactStore
from invoice_referee.evidence.trace import RunBudget

PAPER_MD = (
    "GIẤY QUYẾT TOÁN\nNgười đề nghị: NGUYEN VAN A\n"
    "Di chuyển nội thành 900000 ref PT-251026-016\nTổng cộng: 900000\nTạm ứng: 1000000"
)
INV_MD = (
    "HÓA ĐƠN GTGT\nSố: 00002502 Ký hiệu: IR26E Mẫu: 1C26TAA\n"
    "Tổng tiền: 2160000\nMST bên bán: 0100109106"
)
RECEIPT_MD = (
    "PHIẾU THU\nSố phiếu: PT-251026-016\nNgười nộp: NGUYEN VAN A\n"
    "Số tiền: 700000\nĐã nhận đủ số tiền"
)


class FakeOcrProvider:
    def __init__(self, texts: dict[str, str]) -> None:
        self.texts = texts

    async def ocr_file(
        self,
        source,
        *,
        budget,
        artifacts,
        source_bytes,
        expected_pages=None,
        root_id="",
    ):
        budget.charge_ocr()
        return OcrSourceResult(
            source_id=source.id,
            source_digest=source.digest,
            provider="fake",
            model="m",
            pages=(clear_ocr_page(self.texts[source.id]),),
        )


def _src(i: str, role: str | None) -> SourceRef:
    import hashlib

    return SourceRef(
        id=f"source:{i}",
        digest=hashlib.sha256(f"seed:{i}".encode()).hexdigest(),
        tenant="tenant:demo",
        media="PDF",
        storage_key=f"k:{i}",
        filename=f"{i}.pdf",
        upload_role=role,  # type: ignore[arg-type]
    )


class RoleFake:
    """One combined call per doc; records systems to prove no whole-set classify."""

    def __init__(
        self, *, paper_fit: str = "FIT", evidence_type: str = "E_INVOICE"
    ) -> None:
        self.systems: list[str] = []
        self.paper_fit = paper_fit
        self.evidence_type = evidence_type

    async def complete_json(self, *, system: str, user: str, budget: RunBudget) -> dict:
        import json

        budget.charge_llm()
        self.systems.append(system)
        payload = json.loads(user)
        source_id = payload.get("source_id", "")
        if "role 'paper'" in system:
            if self.paper_fit == "MISFIT":
                return {
                    "fields": [],
                    "line_items": [],
                    "role_fit": "MISFIT",
                    "actual_type": "E_INVOICE",
                    "role_note": "Nội dung là hóa đơn, chuyển sang ô evidence.",
                }
            return {
                "fields": [
                    {
                        "field": "declared_name",
                        "state": "FOUND",
                        "value": "NGUYEN VAN A",
                        "quote": "Người đề nghị: NGUYEN VAN A",
                        "page": 1,
                    },
                    {
                        "field": "printed_total",
                        "state": "FOUND",
                        "value": "900000",
                        "quote": "Tổng cộng: 900000",
                        "page": 1,
                    },
                    {
                        "field": "declared_advance",
                        "state": "FOUND",
                        "value": "1000000",
                        "quote": "Tạm ứng: 1000000",
                        "page": 1,
                    },
                ],
                "line_items": [
                    {
                        "fields": [
                            {
                                "field": "description",
                                "state": "FOUND",
                                "value": "Di chuyển nội thành",
                                "quote": "Di chuyển nội thành 900000 ref PT-251026-016",
                                "page": 1,
                            },
                            {
                                "field": "amount",
                                "state": "FOUND",
                                "value": "900000",
                                "quote": "Di chuyển nội thành 900000 ref PT-251026-016",
                                "page": 1,
                            },
                            {
                                "field": "invoice_refs",
                                "state": "FOUND",
                                "value": ["PT-251026-016"],
                                "quote": "Di chuyển nội thành 900000 ref PT-251026-016",
                                "page": 1,
                            },
                        ]
                    }
                ],
                "role_fit": "FIT",
                "actual_type": "SETTLEMENT_FORM",
                "role_note": "",
            }
        if "role 'evidence'" in system:
            if self.evidence_type == "UNKNOWN":
                return {"document_type": "UNKNOWN", "fields": [], "line_items": []}
            if "PT-251026" in source_id or "receipt" in source_id:
                return {
                    "document_type": "COLLECTION_RECEIPT",
                    "fields": [
                        {
                            "field": "document_number",
                            "state": "FOUND",
                            "value": "PT-251026-016",
                            "quote": "Số phiếu: PT-251026-016",
                            "page": 1,
                        },
                        {
                            "field": "total_amount",
                            "state": "FOUND",
                            "value": "700000",
                            "quote": "Số tiền: 700000",
                            "page": 1,
                        },
                    ],
                    "line_items": [],
                }
            return {
                "document_type": "E_INVOICE",
                "fields": [
                    {
                        "field": "document_number",
                        "state": "FOUND",
                        "value": "IR26E/00002502",
                        "quote": "Số: 00002502 Ký hiệu: IR26E Mẫu: 1C26TAA",
                        "page": 1,
                    },
                    {
                        "field": "total_amount",
                        "state": "FOUND",
                        "value": "2160000",
                        "quote": "Tổng tiền: 2160000",
                        "page": 1,
                    },
                ],
                "line_items": [],
            }
        raise AssertionError(
            f"standalone classification must not run on the new path: {system[:80]}"
        )


def _reader(texts):
    from invoice_referee.evidence.reader import FileOcrReader

    return FileOcrReader(provider=FakeOcrProvider(texts))


async def _run(tmp_path, sources, texts, fake, budget=None):
    from invoice_referee.evidence.pipeline import read_root_role_aware

    return await read_root_role_aware(
        sources=tuple(sources),
        reader=_reader(texts),
        classifier=fake,
        artifacts=ArtifactStore(root=tmp_path / "artifacts"),
        source_bytes={s.id: b"pdf" for s in sources},
        budget=budget or RunBudget(),
        provider_mode="LIVE",
        root_id="root:t",
    )


async def test_one_paper_three_evidence_is_four_extractions_no_classify(tmp_path):
    sources = [
        _src("paper", "paper"),
        _src("inv1", "evidence"),
        _src("inv2", "evidence"),
        _src("receipt", "evidence"),
    ]
    texts = {
        "source:paper": PAPER_MD,
        "source:inv1": INV_MD,
        "source:inv2": INV_MD,
        "source:receipt": RECEIPT_MD,
    }
    fake = RoleFake()
    report = await _run(tmp_path, sources, texts, fake)
    extraction_calls = [
        s for s in fake.systems if "role 'paper'" in s or "role 'evidence'" in s
    ]
    assert len(extraction_calls) == 4
    assert not any("classify documents" in s.lower() for s in fake.systems)
    assert {d.document_type for d in report.documents} >= {"SETTLEMENT_FORM"}


async def test_paper_misfit_is_reported_not_forced(tmp_path):
    sources = [_src("paper", "paper")]
    fake = RoleFake(paper_fit="MISFIT")
    report = await _run(tmp_path, sources, {"source:paper": INV_MD}, fake)
    assert any(
        p.next_action == "fix_upload_role" and "evidence" in p.message
        for p in report.problems
    )
    assert report.documents[0].document_type == "SETTLEMENT_FORM"


async def test_evidence_unknown_stays_unknown(tmp_path):
    sources = [_src("paper", "paper"), _src("weird", "evidence")]
    texts = {"source:paper": PAPER_MD, "source:weird": "ghi chú tay không rõ loại"}
    fake = RoleFake(evidence_type="UNKNOWN")
    report = await _run(tmp_path, sources, texts, fake)
    weird = next(d for d in report.documents if d.source_id == "source:weird")
    assert weird.document_type == "UNKNOWN"


async def test_budget_exhaustion_before_last_file_is_technical_not_missing_source(
    tmp_path,
):
    sources = [_src("paper", "paper"), _src("receipt", "evidence")]
    texts = {"source:paper": PAPER_MD, "source:receipt": RECEIPT_MD}
    fake = RoleFake()
    budget = RunBudget(max_llm_attempts=1)
    report = await _run(tmp_path, sources, texts, fake, budget=budget)
    assert len(report.documents) == 1
    assert any(
        p.kind == "TECHNICAL"
        and p.blocking
        and p.next_action == "resume_extraction"
        and "source:receipt" in p.affected_fields
        for p in report.problems
    )
    # Never a fake missing-source FACT: the receipt OCR ran, extraction did not.
    assert not any("chưa nộp" in p.message for p in report.problems)


async def test_resume_skips_cached_doc(tmp_path):
    from invoice_referee.domain.documents import DocumentAnalysis

    sources = [_src("paper", "paper"), _src("receipt", "evidence")]
    texts = {"source:paper": PAPER_MD, "source:receipt": RECEIPT_MD}
    cached_receipt = DocumentAnalysis(
        source_id="source:receipt",
        document_id="source:receipt:1-1:COLLECTION_RECEIPT",
        document_type="COLLECTION_RECEIPT",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",),
        page_range=(1, 1),
    )
    fake = RoleFake()
    from invoice_referee.evidence.pipeline import read_root_role_aware

    report = await read_root_role_aware(
        sources=tuple(sources),
        reader=_reader(texts),
        classifier=fake,
        artifacts=ArtifactStore(root=tmp_path / "artifacts"),
        source_bytes={s.id: b"pdf" for s in sources},
        budget=RunBudget(),
        provider_mode="LIVE",
        root_id="root:t",
        cached_docs={"source:receipt": cached_receipt},
    )
    assert sum("role 'evidence'" in s for s in fake.systems) == 0
    assert {d.source_id for d in report.documents} == {"source:paper", "source:receipt"}


async def test_missing_role_routes_to_legacy():
    from invoice_referee.evidence.pipeline import read_root_role_aware

    with __import__("pytest").raises(ValueError, match="upload_role"):
        await read_root_role_aware(
            sources=(_src("x", None),),
            reader=None,
            classifier=None,
            artifacts=None,
            source_bytes={},
            budget=RunBudget(),
            provider_mode="LIVE",
        )


def test_hotel_suffix_match_syncs_draft_and_final():
    from invoice_referee.domain.common import EvidenceRef
    from invoice_referee.domain.documents import (
        DocumentAnalysis,
        DocumentLine,
        EvidenceLink,
        FieldCandidate,
    )
    from invoice_referee.domain.evidence import ReadResult, SourceRef
    from invoice_referee.reconciliation.settlement_draft import build_settlement_draft

    def _ref():
        return EvidenceRef(
            source_id="s", source_sha256="a" * 64, page=1, exact_quote="q"
        )

    paper = DocumentAnalysis(
        source_id="source:paper",
        document_id="source:paper:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",),
        page_range=(1, 1),
        fields=(
            FieldCandidate(
                field="printed_total", state="FOUND", value="2160000", refs=(_ref(),)
            ),
        ),
        line_items=(
            DocumentLine(
                id="l1",
                fields=(
                    FieldCandidate(
                        field="description",
                        state="FOUND",
                        value="Phòng nghỉ",
                        refs=(_ref(),),
                    ),
                    FieldCandidate(
                        field="amount", state="FOUND", value="2160000", refs=(_ref(),)
                    ),
                    FieldCandidate(
                        field="invoice_refs",
                        state="FOUND",
                        value=("00002502",),
                        refs=(_ref(),),
                    ),
                ),
            ),
        ),
    )
    hotel = DocumentAnalysis(
        source_id="source:hotel",
        document_id="source:hotel:1-1:E_INVOICE",
        document_type="E_INVOICE",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",),
        page_range=(1, 1),
        fields=(
            FieldCandidate(
                field="document_number",
                state="FOUND",
                value="IR26E/00002502",
                refs=(_ref(),),
            ),
            FieldCandidate(
                field="total_amount", state="FOUND", value="2160000", refs=(_ref(),)
            ),
        ),
        line_items=(),
        profile_status="CLEAR",
    )
    report = ReadResult(
        documents=(paper, hotel),
        links=(
            EvidenceLink(
                item_id="ITEM-001",
                source_id="source:hotel",
                document_id="source:hotel:1-1:E_INVOICE",
                status="AUTO_LINK",
                method="INVOICE_NUMBER_EXACT",
                score=Decimal("1.0"),
                explanation="Số chứng từ trùng tham chiếu",
                refs=(_ref(),),
            ),
        ),
        row_matches=(),
        match_findings=(),
        problems=(),
    )
    sources = (
        SourceRef(
            id="source:paper",
            digest="a",
            tenant="t",
            media="PDF",
            storage_key="k1",
            filename="paper.pdf",
        ),
        SourceRef(
            id="source:hotel",
            digest="b",
            tenant="t",
            media="PDF",
            storage_key="k2",
            filename="hotel.pdf",
        ),
    )
    draft = build_settlement_draft(report, sources=sources)
    assert draft["expenses"][0]["status"] == "CLEAR"
    assert draft["expenses"][0]["matched_invoice"] == "hotel.pdf"

    hotel_blocked = hotel.model_copy(update={"profile_status": "NEEDS_HUMAN"})
    report2 = report.model_copy(update={"documents": (paper, hotel_blocked)})
    draft2 = build_settlement_draft(report2, sources=sources)
    assert draft2["expenses"][0]["status"] == "NEEDS_VERIFICATION"
    assert draft2["expenses"][0]["matched_invoice"] == "hotel.pdf"


def test_evidence_prompt_names_per_type_vocabulary():
    from invoice_referee.evidence.prompts import build_evidence_extraction_prompt

    prompt = build_evidence_extraction_prompt(("E_INVOICE", "COLLECTION_RECEIPT", "UNKNOWN"))
    assert "COLLECTION_RECEIPT" in prompt
    assert "document_number" in prompt and "total_amount" in prompt
    assert "receipt_number/amount" in prompt  # the anti-pattern is named


def test_receipt_aliases_map_to_profile_vocabulary():
    from invoice_referee.evidence.extraction import canonical_field_name

    assert canonical_field_name("receipt_number", "COLLECTION_RECEIPT") == "document_number"
    assert canonical_field_name("receipt_date", "COLLECTION_RECEIPT") == "document_date"
    assert canonical_field_name("amount", "COLLECTION_RECEIPT") == "total_amount"
    # TRANSPORT_TICKET keeps its own money field; SETTLEMENT rows keep `amount`.
    assert canonical_field_name("amount", "TRANSPORT_TICKET") == "amount"
    assert canonical_field_name("amount", "SETTLEMENT_FORM") == "amount"
    assert canonical_field_name("receipt_number", "E_INVOICE") == "receipt_number"


async def test_receipt_variant_names_still_validate(tmp_path):
    """A receipt using printed labels validates to a CLEAR profile (TC25 LIVE)."""
    from invoice_referee.evidence.document_validity import validate_document
    from invoice_referee.evidence.extraction import _pseudo_classification, _build_analysis
    from invoice_referee.evidence.ocr_quality import ConfidenceReview

    receipt_md = (
        "PHIẾU THU\nSố phiếu: PT-251026-016\nNgày: 10/10/2026\n"
        "Người nộp: NGUYEN VAN A\nSố tiền: 700000\nĐơn vị: CONG TY AN THINH"
    )
    from invoice_referee.domain.documents import OcrSourceResult

    ocr = OcrSourceResult(
        source_id="source:receipt", source_digest="e" * 64, provider="fake", model="m",
        pages=(clear_ocr_page(receipt_md),),
    )
    classification = _pseudo_classification(
        ocr, document_type="COLLECTION_RECEIPT", page_range=(1, 1))
    payload = {
        "document_type": "COLLECTION_RECEIPT",
        "fields": [
            {"field": "issuer_name", "state": "FOUND", "value": "CONG TY AN THINH",
             "quote": "Đơn vị: CONG TY AN THINH", "page": 1},
            {"field": "receipt_number", "state": "FOUND", "value": "PT-251026-016",
             "quote": "Số phiếu: PT-251026-016", "page": 1},
            {"field": "receipt_date", "state": "FOUND", "value": "2026-10-10",
             "quote": "Ngày: 10/10/2026", "page": 1},
            {"field": "amount", "state": "FOUND", "value": "700000",
             "quote": "Số tiền: 700000", "page": 1},
            {"field": "payer_name", "state": "FOUND", "value": "NGUYEN VAN A",
             "quote": "Người nộp: NGUYEN VAN A", "page": 1},
        ],
        "line_items": [],
    }
    analysis = _build_analysis(ocr, classification, payload=payload,
                               document_type="COLLECTION_RECEIPT")
    names = {f.field for f in analysis.fields if f.state == "FOUND"}
    assert {"document_number", "document_date", "total_amount"} <= names
    validated = validate_document(
        analysis, ocr,
        ConfidenceReview(status="SKIPPED_NO_NUMERIC_CANDIDATES", block_assessments=()))
    assert validated.profile_status == "CLEAR"


async def test_pure_amount_dispute_skips_resolver_call(tmp_path):
    """TC25 shape end-to-end: exact-number suggestion, amount differs → no resolver LLM."""
    from invoice_referee.evidence.artifacts import ArtifactStore
    from invoice_referee.evidence.pipeline import read_root_role_aware
    from invoice_referee.evidence.trace import RunBudget

    calls = {"resolver": 0}

    class NoResolver(RoleFake):
        async def complete_json(self, *, system: str, user: str, budget: RunBudget) -> dict:
            if "promotions" in system:
                calls["resolver"] += 1
                raise AssertionError("resolver must be skipped for pure amount disputes")
            return await super().complete_json(system=system, user=user, budget=budget)

    paper_md = (
        "GIẤY QUYẾT TOÁN\nNgười đề nghị: NGUYEN VAN A\n"
        "Di chuyển nội thành 900000 ref PT-251026-016\nTổng cộng: 900000\nTạm ứng: 1000000"
    )
    receipt_md = (
        "PHIẾU THU\nSố phiếu: PT-251026-016\nNgười nộp: NGUYEN VAN A\nSố tiền: 700000"
    )
    sources = [_src("paper", "paper"), _src("receipt", "evidence")]
    texts = {"source:paper": paper_md, "source:receipt": receipt_md}
    fake = NoResolver()
    # RoleFake evidence branch keys off source_id containing receipt/PT ref.
    report = await read_root_role_aware(
        sources=tuple(sources), reader=_reader(texts), classifier=fake,
        artifacts=ArtifactStore(root=tmp_path / "artifacts"),
        source_bytes={s.id: b"pdf" for s in sources}, budget=RunBudget(),
        provider_mode="LIVE", root_id="root:t",
    )
    assert calls["resolver"] == 0
    assert any(
        link.status == "SUGGEST_LINK" and link.method == "INVOICE_NUMBER_EXACT"
        for link in report.links
    )
