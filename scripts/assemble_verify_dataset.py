"""Assemble the locked 5-case benchmark dataset under data/verify/.

Cases:
- TC01: Routine, COLLECT 760000, no issues
- TC02: Routine, PAY 400000, no issues
- VFY-BAL-01: Synthetic Routine balanced (2.160.000 cost = 2.160.000 advance), no instruction
- TC06: FACT routing (discrepancy 60.000 between calculated 830k and declared 770k)
- TC04: AUTHORITY routing (83.6M exceeds approver authority limit 20M)
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from invoice_referee.evaluation.models import (
    AllowedGold,
    GoldPacket,
    LatentGold,
    ManifestEntry,
    ObservableGold,
    OrganizationContext,
    PacketMetadata,
    Submission,
    Transcription,
    TranscriptionFact,
)
from scripts.generate_vfy_bal_01 import render_hoa_don_dien_tu, render_report_hoan_ung
VERIFY_DIR = PROJECT_ROOT / "data" / "verify"
CASES_DIR = VERIFY_DIR / "cases"
THAM_KHAO = PROJECT_ROOT / "data" / "tham-khao" / "uc-03"
DEMO_CASES = PROJECT_ROOT / "data" / "demo" / "cases"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _write_json(p: Path, obj: object) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, str):
        p.write_text(obj, encoding="utf-8")
    else:
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")



def _extract_pdf_pages(pdf_path: Path) -> list[dict[str, object]]:
    import pypdf
    reader = pypdf.PdfReader(pdf_path)
    return [
        {'page': idx + 1, 'markdown': page.extract_text(), 'blocks': []}
        for idx, page in enumerate(reader.pages)
    ]

def assemble_tc01() -> ManifestEntry:
    target = CASES_DIR / "tc01"
    src_dir = THAM_KHAO / "tc01-hop-le-nhan-vien-hoan-tra-tien-thua"
    ctx_path = DEMO_CASES / "tc01-hop-le-nhan-vien-hoan-tra-tien-thua" / "context.json"

    # 1. dau-vao
    dau_vao = target / "dau-vao" / "01-nop-ban-dau"
    dau_vao.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_dir / "report_hoan_ung.pdf", dau_vao / "report_hoan_ung.pdf")
    shutil.copy2(src_dir / "hoa_don_dien_tu.pdf", dau_vao / "hoa_don_dien_tu.pdf")

    # 2. cau-hinh
    cau_hinh = target / "cau-hinh"
    cau_hinh.mkdir(parents=True, exist_ok=True)
    org_ctx = OrganizationContext.model_validate_json(ctx_path.read_text(encoding="utf-8"))
    _write_json(cau_hinh / "to-chuc.json", json.loads(org_ctx.model_dump_json()))

    submission = Submission(
        employee="employee:employee-a",
        activity="activity:tc01",
        declared_purpose="Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026",
    )
    _write_json(cau_hinh / "khai-bao.json", json.loads(submission.model_dump_json()))
    _write_json(cau_hinh / "kich-ban.json", {"case_id": "TC01", "slug": "tc01-hop-le-nhan-vien-hoan-tra-tien-thua"})

    transcription = Transcription(
        data_origin="STUB_TRANSCRIPTION",
        facts=(
            TranscriptionFact(field="incurred", value=3240000, role="INVOICE", quote="Tổng cộng tiền thanh toán: 3.240.000"),
            TranscriptionFact(field="paid_employee", value=3240000, role="PAYMENT", quote="Người thanh toán: NGUYỄN MINH AN"),
            TranscriptionFact(field="advance", value=4000000, role="ADVANCE", quote="Số tiền đã tạm ứng: 4.000.000 đồng"),
            TranscriptionFact(field="coverage", value=1, role="LEDGER", quote="Đối chiếu đủ chứng từ"),
            TranscriptionFact(field="economic_key", value="invoice:00000101", role="INVOICE", quote="Số: 00000101"),
        ),
    )
    _write_json(cau_hinh / "ban-doc-stub.json", json.loads(transcription.model_dump_json()))

    # 3. dap-an
    dap_an = target / "dap-an"
    dap_an.mkdir(parents=True, exist_ok=True)
    _write_json(dap_an / "su-that-an.json", {
        "stages": {"ban-dau": {"facts": {"real_payer": "employee:employee-a", "advance_settlement_diff": 760000}}}
    })
    _write_json(dap_an / "quan-sat-duoc.json", {
        "stages": {"ban-dau": {"facts": {"incurred": 3240000, "paid_employee": 3240000, "advance": 4000000, "coverage": 1, "buyer_tax_code": "0319999996"}}}
    })
    _write_json(dap_an / "ket-qua-hop-le.json", {
        "stages": {"ban-dau": {
            "route": "AUTO",
            "expected_amounts": {"COLLECT": 760000},
            "owner": "employee:employee-a",
            "question_required": False
        }}
    })

    # 4. recordings for RECORDED_REPLAY
    recordings = target / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    rep_sha = _file_sha256(dau_vao / "report_hoan_ung.pdf")
    inv_sha = _file_sha256(dau_vao / "hoa_don_dien_tu.pdf")
    _write_json(recordings / "recording.json", {
        "case_id": "TC01",
        "data_origin": "SYNTHETIC_FIXTURE",
        "digests": {
            "report_hoan_ung.pdf": rep_sha,
            "hoa_don_dien_tu.pdf": inv_sha,
        },
        "ocr": {
            rep_sha: {"pages": _extract_pdf_pages(dau_vao / "report_hoan_ung.pdf"), "complete": True},
            inv_sha: {"pages": _extract_pdf_pages(dau_vao / "hoa_don_dien_tu.pdf"), "complete": True},
        },
        "extractions": {
            "paper": {
                "role_fit": "FIT",
                "actual_type": "SETTLEMENT_FORM",
                "fields": [
                    {"field": "declared_advance", "state": "FOUND", "value": 4000000, "quote": "4.000.000", "page": 1},
                    {"field": "printed_total", "state": "FOUND", "value": 3240000, "quote": "3.240.000", "page": 1},
                    {"field": "printed_return", "state": "FOUND", "value": 760000, "quote": "760.000", "page": 1},
                    {"field": "declared_name", "state": "FOUND", "value": "NGUYỄN MINH AN", "quote": "NGUYỄN MINH AN", "page": 1},
                    {"field": "purpose", "state": "FOUND", "value": "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026", "quote": "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026", "page": 1},
                ],
                "line_items": [
                    {"fields": [
                        {"field": "description", "state": "FOUND", "value": "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026", "quote": "Chi phí tiếp khách phục vụ dự án Nâng cấp văn\nphòng 2026", "page": 1},
                        {"field": "amount", "state": "FOUND", "value": 3240000, "quote": "3.240.000", "page": 1},
                        {"field": "invoice_refs", "state": "FOUND", "value": ["00000101"], "quote": "00000101", "page": 1},
                    ]}
                ]
            },
            "evidence": {
                "document_type": "E_INVOICE",
                "fields": [
                    {"field": "document_date", "state": "FOUND", "value": "2026-10-10", "quote": "Ngày 10 tháng 10 năm 2026", "page": 1},
                    {"field": "buyer_name", "state": "FOUND", "value": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH", "quote": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH", "page": 1},
                    {"field": "total_amount", "state": "FOUND", "value": 3240000, "quote": "3.240.000", "page": 1},
                    {"field": "tax", "state": "FOUND", "value": 240000, "quote": "240.000", "page": 1},
                    {"field": "subtotal", "state": "FOUND", "value": 3000000, "quote": "3.000.000", "page": 1},
                    {"field": "buyer_tax_code", "state": "FOUND", "value": "0319999996", "quote": "0319999996", "page": 1},
                    {"field": "issuer_name", "state": "FOUND", "value": "CÔNG TY TNHH THƯƠNG MẠI VÀ DỊCH VỤ MINH PHÁT", "quote": "CÔNG TY TNHH THƯƠNG MẠI VÀ DỊCH VỤ MINH PHÁT", "page": 1},
                    {"field": "document_number", "state": "FOUND", "value": "00000101", "quote": "00000101", "page": 1},
                ],
                "line_items": [
                    {"fields": [
                        {"field": "item_name", "state": "FOUND", "value": "Dịch vụ ăn uống tiếp khách", "quote": "Dịch vụ ăn uống tiếp khách", "page": 1},
                        {"field": "line_amount", "state": "FOUND", "value": 3000000, "quote": "3.000.000", "page": 1},
                    ]}
                ]
            }
        },
        "transcription": json.loads(transcription.model_copy(update={"data_origin": "SYNTHETIC_FIXTURE"}).model_dump_json()),
    })

    input_digest = hashlib.sha256(
        (org_ctx.model_dump_json() + submission.model_dump_json() + rep_sha + inv_sha).encode("utf-8")
    ).hexdigest()
    gold_digest = _file_sha256(dap_an / "su-that-an.json")

    return ManifestEntry(
        root_id="activity:tc01",
        split="development",
        strata="routine",
        profile="WORK_EXPENSE",
        economic_key="invoice:00000101",
        family="uc03",
        template="report_and_vat_invoice",
        layout="portrait_a4",
        issuer="0101234565",
        input_digest=input_digest,
        gold_digest=gold_digest,
    )


def assemble_tc02() -> ManifestEntry:
    target = CASES_DIR / "tc02"
    src_dir = THAM_KHAO / "tc02-hop-le-cong-ty-thanh-toan-them"
    ctx_path = DEMO_CASES / "tc02-hop-le-cong-ty-thanh-toan-them" / "context.json"

    # 1. dau-vao
    dau_vao = target / "dau-vao" / "01-nop-ban-dau"
    dau_vao.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_dir / "report_hoan_ung.pdf", dau_vao / "report_hoan_ung.pdf")
    shutil.copy2(src_dir / "hoa_don_dien_tu.pdf", dau_vao / "hoa_don_dien_tu.pdf")

    # 2. cau-hinh
    cau_hinh = target / "cau-hinh"
    cau_hinh.mkdir(parents=True, exist_ok=True)
    org_ctx = OrganizationContext.model_validate_json(ctx_path.read_text(encoding="utf-8"))
    _write_json(cau_hinh / "to-chuc.json", json.loads(org_ctx.model_dump_json()))

    submission = Submission(
        employee="employee:employee-a",
        activity="activity:tc02",
        declared_purpose="Mua thiết bị văn phòng phục vụ hoạt động công ty",
    )
    _write_json(cau_hinh / "khai-bao.json", json.loads(submission.model_dump_json()))
    _write_json(cau_hinh / "kich-ban.json", {"case_id": "TC02", "slug": "tc02-hop-le-cong-ty-thanh-toan-them"})

    transcription = Transcription(
        data_origin="STUB_TRANSCRIPTION",
        facts=(
            TranscriptionFact(field="incurred", value=5400000, role="INVOICE", quote="Tổng cộng: 5.400.000"),
            TranscriptionFact(field="paid_employee", value=5400000, role="PAYMENT", quote="Người thanh toán: NGUYỄN MINH AN"),
            TranscriptionFact(field="advance", value=5000000, role="ADVANCE", quote="Số tiền đã tạm ứng: 5.000.000 đồng"),
            TranscriptionFact(field="coverage", value=1, role="LEDGER", quote="Đối chiếu đủ chứng từ"),
            TranscriptionFact(field="economic_key", value="invoice:00000201", role="INVOICE", quote="Số: 00000201"),
        ),
    )
    _write_json(cau_hinh / "ban-doc-stub.json", json.loads(transcription.model_dump_json()))

    # 3. dap-an
    dap_an = target / "dap-an"
    dap_an.mkdir(parents=True, exist_ok=True)
    _write_json(dap_an / "su-that-an.json", {
        "stages": {"ban-dau": {"facts": {"real_payer": "employee:employee-a", "advance_settlement_diff": 400000}}}
    })
    _write_json(dap_an / "quan-sat-duoc.json", {
        "stages": {"ban-dau": {"facts": {"incurred": 5400000, "paid_employee": 5400000, "advance": 5000000, "coverage": 1, "buyer_tax_code": "0319999996"}}}
    })
    _write_json(dap_an / "ket-qua-hop-le.json", {
        "stages": {"ban-dau": {
            "route": "AUTO",
            "expected_amounts": {"PAY": 400000},
            "owner": "employee:employee-a",
            "question_required": False
        }}
    })

    # 4. recordings
    recordings = target / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    rep_sha = _file_sha256(dau_vao / "report_hoan_ung.pdf")
    inv_sha = _file_sha256(dau_vao / "hoa_don_dien_tu.pdf")
    _write_json(recordings / "recording.json", {
        "case_id": "TC02",
        "data_origin": "SYNTHETIC_FIXTURE",
        "digests": {
            "report_hoan_ung.pdf": rep_sha,
            "hoa_don_dien_tu.pdf": inv_sha,
        },
        "ocr": {
            rep_sha: {"pages": _extract_pdf_pages(dau_vao / "report_hoan_ung.pdf"), "complete": True},
            inv_sha: {"pages": _extract_pdf_pages(dau_vao / "hoa_don_dien_tu.pdf"), "complete": True},
        },
        "extractions": {
            "paper": {
                "role_fit": "FIT",
                "actual_type": "SETTLEMENT_FORM",
                "fields": [
                    {"field": "declared_advance", "state": "FOUND", "value": 5000000, "quote": "5.000.000", "page": 1},
                    {"field": "printed_total", "state": "FOUND", "value": 5400000, "quote": "5.400.000", "page": 1},
                    {"field": "printed_reimbursement", "state": "FOUND", "value": 400000, "quote": "400.000", "page": 1},
                    {"field": "declared_name", "state": "FOUND", "value": "NGUYỄN MINH AN", "quote": "NGUYỄN MINH AN", "page": 1},
                    {"field": "purpose", "state": "FOUND", "value": "Mua thiết bị văn phòng phục vụ hoạt động công ty", "quote": "Mua thiết bị văn phòng phục vụ hoạt động công ty", "page": 1},
                ],
                "line_items": [
                    {"fields": [
                        {"field": "description", "state": "FOUND", "value": "Mua thiết bị văn phòng phục vụ hoạt động công ty", "quote": "Mua thiết bị văn phòng phục vụ hoạt động công ty", "page": 1},
                        {"field": "amount", "state": "FOUND", "value": 5400000, "quote": "5.400.000", "page": 1},
                        {"field": "invoice_refs", "state": "FOUND", "value": ["00000201"], "quote": "00000201", "page": 1},
                    ]}
                ]
            },
            "evidence": {
                "document_type": "E_INVOICE",
                "fields": [
                    {"field": "document_date", "state": "FOUND", "value": "2026-10-10", "quote": "Ngày 10 tháng 10 năm 2026", "page": 1},
                    {"field": "buyer_name", "state": "FOUND", "value": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH", "quote": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH", "page": 1},
                    {"field": "total_amount", "state": "FOUND", "value": 5400000, "quote": "5.400.000", "page": 1},
                    {"field": "tax", "state": "FOUND", "value": 400000, "quote": "400.000", "page": 1},
                    {"field": "subtotal", "state": "FOUND", "value": 5000000, "quote": "5.000.000", "page": 1},
                    {"field": "buyer_tax_code", "state": "FOUND", "value": "0319999996", "quote": "0319999996", "page": 1},
                    {"field": "issuer_name", "state": "FOUND", "value": "CÔNG TY TNHH THƯƠNG MẠI VÀ DỊCH VỤ MINH PHÁT", "quote": "CÔNG TY TNHH THƯƠNG MẠI VÀ DỊCH VỤ MINH PHÁT", "page": 1},
                    {"field": "document_number", "state": "FOUND", "value": "00000201", "quote": "00000201", "page": 1},
                ],
                "line_items": [
                    {"fields": [
                        {"field": "item_name", "state": "FOUND", "value": "Máy in văn phòng", "quote": "Máy in văn phòng", "page": 1},
                        {"field": "line_amount", "state": "FOUND", "value": 5000000, "quote": "5.000.000", "page": 1},
                    ]}
                ]
            }
        },
        "transcription": json.loads(transcription.model_copy(update={"data_origin": "SYNTHETIC_FIXTURE"}).model_dump_json()),
    })

    input_digest = hashlib.sha256(
        (org_ctx.model_dump_json() + submission.model_dump_json() + rep_sha + inv_sha).encode("utf-8")
    ).hexdigest()
    gold_digest = _file_sha256(dap_an / "su-that-an.json")

    return ManifestEntry(
        root_id="activity:tc02",
        split="development",
        strata="routine",
        profile="WORK_EXPENSE",
        economic_key="invoice:00000201",
        family="uc03",
        template="report_and_vat_invoice",
        layout="portrait_a4",
        issuer="0101234565",
        input_digest=input_digest,
        gold_digest=gold_digest,
    )


def assemble_vfy_bal_01() -> ManifestEntry:
    target = CASES_DIR / "vfy-bal-01"

    # 1. dau-vao
    dau_vao = target / "dau-vao" / "01-nop-ban-dau"
    dau_vao.mkdir(parents=True, exist_ok=True)
    render_report_hoan_ung(dau_vao / "report_hoan_ung.pdf")
    render_hoa_don_dien_tu(dau_vao / "hoa_don_dien_tu.pdf")

    # 2. cau-hinh
    cau_hinh = target / "cau-hinh"
    cau_hinh.mkdir(parents=True, exist_ok=True)

    # Synthetic organization context for VFY-BAL-01
    ctx_data = {
        "tenant": "tenant:demo",
        "organization_id": "tenant:demo",
        "company_name": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
        "company_tax_id": "0319999996",
        "profile": "WORK_EXPENSE",
        "data_origin": "SIMULATED",
        "records": ["Synthetic balanced scenario VFY-BAL-01: 2.160.000 VND cost and advance."],
        "activity": {
            "activity_id": "activity:vfy-bal-01",
            "name": "VFY-BAL-01 — Quyết toán chi phí mua văn phòng phẩm và vật tư dự án Quý 4/2026",
            "purpose": "Quyết toán chi phí mua văn phòng phẩm và vật tư dự án Quý 4/2026",
            "occurred_at": "2026-10-10T09:00:00+07:00",
            "profile": "WORK_EXPENSE",
            "status": "AUTHORIZED",
            "references": ["TU-VFY-BAL-01"],
            "authorization": {
                "id": "auth:VFY-BAL-01",
                "actor": "employee:approver",
                "reason": "Phê duyệt quyết toán cân bằng giả lập",
            },
        },
        "people": [
            {"id": "employee:employee-a", "name": "NGUYỄN MINH AN"},
            {"id": "employee:accountant-demo", "name": "Trần Thị B (kế toán)"},
            {"id": "employee:approver", "name": "Lê Văn C (người quyết định)"},
        ],
        "policies": [
            {
                "id": "policy:uc03:WORK_EXPENSE",
                "version": "uc03-v1",
                "profile": "WORK_EXPENSE",
                "effective_from": "2026-10-01T00:00:00+07:00",
                "effective_to": "2026-12-31T23:59:59+07:00",
                "rules": ["EMPLOYEE_PAID_INVOICE_BOUNDED"],
            }
        ],
        "category_policies": [
            {
                "id": "category:uc03:WORK_EXPENSE",
                "version": "uc03-v1",
                "profile": "WORK_EXPENSE",
                "effective_from": "2026-10-01T00:00:00+07:00",
                "effective_to": "2026-12-31T23:59:59+07:00",
                "per_item_caps": {"CLIENT_MEAL": 5000000, "WORK_CLIENT_MEAL": 5000000, "TAXI": 2000000},
                "submission_window_days": 30,
                "excluded_categories": ["PERSONAL"],
            }
        ],
        "grants": [
            {
                "id": "grant:activity:vfy-bal-01:recognize",
                "version": "uc03-v1",
                "actor": "system:referee",
                "actions": ["RECOGNIZE_COST"],
                "scope": "activity:vfy-bal-01",
                "max_amount": 8000000,
                "effective_from": "2026-10-01T00:00:00+07:00",
                "effective_to": "2026-12-31T23:59:59+07:00",
                "allowed_profiles": ["TRAVEL", "WORK_EXPENSE"],
            },
            {
                "id": "grant:activity:vfy-bal-01:issue",
                "version": "uc03-v1",
                "actor": "system:referee",
                "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"],
                "scope": "activity:vfy-bal-01",
                "max_amount": 4000000,
                "effective_from": "2026-10-01T00:00:00+07:00",
                "effective_to": "2026-12-31T23:59:59+07:00",
                "allowed_profiles": ["TRAVEL", "WORK_EXPENSE"],
            },
            {
                "id": "grant:activity:vfy-bal-01:approver",
                "version": "uc03-v1",
                "actor": "employee:approver",
                "actions": ["AUTHORIZE_ACTIVITY", "RECOGNIZE_COST", "EXCEPT_POLICY", "ISSUE_PAYMENT", "ISSUE_COLLECTION", "OVERRIDE"],
                "scope": "activity:vfy-bal-01",
                "max_amount": 20000000,
                "effective_from": "2026-10-01T00:00:00+07:00",
                "effective_to": "2026-12-31T23:59:59+07:00",
                "allowed_profiles": ["TRAVEL", "WORK_EXPENSE"],
            },
            {
                "id": "grant:activity:vfy-bal-01:accountant",
                "version": "uc03-v1",
                "actor": "employee:accountant-demo",
                "actions": ["CONFIRM_FINANCIAL_FACT", "RECORD_ACTUAL", "STOP", "RESUME"],
                "scope": "activity:vfy-bal-01",
                "max_amount": 120000000,
                "effective_from": "2026-10-01T00:00:00+07:00",
                "effective_to": "2026-12-31T23:59:59+07:00",
                "allowed_profiles": ["TRAVEL", "WORK_EXPENSE"],
            },
        ],
        "ledger": [
            {
                "id": "advance:vfy-bal-01",
                "external_key": "transfer:FT-VFY-BAL-0001",
                "kind": "ADVANCE_RECEIVED",
                "scope": "activity:vfy-bal-01",
                "payer": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
                "payee": "employee:employee-a",
                "amount": 2160000,
                "event_at": "2026-10-05T09:00:00+07:00",
                "recorded_at": "2026-10-05T10:00:00+07:00",
                "verification_state": "CONFIRMED",
                "allocation_state": "ALLOCATED",
                "reverses_event_id": None,
            }
        ],
        "coverage": {
            "employee": "employee:employee-a",
            "activity": "activity:vfy-bal-01",
            "start": "2026-10-01T00:00:00+07:00",
            "as_of": "2026-10-16T12:00:00+07:00",
            "fund_ids": ["company:bank-demo"],
            "flow_kinds": ["ADVANCE_RECEIVED", "REIMBURSEMENT_RECEIVED", "EMPLOYEE_RETURN", "REVERSAL", "OBSERVED_UNALLOCATED"],
            "opening_by_fund": {"company:bank-demo": 0},
            "ledger_version": "ledger:VFY-BAL-01:initial-v1",
            "witness_keys": ["coverage:VFY-BAL-01"],
        },
        "coverages": [],
        "witnesses": [
            {
                "record_key": "advance:vfy-bal-01",
                "actor": "employee:accountant-demo",
                "scope": "activity:vfy-bal-01",
                "observed_at": "2026-10-05T10:00:00+07:00",
                "quote": "Công ty đã ứng thực nhận 2.160.000 VND cho Nguyễn Minh An.",
            },
            {
                "record_key": "coverage:VFY-BAL-01",
                "actor": "employee:accountant-demo",
                "scope": "activity:vfy-bal-01",
                "observed_at": "2026-10-16T12:00:00+07:00",
                "quote": "Sổ tạm ứng activity:vfy-bal-01 đã xác nhận đủ 2.160.000 VND.",
            },
        ],
        "activities": [],
        "financial_as_of": "2026-10-16T12:00:00+07:00",
    }
    org_ctx = OrganizationContext.model_validate_json(json.dumps(ctx_data))
    _write_json(cau_hinh / "to-chuc.json", json.loads(org_ctx.model_dump_json()))

    submission = Submission(
        employee="employee:employee-a",
        activity="activity:vfy-bal-01",
        declared_purpose="Quyết toán chi phí mua văn phòng phẩm và vật tư dự án Quý 4/2026",
    )
    _write_json(cau_hinh / "khai-bao.json", json.loads(submission.model_dump_json()))
    _write_json(cau_hinh / "kich-ban.json", {"case_id": "VFY-BAL-01", "slug": "vfy-bal-01-quyet-toan-can-bang"})

    transcription = Transcription(
        data_origin="STUB_TRANSCRIPTION",
        facts=(
            TranscriptionFact(field="incurred", value=2160000, role="INVOICE", quote="Tổng cộng tiền thanh toán: 2.160.000"),
            TranscriptionFact(field="paid_employee", value=2160000, role="PAYMENT", quote="Người thanh toán: NGUYỄN MINH AN"),
            TranscriptionFact(field="advance", value=2160000, role="ADVANCE", quote="Số tiền đã tạm ứng: 2.160.000 đồng"),
            TranscriptionFact(field="coverage", value=1, role="LEDGER", quote="Đối chiếu đủ chứng từ"),
            TranscriptionFact(field="economic_key", value="invoice:00000888", role="INVOICE", quote="Số: 00000888"),
        ),
    )
    _write_json(cau_hinh / "ban-doc-stub.json", json.loads(transcription.model_dump_json()))

    # 3. dap-an
    dap_an = target / "dap-an"
    dap_an.mkdir(parents=True, exist_ok=True)
    _write_json(dap_an / "su-that-an.json", {
        "stages": {"ban-dau": {"facts": {"real_payer": "employee:employee-a", "advance_settlement_diff": 0}}}
    })
    _write_json(dap_an / "quan-sat-duoc.json", {
        "stages": {"ban-dau": {"facts": {"incurred": 2160000, "paid_employee": 2160000, "advance": 2160000, "coverage": 1, "buyer_tax_code": "0319999996"}}}
    })
    _write_json(dap_an / "ket-qua-hop-le.json", {
        "stages": {"ban-dau": {
            "route": "AUTO",
            "expected_amounts": {},
            "owner": None,
            "question_required": False
        }}
    })

    # 4. recordings
    recordings = target / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    rep_sha = _file_sha256(dau_vao / "report_hoan_ung.pdf")
    inv_sha = _file_sha256(dau_vao / "hoa_don_dien_tu.pdf")
    _write_json(recordings / "recording.json", {
        "case_id": "VFY-BAL-01",
        "data_origin": "SYNTHETIC_FIXTURE",
        "digests": {
            "report_hoan_ung.pdf": rep_sha,
            "hoa_don_dien_tu.pdf": inv_sha,
        },
        "ocr": {
            rep_sha: {"pages": _extract_pdf_pages(dau_vao / "report_hoan_ung.pdf"), "complete": True},
            inv_sha: {"pages": _extract_pdf_pages(dau_vao / "hoa_don_dien_tu.pdf"), "complete": True},
        },
        "extractions": {
            "paper": {
                "role_fit": "FIT",
                "actual_type": "SETTLEMENT_FORM",
                "fields": [
                    {"field": "declared_advance", "state": "FOUND", "value": 2160000, "quote": "2.160.000", "page": 1},
                    {"field": "printed_total", "state": "FOUND", "value": 2160000, "quote": "2.160.000", "page": 1},
                    {"field": "declared_name", "state": "FOUND", "value": "NGUYỄN MINH AN", "quote": "NGUYỄN MINH AN", "page": 1},
                    {"field": "purpose", "state": "FOUND", "value": "Quyết toán chi phí mua văn phòng phẩm và vật tư dự án Quý 4/2026", "quote": "Quyết toán chi phí mua văn phòng phẩm và vật tư dự án Quý 4/2026", "page": 1},
                ],
                "line_items": [
                    {"fields": [
                        {"field": "description", "state": "FOUND", "value": "Chi phí văn phòng phẩm phục vụ dự án Q4/2026", "quote": "Chi phí văn phòng phẩm phục vụ dự án Q4/2026", "page": 1},
                        {"field": "amount", "state": "FOUND", "value": 2160000, "quote": "2.160.000", "page": 1},
                        {"field": "invoice_refs", "state": "FOUND", "value": ["00000888"], "quote": "00000888", "page": 1},
                    ]}
                ]
            },
            "evidence": {
                "document_type": "E_INVOICE",
                "fields": [
                    {"field": "document_date", "state": "FOUND", "value": "2026-10-10", "quote": "Ngày 10 tháng 10 năm 2026", "page": 1},
                    {"field": "buyer_name", "state": "FOUND", "value": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH", "quote": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH", "page": 1},
                    {"field": "total_amount", "state": "FOUND", "value": 2160000, "quote": "2.160.000", "page": 1},
                    {"field": "tax", "state": "FOUND", "value": 160000, "quote": "160.000", "page": 1},
                    {"field": "subtotal", "state": "FOUND", "value": 2000000, "quote": "2.000.000", "page": 1},
                    {"field": "buyer_tax_code", "state": "FOUND", "value": "0319999996", "quote": "0319999996", "page": 1},
                    {"field": "issuer_name", "state": "FOUND", "value": "CÔNG TY CỔ PHẦN VĂN PHÒNG PHẨM HỒNG HÀ", "quote": "CÔNG TY CỔ PHẦN VĂN PHÒNG PHẨM HỒNG HÀ", "page": 1},
                    {"field": "document_number", "state": "FOUND", "value": "00000888", "quote": "00000888", "page": 1},
                ],
                "line_items": [
                    {"fields": [
                        {"field": "item_name", "state": "FOUND", "value": "Văn phòng phẩm và vật tư phục vụ dự án Q4", "quote": "Văn phòng phẩm và vật tư phục vụ dự án Q4", "page": 1},
                        {"field": "line_amount", "state": "FOUND", "value": 2000000, "quote": "2.000.000", "page": 1},
                    ]}
                ]
            }
        },
        "transcription": json.loads(transcription.model_copy(update={"data_origin": "SYNTHETIC_FIXTURE"}).model_dump_json()),
    })

    input_digest = hashlib.sha256(
        (org_ctx.model_dump_json() + submission.model_dump_json() + rep_sha + inv_sha).encode("utf-8")
    ).hexdigest()
    gold_digest = _file_sha256(dap_an / "su-that-an.json")

    return ManifestEntry(
        root_id="activity:vfy-bal-01",
        split="development",
        strata="routine",
        profile="WORK_EXPENSE",
        economic_key="invoice:00000888",
        family="uc03",
        template="report_and_vat_invoice",
        layout="portrait_a4",
        issuer="0100108637",
        input_digest=input_digest,
        gold_digest=gold_digest,
    )


def assemble_tc06() -> ManifestEntry:
    target = CASES_DIR / "tc06"
    src_dir = THAM_KHAO / "tc06-chenh-lech-quyet-toan-ghi-sai"
    ctx_path = DEMO_CASES / "tc06-chenh-lech-quyet-toan-ghi-sai" / "context.json"

    # 1. dau-vao
    dau_vao = target / "dau-vao" / "01-nop-ban-dau"
    dau_vao.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_dir / "report_hoan_ung.pdf", dau_vao / "report_hoan_ung.pdf")
    shutil.copy2(src_dir / "hoa_don_dien_tu.pdf", dau_vao / "hoa_don_dien_tu.pdf")

    # 2. cau-hinh
    cau_hinh = target / "cau-hinh"
    cau_hinh.mkdir(parents=True, exist_ok=True)
    org_ctx = OrganizationContext.model_validate_json(ctx_path.read_text(encoding="utf-8"))
    _write_json(cau_hinh / "to-chuc.json", json.loads(org_ctx.model_dump_json()))

    submission = Submission(
        employee="employee:employee-a",
        activity="activity:tc06",
        declared_purpose="Chi phí ăn trưa làm việc với đối tác kiểm toán hệ thống",
    )
    _write_json(cau_hinh / "khai-bao.json", json.loads(submission.model_dump_json()))
    _write_json(cau_hinh / "kich-ban.json", {"case_id": "TC06", "slug": "tc06-chenh-lech-quyet-toan-ghi-sai"})

    transcription = Transcription(
        data_origin="STUB_TRANSCRIPTION",
        facts=(
            TranscriptionFact(field="incurred", value=2970000, role="INVOICE", quote="Tổng cộng: 2.970.000"),
            TranscriptionFact(field="paid_employee", value=2970000, role="PAYMENT", quote="Người thanh toán: NGUYỄN MINH AN"),
            TranscriptionFact(field="advance", value=3800000, role="ADVANCE", quote="Số tiền đã tạm ứng: 3.800.000 đồng"),
            TranscriptionFact(field="coverage", value=1, role="LEDGER", quote="Đối chiếu đủ chứng từ"),
            TranscriptionFact(field="declared_return", value=770000, role="PAYMENT", quote="Số tiền nhân viên hoàn trả: 770.000 đồng"),
            TranscriptionFact(field="economic_key", value="invoice:00000601", role="INVOICE", quote="Số: 00000601"),
        ),
    )
    _write_json(cau_hinh / "ban-doc-stub.json", json.loads(transcription.model_dump_json()))

    # 3. dap-an
    dap_an = target / "dap-an"
    dap_an.mkdir(parents=True, exist_ok=True)
    _write_json(dap_an / "su-that-an.json", {
        "stages": {"ban-dau": {"facts": {"real_payer": "employee:employee-a", "delta": 60000, "error": "DISCREPANCY_BETWEEN_DECLARED_AND_CALCULATED"}}}
    })
    _write_json(dap_an / "quan-sat-duoc.json", {
        "stages": {"ban-dau": {"facts": {"incurred": 2970000, "advance": 3800000, "declared_difference": 770000, "calculated_difference": 830000}}}
    })
    _write_json(dap_an / "ket-qua-hop-le.json", {
        "stages": {"ban-dau": {
            "route": "FACT",
            "expected_amounts": {},
            "owner": "employee:employee-a",
            "question_required": True
        }}
    })

    # 4. recordings
    recordings = target / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    rep_sha = _file_sha256(dau_vao / "report_hoan_ung.pdf")
    inv_sha = _file_sha256(dau_vao / "hoa_don_dien_tu.pdf")
    _write_json(recordings / "recording.json", {
        "case_id": "TC06",
        "data_origin": "SYNTHETIC_FIXTURE",
        "digests": {
            "report_hoan_ung.pdf": rep_sha,
            "hoa_don_dien_tu.pdf": inv_sha,
        },
        "ocr": {
            rep_sha: {"pages": _extract_pdf_pages(dau_vao / "report_hoan_ung.pdf"), "complete": True},
            inv_sha: {"pages": _extract_pdf_pages(dau_vao / "hoa_don_dien_tu.pdf"), "complete": True},
        },
        "extractions": {
            "paper": {
                "role_fit": "FIT",
                "actual_type": "SETTLEMENT_FORM",
                "fields": [
                    {"field": "declared_advance", "state": "FOUND", "value": 3800000, "quote": "3.800.000", "page": 1},
                    {"field": "printed_total", "state": "FOUND", "value": 2970000, "quote": "2.970.000", "page": 1},
                    {"field": "printed_return", "state": "FOUND", "value": 770000, "quote": "770.000", "page": 1},
                    {"field": "declared_name", "state": "FOUND", "value": "NGUYỄN MINH AN", "quote": "NGUYỄN MINH AN", "page": 1},
                    {"field": "purpose", "state": "FOUND", "value": "Chi phí tiếp khách đoàn kiểm toán hệ thống an toàn thông tin", "quote": "Chi phí tiếp khách đoàn kiểm toán hệ thống an toàn thông tin", "page": 1},
                ],
                "line_items": [
                    {"fields": [
                        {"field": "description", "state": "FOUND", "value": "Chi phí tiếp khách đoàn kiểm toán hệ thống an toàn thông tin", "quote": "Chi phí tiếp khách đoàn kiểm toán hệ thống an\ntoàn thông tin", "page": 1},
                        {"field": "amount", "state": "FOUND", "value": 2970000, "quote": "2.970.000", "page": 1},
                        {"field": "invoice_refs", "state": "FOUND", "value": ["00000601"], "quote": "00000601", "page": 1},
                    ]}
                ]
            },
            "evidence": {
                "document_type": "E_INVOICE",
                "fields": [
                    {"field": "document_date", "state": "FOUND", "value": "2026-10-10", "quote": "Ngày 10 tháng 10 năm 2026", "page": 1},
                    {"field": "buyer_name", "state": "FOUND", "value": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH", "quote": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH", "page": 1},
                    {"field": "total_amount", "state": "FOUND", "value": 2970000, "quote": "2.970.000", "page": 1},
                    {"field": "tax", "state": "FOUND", "value": 220000, "quote": "220.000", "page": 1},
                    {"field": "subtotal", "state": "FOUND", "value": 2750000, "quote": "2.750.000", "page": 1},
                    {"field": "buyer_tax_code", "state": "FOUND", "value": "0319999996", "quote": "0319999996", "page": 1},
                    {"field": "issuer_name", "state": "FOUND", "value": "CÔNG TY TNHH THƯƠNG MẠI VÀ DỊCH VỤ MINH PHÁT", "quote": "CÔNG TY TNHH THƯƠNG MẠI VÀ DỊCH VỤ MINH PHÁT", "page": 1},
                    {"field": "document_number", "state": "FOUND", "value": "00000601", "quote": "00000601", "page": 1},
                ],
                "line_items": [
                    {"fields": [
                        {"field": "item_name", "state": "FOUND", "value": "Dịch vụ tiệc tiếp khách đoàn kiểm toán", "quote": "Dịch vụ tiệc tiếp khách đoàn kiểm toán", "page": 1},
                        {"field": "line_amount", "state": "FOUND", "value": 2750000, "quote": "2.750.000", "page": 1},
                    ]}
                ]
            }
        },
        "transcription": json.loads(transcription.model_copy(update={"data_origin": "SYNTHETIC_FIXTURE"}).model_dump_json()),
    })

    input_digest = hashlib.sha256(
        (org_ctx.model_dump_json() + submission.model_dump_json() + rep_sha + inv_sha).encode("utf-8")
    ).hexdigest()
    gold_digest = _file_sha256(dap_an / "su-that-an.json")

    return ManifestEntry(
        root_id="activity:tc06",
        split="development",
        strata="FACT",
        profile="WORK_EXPENSE",
        economic_key="invoice:00000601",
        family="uc03",
        template="report_and_vat_invoice",
        layout="portrait_a4",
        issuer="0101234565",
        input_digest=input_digest,
        gold_digest=gold_digest,
    )


def assemble_tc04() -> ManifestEntry:
    target = CASES_DIR / "tc04"
    src_dir = THAM_KHAO / "tc04-hop-le-nhieu-mat-hang-thiet-bi"
    ctx_path = DEMO_CASES / "tc04-hop-le-nhieu-mat-hang-thiet-bi" / "context.json"

    # 1. dau-vao
    dau_vao = target / "dau-vao" / "01-nop-ban-dau"
    dau_vao.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_dir / "report_hoan_ung.pdf", dau_vao / "report_hoan_ung.pdf")
    shutil.copy2(src_dir / "hoa_don_dien_tu.pdf", dau_vao / "hoa_don_dien_tu.pdf")

    # 2. cau-hinh
    cau_hinh = target / "cau-hinh"
    cau_hinh.mkdir(parents=True, exist_ok=True)
    org_ctx = OrganizationContext.model_validate_json(ctx_path.read_text(encoding="utf-8"))
    _write_json(cau_hinh / "to-chuc.json", json.loads(org_ctx.model_dump_json()))

    submission = Submission(
        employee="employee:employee-a",
        activity="activity:tc04",
        declared_purpose="Mua thiết bị máy tính cho nhân viên",
    )
    _write_json(cau_hinh / "khai-bao.json", json.loads(submission.model_dump_json()))
    _write_json(cau_hinh / "kich-ban.json", {"case_id": "TC04", "slug": "tc04-hop-le-nhieu-mat-hang-thiet-bi"})

    transcription = Transcription(
        data_origin="STUB_TRANSCRIPTION",
        facts=(
            TranscriptionFact(field="incurred", value=83600000, role="INVOICE", quote="Tổng cộng: 83.600.000"),
            TranscriptionFact(field="paid_employee", value=83600000, role="PAYMENT", quote="Người thanh toán: NGUYỄN MINH AN"),
            TranscriptionFact(field="advance", value=85000000, role="ADVANCE", quote="Số tiền đã tạm ứng: 85.000.000 đồng"),
            TranscriptionFact(field="coverage", value=1, role="LEDGER", quote="Đối chiếu đủ chứng từ"),
            TranscriptionFact(field="economic_key", value="invoice:00000401", role="INVOICE", quote="Số: 00000401"),
        ),
    )
    _write_json(cau_hinh / "ban-doc-stub.json", json.loads(transcription.model_dump_json()))

    # 3. dap-an
    dap_an = target / "dap-an"
    dap_an.mkdir(parents=True, exist_ok=True)
    _write_json(dap_an / "su-that-an.json", {
        "stages": {"ban-dau": {"facts": {"exceeds_authority": 1, "total": 83600000, "limit": 20000000}}}
    })
    _write_json(dap_an / "quan-sat-duoc.json", {
        "stages": {"ban-dau": {"facts": {"incurred": 83600000, "advance": 85000000, "coverage": 1, "approver_limit": 20000000}}}
    })
    _write_json(dap_an / "ket-qua-hop-le.json", {
        "stages": {"ban-dau": {
            "route": "AUTHORITY",
            "expected_amounts": {},
            "owner": "employee:approver",
            "question_required": True
        }}
    })

    # 4. recordings
    recordings = target / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    rep_sha = _file_sha256(dau_vao / "report_hoan_ung.pdf")
    inv_sha = _file_sha256(dau_vao / "hoa_don_dien_tu.pdf")
    _write_json(recordings / "recording.json", {
        "case_id": "TC04",
        "data_origin": "SYNTHETIC_FIXTURE",
        "digests": {
            "report_hoan_ung.pdf": rep_sha,
            "hoa_don_dien_tu.pdf": inv_sha,
        },
        "ocr": {
            rep_sha: {"pages": _extract_pdf_pages(dau_vao / "report_hoan_ung.pdf"), "complete": True},
            inv_sha: {"pages": _extract_pdf_pages(dau_vao / "hoa_don_dien_tu.pdf"), "complete": True},
        },
        "extractions": {
            "paper": {
                "role_fit": "FIT",
                "actual_type": "SETTLEMENT_FORM",
                "fields": [
                    {"field": "declared_advance", "state": "FOUND", "value": 85000000, "quote": "85.000.000", "page": 1},
                    {"field": "printed_total", "state": "FOUND", "value": 83600000, "quote": "83.600.000", "page": 1},
                    {"field": "printed_return", "state": "FOUND", "value": 1400000, "quote": "1.400.000", "page": 1},
                    {"field": "declared_name", "state": "FOUND", "value": "NGUYỄN MINH AN", "quote": "NGUYỄN MINH AN", "page": 1},
                    {"field": "purpose", "state": "FOUND", "value": "Mua thiết bị máy tính cho nhân viên", "quote": "Mua thiết bị máy tính cho nhân viên", "page": 1},
                ],
                "line_items": [
                    {"fields": [
                        {"field": "description", "state": "FOUND", "value": "Mua thiết bị máy tính cho nhân viên", "quote": "Mua thiết bị máy tính cho nhân viên", "page": 1},
                        {"field": "amount", "state": "FOUND", "value": 83600000, "quote": "83.600.000", "page": 1},
                        {"field": "invoice_refs", "state": "FOUND", "value": ["00000401"], "quote": "00000401", "page": 1},
                    ]}
                ]
            },
            "evidence": {
                "document_type": "E_INVOICE",
                "fields": [
                    {"field": "document_date", "state": "FOUND", "value": "2026-10-10", "quote": "Ngày 10 tháng 10 năm 2026", "page": 1},
                    {"field": "buyer_name", "state": "FOUND", "value": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH", "quote": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH", "page": 1},
                    {"field": "total_amount", "state": "FOUND", "value": 83600000, "quote": "83.600.000", "page": 1},
                    {"field": "tax", "state": "FOUND", "value": 7600000, "quote": "7.600.000", "page": 1},
                    {"field": "subtotal", "state": "FOUND", "value": 76000000, "quote": "76.000.000", "page": 1},
                    {"field": "buyer_tax_code", "state": "FOUND", "value": "0319999996", "quote": "0319999996", "page": 1},
                    {"field": "issuer_name", "state": "FOUND", "value": "CÔNG TY TNHH THƯƠNG MẠI VÀ DỊCH VỤ MINH PHÁT", "quote": "CÔNG TY TNHH THƯƠNG MẠI VÀ DỊCH VỤ MINH PHÁT", "page": 1},
                    {"field": "document_number", "state": "FOUND", "value": "00000401", "quote": "00000401", "page": 1},
                ],
                "line_items": [
                    {"fields": [
                        {"field": "item_name", "state": "FOUND", "value": "Máy tính để bàn", "quote": "Máy tính để bàn", "page": 1},
                        {"field": "line_amount", "state": "FOUND", "value": 60000000, "quote": "60.000.000", "page": 1},
                    ]},
                    {"fields": [
                        {"field": "item_name", "state": "FOUND", "value": "Chuột máy tính", "quote": "Chuột máy tính", "page": 1},
                        {"field": "line_amount", "state": "FOUND", "value": 1000000, "quote": "1.000.000", "page": 1},
                    ]},
                    {"fields": [
                        {"field": "item_name", "state": "FOUND", "value": "Màn hình máy tính", "quote": "Màn hình máy tính", "page": 1},
                        {"field": "line_amount", "state": "FOUND", "value": 15000000, "quote": "15.000.000", "page": 1},
                    ]}
                ]
            }
        },
        "transcription": json.loads(transcription.model_copy(update={"data_origin": "SYNTHETIC_FIXTURE"}).model_dump_json()),
    })

    input_digest = hashlib.sha256(
        (org_ctx.model_dump_json() + submission.model_dump_json() + rep_sha + inv_sha).encode("utf-8")
    ).hexdigest()
    gold_digest = _file_sha256(dap_an / "su-that-an.json")

    return ManifestEntry(
        root_id="activity:tc04",
        split="development",
        strata="AUTHORITY",
        profile="WORK_EXPENSE",
        economic_key="invoice:00000401",
        family="uc03",
        template="report_and_vat_invoice",
        layout="portrait_a4",
        issuer="0101234565",
        input_digest=input_digest,
        gold_digest=gold_digest,
    )


def main() -> None:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    entries = [
        assemble_tc01(),
        assemble_tc02(),
        assemble_vfy_bal_01(),
        assemble_tc06(),
        assemble_tc04(),
    ]

    manifest = {
        "dataset": "invoice-referee-verify",
        "frozen_at": "2026-10-16T12:00:00+07:00",
        "entries": [json.loads(e.model_dump_json()) for e in entries],
    }
    _write_json(VERIFY_DIR / "manifest.json", manifest)

    readme_content = """# InvoiceReferee Verify Dataset (Locked Benchmark)

Bộ dữ liệu kiểm thử phát triển gồm 5 kịch bản đã được khóa cứng:
- **TC01**: Quy trình hoàn ứng thông thường (Routine), nhân viên hoàn trả 760.000 VND (`COLLECT 760000`), không phát sinh câu hỏi ngoại lệ.
- **TC02**: Quy trình thanh toán thêm thông thường (Routine), công ty thanh toán thêm 400.000 VND (`PAY 400000`), không phát sinh câu hỏi ngoại lệ.
- **VFY-BAL-01**: Kịch bản cân bằng tổng hợp (Synthetic Routine Balanced), chi phí 2.160.000 VND đúng bằng tiền tạm ứng 2.160.000 VND ($S = 0$), kết luận `BALANCED`, không tạo lệnh chuyển tiền.
- **TC06**: Kịch bản lỗi sự kiện số liệu (FACT), sai lệch 60.000 VND giữa số tính toán (830.000 VND) và số kê khai trên giấy (770.000 VND), chuyển nhân viên giải trình, chặn phát hành tiền.
- **TC04**: Kịch bản vượt hạn mức thẩm quyền (AUTHORITY), tổng chi 83.600.000 VND vượt hạn mức 20.000.000 VND của người phê duyệt, chuyển người quyết định có thẩm quyền cao hơn, chặn phát hành tiền.

## Các bộ kiểm thử
1. **Core4**: `[TC01, TC02, VFY-BAL-01, TC06]` (4 ca tuần tự)
2. **Escalation5**: `[TC01, TC02, VFY-BAL-01, TC06, TC04]` (5 ca: 3 routine + 2 human-required)
"""
    (VERIFY_DIR / "README.md").write_text(readme_content, encoding="utf-8")
    # Freeze every source/context/gold/recording input; runtime validates before use.
    for case_dir in CASES_DIR.iterdir():
        path=case_dir / "cau-hinh" / "kich-ban.json"
        item=json.loads(path.read_text())
        item["upload_roles"]={"report_hoan_ung.pdf":"paper","hoa_don_dien_tu.pdf":"evidence"}
        _write_json(path,item)
    # Independent literal oracle refinements. Never derive these from app output.
    for cid in ("tc01","tc02","vfy-bal-01"):
        path=CASES_DIR/cid/"dap-an/ket-qua-hop-le.json"
        oracle=json.loads(path.read_text())
        oracle["stages"]["ban-dau"]["money_source_digests"]=[_file_sha256(CASES_DIR/cid/"dau-vao/01-nop-ban-dau/hoa_don_dien_tu.pdf")]
        e,advance={"tc01":(3240000,4000000),"tc02":(5400000,5000000),"vfy-bal-01":(2160000,2160000)}[cid]
        oracle["stages"]["ban-dau"]["expected_money"]={"E":e,"A":advance,"P":0,"R":0,"S":e-advance}
        _write_json(path,oracle)
    for cid,expected in {
        "tc06":{"kind":"FACT","owner":"employee","field_or_rule":"expense:arithmetic:return","question_values":["830000","770000","60000"],"source_digests":[_file_sha256(CASES_DIR/"tc06/dau-vao/01-nop-ban-dau/report_hoan_ung.pdf")],"required_quotes":["770.000"]},
        "tc04":{"kind":"AUTHORITY","owner":"approver","field_or_rule":"RECOGNIZE_COST","question_values":["83600000"],"source_digests":[],"required_quotes":[]},
    }.items():
        path=CASES_DIR/cid/"dap-an/ket-qua-hop-le.json"
        oracle=json.loads(path.read_text());oracle["stages"]["ban-dau"]["expected_issues"]=[expected]
        _write_json(path,oracle)
    manifest["files"]={p.relative_to(VERIFY_DIR).as_posix():_file_sha256(p) for p in sorted(VERIFY_DIR.rglob("*")) if p.is_file() and p.name!="manifest.json"}
    _write_json(VERIFY_DIR / "manifest.json",manifest)
    print(f"Successfully assembled {len(entries)} verify cases into {VERIFY_DIR}")


if __name__ == "__main__":
    main()
