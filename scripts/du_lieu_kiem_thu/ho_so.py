"""R1 case specifications: 14 current-scope development roots.

Each case is a literal, typed spec: the activity/people/budget/grants/coverage
context, the staged documents whose *visible text* carries the facts, and the
literal gold. Nothing here computes an expected outcome with the Reconciler;
gold lives in dap_an.py as literal values.

Physical layout per case (plan A):
    case-NN-<slug>/
      HUONG-DAN.md
      cau-hinh/{to-chuc,khai-bao,kich-ban,ban-doc-stub}.json
      dau-vao/01-nop-ban-dau/*.pdf
      dau-vao/02-bo-sung/*.pdf          (only when the case has a later stage)
      dau-vao/03-thuc-hien-tien/{chuyen-khoan,tien-mat}/
      dap-an/{su-that-an,quan-sat-duoc,ket-qua-hop-le}.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from du_lieu_kiem_thu import dap_an
from invoice_referee.evaluation.models import ManifestEntry

# Stage folder names -> the physical home of each stage's documents (plan A).
# A stage_id names the business step; several stage ids may share one folder.
STAGE_FOLDERS: dict[str, str] = {
    "ban-dau": "01-nop-ban-dau",
    "bo-sung": "02-bo-sung",
    "bo-sung-payer": "02-bo-sung",
    "bo-sung-thanh-toan": "02-bo-sung",
    "duyet-chi": "03-duyet-chi",
    "thuc-hien-tien": "03-thuc-hien-tien",
}
# The physical folder order, for computing a stage's read-set cutoff.
FOLDER_ORDER: tuple[str, ...] = ("01-nop-ban-dau", "02-bo-sung", "03-duyet-chi", "03-thuc-hien-tien")
# Ordered stages per case (later stages are absent from the initial read-set).
DEFAULT_STAGES: tuple[str, ...] = ("ban-dau",)


@dataclass(frozen=True)
class DocumentSpec:
    """One source file: its role, its filename, and the literal lines printed."""

    filename: str
    role: str
    lines: tuple[str, ...]
    stage: str = "ban-dau"
    # Image-only scan (render + rasterize) vs native text PDF.
    scan: bool = False


@dataclass(frozen=True)
class ActivitySpec:
    activity_id: str
    name: str
    occurred_at: str
    purpose: str


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    slug: str
    activity: ActivitySpec
    documents: tuple[DocumentSpec, ...]
    stages: tuple[str, ...] = DEFAULT_STAGES
    employee: str = "employee:employee-a"
    profile: str = "TRAVEL"
    # Observable organization records (no expected/route). These are context the
    # server imports, not fields forced into the model prompt.
    budget_amount: int | None = None
    budget_effect_from: str | None = "2026-10-01T00:00:00+07:00"
    coverage: bool = True
    grants: tuple[dict[str, object], ...] = ()
    ledger: tuple[dict[str, object], ...] = ()
    # The literal STUB hand-transcription (contracts §5): the fields a correct
    # reader should observe, with a page/quote locator. Written to
    # ban-doc-stub.json and loaded only by the STUB reader path.
    stub_facts: tuple[dict[str, object], ...] = ()


# -- shared fixtures ---------------------------------------------------------

DEMO_TENANT = "tenant:demo"
PEOPLE = (
    {"id": "employee:employee-a", "name": "Nguyễn Văn A"},
    {"id": "employee:accountant-demo", "name": "Trần Thị B (kế toán)"},
    {"id": "employee:approver", "name": "Lê Văn C (người quyết định)"},
)


def _grants() -> tuple[dict[str, object], ...]:
    return (
        {
            "id": "grant:system:recognize",
            "version": "v1",
            "actor": "system:referee",
            "actions": ["RECOGNIZE_COST"],
            "scope": "tenant:demo",
            "max_amount": 8_000_000,
            "effective_from": "2026-10-01T00:00:00+07:00",
        },
        {
            "id": "grant:system:issue",
            "version": "v1",
            "actor": "system:referee",
            "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"],
            "scope": "tenant:demo",
            "max_amount": 4_000_000,
            "effective_from": "2026-10-01T00:00:00+07:00",
        },
        {
            "id": "grant:approver:per-action",
            "version": "v1",
            "actor": "employee:approver",
            "actions": [
                "AUTHORIZE_ACTIVITY",
                "RECOGNIZE_COST",
                "EXCEPT_POLICY",
                "ISSUE_PAYMENT",
                "ISSUE_COLLECTION",
                "OVERRIDE",
            ],
            "scope": "tenant:demo",
            "max_amount": 20_000_000,
            "effective_from": "2026-10-01T00:00:00+07:00",
        },
    )


def _invoice(number: str, total: int, *, supplier: str = "Công ty Demo") -> tuple[str, ...]:
    return (
        "HÓA ĐƠN GIÁ TRỊ GIA TĂNG",
        f"Số hóa đơn: {number}",
        f"Đơn vị cung cấp: {supplier}",
        "Nội dung: Chi phí phục vụ hoạt động công tác",
        "Ngày: 05/10/2026",
        f"Tổng chi {_vnd(total)}",
    )


def _payment(payer: str, amount: int, *, method: str = "Chuyển khoản") -> tuple[str, ...]:
    return (
        "BIÊN NHẬN THANH TOÁN",
        f"Người thanh toán: {payer}",
        f"Hình thức: {method}",
        f"Đã thanh toán {_vnd(amount)}",
        "Ngày: 05/10/2026",
    )


def _vnd(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + " VND"


def _stub(
    incurred: int,
    *,
    paid_employee: int = 0,
    paid_company: int = 0,
    advance: int = 0,
    coverage: bool = True,
    key: str | None = None,
    eligibility: str | None = None,
) -> tuple[dict[str, object], ...]:
    """A literal STUB hand-transcription (contracts §5): the observed fields.

    This is the human-written reading the STUB reader assesses; it carries a
    quote locator and never an expected/route value.
    """
    out: list[dict[str, object]] = [
        {"field": "incurred", "value": incurred, "role": "INVOICE", "quote": f"Tổng chi {_vnd(incurred)}"}
    ]
    if paid_employee:
        out.append({"field": "paid_employee", "value": paid_employee, "role": "PAYMENT", "quote": f"Đã thanh toán {_vnd(paid_employee)}"})
    if paid_company:
        out.append({"field": "paid_company", "value": paid_company, "role": "PAYMENT", "quote": f"Đã thanh toán {_vnd(paid_company)}"})
    if advance:
        out.append({"field": "advance", "value": advance, "role": "ADVANCE", "quote": f"Ứng {_vnd(advance)}"})
    if coverage:
        out.append({"field": "coverage", "value": 1, "role": "LEDGER", "quote": "Đối chiếu đủ giai đoạn"})
    if key:
        out.append({"field": "economic_key", "value": key, "role": "INVOICE", "quote": key})
    if eligibility:
        out.append({"field": "eligibility", "value": eligibility, "role": "INVOICE", "quote": "Loại chi phí"})
    return tuple(out)


# -- authored cases; D06 is held for the future budget policy suite ---------

def _case_01() -> CaseSpec:
    return CaseSpec(
        case_id="D01",
        slug="case-01-cong-ty-chi-them",
        activity=ActivitySpec("activity:d01", "Công tác Hà Nội", "2026-10-05T09:00:00+07:00", "Làm việc với đối tác Hà Nội"),
        budget_amount=8_000_000,
        grants=_grants(),
        ledger=(
            {"kind": "ADVANCE_RECEIVED", "amount": 2_000_000, "payer": "company:demo", "payee": "employee:employee-a"},
        ),
        documents=(
            DocumentSpec("01-hoa-don-chi-phi.pdf", "INVOICE", _invoice("HD-D01", 8_000_000)),
            DocumentSpec("02-bien-nhan-nhan-vien-thanh-toan.pdf", "PAYMENT", _payment("Nguyễn Văn A", 5_000_000)),
            DocumentSpec("03-bien-nhan-cong-ty-thanh-toan.pdf", "PAYMENT", _payment("Công ty Demo", 3_000_000)),
            DocumentSpec("04-phieu-ung.pdf", "ADVANCE", ("PHIẾU TẠM ỨNG", "Ứng 2.000.000 VND", "Người nhận: Nguyễn Văn A")),
            DocumentSpec("05-bang-ke-hoat-dong.pdf", "DECLARATION", ("BẢNG KÊ HOẠT ĐỘNG", "Đối chiếu đủ giai đoạn 01/10–13/10/2026", "invoice:d01")),
        ),
    )


def _case_02() -> CaseSpec:
    return CaseSpec(
        case_id="D02",
        slug="case-02-nhan-vien-hoan-tien",
        activity=ActivitySpec("activity:d02", "Công tác Đà Nẵng", "2026-11-02T09:00:00+07:00", "Khảo sát nhà cung cấp"),
        budget_amount=8_000_000,
        grants=_grants(),
        ledger=({"kind": "ADVANCE_RECEIVED", "amount": 2_000_000, "payer": "company:demo", "payee": "employee:employee-a"},),
        documents=(
            DocumentSpec("01-hoa-don-chi-phi.pdf", "INVOICE", _invoice("HD-D02", 1_500_000)),
            DocumentSpec("02-bien-nhan-nhan-vien-thanh-toan.pdf", "PAYMENT", _payment("Nguyễn Văn A", 1_500_000)),
            DocumentSpec("03-phieu-ung.pdf", "ADVANCE", ("PHIẾU TẠM ỨNG", "Ứng 2.000.000 VND")),
            DocumentSpec("04-bang-ke-hoat-dong.pdf", "DECLARATION", ("BẢNG KÊ HOẠT ĐỘNG", "Đối chiếu đủ giai đoạn", "invoice:d02")),
        ),
    )


def _case_03() -> CaseSpec:
    return CaseSpec(
        case_id="D03",
        slug="case-03-quyet-toan-can-bang",
        activity=ActivitySpec("activity:d03", "Công tác Hải Phòng", "2026-10-20T09:00:00+07:00", "Làm việc với chi nhánh"),
        budget_amount=8_000_000,
        grants=_grants(),
        ledger=({"kind": "ADVANCE_RECEIVED", "amount": 2_000_000, "payer": "company:demo", "payee": "employee:employee-a"},),
        documents=(
            DocumentSpec("01-hoa-don-chi-phi.pdf", "INVOICE", _invoice("HD-D03", 2_000_000)),
            DocumentSpec("02-bien-nhan-nhan-vien-thanh-toan.pdf", "PAYMENT", _payment("Nguyễn Văn A", 2_000_000)),
            DocumentSpec("03-phieu-ung.pdf", "ADVANCE", ("PHIẾU TẠM ỨNG", "Ứng 2.000.000 VND")),
            DocumentSpec("04-bang-ke-hoat-dong.pdf", "DECLARATION", ("BẢNG KÊ HOẠT ĐỘNG", "Đối chiếu đủ giai đoạn", "invoice:d03")),
        ),
    )


def _case_04() -> CaseSpec:
    return CaseSpec(
        case_id="D04",
        slug="case-04-chua-ro-nguoi-thanh-toan",
        activity=ActivitySpec("activity:d04", "Công tác Cần Thơ", "2026-10-25T09:00:00+07:00", "Khảo sát đối tác"),
        budget_amount=8_000_000,
        grants=_grants(),
        stages=("ban-dau", "bo-sung-payer"),
        documents=(
            DocumentSpec("01-hoa-don-chi-phi.pdf", "INVOICE", _invoice("HD-D04", 5_000_000)),
            DocumentSpec("02-bang-ke-hoat-dong.pdf", "DECLARATION", ("BẢNG KÊ HOẠT ĐỘNG", "Đối chiếu đủ giai đoạn", "invoice:d04")),
            DocumentSpec(
                "01-xac-nhan-nguoi-tra.pdf",
                "PAYMENT",
                _payment("Nguyễn Văn A", 5_000_000),
                stage="bo-sung-payer",
            ),
        ),
    )


def _case_05() -> CaseSpec:
    return CaseSpec(
        case_id="D05",
        slug="case-05-mau-thuan-lien-ket-cong-viec",
        activity=ActivitySpec("activity:d05", "Công tác Huế", "2026-10-28T09:00:00+07:00", "Làm việc với đối tác Huế"),
        budget_amount=8_000_000,
        grants=_grants(),
        documents=(
            DocumentSpec("01-hoa-don-chi-phi.pdf", "INVOICE", _invoice("HD-D05", 3_000_000)),
            DocumentSpec("02-bien-nhan-thanh-toan.pdf", "PAYMENT", _payment("Nguyễn Văn A", 3_000_000)),
            DocumentSpec("03-bang-ke-hoat-dong.pdf", "DECLARATION", ("BẢNG KÊ HOẠT ĐỘNG", "Đối chiếu đủ giai đoạn", "invoice:d05")),
        ),
    )


def _case_06() -> CaseSpec:
    return CaseSpec(
        case_id="D06",
        slug="case-06-chi-phi-vuot-ngan-sach",
        activity=ActivitySpec("activity:d06", "Hội thảo khách hàng", "2026-10-18T09:00:00+07:00", "Tổ chức hội thảo"),
        budget_amount=8_000_000,
        grants=_grants(),
        ledger=({"kind": "ADVANCE_RECEIVED", "amount": 2_000_000, "payer": "company:demo", "payee": "employee:employee-a"},),
        documents=(
            DocumentSpec("01-hoa-don-chi-phi.pdf", "INVOICE", _invoice("HD-D06", 10_000_000, supplier="Trung tâm Hội nghị")),
            DocumentSpec("02-bien-nhan-nhan-vien-thanh-toan.pdf", "PAYMENT", _payment("Nguyễn Văn A", 5_000_000)),
            DocumentSpec("03-bien-nhan-cong-ty-thanh-toan.pdf", "PAYMENT", _payment("Công ty Demo", 3_000_000)),
            DocumentSpec("04-phieu-ung.pdf", "ADVANCE", ("PHIẾU TẠM ỨNG", "Ứng 2.000.000 VND")),
            DocumentSpec("05-bang-ke-hoat-dong.pdf", "DECLARATION", ("BẢNG KÊ HOẠT ĐỘNG", "Đối chiếu đủ giai đoạn", "invoice:d06")),
        ),
    )


def _case_07() -> CaseSpec:
    return CaseSpec(
        case_id="D07",
        slug="case-07-vuot-quyen-cong-nhan-chi-phi",
        activity=ActivitySpec("activity:d07", "Công tác quốc tế", "2026-10-12T09:00:00+07:00", "Làm việc với đối tác nước ngoài"),
        budget_amount=12_000_000,
        grants=_grants(),
        ledger=({"kind": "ADVANCE_RECEIVED", "amount": 6_000_000, "payer": "company:demo", "payee": "employee:employee-a"},),
        documents=(
            DocumentSpec("01-hoa-don-chi-phi.pdf", "INVOICE", _invoice("HD-D07", 9_000_000, supplier="Air Global")),
            DocumentSpec("02-bien-nhan-nhan-vien-thanh-toan.pdf", "PAYMENT", _payment("Nguyễn Văn A", 9_000_000)),
            DocumentSpec("03-phieu-ung.pdf", "ADVANCE", ("PHIẾU TẠM ỨNG", "Ứng 6.000.000 VND")),
            DocumentSpec("04-bang-ke-hoat-dong.pdf", "DECLARATION", ("BẢNG KÊ HOẠT ĐỘNG", "Đối chiếu đủ giai đoạn", "invoice:d07")),
        ),
    )


def _case_08() -> CaseSpec:
    return CaseSpec(
        case_id="D08",
        slug="case-08-vuot-quyen-tao-yeu-cau-chi",
        activity=ActivitySpec("activity:d08", "Công tác đường sắt", "2026-10-15T09:00:00+07:00", "Khảo sát tuyến đường sắt"),
        budget_amount=8_000_000,
        grants=_grants(),
        ledger=({"kind": "ADVANCE_RECEIVED", "amount": 2_000_000, "payer": "company:demo", "payee": "employee:employee-a"},),
        documents=(
            DocumentSpec("01-hoa-don-chi-phi.pdf", "INVOICE", _invoice("HD-D08", 8_000_000, supplier="Đường sắt VN")),
            DocumentSpec("02-bien-nhan-nhan-vien-thanh-toan.pdf", "PAYMENT", _payment("Nguyễn Văn A", 8_000_000)),
            DocumentSpec("03-phieu-ung.pdf", "ADVANCE", ("PHIẾU TẠM ỨNG", "Ứng 2.000.000 VND")),
            DocumentSpec("04-bang-ke-hoat-dong.pdf", "DECLARATION", ("BẢNG KÊ HOẠT ĐỘNG", "Đối chiếu đủ giai đoạn", "invoice:d08")),
        ),
    )


def _case_09() -> CaseSpec:
    return CaseSpec(
        case_id="D09",
        slug="case-09-thieu-lich-su-tam-ung",
        activity=ActivitySpec("activity:d09", "Công tác Nha Trang", "2026-10-22T09:00:00+07:00", "Khảo sát dịch vụ"),
        budget_amount=8_000_000,
        grants=_grants(),
        coverage=False,  # history not established: A/P/R must stay UNKNOWN
        documents=(
            DocumentSpec("01-hoa-don-chi-phi.pdf", "INVOICE", _invoice("HD-D09", 3_000_000)),
            DocumentSpec("02-bien-nhan-nhan-vien-thanh-toan.pdf", "PAYMENT", _payment("Nguyễn Văn A", 3_000_000)),
        ),
    )


def _case_10() -> CaseSpec:
    return CaseSpec(
        case_id="D10",
        slug="case-10-chung-tu-trung-lap",
        activity=ActivitySpec("activity:d10", "Công tác Vũng Tàu", "2026-10-08T09:00:00+07:00", "Khảo sát nhà cung cấp"),
        budget_amount=8_000_000,
        grants=_grants(),
        documents=(
            DocumentSpec("01-hoa-don-chi-phi.pdf", "INVOICE", _invoice("HD-D10", 3_000_000)),
            DocumentSpec("02-ban-scan-hoa-don.pdf", "INVOICE", _invoice("HD-D10", 3_000_000), scan=True),
            DocumentSpec("03-bien-nhan-nhan-vien-thanh-toan.pdf", "PAYMENT", _payment("Nguyễn Văn A", 3_000_000)),
            DocumentSpec("04-bang-ke-hoat-dong.pdf", "DECLARATION", ("BẢNG KÊ HOẠT ĐỘNG", "Đối chiếu đủ giai đoạn", "invoice:d10")),
        ),
    )


def _case_11() -> CaseSpec:
    return CaseSpec(
        case_id="D11",
        slug="case-11-loai-khoan-chi-ca-nhan",
        activity=ActivitySpec("activity:d11", "Công tác cá nhân", "2026-10-09T09:00:00+07:00", "Chuyến đi cá nhân"),
        budget_amount=8_000_000,
        grants=_grants(),
        documents=(
            DocumentSpec("01-hoa-don-ca-nhan.pdf", "INVOICE", _invoice("HD-D11", 500_000, supplier="Cửa hàng tiện lợi")),
            DocumentSpec("02-bang-ke-hoat-dong.pdf", "DECLARATION", ("BẢNG KÊ HOẠT ĐỘNG", "Đối chiếu đủ giai đoạn", "invoice:d11")),
        ),
    )


def _case_12() -> CaseSpec:
    return CaseSpec(
        case_id="D12",
        slug="case-12-khoan-chi-ngoai-pham-vi",
        activity=ActivitySpec("activity:d12", "Công tác nước ngoài", "2026-10-11T09:00:00+07:00", "Làm việc với đối tác"),
        budget_amount=8_000_000,
        grants=_grants(),
        documents=(
            DocumentSpec("01-hoa-don-ngoai-te.pdf", "INVOICE", ("HÓA ĐƠN NGOẠI TỆ", "Số hóa đơn: HD-D12", "Đơn vị: Overseas Vendor", "Tổng chi USD 200", "Ngày: 05/10/2026")),
            DocumentSpec("02-bang-ke-hoat-dong.pdf", "DECLARATION", ("BẢNG KÊ HOẠT ĐỘNG", "Đối chiếu đủ giai đoạn", "invoice:d12")),
        ),
    )


def _case_13() -> CaseSpec:
    return CaseSpec(
        case_id="D13",
        slug="case-13-giao-dich-chua-hoan-tat",
        activity=ActivitySpec("activity:d13", "Công tác Bình Dương", "2026-10-19T09:00:00+07:00", "Khảo sát nhà máy"),
        budget_amount=8_000_000,
        grants=_grants(),
        documents=(
            DocumentSpec("01-hoa-don-chi-phi.pdf", "INVOICE", _invoice("HD-D13", 3_000_000)),
            DocumentSpec("02-bien-nhan-nhan-vien-thanh-toan.pdf", "PAYMENT", _payment("Nguyễn Văn A", 3_000_000)),
            DocumentSpec("03-bien-nhan-dang-xu-ly.pdf", "ADVANCE", ("BIÊN NHẬN ĐANG XỬ LÝ", "Ứng 2.000.000 VND", "Trạng thái: PENDING")),
        ),
    )


def _case_14() -> CaseSpec:
    return CaseSpec(
        case_id="D14",
        slug="case-14-pdf-nhieu-trang-nhieu-chung-tu",
        activity=ActivitySpec("activity:d14", "Công tác Đà Lạt", "2026-10-21T09:00:00+07:00", "Khảo sát dịch vụ"),
        budget_amount=8_000_000,
        grants=_grants(),
        ledger=({"kind": "ADVANCE_RECEIVED", "amount": 2_000_000, "payer": "company:demo", "payee": "employee:employee-a"},),
        documents=(
            DocumentSpec(
                "01-ho-so-nhieu-trang.pdf",
                "INVOICE",
                ("HỒ SƠ CHI PHÍ CÔNG TÁC", "Trang 1: Hóa đơn", "Tổng chi 3.000.000 VND", "Ngày: 05/10/2026"),
            ),
            DocumentSpec(
                "02-ho-so-nhieu-trang.pdf",
                "PAYMENT",
                ("HỒ SƠ CHI PHÍ CÔNG TÁC", "Trang 2: Biên nhận", "Nhân viên trả 3.000.000 VND"),
            ),
            DocumentSpec(
                "03-ho-so-nhieu-trang.pdf",
                "ADVANCE",
                ("HỒ SƠ CHI PHÍ CÔNG TÁC", "Trang 3: Ứng", "Ứng 2.000.000 VND", "invoice:d14"),
            ),
        ),
    )


def _case_15() -> CaseSpec:
    return CaseSpec(
        case_id="D15",
        slug="case-15-bo-sung-khoan-da-thanh-toan",
        activity=ActivitySpec("activity:d15", "Công tác Quảng Ninh", "2026-10-24T09:00:00+07:00", "Khảo sát nhà cung cấp"),
        budget_amount=12_000_000,
        grants=_grants(),
        stages=("ban-dau", "bo-sung-thanh-toan"),
        ledger=({"kind": "ADVANCE_RECEIVED", "amount": 3_000_000, "payer": "company:demo", "payee": "employee:employee-a"},),
        documents=(
            DocumentSpec("01-hoa-don-chi-phi.pdf", "INVOICE", _invoice("HD-D15", 10_000_000)),
            DocumentSpec("02-bien-nhan-nhan-vien-thanh-toan.pdf", "PAYMENT", _payment("Nguyễn Văn A", 5_000_000)),
            DocumentSpec("03-bien-nhan-cong-ty-thanh-toan.pdf", "PAYMENT", _payment("Công ty Demo", 3_000_000)),
            DocumentSpec("04-phieu-ung.pdf", "ADVANCE", ("PHIẾU TẠM ỨNG", "Ứng 3.000.000 VND")),
            DocumentSpec("05-bang-ke-hoat-dong.pdf", "DECLARATION", ("BẢNG KÊ HOẠT ĐỘNG", "Đối chiếu đủ giai đoạn", "invoice:d15")),
            DocumentSpec(
                "01-bo-sung-thanh-toan.pdf",
                "PAYMENT",
                _payment("Nguyễn Văn A", 2_000_000),
                stage="bo-sung-thanh-toan",
            ),
        ),
    )


FUTURE_SCOPE_CASES: tuple[CaseSpec, ...] = (_case_06(),)
FUTURE_SCOPE_REASONS: dict[str, str] = {
    "D06": "Its only POLICY basis is T>B, which is outside the current product scope.",
}

CASES: tuple[CaseSpec, ...] = (
    _case_01(), _case_02(), _case_03(), _case_04(), _case_05(),
    _case_07(), _case_08(), _case_09(), _case_10(),
    _case_11(), _case_12(), _case_13(), _case_14(), _case_15(),
)

CASE_IDS: list[str] = [c.case_id for c in CASES]
CASE_SLUGS: list[str] = [c.slug for c in CASES]


def _stub_facts_from_gold(spec: CaseSpec) -> list[dict[str, object]]:
    """Build the STUB hand-transcription from the case's observable reading.

    The observable facts are what a correct reader sees on the sources (the
    input-layer reading), not the expected outcome; the STUB reader assesses
    exactly these. `budget`/`excluded`/`advance_pending`/`currency` are context
    or outcome notes, not transcription fields.
    """
    observable = dap_an.GOLD[spec.case_id].get("observable", {})
    facts: list[dict[str, object]] = []
    field_map = {
        "incurred": ("incurred", "INVOICE"),
        "paid_employee": ("paid_employee", "PAYMENT"),
        "paid_company": ("paid_company", "PAYMENT"),
        "advance": ("advance", "ADVANCE"),
    }
    for key, (field, role) in field_map.items():
        if key in observable:
            facts.append(
                {"field": field, "value": observable[key], "role": role, "quote": f"{field} (hand-transcription)"}
            )
    # Coverage is present unless the case is intentionally missing history (D09).
    if spec.coverage:
        facts.append({"field": "coverage", "value": 1, "role": "LEDGER", "quote": "Đối chiếu đủ giai đoạn"})
    # A stable economic key so two representations of one invoice dedup (D10).
    facts.append(
        {"field": "economic_key", "value": f"invoice:{spec.case_id.lower()}", "role": "INVOICE", "quote": f"invoice:{spec.case_id.lower()}"}
    )
    return facts


def stage_id_for_folder(folder: str) -> str:
    for stage, name in STAGE_FOLDERS.items():
        if name == folder:
            return stage
    return folder


def stage_documents(spec: CaseSpec, stage: str) -> tuple[DocumentSpec, ...]:
    return tuple(d for d in spec.documents if d.stage == stage)


def build_case(spec: CaseSpec, out: Path) -> ManifestEntry:
    """Write one case tree under ``out`` and return its manifest entry."""
    from du_lieu_kiem_thu.pdf import render_document

    case_dir = Path(out) / spec.slug
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "cau-hinh").mkdir(exist_ok=True)
    (case_dir / "dap-an").mkdir(exist_ok=True)
    (case_dir / "dau-vao").mkdir(exist_ok=True)

    # Stage documents into dau-vao/<stage folder>/.
    for stage in spec.stages:
        folder = case_dir / "dau-vao" / STAGE_FOLDERS[stage]
        folder.mkdir(parents=True, exist_ok=True)
        for doc in stage_documents(spec, stage):
            render_document(doc, folder)

    # Context the server imports (observable, no expected/route).
    (case_dir / "cau-hinh" / "to-chuc.json").write_text(
        json.dumps(_organization_json(spec), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (case_dir / "cau-hinh" / "khai-bao.json").write_text(
        json.dumps(
            {
                "employee": spec.employee,
                "activity": spec.activity.activity_id,
                "declared_purpose": spec.activity.purpose,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (case_dir / "cau-hinh" / "kich-ban.json").write_text(
        json.dumps(
            {
                "case_id": spec.case_id,
                "stages": [
                    {"stage_id": s, "folder": STAGE_FOLDERS[s]} for s in spec.stages
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # A STUB hand-transcription is written by the generator ONLY for the STUB
    # reader path; it is excluded from load_input (plan A). It is the literal
    # observable reading (input-layer facts), never the expected outcome.
    (case_dir / "cau-hinh" / "ban-doc-stub.json").write_text(
        json.dumps(
            {
                "data_origin": "STUB_TRANSCRIPTION",
                "facts": _stub_facts_from_gold(spec),
                "relations": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (case_dir / "HUONG-DAN.md").write_text(_guide(spec), encoding="utf-8")

    # Literal gold, staged.
    dap_an.write_gold(spec, case_dir / "dap-an")

    from invoice_referee.evaluation.packets import digest_packet_input

    return ManifestEntry(
        root_id=spec.case_id,
        split="development",
        strata=dap_an.strata_for(spec.case_id),
        profile=spec.profile,
        economic_key=f"invoice:{spec.case_id.lower()}",
        family=f"fam:{spec.case_id.lower()}",
        template=f"tpl:{spec.case_id.lower()}",
        layout="lay:a",
        issuer=f"iss:{spec.case_id.lower()}",
        input_digest=digest_packet_input(case_dir, stage_id="ban-dau"),
        gold_digest=dap_an.gold_digest(case_dir / "dap-an"),
    )


def _organization_json(spec: CaseSpec) -> dict[str, object]:
    activity: dict[str, object] = {
        "activity_id": spec.activity.activity_id,
        "name": spec.activity.name,
        "occurred_at": spec.activity.occurred_at,
        "profile": spec.profile,
    }
    if spec.budget_amount is not None:
        activity["authorization"] = {
            "id": f"auth:{spec.case_id.lower()}",
            "activity_id": spec.activity.activity_id,
            "actor": "employee:approver",
            "grant_ref": "grant:approver:per-action",
            "effect_range": [spec.budget_effect_from, None],
            "reason": "Phê duyệt hoạt động công tác",
            "record_key": f"auth:{spec.case_id.lower()}",
        }
    budgets: list[dict[str, object]] = []
    if spec.budget_amount is not None:
        budgets.append(
            {
                "id": f"budget:{spec.case_id.lower()}",
                "activity": spec.activity.activity_id,
                "amount": spec.budget_amount,
                "effect_range": [spec.budget_effect_from, None],
                "actor": "employee:approver",
                "grant_ref": "grant:approver:per-action",
                "witness_keys": [f"budget:{spec.case_id.lower()}"],
            }
        )
    coverage = None
    if spec.coverage:
        coverage = {
            "employee": spec.employee,
            "activity": spec.activity.activity_id,
            "start": "2026-09-01T00:00:00+07:00",
            "as_of": "2026-10-13T00:00:00+07:00",
            "fund_ids": ["company:demo"],
            "flow_kinds": [
                "ADVANCE_RECEIVED",
                "REIMBURSEMENT_RECEIVED",
                "EMPLOYEE_RETURN",
                "REVERSAL",
                "OBSERVED_UNALLOCATED",
            ],
            "opening_by_fund": {"company:demo": 0},
            "ledger_version": "ledger:v1",
            "witness_keys": ["ledger:coverage:2026-10"],
        }
    return {
        "organization_id": DEMO_TENANT,
        "profile": spec.profile,
        "data_origin": "SIMULATED",
        "activity": activity,
        "people": list(PEOPLE),
        "budgets": budgets,
        "grants": list(spec.grants),
        "ledger": list(spec.ledger),
        "coverage": coverage,
        "witnesses": [
            {
                "record_key": "ledger:coverage:2026-10",
                "quote": "Sổ theo dõi ứng/hoàn được đối chiếu đủ giai đoạn.",
                "actor": "employee:accountant-demo",
                "scope": spec.activity.activity_id,
                "observed_at": "2026-10-13T00:00:00+07:00",
            }
        ],
        "financial_as_of": "2026-10-13T00:00:00+07:00",
    }


def _guide(spec: CaseSpec) -> str:
    lines = [
        f"# Hướng dẫn case {spec.case_id} — {spec.activity.name}",
        "",
        f"- Nhân viên: Nguyễn Văn A",
        f"- Hoạt động: {spec.activity.name} ({spec.activity.activity_id})",
        f"- Mục đích: {spec.activity.purpose}",
        "",
        "## Các bước",
        "1. Chọn hoạt động và tạo hồ sơ.",
        "2. Đính kèm các tệp trong `dau-vao/01-nop-ban-dau/` theo đúng thứ tự.",
        "3. Nộp hồ sơ và xem kết luận/câu hỏi.",
    ]
    if len(spec.stages) > 1:
        lines.append("4. Khi được yêu cầu, đính kèm tệp trong `dau-vao/02-bo-sung/`.")
    lines += [
        "",
        "## Ghi chú",
        "- Đây là dữ liệu tổng hợp để kiểm thử; không phải hồ sơ doanh nghiệp thật.",
        "- Số tiền hiển thị trên chứng từ là căn cứ để hệ thống đọc và đối chiếu.",
    ]
    return "\n".join(lines) + "\n"
