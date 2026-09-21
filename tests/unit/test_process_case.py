from pathlib import Path

from invoice_referee.application import CaseProcessingService
from invoice_referee.domain import (
    BlockAssessment,
    ClaimDraft,
    ConfidenceAnalysis,
    EvidenceRole,
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
        omit_confidence_assessments: bool = False,
    ) -> None:
        self.confidence_importance = confidence_importance
        self.confidence_quality = confidence_quality
        self.confidence_action = confidence_action
        self.semantic_category = semantic_category
        self.omit_confidence_assessments = omit_confidence_assessments
        self.confidence_calls: list[dict] = []

    def analyze_confidence(self, payload: dict) -> ConfidenceAnalysis:
        self.confidence_calls.append(payload)
        if self.omit_confidence_assessments:
            return ConfidenceAnalysis()
        candidates = [
            candidate
            for document in payload["documents"]
            for candidate in document["candidate_blocks"]
        ]
        review_action = self.confidence_action
        if review_action is None:
            review_action = (
                "ASK_HUMAN"
                if self.confidence_importance == "CRITICAL"
                and self.confidence_quality not in {"READABLE", "SEMANTICALLY_READABLE"}
                else "CONTINUE"
            )
        return ConfidenceAnalysis(
            document_types={
                document["evidence_id"]: "PAPER_RECEIPT"
                for document in payload["documents"]
            },
            block_assessments=[
                BlockAssessment(
                    candidate_id=candidate["candidate_id"],
                    importance=self.confidence_importance,
                    quality_state=self.confidence_quality,
                    review_action=review_action,
                    canonical_fields=(
                        ["total_amount"]
                        if self.confidence_importance == "CRITICAL"
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


def test_complete_case_skips_kimi_without_low_confidence_candidates(
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
    assert any(
        item.rule_id == "OCR_CONFIDENCE_REVIEW" and item.status == "PASS"
        for item in result.findings
    )


def test_semantically_readable_policy_signal_does_not_block_extraction(
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
        confidence_action="DEFER_TO_POLICY",
        semantic_category="ALCOHOL",
    )

    result = CaseProcessingService(repository, ocr, agent).process_case(case_id)

    assert result.decision == ProcessingDecision.PASS
    assert "chính sách chi phí" in result.summary
    assert any(
        item.rule_id == "OCR_POLICY_SIGNAL" and item.status == "WARN"
        for item in result.findings
    )
    assert result.reasoning.startswith("Chứng từ vẫn có thể tiếp tục xử lý")


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


def test_two_sources_run_ocr_independently_and_batch_each_agent_stage(
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
    assert len(agent.confidence_calls) == 1
    assert len(agent.confidence_calls[0]["documents"]) == 2
    assert len(result.low_confidence_candidates) == 2
