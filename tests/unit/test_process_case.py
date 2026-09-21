from pathlib import Path

from invoice_referee.application import CaseProcessingService
from invoice_referee.domain import (
    ClaimDraft,
    EvidenceRole,
    KimiAnalysis,
    ProcessingDecision,
    UploadPayload,
)
from invoice_referee.extraction import OcrExecution
from invoice_referee.storage import LocalCaseStore, LocalEvidenceRepository


class FakeOcrAdapter:
    def __init__(self) -> None:
        self.calls: list[Path] = []

    def process(self, file_path: Path, mime_type: str) -> OcrExecution:
        self.calls.append(file_path)
        return OcrExecution(
            provider="mistral",
            model="mistral-ocr-latest",
            processed_at="2026-09-21T10:00:00+07:00",
            response={
                "pages": [
                    {
                        "index": 0,
                        "markdown": f"OCR {file_path.name}",
                        "blocks": [],
                        "confidence_scores": {"word_confidence_scores": []},
                    }
                ]
            },
        )


class FakeKimiAdapter:
    def __init__(self, analysis: KimiAnalysis) -> None:
        self.analysis = analysis
        self.calls: list[dict] = []

    def analyze(self, payload: dict) -> KimiAnalysis:
        self.calls.append(payload)
        return self.analysis


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


def test_missing_bill_stops_before_ocr_and_kimi(tmp_path: Path) -> None:
    case_id, repository = _save_case(
        tmp_path,
        body="Tiếp khách dự án Phoenix",
        uploads=[],
    )
    ocr = FakeOcrAdapter()
    kimi = FakeKimiAdapter(
        KimiAnalysis(
            business_context_present=True,
            conflict_detected=False,
            summary="unused",
            reasoning="unused",
        )
    )

    result = CaseProcessingService(repository, ocr, kimi).process_case(case_id)

    assert result.decision == ProcessingDecision.NEEDS_HUMAN
    assert result.findings[0].rule_id == "MISSING_BILL_EVIDENCE"
    assert ocr.calls == []
    assert kimi.calls == []


def test_complete_case_runs_ocr_then_kimi_once_and_passes(tmp_path: Path) -> None:
    case_id, repository = _save_case(
        tmp_path,
        body="Mua thiết bị cho dự án Phoenix",
        uploads=[_upload("bill.jpg", EvidenceRole.PRIMARY_DOCUMENT)],
    )
    ocr = FakeOcrAdapter()
    kimi = FakeKimiAdapter(
        KimiAnalysis(
            business_context_present=True,
            conflict_detected=False,
            summary="Hồ sơ đủ dữ liệu.",
            reasoning="Bill phù hợp với mục đích mua thiết bị.",
        )
    )

    result = CaseProcessingService(repository, ocr, kimi).process_case(case_id)

    assert result.decision == ProcessingDecision.PASS
    assert len(ocr.calls) == 1
    assert len(kimi.calls) == 1
    assert len(kimi.calls[0]["documents"]) == 1
    assert repository.load_processing_result(case_id)["decision"] == "PASS"
    evidence = repository.get_case(case_id).evidence[0]
    assert repository.load_ocr_result(evidence) is not None


def test_two_image_sources_run_independently_before_one_kimi_call(
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
    ocr = FakeOcrAdapter()
    kimi = FakeKimiAdapter(
        KimiAnalysis(
            business_context_present=True,
            conflict_detected=True,
            summary="Hai nguồn không thống nhất.",
            reasoning="Số tiền trên bill khác số tiền trong report.",
            conflicts=[{"field": "total_amount"}],
        )
    )

    result = CaseProcessingService(repository, ocr, kimi).process_case(case_id)

    assert result.decision == ProcessingDecision.NEEDS_HUMAN
    assert [path.name.split("__", 1)[1] for path in ocr.calls] == [
        "bill.jpg",
        "report.jpg",
    ]
    assert len(kimi.calls) == 1
    assert len(kimi.calls[0]["documents"]) == 2
    assert any(
        finding.rule_id == "BILL_CONTEXT_CONFLICT"
        and finding.status == "FAIL"
        for finding in result.findings
    )
