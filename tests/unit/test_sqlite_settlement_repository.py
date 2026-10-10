from decimal import Decimal
from pathlib import Path

import pytest

from invoice_referee.application import (
    ReviewSettlementService,
    SettlementProcessingService,
    SubmitSettlementService,
)
from invoice_referee.domain import (
    BlockAssessment,
    BusinessContext,
    ConfidenceAnalysis,
    ExpenseCategory,
    ExpenseDocumentFacts,
    ExpenseItemDraft,
    SettlementDocumentRole,
    SettlementDraft,
    SettlementType,
    SettlementUpload,
    SubmissionSourceType,
)
from invoice_referee.extraction import OcrExecution
from invoice_referee.storage import SQLiteSettlementRepository


def _draft(filename: str = "bill.jpg") -> SettlementDraft:
    return SettlementDraft(
        settlement_type=SettlementType.EMPLOYEE_REIMBURSEMENT,
        source_type=SubmissionSourceType.DIGITAL_FORM,
        business_context=BusinessContext(purpose="Tiếp khách dự án Demo"),
        expense_items=[
            ExpenseItemDraft(
                item_id="ITEM-001",
                category=ExpenseCategory.CLIENT_MEAL,
                description="Bữa trưa với khách hàng",
                claimed_amount=Decimal("1200000"),
                evidence_names=[filename],
            )
        ],
    )


def _upload(filename: str = "bill.jpg") -> SettlementUpload:
    return SettlementUpload(
        original_name=filename,
        content=b"same-bill-content",
        mime_type="image/jpeg",
        role=SettlementDocumentRole.EXPENSE_EVIDENCE,
        linked_item_id="ITEM-001",
    )


class _ClearOcr:
    def process(self, _path, _mime_type):
        return OcrExecution(
            provider="fake",
            model="fake-ocr",
            processed_at="2026-10-10T10:00:00+07:00",
            response={
                "pages": [
                    {
                        "index": 0,
                        "markdown": "Tổng thanh toán: 1.200.000",
                        "confidence_scores": {
                            "word_confidence_scores": [
                                {
                                    "text": "Tổng thanh toán: 1.200.000",
                                    "confidence": 0.99,
                                    "start_index": 0,
                                }
                            ]
                        },
                        "blocks": [
                            {
                                "type": "text",
                                "content": "Tổng thanh toán: 1.200.000",
                                "top_left_x": 0,
                                "top_left_y": 0,
                                "bottom_right_x": 100,
                                "bottom_right_y": 20,
                            }
                        ],
                    }
                ]
            },
        )


class _ExpenseExtractor:
    def __init__(self, total: str = "1200000") -> None:
        self.total = Decimal(total)

    def extract_expense_document(self, payload):
        return ExpenseDocumentFacts(
            document_id=payload["document_id"],
            document_type="PAPER_RECEIPT",
            issuer_name="Nhà hàng Demo",
            total_amount=self.total,
            source_refs=[f"DOC:{payload['document_id']}"],
        )


class _LowConfidenceOcr:
    def process(self, _path, _mime_type):
        return OcrExecution(
            provider="fake",
            model="fake-ocr",
            processed_at="2026-10-10T10:00:00+07:00",
            response={
                "pages": [
                    {
                        "index": 0,
                        "dimensions": {"width": 1000, "height": 2000},
                        "markdown": "Tổng thanh toán: 1.2O0.000",
                        "confidence_scores": {
                            "word_confidence_scores": [
                                {
                                    "text": "Tổng thanh toán: ",
                                    "confidence": 0.99,
                                    "start_index": 0,
                                },
                                {
                                    "text": "1.2O0.000",
                                    "confidence": 0.61,
                                    "start_index": 17,
                                },
                            ]
                        },
                        "blocks": [
                            {
                                "type": "text",
                                "content": "Tổng thanh toán: 1.2O0.000",
                                "top_left_x": 500,
                                "top_left_y": 1500,
                                "bottom_right_x": 900,
                                "bottom_right_y": 1600,
                            }
                        ],
                    }
                ]
            },
        )


class _BlockingConfidenceReasoner:
    def analyze_confidence(self, payload):
        candidate_id = payload["evidence"]["candidate_blocks"][0]["candidate_id"]
        return ConfidenceAnalysis(
            block_assessments=[
                BlockAssessment(
                    candidate_id=candidate_id,
                    importance="CRITICAL",
                    quality_state="UNCERTAIN",
                    review_action="ASK_HUMAN",
                    canonical_fields=["total_amount"],
                    reason="Tổng thanh toán không đọc chắc chắn.",
                    human_question="Vui lòng xác nhận tổng thanh toán.",
                )
            ]
        )


def test_repository_persists_case_processes_job_and_audit(tmp_path: Path) -> None:
    repository = SQLiteSettlementRepository(
        tmp_path / "invoice_referee.sqlite3",
        tmp_path / "cases",
        id_factory=lambda: "SET-TEST-001",
    )
    receipt = SubmitSettlementService(repository).submit(_draft(), [_upload()])

    assert receipt.processing_status == "PENDING"
    assert SettlementProcessingService(repository).run_once() is True

    case = repository.get_case(receipt.case_id)
    assert case["automation_decision"] == "AUTO_PROCESS"
    assert case["processing_status"] == "COMPLETED"
    assert case["expense_items"][0]["claimed_amount"] == "1200000"
    assert repository.document_path(
        receipt.case_id,
        case["documents"][0]["document_id"],
    ).read_bytes() == b"same-bill-content"
    assert [event["event_type"] for event in case["audit_events"]] == [
        "CASE_CREATED",
        "CASE_PROCESSED",
    ]


def test_same_document_in_later_case_is_escalated(tmp_path: Path) -> None:
    ids = iter(["SET-TEST-001", "SET-TEST-002"])
    repository = SQLiteSettlementRepository(
        tmp_path / "invoice_referee.sqlite3",
        tmp_path / "cases",
        id_factory=lambda: next(ids),
    )
    service = SubmitSettlementService(repository)
    processor = SettlementProcessingService(repository)

    service.submit(_draft(), [_upload()])
    processor.run_once()
    second = service.submit(_draft(filename="bill-copy.jpg"), [_upload("bill-copy.jpg")])
    processor.run_once()

    case = repository.get_case(second.case_id)
    assert case["automation_decision"] == "ESCALATE"
    assert case["uncertainty_type"] == "SUSPICIOUS"
    assert case["primary_finding_code"] == "SET_DUP_001"


def test_accountant_override_is_versioned_and_audited(tmp_path: Path) -> None:
    repository = SQLiteSettlementRepository(
        tmp_path / "invoice_referee.sqlite3",
        tmp_path / "cases",
        id_factory=lambda: "SET-TEST-REVIEW",
    )
    receipt = SubmitSettlementService(repository).submit(_draft(), [_upload()])
    SettlementProcessingService(repository).run_once()

    ReviewSettlementService(repository).record_action(
        case_id=receipt.case_id,
        action_type="OVERRIDE_DECISION",
        reason="Cần xác minh thêm hợp đồng với khách hàng.",
        override_decision="REQUEST_INFO",
    )

    case = repository.get_case(receipt.case_id)
    assert case["automation_decision"] == "REQUEST_INFO"
    assert case["decision"]["primary_finding_code"] == "HUMAN_OVERRIDE"
    assert case["human_actions"][0]["previous_decision"] == "AUTO_PROCESS"
    assert case["audit_events"][-1]["event_type"] == "OVERRIDE_DECISION"


def test_document_pipeline_extracts_and_reconciles_total(tmp_path: Path) -> None:
    repository = SQLiteSettlementRepository(
        tmp_path / "invoice_referee.sqlite3",
        tmp_path / "cases",
        id_factory=lambda: "SET-TEST-PIPELINE",
    )
    receipt = SubmitSettlementService(repository).submit(_draft(), [_upload()])
    processor = SettlementProcessingService(
        repository,
        ocr_adapter=_ClearOcr(),
        reasoning_adapter=_ExpenseExtractor(),
        enable_document_pipeline=True,
    )

    processor.run_once()

    case = repository.get_case(receipt.case_id)
    assert case["automation_decision"] == "AUTO_PROCESS"
    assert any(
        finding["rule_id"] == "SET_TOTAL_001"
        and finding["status"] == "PASS"
        for finding in case["findings"]
    )
    document_id = case["documents"][0]["document_id"]
    assert case["decision"]["source_refs"] == [f"DOC:{document_id}"]
    queue_item = repository.list_cases()[0]
    assert "vượt qua các kiểm tra bắt buộc" in queue_item["decision_reason"]
    assert (
        tmp_path / "cases" / receipt.case_id / "ocr" / f"{document_id}.json"
    ).exists()
    assert (
        tmp_path / "cases" / receipt.case_id / "facts" / f"{document_id}.json"
    ).exists()


def test_document_total_mismatch_requests_employee_confirmation(
    tmp_path: Path,
) -> None:
    repository = SQLiteSettlementRepository(
        tmp_path / "invoice_referee.sqlite3",
        tmp_path / "cases",
        id_factory=lambda: "SET-TEST-MISMATCH",
    )
    receipt = SubmitSettlementService(repository).submit(_draft(), [_upload()])
    processor = SettlementProcessingService(
        repository,
        ocr_adapter=_ClearOcr(),
        reasoning_adapter=_ExpenseExtractor(total="1000000"),
        enable_document_pipeline=True,
    )

    processor.run_once()

    case = repository.get_case(receipt.case_id)
    assert case["automation_decision"] == "REQUEST_INFO"
    assert case["primary_finding_code"] == "SET_TOTAL_001"


def test_low_confidence_finding_keeps_block_reference_for_visual_review(
    tmp_path: Path,
) -> None:
    repository = SQLiteSettlementRepository(
        tmp_path / "invoice_referee.sqlite3",
        tmp_path / "cases",
        id_factory=lambda: "SET-TEST-LOW-CONFIDENCE",
    )
    receipt = SubmitSettlementService(repository).submit(_draft(), [_upload()])
    processor = SettlementProcessingService(
        repository,
        ocr_adapter=_LowConfidenceOcr(),
        reasoning_adapter=_BlockingConfidenceReasoner(),
        enable_document_pipeline=True,
    )

    processor.run_once()

    case = repository.get_case(receipt.case_id)
    document_id = case["documents"][0]["document_id"]
    expected_ref = f"DOC:{document_id}:page-0-block-0"
    quality = next(
        finding
        for finding in case["findings"]
        if finding["rule_id"] == "SET_QUALITY_001"
    )
    assert quality["source_refs"] == [expected_ref]
    assert case["decision"]["source_refs"] == [expected_ref]


def test_accountant_can_requeue_existing_case_without_resubmission(
    tmp_path: Path,
) -> None:
    repository = SQLiteSettlementRepository(
        tmp_path / "invoice_referee.sqlite3",
        tmp_path / "cases",
        id_factory=lambda: "SET-TEST-REPROCESS",
    )
    receipt = SubmitSettlementService(repository).submit(_draft(), [_upload()])
    processor = SettlementProcessingService(repository)
    processor.run_once()

    ReviewSettlementService(repository).record_action(
        case_id=receipt.case_id,
        action_type="REPROCESS_CASE",
        reason="Đã cập nhật cấu hình endpoint Kimi.",
    )

    queued = repository.get_case(receipt.case_id)
    assert queued["processing_status"] == "PENDING"
    assert queued["automation_decision"] is None
    assert queued["decision"] is None
    assert repository.list_cases()[0]["decision_reason"] is None
    assert processor.run_once() is True
    completed = repository.get_case(receipt.case_id)
    assert completed["processing_status"] == "COMPLETED"
    assert completed["audit_events"][-2]["event_type"] == "REPROCESS_CASE"


def test_delete_case_removes_database_records_artifacts_and_duplicate_history(
    tmp_path: Path,
) -> None:
    ids = iter(["SET-DELETE-001", "SET-DELETE-002"])
    repository = SQLiteSettlementRepository(
        tmp_path / "invoice_referee.sqlite3",
        tmp_path / "cases",
        id_factory=lambda: next(ids),
    )
    service = SubmitSettlementService(repository)
    first = service.submit(_draft(), [_upload()])
    first_case_dir = tmp_path / "cases" / first.case_id

    repository.delete_case(first.case_id)

    assert repository.list_cases() == []
    assert not first_case_dir.exists()
    with pytest.raises(FileNotFoundError):
        repository.get_case(first.case_id)

    second = service.submit(_draft(), [_upload()])
    assert repository.find_case_duplicate_documents(second.case_id) == []


def test_delete_case_rejects_unsafe_case_id(tmp_path: Path) -> None:
    repository = SQLiteSettlementRepository(
        tmp_path / "invoice_referee.sqlite3",
        tmp_path / "cases",
    )

    with pytest.raises(ValueError, match="Mã hồ sơ không hợp lệ"):
        repository.delete_case("../outside")
