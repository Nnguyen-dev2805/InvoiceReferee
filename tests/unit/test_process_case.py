from pathlib import Path
from typing import Callable

from invoice_referee.application import CaseProcessingService
from invoice_referee.domain import (
    BlockAssessment,
    ClaimDraft,
    ConfidenceAnalysis,
    ConflictAnalysis,
    EvidenceRole,
    InventoryDocumentFacts,
    InventoryItemMatch,
    InventoryLineItemFact,
    ProcessingDecision,
    UploadPayload,
)
from invoice_referee.extraction import OcrExecution
from invoice_referee.storage import LocalCaseStore, LocalEvidenceRepository


class FakeOcrAdapter:
    def __init__(self, block_text: str | None = None) -> None:
        self.block_text = block_text
        self.calls: list[Path] = []

    def process(self, file_path: Path, mime_type: str) -> OcrExecution:
        self.calls.append(file_path)
        text = self.block_text or f"OCR {file_path.name} - Tổng tiền 100.000đ"
        page = {
            "index": 0,
            "markdown": text,
            "dimensions": {"width": 100, "height": 100},
            "blocks": [],
            "confidence_scores": {"word_confidence_scores": []},
        }
        if self.block_text is not None:
            page["blocks"] = [
                {
                    "type": "text",
                    "content": text,
                    "top_left_x": 1,
                    "top_left_y": 1,
                    "bottom_right_x": 90,
                    "bottom_right_y": 20,
                }
            ]
            page["confidence_scores"] = {
                "word_confidence_scores": [
                    {"text": text, "confidence": 0.62, "start_index": 0}
                ]
            }
        return OcrExecution(
            provider="mistral",
            model="mistral-ocr-latest",
            processed_at="2026-09-21T10:00:00+07:00",
            response={"pages": [page]},
        )


class FakeQualityAdapter:
    def __init__(
        self,
        *,
        confidence_importance: str = "NON_CRITICAL",
        confidence_quality: str = "UNCERTAIN",
        confidence_action: str | None = None,
        semantic_category: str | None = None,
        blocking_filename: str | None = None,
        omit_confidence_assessments: bool = False,
        conflict_factory: Callable[[dict], ConflictAnalysis] | None = None,
    ) -> None:
        self.confidence_importance = confidence_importance
        self.confidence_quality = confidence_quality
        self.confidence_action = confidence_action
        self.semantic_category = semantic_category
        self.blocking_filename = blocking_filename
        self.omit_confidence_assessments = omit_confidence_assessments
        self.conflict_factory = conflict_factory
        self.confidence_calls: list[dict] = []
        self.conflict_calls: list[dict] = []

    def analyze_confidence(self, payload: dict) -> ConfidenceAnalysis:
        self.confidence_calls.append(payload)
        if self.omit_confidence_assessments:
            return ConfidenceAnalysis()
        document = payload["evidence"]
        candidates = document["candidate_blocks"]
        importance = (
            "CRITICAL"
            if document["filename"] == self.blocking_filename
            else self.confidence_importance
        )
        review_action = self.confidence_action
        if review_action is None:
            review_action = (
                "ASK_HUMAN"
                if importance == "CRITICAL"
                and self.confidence_quality not in {"READABLE", "SEMANTICALLY_READABLE"}
                else "CONTINUE"
            )
        return ConfidenceAnalysis(
            block_assessments=[
                BlockAssessment(
                    candidate_id=candidate["candidate_id"],
                    importance=importance,
                    quality_state=self.confidence_quality,
                    review_action=review_action,
                    requires_verification=review_action == "ASK_HUMAN",
                    canonical_fields=(
                        ["total_amount"]
                        if importance == "CRITICAL"
                        else []
                    ),
                    observed_text=candidate["content"],
                    semantic_category=self.semantic_category,
                    reason="Đánh giá phần OCR có confidence thấp.",
                    human_question=(
                        f"Vui lòng xác nhận {candidate['candidate_id']}."
                        if review_action == "ASK_HUMAN"
                        else None
                    ),
                )
                for candidate in candidates
            ]
        )

    def analyze_conflict(self, payload: dict) -> ConflictAnalysis:
        self.conflict_calls.append(payload)
        if self.conflict_factory is not None:
            return self.conflict_factory(payload)
        return ConflictAnalysis(
            applicability="NOT_APPLICABLE",
            applicability_reason="Fake mặc định không áp dụng policy kiểm kê.",
            document_facts=[
                InventoryDocumentFacts(
                    evidence_id=document["evidence_id"],
                    document_type="OTHER",
                    receipt_status="NOT_APPLICABLE",
                )
                for document in payload["documents"]
            ],
        )


def _upload(name: str, role: EvidenceRole) -> UploadPayload:
    return UploadPayload(
        original_name=name,
        content=f"content-{name}".encode(),
        mime_type="image/jpeg",
        role=role,
    )


def _save_case(
    root: Path,
    *,
    body: str,
    uploads: list[UploadPayload],
) -> tuple[str, LocalEvidenceRepository]:
    store = LocalCaseStore(root, id_factory=lambda: "CASE-PROCESS-001")
    receipt = store.save_submission(
        ClaimDraft(subject="Đề nghị chi phí", body=body),
        uploads,
        [],
    )
    return receipt.case_id, LocalEvidenceRepository(root)


def _conflict_factory(
    *,
    report_quantity: str,
    report_amount: str,
) -> Callable[[dict], ConflictAnalysis]:
    def build(payload: dict) -> ConflictAnalysis:
        primary = next(
            document
            for document in payload["documents"]
            if document["role"] == EvidenceRole.PRIMARY_DOCUMENT.value
        )
        supporting = next(
            document
            for document in payload["documents"]
            if document["role"] == EvidenceRole.SUPPORTING_DOCUMENT.value
        )
        primary_item_id = f"{primary['evidence_id']}:ITEM-001"
        supporting_item_id = f"{supporting['evidence_id']}:ITEM-001"
        return ConflictAnalysis(
            applicability="APPLICABLE",
            applicability_reason="Hóa đơn mua hàng có phiếu nhập kho.",
            document_facts=[
                InventoryDocumentFacts(
                    evidence_id=primary["evidence_id"],
                    document_type="E_INVOICE",
                    supplier_tax_code="4400995188",
                    document_date="2026-09-19",
                    receipt_status="NOT_APPLICABLE",
                    items=[
                        InventoryLineItemFact(
                            item_id=primary_item_id,
                            raw_name="Củ sắn tươi",
                            quantity="25992",
                            unit="kg",
                            unit_price="3300",
                            line_amount="85773600",
                            source_refs=[primary["evidence_id"]],
                        )
                    ],
                ),
                InventoryDocumentFacts(
                    evidence_id=supporting["evidence_id"],
                    document_type="GOODS_RECEIPT",
                    supplier_tax_code="4400995188",
                    document_date="2026-09-19",
                    receipt_status="RECEIVED_FULL",
                    items=[
                        InventoryLineItemFact(
                            item_id=supporting_item_id,
                            raw_name="Củ sắn tươi",
                            quantity=report_quantity,
                            unit="kg",
                            unit_price="3300",
                            line_amount=report_amount,
                            source_refs=[supporting["evidence_id"]],
                        )
                    ],
                ),
            ],
            suggested_item_matches=[
                InventoryItemMatch(
                    primary_item_id=primary_item_id,
                    supporting_item_id=supporting_item_id,
                    semantic_match=True,
                    reason="Hai nguồn cùng ghi củ sắn tươi.",
                )
            ],
        )

    return build


def test_missing_bill_stops_before_ocr_and_agents(tmp_path: Path) -> None:
    case_id, repository = _save_case(
        tmp_path,
        body="Tiếp khách dự án Phoenix",
        uploads=[],
    )
    ocr = FakeOcrAdapter()
    agent = FakeQualityAdapter()

    result = CaseProcessingService(repository, ocr, agent).process_case(case_id)

    assert result.decision == ProcessingDecision.NEEDS_HUMAN
    assert result.findings[0].rule_id == "MISSING_BILL_EVIDENCE"
    assert ocr.calls == []
    assert agent.confidence_calls == []


def test_missing_business_context_stops_before_ocr_and_agents(tmp_path: Path) -> None:
    case_id, repository = _save_case(
        tmp_path,
        body="",
        uploads=[_upload("bill.jpg", EvidenceRole.PRIMARY_DOCUMENT)],
    )
    ocr = FakeOcrAdapter()
    agent = FakeQualityAdapter()

    result = CaseProcessingService(repository, ocr, agent).process_case(case_id)

    assert result.decision == ProcessingDecision.NEEDS_HUMAN
    assert result.findings[0].rule_id == "MISSING_BUSINESS_CONTEXT"
    assert ocr.calls == []
    assert agent.confidence_calls == []


def test_complete_case_skips_confidence_agent_but_runs_conflict_agent(
    tmp_path: Path,
) -> None:
    case_id, repository = _save_case(
        tmp_path,
        body="Mua thiết bị cho dự án Phoenix",
        uploads=[_upload("bill.jpg", EvidenceRole.PRIMARY_DOCUMENT)],
    )
    ocr = FakeOcrAdapter()
    agent = FakeQualityAdapter()

    result = CaseProcessingService(repository, ocr, agent).process_case(case_id)

    assert result.decision == ProcessingDecision.PASS
    assert len(ocr.calls) == 1
    assert agent.confidence_calls == []
    assert len(agent.conflict_calls) == 1
    assert result.confidence_analysis is None


def test_non_critical_low_confidence_block_can_continue(tmp_path: Path) -> None:
    case_id, repository = _save_case(
        tmp_path,
        body="Ăn uống phục vụ tiếp khách công ty ABC",
        uploads=[_upload("bill.jpg", EvidenceRole.PRIMARY_DOCUMENT)],
    )
    ocr = FakeOcrAdapter("Chúc quý khách ngon miệng")
    agent = FakeQualityAdapter(confidence_importance="NON_CRITICAL")

    result = CaseProcessingService(repository, ocr, agent).process_case(case_id)

    assert result.decision == ProcessingDecision.PASS
    assert len(result.low_confidence_candidates) == 1
    assert len(agent.confidence_calls) == 1
    assert len(agent.conflict_calls) == 1
    assert result.confidence_analysis is not None


def test_uncertain_critical_low_confidence_block_asks_human(tmp_path: Path) -> None:
    case_id, repository = _save_case(
        tmp_path,
        body="Mua vật tư cho dự án Phoenix",
        uploads=[_upload("bill.jpg", EvidenceRole.PRIMARY_DOCUMENT)],
    )
    ocr = FakeOcrAdapter("Amount Due: 1,200,000")
    agent = FakeQualityAdapter(
        confidence_importance="CRITICAL",
        confidence_quality="UNCERTAIN",
    )

    result = CaseProcessingService(repository, ocr, agent).process_case(case_id)

    assert result.decision == ProcessingDecision.NEEDS_HUMAN
    assert "Vui lòng kiểm tra" in result.reasoning
    assert "bill.jpg" in result.reasoning
    assert "EV-" not in result.reasoning
    assert "block" not in result.reasoning.lower()
    assert "confidence" not in result.reasoning.lower()
    assert any(
        item.rule_id == "LOW_CONFIDENCE_ASK_HUMAN"
        for item in result.findings
    )
    assert agent.conflict_calls == []


def test_readable_critical_low_confidence_block_can_continue(tmp_path: Path) -> None:
    case_id, repository = _save_case(
        tmp_path,
        body="Mua vật tư cho dự án Phoenix",
        uploads=[_upload("bill.jpg", EvidenceRole.PRIMARY_DOCUMENT)],
    )
    ocr = FakeOcrAdapter("Tổng thanh toán: 1.200.000")
    agent = FakeQualityAdapter(
        confidence_importance="CRITICAL",
        confidence_quality="READABLE",
    )

    result = CaseProcessingService(repository, ocr, agent).process_case(case_id)

    assert result.decision == ProcessingDecision.PASS
    assert len(agent.conflict_calls) == 1
    assert any(
        item.rule_id == "OCR_CONFIDENCE_REVIEW" and item.status == "PASS"
        for item in result.findings
    )


def test_semantically_readable_item_name_does_not_block_extraction(
    tmp_path: Path,
) -> None:
    case_id, repository = _save_case(
        tmp_path,
        body="Ăn uống phục vụ tiếp khách công ty ABC",
        uploads=[_upload("bill.jpg", EvidenceRole.PRIMARY_DOCUMENT)],
    )
    ocr = FakeOcrAdapter("Helineken 24.000 864.000")
    agent = FakeQualityAdapter(
        confidence_importance="NON_CRITICAL",
        confidence_quality="SEMANTICALLY_READABLE",
        confidence_action="CONTINUE",
        semantic_category="ALCOHOL",
    )

    result = CaseProcessingService(repository, ocr, agent).process_case(case_id)

    assert result.decision == ProcessingDecision.PASS
    assert any(
        item.rule_id == "OCR_CONFIDENCE_REVIEW" and item.status == "PASS"
        for item in result.findings
    )
    assert len(agent.conflict_calls) == 1


def test_unassessed_low_confidence_block_fails_closed(tmp_path: Path) -> None:
    case_id, repository = _save_case(
        tmp_path,
        body="Chi phí vận hành cửa hàng",
        uploads=[_upload("bill.jpg", EvidenceRole.PRIMARY_DOCUMENT)],
    )
    ocr = FakeOcrAdapter("Tổng cộng: 900.000")
    agent = FakeQualityAdapter(omit_confidence_assessments=True)

    result = CaseProcessingService(repository, ocr, agent).process_case(case_id)

    assert result.decision == ProcessingDecision.NEEDS_HUMAN
    assert any(
        item.rule_id == "LOW_CONFIDENCE_BLOCK_UNKNOWN"
        for item in result.findings
    )
    assert agent.conflict_calls == []


def test_two_sources_run_independent_ocr_and_confidence_before_one_conflict_call(
    tmp_path: Path,
) -> None:
    case_id, repository = _save_case(
        tmp_path,
        body="",
        uploads=[
            _upload("bill.jpg", EvidenceRole.PRIMARY_DOCUMENT),
            _upload("report.jpg", EvidenceRole.SUPPORTING_DOCUMENT),
        ],
    )
    ocr = FakeOcrAdapter("Thank you for your business")
    agent = FakeQualityAdapter(confidence_importance="NON_CRITICAL")

    result = CaseProcessingService(repository, ocr, agent).process_case(case_id)

    assert result.decision == ProcessingDecision.PASS
    assert [path.name.split("__", 1)[1] for path in ocr.calls] == [
        "bill.jpg",
        "report.jpg",
    ]
    assert len(agent.confidence_calls) == 2
    assert all("evidence" in payload for payload in agent.confidence_calls)
    assert all("documents" not in payload for payload in agent.confidence_calls)
    assert all("business_context" not in payload for payload in agent.confidence_calls)
    assert [
        payload["evidence"]["filename"] for payload in agent.confidence_calls
    ] == ["bill.jpg", "report.jpg"]
    assert len(agent.conflict_calls) == 1
    assert len(agent.conflict_calls[0]["documents"]) == 2
    assert "business_context" in agent.conflict_calls[0]
    assert len(result.low_confidence_candidates) == 2


def test_one_unclear_evidence_stops_before_cross_source_conflict(tmp_path: Path) -> None:
    case_id, repository = _save_case(
        tmp_path,
        body="Đã nhận đủ hàng cho dự án Phoenix.",
        uploads=[
            _upload("bill.jpg", EvidenceRole.PRIMARY_DOCUMENT),
            _upload("report.jpg", EvidenceRole.SUPPORTING_DOCUMENT),
        ],
    )
    agent = FakeQualityAdapter(blocking_filename="report.jpg")

    result = CaseProcessingService(
        repository,
        FakeOcrAdapter("Tổng tiền: 1.200.000"),
        agent,
    ).process_case(case_id)

    assert result.decision == ProcessingDecision.NEEDS_HUMAN
    assert len(agent.confidence_calls) == 2
    assert agent.conflict_calls == []
    quality = {item.filename: item.status for item in result.evidence_quality}
    assert quality == {"bill.jpg": "CLEAR", "report.jpg": "NEEDS_HUMAN"}


def test_inventory_policy_runs_after_clear_confidence_and_passes_happy_case(
    tmp_path: Path,
) -> None:
    case_id, repository = _save_case(
        tmp_path,
        body="Lô củ sắn ngày 19/09/2026 đã được kho nhận đủ.",
        uploads=[
            _upload("mua_san.pdf", EvidenceRole.PRIMARY_DOCUMENT),
            _upload("Phieu_nhap_kho.pdf", EvidenceRole.SUPPORTING_DOCUMENT),
        ],
    )
    agent = FakeQualityAdapter(
        conflict_factory=_conflict_factory(
            report_quantity="25992",
            report_amount="85773600",
        )
    )

    result = CaseProcessingService(
        repository,
        FakeOcrAdapter(),
        agent,
    ).process_case(case_id)

    assert result.decision == ProcessingDecision.PASS
    assert len(agent.conflict_calls) == 1
    assert result.conflict_analysis is not None
    assert any(
        finding.rule_id == "INVENTORY_CONSISTENCY"
        for finding in result.findings
    )


def test_inventory_policy_routes_unhappy_case_to_accountant(
    tmp_path: Path,
) -> None:
    case_id, repository = _save_case(
        tmp_path,
        body="Lô củ sắn ngày 19/09/2026 đã được kho nhận đủ.",
        uploads=[
            _upload("mua_san.pdf", EvidenceRole.PRIMARY_DOCUMENT),
            _upload("Phieu_nhap_kho_2.pdf", EvidenceRole.SUPPORTING_DOCUMENT),
        ],
    )
    agent = FakeQualityAdapter(
        conflict_factory=_conflict_factory(
            report_quantity="2",
            report_amount="92828283",
        )
    )

    result = CaseProcessingService(
        repository,
        FakeOcrAdapter(),
        agent,
    ).process_case(case_id)

    assert result.decision == ProcessingDecision.NEEDS_HUMAN
    assert "25992" in result.reasoning
    assert "2" in result.reasoning
    rule_ids = {finding.rule_id for finding in result.findings}
    assert "INVENTORY_QUANTITY_MISMATCH" in rule_ids
    assert "INVENTORY_LINE_AMOUNT_MISMATCH" in rule_ids


def test_inventory_policy_repairs_one_semantically_incomplete_response(
    tmp_path: Path,
) -> None:
    case_id, repository = _save_case(
        tmp_path,
        body="Lô củ sắn ngày 19/09/2026 đã được kho nhận đủ.",
        uploads=[
            _upload("mua_san.pdf", EvidenceRole.PRIMARY_DOCUMENT),
            _upload("Phieu_nhap_kho.pdf", EvidenceRole.SUPPORTING_DOCUMENT),
        ],
    )
    complete_factory = _conflict_factory(
        report_quantity="25992",
        report_amount="85773600",
    )
    attempts = 0

    def incomplete_then_complete(payload: dict) -> ConflictAnalysis:
        nonlocal attempts
        attempts += 1
        analysis = complete_factory(payload)
        if attempts == 1:
            analysis.document_facts = analysis.document_facts[:1]
        return analysis

    agent = FakeQualityAdapter(conflict_factory=incomplete_then_complete)

    result = CaseProcessingService(
        repository,
        FakeOcrAdapter(),
        agent,
    ).process_case(case_id)

    assert result.decision == ProcessingDecision.PASS
    assert len(agent.conflict_calls) == 2
    repair_request = agent.conflict_calls[1]["repair_request"]
    assert len(repair_request["missing_evidence_ids"]) == 1
    assert repair_request["required_documents"][1]["filename"] == (
        "Phieu_nhap_kho.pdf"
    )
    assert any(
        finding.rule_id == "INVENTORY_CONSISTENCY"
        for finding in result.findings
    )


def test_unclear_tax_rate_with_clear_zero_tax_does_not_block_inventory() -> None:
    candidate = {
        "candidate_id": "EV-001:page-0-block-10",
        "source_file": "bill_nong_san.pdf",
        "content": "Thuế suất GTGT: KKKNT\nTiền thuế GTGT: 0đ",
    }
    assessment = BlockAssessment(
        candidate_id=candidate["candidate_id"],
        importance="CRITICAL",
        quality_state="UNCERTAIN",
        review_action="ASK_HUMAN",
        canonical_fields=["tax_rate", "tax_amount"],
        observed_text="Thuế suất GTGT: KKKNT / Tiền thuế GTGT: 0đ",
        reason="Thuế suất chưa đọc được.",
        human_question="Vui lòng xác nhận thuế suất.",
    )

    findings = CaseProcessingService._confidence_findings(
        [candidate],
        ConfidenceAnalysis(block_assessments=[assessment]),
    )

    assert assessment.review_action == "ASK_HUMAN"
    assert assessment.semantic_category is None
    assert assessment.human_question is not None
    assert findings[0].rule_id == "OCR_NON_BLOCKING_QUALITY_WARNING"
    assert findings[0].status == "WARN"
