"""Generate the versioned UC-03 reimbursement regression corpus.

The corpus is synthetic. It intentionally contains both clean and failing cases
so the accounting workflow can be demonstrated without handling real records.
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from html import escape
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.shared import Cm, Pt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "testcase_uc3_v2"
COMPANY_NAME = "CÔNG TY CỔ PHẦN GIẢI PHÁP BẮC NAM"
COMPANY_TAX_CODE = "0312345678"
EMPLOYEE_NAME = "Donal Trump"
EMPLOYEE_DEPARTMENT = "Phòng Kinh doanh"
EMPLOYEE_POSITION = "Nhân viên"


@dataclass(frozen=True)
class Line:
    item_id: str
    description: str
    amount: int
    category: str
    date: str = "2026-10-01"
    reference: str = ""
    note: str = "Đính kèm hóa đơn"


@dataclass(frozen=True)
class Evidence:
    file_stem: str
    document_type: str
    document_number: str
    description: str
    amount: int
    document_date: str = "2026-10-01"
    seller_name: str = "CÔNG TY TNHH THƯƠNG MẠI MINH PHÁT"
    seller_tax_code: str | None = "0101234567"
    buyer_name: str | None = COMPANY_NAME
    buyer_tax_code: str | None = COMPANY_TAX_CODE
    template_number: str | None = "01GTKT0/001"
    serial_number: str | None = "MP/26E"
    seller_address: str = "Tầng 5, 117-119 Nguyễn Du, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh"
    buyer_address: str = "Tầng 8, Tòa nhà Bắc Nam, 52 Đồng Du, Phường Bến Nghé, Quận 1, TP. Hồ Chí Minh"
    warehouse_address: str = "Kho Bắc Nam, Quận 7, TP. Hồ Chí Minh"
    payment_method: str = "Chuyển khoản"
    purchase_order: str = "PO-BN-2026-001"
    tax_rate: int = 10
    note: str = ""


@dataclass(frozen=True)
class Case:
    group_id: str
    group_name: str
    case_number: int
    slug: str
    title: str
    settlement_type: str
    lines: tuple[Line, ...]
    evidence: tuple[Evidence, ...]
    advance_amount: int = 0
    settlement_amount: int | None = None
    settlement_direction: str = ""
    report_total_override: int | None = None
    total_in_words: str | None = None
    expected_decision: str = "READY_FOR_APPROVAL"
    expected_rule: str | None = None
    implementation_status: str = "COVERED"
    expected_findings: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def case_id(self) -> str:
        return f"{self.group_id}-TC{self.case_number:02d}"

    @property
    def report_total(self) -> int:
        return self.report_total_override if self.report_total_override is not None else sum(
            line.amount for line in self.lines
        )


def money(value: int | Decimal | None) -> str:
    if value is None:
        return ""
    return f"{int(value):,}".replace(",", ".")


def vietnamese_date(value: str) -> str:
    if not value:
        return ""
    parsed = date.fromisoformat(value)
    return f"Ngày {parsed.day:02d} tháng {parsed.month:02d} năm {parsed.year}"


def invoice_amounts(evidence: Evidence) -> tuple[int, int, int]:
    """Return subtotal, VAT, total while preserving evidence.amount as total paid."""
    if evidence.tax_rate <= 0:
        return evidence.amount, 0, evidence.amount
    subtotal = round(evidence.amount * 100 / (100 + evidence.tax_rate))
    vat = evidence.amount - subtotal
    return subtotal, vat, evidence.amount


def unit_for(description: str) -> str:
    normalized = description.casefold()
    if "taxi" in normalized or "thuê xe" in normalized:
        return "Chuyến"
    if "khách sạn" in normalized:
        return "Đêm"
    if "ăn" in normalized or "tiếp khách" in normalized:
        return "Suất"
    if "dịch vụ" in normalized or "phí" in normalized:
        return "Lần"
    return "Cái"


def vietnamese_money_words(value: int) -> str:
    digits = ("không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín")

    def read_block(number: int, full: bool) -> str:
        hundreds, remainder = divmod(number, 100)
        tens, ones = divmod(remainder, 10)
        parts: list[str] = []
        if hundreds or full:
            parts.extend((digits[hundreds], "trăm"))
        if tens > 1:
            parts.extend((digits[tens], "mươi"))
            if ones == 1:
                parts.append("mốt")
            elif ones == 5:
                parts.append("lăm")
            elif ones:
                parts.append(digits[ones])
        elif tens == 1:
            parts.append("mười")
            if ones == 5:
                parts.append("lăm")
            elif ones:
                parts.append(digits[ones])
        elif ones:
            if hundreds or full:
                parts.append("lẻ")
            parts.append(digits[ones])
        return " ".join(parts)

    if value == 0:
        return "Không đồng"
    groups = ((1_000_000_000, "tỷ"), (1_000_000, "triệu"), (1_000, "nghìn"), (1, ""))
    remaining = value
    rendered: list[str] = []
    had_higher_group = False
    for divisor, label in groups:
        block, remaining = divmod(remaining, divisor)
        if block:
            rendered.append(read_block(block, had_higher_group))
            if label:
                rendered.append(label)
            had_higher_group = True
    phrase = " ".join(rendered).strip()
    return phrase[:1].upper() + phrase[1:] + " đồng"


def report_business_purpose(case_spec: "Case") -> str:
    """Use a natural business purpose instead of exposing testcase assertions."""
    if case_spec.settlement_type == "EMPLOYEE_REIMBURSEMENT":
        return "Đề nghị hoàn ứng các khoản chi đã chi trả phục vụ công việc theo bảng kê đính kèm."
    return "Quyết toán các khoản chi phục vụ công việc theo bảng kê và chứng từ đính kèm."


def case(
    group_id: str,
    group_name: str,
    number: int,
    slug: str,
    title: str,
    *,
    lines: tuple[Line, ...],
    evidence: tuple[Evidence, ...] = (),
    settlement_type: str = "ADVANCE_SETTLEMENT",
    advance_amount: int = 0,
    settlement_amount: int | None = None,
    settlement_direction: str = "",
    report_total_override: int | None = None,
    total_in_words: str | None = None,
    expected_decision: str = "READY_FOR_APPROVAL",
    expected_rule: str | None = None,
    implementation_status: str = "COVERED",
    expected_findings: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
) -> Case:
    return Case(
        group_id=group_id,
        group_name=group_name,
        case_number=number,
        slug=slug,
        title=title,
        settlement_type=settlement_type,
        lines=lines,
        evidence=evidence,
        advance_amount=advance_amount,
        settlement_amount=settlement_amount,
        settlement_direction=settlement_direction,
        report_total_override=report_total_override,
        total_in_words=total_in_words,
        expected_decision=expected_decision,
        expected_rule=expected_rule,
        implementation_status=implementation_status,
        expected_findings=expected_findings,
        notes=notes,
    )


def invoice(
    number: str,
    description: str,
    amount: int,
    *,
    stem: str | None = None,
    **kwargs: object,
) -> Evidence:
    return Evidence(
        file_stem=stem or f"hoa_don_{number}",
        document_type="E_INVOICE",
        document_number=number,
        description=description,
        amount=amount,
        **kwargs,
    )


def receipt(
    number: str,
    description: str,
    amount: int,
    *,
    doc_type: str = "PAPER_RECEIPT",
    stem: str | None = None,
    **kwargs: object,
) -> Evidence:
    return Evidence(
        file_stem=stem or f"chung_tu_{number}",
        document_type=doc_type,
        document_number=number,
        description=description,
        amount=amount,
        **kwargs,
    )


def build_cases() -> tuple[Case, ...]:
    g1 = "01_quyet_toan_so_tien"
    g1n = "Quyết toán và số tiền"
    g2 = "02_hop_le_chung_tu"
    g2n = "Hợp lệ chứng từ trước đối chiếu"
    g3 = "03_policy_khoan_chi"
    g3n = "Policy khoản chi và thẩm quyền"
    g4 = "04_bang_chung_va_matching"
    g4n = "Bằng chứng và ghép dòng chi"
    g5 = "05_ho_so_phuc_hop"
    g5n = "Hồ sơ hoàn ứng phức hợp"

    return (
        # Group 01: settlement arithmetic.
        case(g1, g1n, 1, "hoan_tra_tien_thua", "Hợp lệ - nhân viên hoàn trả tiền thừa", lines=(Line("L01", "Ăn uống tiếp khách dự án A", 3_240_000, "CLIENT_MEAL", reference="0001701"),), evidence=(invoice("0001701", "Ăn uống tiếp khách dự án A", 3_240_000),), advance_amount=4_000_000, settlement_amount=760_000, settlement_direction="Nhân viên hoàn trả công ty", expected_findings=("SET_PAPER_TOTAL_001", "SET_SETTLEMENT_DIFF_001")),
        case(g1, g1n, 2, "cong_ty_thanh_toan_them", "Hợp lệ - công ty thanh toán thêm", lines=(Line("L01", "Chi phí khách sạn công tác", 4_800_000, "HOTEL", reference="0001702"),), evidence=(invoice("0001702", "Chi phí khách sạn công tác", 4_800_000),), advance_amount=4_000_000, settlement_amount=800_000, settlement_direction="Công ty thanh toán thêm", expected_findings=("SET_PAPER_TOTAL_001", "SET_SETTLEMENT_DIFF_001")),
        case(g1, g1n, 3, "khong_chenh_lech", "Hợp lệ - không phát sinh chênh lệch", lines=(Line("L01", "Vật tư văn phòng phục vụ dự án", 2_500_000, "OFFICE_SUPPLIES", reference="0001703"),), evidence=(invoice("0001703", "Vật tư văn phòng phục vụ dự án", 2_500_000),), advance_amount=2_500_000, settlement_amount=0, settlement_direction="Không phát sinh chênh lệch"),
        case(g1, g1n, 4, "nhieu_dong_hop_le", "Hợp lệ - nhiều dòng chi trong một báo cáo", lines=(Line("L01", "Taxi gặp khách hàng", 650_000, "TAXI", reference="0001704"), Line("L02", "Ăn trưa tiếp khách", 1_450_000, "CLIENT_MEAL", reference="0001705"), Line("L03", "Văn phòng phẩm", 320_000, "OFFICE_SUPPLIES", reference="0001706")), evidence=(invoice("0001704", "Taxi gặp khách hàng", 650_000), invoice("0001705", "Ăn trưa tiếp khách", 1_450_000), invoice("0001706", "Văn phòng phẩm", 320_000)), advance_amount=3_000_000, settlement_amount=580_000, settlement_direction="Nhân viên hoàn trả công ty"),
        case(g1, g1n, 5, "tong_dong_khong_khop", "Không hợp lệ - tổng dòng không khớp tổng cộng", lines=(Line("L01", "Chi phí tiếp khách", 2_000_000, "CLIENT_MEAL", reference="0001707"), Line("L02", "Taxi công tác", 500_000, "TAXI", reference="0001708")), evidence=(invoice("0001707", "Chi phí tiếp khách", 2_000_000), invoice("0001708", "Taxi công tác", 500_000)), advance_amount=3_000_000, settlement_amount=500_000, settlement_direction="Nhân viên hoàn trả công ty", report_total_override=2_700_000, expected_decision="REQUEST_INFO", expected_rule="SET_PAPER_TOTAL_001", expected_findings=("SET_PAPER_TOTAL_001",)),
        case(g1, g1n, 6, "chenh_lech_ghi_sai", "Không hợp lệ - số tiền quyết toán chênh lệch ghi sai", lines=(Line("L01", "Chi phí hội họp", 3_600_000, "OPERATIONS", reference="0001709"),), evidence=(invoice("0001709", "Chi phí hội họp", 3_600_000),), advance_amount=5_000_000, settlement_amount=1_000_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="REQUEST_INFO", expected_rule="SET_SETTLEMENT_DIFF_001", expected_findings=("SET_SETTLEMENT_DIFF_001",)),
        case(g1, g1n, 7, "so_tien_bang_chu_khong_khop", "Không hợp lệ - số tiền bằng chữ không khớp", lines=(Line("L01", "Chi phí đào tạo nội bộ", 4_200_000, "OPERATIONS", reference="0001710"),), evidence=(invoice("0001710", "Chi phí đào tạo nội bộ", 4_200_000),), advance_amount=5_000_000, settlement_amount=800_000, settlement_direction="Nhân viên hoàn trả công ty", total_in_words="Bốn triệu một trăm nghìn đồng", expected_decision="REQUEST_INFO", expected_rule="SET_PAPER_CONSISTENCY_001", expected_findings=("SET_PAPER_CONSISTENCY_001",)),
        case(g1, g1n, 8, "thieu_so_tien_tam_ung", "Không hợp lệ - đơn quyết toán thiếu số tiền tạm ứng", lines=(Line("L01", "Dịch vụ in ấn tài liệu", 1_800_000, "OPERATIONS", reference="0001711"),), evidence=(invoice("0001711", "Dịch vụ in ấn tài liệu", 1_800_000),), settlement_amount=1_800_000, settlement_direction="Công ty thanh toán thêm", expected_decision="REQUEST_INFO", expected_rule="SET_ADV_AMOUNT_001", expected_findings=("SET_ADV_AMOUNT_001",)),
        case(g1, g1n, 9, "thieu_tong_cong", "Không hợp lệ - không đọc được tổng cộng trên đơn", lines=(Line("L01", "Chi phí thuê thiết bị", 6_000_000, "OPERATIONS", reference="0001712"),), evidence=(invoice("0001712", "Chi phí thuê thiết bị", 6_000_000),), advance_amount=6_000_000, report_total_override=0, expected_decision="REQUEST_INFO", expected_rule="SET_PAPER_TOTAL_001", expected_findings=("SET_PAPER_TOTAL_001",), notes=("Đây là fixture trích xuất: tổng cộng được cố ý để trống trên form.",)),
        case(g1, g1n, 10, "vuot_tham_quyen", "Vượt thẩm quyền - tổng hồ sơ trên 100 triệu", lines=(Line("L01", "Mua thiết bị phục vụ sự kiện", 120_000_000, "OPERATIONS", reference="0001713"),), evidence=(invoice("0001713", "Mua thiết bị phục vụ sự kiện", 120_000_000),), advance_amount=120_000_000, settlement_amount=0, settlement_direction="Không phát sinh chênh lệch", expected_decision="ESCALATE", expected_rule="SET_AUTH_001", expected_findings=("SET_AUTH_001",)),

        # Group 02: evidence validity before matching.
        case(g2, g2n, 1, "hoa_don_dien_tu_day_du", "Hợp lệ - hóa đơn điện tử đủ trường bắt buộc", lines=(Line("L01", "Mua chuột và bàn phím", 3_600_000, "OFFICE_SUPPLIES", reference="0001801"),), evidence=(invoice("0001801", "Mua chuột và bàn phím", 3_600_000),), advance_amount=4_000_000, settlement_amount=400_000, settlement_direction="Nhân viên hoàn trả công ty"),
        case(g2, g2n, 2, "hoa_don_thieu_mst_nguoi_mua", "Không hợp lệ - hóa đơn điện tử thiếu MST người mua", lines=(Line("L01", "Mua màn hình", 5_400_000, "OFFICE_SUPPLIES", reference="0001802"),), evidence=(invoice("0001802", "Mua màn hình", 5_400_000, buyer_tax_code=None),), advance_amount=6_000_000, settlement_amount=600_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="REQUEST_INFO", expected_rule="SET_DOCUMENT_REQUIRED_FIELDS_001", expected_findings=("REQUIRED_FIELD_UNCLEAR:buyer_tax_code",)),
        case(g2, g2n, 3, "mst_nguoi_mua_khac", "Không hợp lệ - MST người mua thuộc công ty khác", lines=(Line("L01", "Mua thiết bị mạng", 8_600_000, "OFFICE_SUPPLIES", reference="0001803"),), evidence=(invoice("0001803", "Mua thiết bị mạng", 8_600_000, buyer_tax_code="0309876543", buyer_name="CÔNG TY TNHH ĐÔNG NAM"),), advance_amount=9_000_000, settlement_amount=400_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="RECOMMEND_REJECT", expected_rule="SET_BUYER_IDENTITY_001", expected_findings=("BUYER_TAX_CODE_MISMATCH",)),
        case(g2, g2n, 4, "hoa_don_thieu_so", "Không hợp lệ - hóa đơn điện tử thiếu số hóa đơn", lines=(Line("L01", "Mua giấy in", 1_260_000, "OFFICE_SUPPLIES", reference=""),), evidence=(invoice("", "Mua giấy in", 1_260_000, stem="hoa_don_thieu_so"),), advance_amount=1_500_000, settlement_amount=240_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="REQUEST_INFO", expected_rule="SET_DOCUMENT_REQUIRED_FIELDS_001", expected_findings=("REQUIRED_FIELD_UNCLEAR:document_number",)),
        case(g2, g2n, 5, "mst_nguoi_ban_sai_dinh_dang", "Không hợp lệ - MST người bán sai định dạng", lines=(Line("L01", "Sửa máy in", 1_950_000, "OPERATIONS", reference="0001805"),), evidence=(invoice("0001805", "Sửa máy in", 1_950_000, seller_tax_code="01012A4567"),), advance_amount=2_000_000, settlement_amount=50_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="REQUEST_INFO", expected_rule="SET_DOCUMENT_REQUIRED_FIELDS_001", expected_findings=("INVALID_TAX_CODE_FORMAT:issuer_tax_code",)),
        case(g2, g2n, 6, "ve_may_bay_hop_le", "Hợp lệ - vé máy bay điện tử là chứng từ gốc", lines=(Line("L01", "Vé máy bay công tác Hà Nội Đà Nẵng", 2_850_000, "TRAVEL", reference="VN-ABC123"),), evidence=(receipt("VN-ABC123", "Vé máy bay công tác Hà Nội Đà Nẵng", 2_850_000, doc_type="TRANSPORT_TICKET", seller_name="Vietnam Airlines", seller_tax_code="0100107518", buyer_name=EMPLOYEE_NAME, buyer_tax_code=None, template_number=None, serial_number=None),), advance_amount=3_000_000, settlement_amount=150_000, settlement_direction="Nhân viên hoàn trả công ty"),
        case(g2, g2n, 7, "chuyen_khoan_chua_thanh_cong", "Không hợp lệ - bằng chứng chuyển khoản chưa hoàn tất", lines=(Line("L01", "Phí gửi hồ sơ", 450_000, "OPERATIONS", reference="GD-1807", note="Chứng từ chuyển khoản thay thế"),), evidence=(receipt("GD-1807", "Chuyển khoản phí gửi hồ sơ", 450_000, doc_type="PAYMENT_PROOF", seller_name="Ngân hàng Demo", seller_tax_code=None, buyer_name=None, buyer_tax_code=None, template_number=None, serial_number=None, note="Trạng thái: Đang xử lý"),), settlement_type="EMPLOYEE_REIMBURSEMENT", expected_decision="REQUEST_INFO", expected_rule="SET_DOCUMENT_VALIDITY_001", expected_findings=("PAYMENT_NOT_CONFIRMED",)),
        case(g2, g2n, 8, "khong_phan_loai_duoc_chung_tu", "Không hợp lệ - không phân loại được chứng từ", lines=(Line("L01", "Thanh toán dịch vụ tại đối tác", 720_000, "OTHER", reference="DOC-1808"),), evidence=(receipt("DOC-1808", "Giấy xác nhận thanh toán dịch vụ", 720_000, doc_type="UNKNOWN", seller_name="Đơn vị đối tác", seller_tax_code=None, buyer_name=None, buyer_tax_code=None, template_number=None, serial_number=None),), settlement_type="EMPLOYEE_REIMBURSEMENT", expected_decision="REQUEST_INFO", expected_rule="SET_DOCUMENT_CLASSIFICATION_001", implementation_status="COVERED", expected_findings=("DOCUMENT_TYPE_UNCLEAR",)),
        case(g2, g2n, 9, "hoa_don_so_hoc_khong_khop", "Không hợp lệ - tiền hàng và tổng thanh toán không nhất quán", lines=(Line("L01", "Mua dây cáp", 1_100_000, "OFFICE_SUPPLIES", reference="0001809"),), evidence=(invoice("0001809", "Mua dây cáp", 1_100_000, note="Tiền hàng 1.000.000 đồng, thuế GTGT 100.000 đồng, tổng thanh toán 1.100.000 đồng"),), advance_amount=1_500_000, settlement_amount=400_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="REQUEST_INFO", expected_rule="SET_DOCUMENT_CONSISTENCY_001", implementation_status="PLANNED", expected_findings=("DOCUMENT_ARITHMETIC_MISMATCH",)),
        case(g2, g2n, 10, "nguoi_mua_khach_le", "Không hợp lệ - hóa đơn ghi người mua là khách lẻ", lines=(Line("L01", "Mua vật tư sửa chữa", 2_200_000, "OPERATIONS", reference="0001810"),), evidence=(invoice("0001810", "Mua vật tư sửa chữa", 2_200_000, buyer_name="Khách lẻ", buyer_tax_code=None),), advance_amount=2_500_000, settlement_amount=300_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="REQUEST_INFO", expected_rule="SET_DOCUMENT_REQUIRED_FIELDS_001", expected_findings=("BUYER_IDENTITY_UNCLEAR",)),

        # Group 03: deterministic policy.
        case(g3, g3n, 1, "taxi_trong_han_muc", "Hợp lệ - taxi trong hạn mức", lines=(Line("L01", "Taxi đi gặp khách hàng", 1_800_000, "TAXI", reference="0001901"),), evidence=(invoice("0001901", "Taxi đi gặp khách hàng", 1_800_000),), advance_amount=2_000_000, settlement_amount=200_000, settlement_direction="Nhân viên hoàn trả công ty"),
        case(g3, g3n, 2, "taxi_vuot_han_muc", "Vượt policy - taxi trên hạn mức", lines=(Line("L01", "Taxi đi gặp khách hàng", 2_300_000, "TAXI", reference="0001902"),), evidence=(invoice("0001902", "Taxi đi gặp khách hàng", 2_300_000),), advance_amount=2_500_000, settlement_amount=200_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="ESCALATE", expected_rule="SET_LIMIT_001", expected_findings=("SET_LIMIT_001",)),
        case(g3, g3n, 3, "tiep_khach_trong_han_muc", "Hợp lệ - tiếp khách trong hạn mức", lines=(Line("L01", "Tiếp khách dự án Bắc Nam", 4_800_000, "CLIENT_MEAL", reference="0001903"),), evidence=(invoice("0001903", "Tiếp khách dự án Bắc Nam", 4_800_000),), advance_amount=5_000_000, settlement_amount=200_000, settlement_direction="Nhân viên hoàn trả công ty"),
        case(g3, g3n, 4, "tiep_khach_vuot_han_muc", "Vượt policy - tiếp khách trên hạn mức", lines=(Line("L01", "Tiếp khách dự án Bắc Nam", 5_600_000, "CLIENT_MEAL", reference="0001904"),), evidence=(invoice("0001904", "Tiếp khách dự án Bắc Nam", 5_600_000),), advance_amount=6_000_000, settlement_amount=400_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="ESCALATE", expected_rule="SET_LIMIT_001", expected_findings=("SET_LIMIT_001",)),
        case(g3, g3n, 5, "chi_tieu_ca_nhan", "Không hợp lệ - khoản chi cá nhân", lines=(Line("L01", "Mua nước hoa", 1_200_000, "PERSONAL", reference="0001905"),), evidence=(invoice("0001905", "Mua nước hoa", 1_200_000),), settlement_type="EMPLOYEE_REIMBURSEMENT", expected_decision="RECOMMEND_REJECT", expected_rule="SET_CATEGORY_001", expected_findings=("SET_CATEGORY_001",)),
        case(g3, g3n, 6, "ruou_bia_theo_chinh_sach", "Ngoại lệ policy - rượu bia tiếp khách", lines=(Line("L01", "Rượu vang tiếp khách", 1_650_000, "CLIENT_MEAL", reference="0001906"),), evidence=(invoice("0001906", "Rượu vang tiếp khách", 1_650_000),), advance_amount=2_000_000, settlement_amount=350_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="ACCOUNTANT_REVIEW", expected_rule="SET_PROHIBITED_ITEM_001", implementation_status="PLANNED", expected_findings=("PROHIBITED_OR_RESTRICTED_ITEM",)),
        case(g3, g3n, 7, "nop_dung_han_30_ngay", "Hợp lệ - khoản chi đúng hạn 30 ngày", lines=(Line("L01", "Phí vận chuyển hàng hóa", 900_000, "OPERATIONS", date="2026-09-12", reference="0001907"),), evidence=(invoice("0001907", "Phí vận chuyển hàng hóa", 900_000, document_date="2026-09-12"),), advance_amount=1_000_000, settlement_amount=100_000, settlement_direction="Nhân viên hoàn trả công ty"),
        case(g3, g3n, 8, "nop_qua_han_31_ngay", "Ngoại lệ policy - nộp hồ sơ quá 30 ngày", lines=(Line("L01", "Phí vận chuyển hàng hóa", 900_000, "OPERATIONS", date="2026-09-11", reference="0001908"),), evidence=(invoice("0001908", "Phí vận chuyển hàng hóa", 900_000, document_date="2026-09-11"),), advance_amount=1_000_000, settlement_amount=100_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="ACCOUNTANT_REVIEW", expected_rule="SET_DEADLINE_001", expected_findings=("SET_DEADLINE_001",)),
        case(g3, g3n, 9, "ngay_chi_chua_xac_dinh", "Không hợp lệ - chưa xác định ngày chi", lines=(Line("L01", "Phí dịch vụ kỹ thuật", 1_400_000, "OPERATIONS", date="", reference="0001909"),), evidence=(invoice("0001909", "Phí dịch vụ kỹ thuật", 1_400_000, document_date=""),), advance_amount=1_500_000, settlement_amount=100_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="REQUEST_INFO", expected_rule="SET_EXPENSE_DATE_001", expected_findings=("SET_EXPENSE_DATE_001",)),
        case(g3, g3n, 10, "danh_muc_chua_xac_dinh", "Không hợp lệ - chưa xác định danh mục khoản chi", lines=(Line("L01", "Thanh toán dịch vụ tại đơn vị đối tác", 1_100_000, "UNKNOWN", reference="0001910"),), evidence=(invoice("0001910", "Thanh toán dịch vụ tại đơn vị đối tác", 1_100_000),), advance_amount=1_300_000, settlement_amount=200_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="REQUEST_INFO", expected_rule="SET_CATEGORY_UNKNOWN_001", expected_findings=("SET_CATEGORY_UNKNOWN_001",)),

        # Group 04: evidence declarations and matching.
        case(g4, g4n, 1, "khop_so_hoa_don_va_so_tien", "Hợp lệ - số hóa đơn và số tiền khớp", lines=(Line("L01", "Ăn uống tiếp khách khách hàng ABC", 3_240_000, "CLIENT_MEAL", reference="0002001"),), evidence=(invoice("0002001", "Ăn uống tiếp khách khách hàng ABC", 3_240_000),), advance_amount=4_000_000, settlement_amount=760_000, settlement_direction="Nhân viên hoàn trả công ty"),
        case(g4, g4n, 2, "cung_so_tien_sai_noi_dung", "Không hợp lệ - cùng số tiền nhưng sai nội dung", lines=(Line("L01", "Ăn uống tiếp khách khách hàng ABC", 2_500_000, "CLIENT_MEAL", reference="0002002"),), evidence=(invoice("0002002", "Mua ghế văn phòng", 2_500_000),), advance_amount=3_000_000, settlement_amount=500_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="REQUEST_INFO", expected_rule="SET_PAPER_MATCH_001", expected_findings=("SET_PAPER_MATCH_001",)),
        case(g4, g4n, 3, "khop_so_hoa_don_lech_so_tien", "Không hợp lệ - số hóa đơn khớp nhưng số tiền lệch", lines=(Line("L01", "Thuê phòng họp", 2_160_000, "OPERATIONS", reference="0002003"),), evidence=(invoice("0002003", "Thuê phòng họp", 2_500_000),), advance_amount=3_000_000, settlement_amount=840_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="REQUEST_INFO", expected_rule="SET_PAPER_AMOUNT_001", expected_findings=("SET_PAPER_AMOUNT_001",)),
        case(g4, g4n, 4, "thieu_chung_tu_khong_ly_do", "Không hợp lệ - dòng ghi đính kèm nhưng thiếu chứng từ", lines=(Line("L01", "Mua vật tư sửa chữa", 2_750_000, "OPERATIONS", reference="0002004"),), evidence=(), advance_amount=3_000_000, settlement_amount=250_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="REQUEST_INFO", expected_rule="SET_PAPER_EVIDENCE_REQUIRED", expected_findings=("SET_PAPER_EVIDENCE_REQUIRED",)),
        case(g4, g4n, 5, "khong_chung_tu_co_ly_do", "Ngoại lệ - không có chứng từ nhưng có giải trình", lines=(Line("L01", "Phí bốc xếp tại chợ", 450_000, "OPERATIONS", reference="", note="Không có chứng từ: người cung cấp không xuất hóa đơn"),), evidence=(), advance_amount=500_000, settlement_amount=50_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="ACCOUNTANT_REVIEW", expected_rule="SET_PAPER_EVIDENCE_EXCEPTION", expected_findings=("SET_PAPER_EVIDENCE_EXCEPTION",)),
        case(g4, g4n, 6, "bang_chung_chuyen_khoan_thay_the", "Ngoại lệ - dùng chứng từ chuyển khoản thay thế", lines=(Line("L01", "Phí dịch vụ công chứng", 1_200_000, "OPERATIONS", reference="GD-2006", note="Chứng từ chuyển khoản thay thế hóa đơn"),), evidence=(receipt("GD-2006", "Chuyển khoản phí dịch vụ công chứng", 1_200_000, doc_type="PAYMENT_PROOF", seller_name="Ngân hàng Demo", seller_tax_code=None, buyer_name=None, buyer_tax_code=None, template_number=None, serial_number=None, note="Trạng thái: Đã chuyển thành công"),), advance_amount=1_500_000, settlement_amount=300_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="ACCOUNTANT_REVIEW", expected_rule="SET_PAPER_EVIDENCE_EXCEPTION", expected_findings=("SET_PAPER_EVIDENCE_EXCEPTION",)),
        case(g4, g4n, 7, "ve_dien_tu_thay_the", "Hợp lệ - vé điện tử thay thế hóa đơn", lines=(Line("L01", "Phí gửi xe công tác", 200_000, "TRAVEL", reference="VDT-2007", note="Vé điện tử thay thế hóa đơn"),), evidence=(receipt("VDT-2007", "Vé điện tử bãi đỗ xe", 200_000, doc_type="TRANSPORT_TICKET", seller_name="Bãi đỗ xe Sân bay", seller_tax_code=None, buyer_name=EMPLOYEE_NAME, buyer_tax_code=None, template_number=None, serial_number=None),), advance_amount=300_000, settlement_amount=100_000, settlement_direction="Nhân viên hoàn trả công ty"),
        case(g4, g4n, 8, "chung_tu_dinh_kem_khong_co_tren_report", "Không hợp lệ - chứng từ đính kèm không thuộc dòng nào", lines=(Line("L01", "Chi phí in ấn", 850_000, "OPERATIONS", reference="0002008"),), evidence=(invoice("0002008", "Chi phí in ấn", 850_000), invoice("0002099", "Mua văn phòng phẩm không khai báo", 300_000)), advance_amount=1_500_000, settlement_amount=650_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="REQUEST_INFO", expected_rule="SET_PAPER_UNMATCHED_001", expected_findings=("SET_PAPER_UNMATCHED_001",)),
        case(g4, g4n, 9, "so_hoa_don_khai_bao_nhung_thieu_file", "Không hợp lệ - khai báo hóa đơn nhưng không đính kèm file", lines=(Line("L01", "Mua đồng phục nhân viên", 4_200_000, "OPERATIONS", reference="0002009"),), evidence=(), advance_amount=5_000_000, settlement_amount=800_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="REQUEST_INFO", expected_rule="SET_PAPER_EVIDENCE_REQUIRED", expected_findings=("SET_PAPER_EVIDENCE_REQUIRED",)),
        case(g4, g4n, 10, "evidence_gan_phu_hop_nhung_mo_ho", "Cần xác nhận - evidence gần phù hợp nhưng chưa đủ chắc chắn", lines=(Line("L01", "Mua vật phẩm công nghệ từ công ty Thiên Ưng", 83_600_000, "OPERATIONS", reference=""),), evidence=(invoice("0002010", "Mua phụ kiện máy tính", 83_600_000, seller_name="CÔNG TY TNHH THIÊN ƯNG"),), advance_amount=85_000_000, settlement_amount=1_400_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="REQUEST_INFO", expected_rule="SET_PAPER_MATCH_001", expected_findings=("SET_PAPER_MATCH_001",)),

        # Group 05: complex reimbursement reports.
        case(g5, g5n, 1, "ba_hoa_don_cong_tac_hop_le", "Hợp lệ - ba hóa đơn cho một chuyến công tác", lines=(Line("L01", "Vé máy bay đi công tác", 2_850_000, "TRAVEL", reference="VN-5001"), Line("L02", "Khách sạn công tác", 3_600_000, "HOTEL", reference="0005002"), Line("L03", "Taxi di chuyển công tác", 850_000, "TAXI", reference="0005003")), evidence=(receipt("VN-5001", "Vé máy bay đi công tác", 2_850_000, doc_type="TRANSPORT_TICKET", seller_name="Vietnam Airlines", seller_tax_code="0100107518", buyer_name=EMPLOYEE_NAME, buyer_tax_code=None, template_number=None, serial_number=None), invoice("0005002", "Khách sạn công tác", 3_600_000), invoice("0005003", "Taxi di chuyển công tác", 850_000)), advance_amount=8_000_000, settlement_amount=700_000, settlement_direction="Nhân viên hoàn trả công ty"),
        case(g5, g5n, 2, "mot_hoa_don_phan_bo_hai_dong", "Hợp lệ - một hóa đơn phân bổ đúng cho hai dòng", lines=(Line("L01", "Thiết bị cho nhân viên A", 2_000_000, "OFFICE_SUPPLIES", reference="0005004"), Line("L02", "Thiết bị cho nhân viên B", 1_500_000, "OFFICE_SUPPLIES", reference="0005004")), evidence=(invoice("0005004", "Thiết bị công nghệ cho nhân viên A và B", 3_500_000),), advance_amount=4_000_000, settlement_amount=500_000, settlement_direction="Nhân viên hoàn trả công ty", implementation_status="PLANNED", expected_findings=("INVOICE_ALLOCATION_SUM_MATCH",)),
        case(g5, g5n, 3, "phan_bo_vuot_gia_tri_hoa_don", "Không hợp lệ - một hóa đơn bị phân bổ vượt giá trị", lines=(Line("L01", "Thiết bị cho nhân viên A", 2_500_000, "OFFICE_SUPPLIES", reference="0005005"), Line("L02", "Thiết bị cho nhân viên B", 2_000_000, "OFFICE_SUPPLIES", reference="0005005")), evidence=(invoice("0005005", "Thiết bị công nghệ", 3_500_000),), advance_amount=5_000_000, settlement_amount=500_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="REQUEST_INFO", expected_rule="SET_EVIDENCE_REUSE_001", implementation_status="PLANNED", expected_findings=("INVOICE_ALLOCATION_OVER_LIMIT",)),
        case(g5, g5n, 4, "mot_dong_hai_hoa_don", "Hợp lệ - một dòng dùng hai hóa đơn gốc", lines=(Line("L01", "Mua vật tư sự kiện", 5_000_000, "OPERATIONS", reference="0005006, 0005007"),), evidence=(invoice("0005006", "Mua vật tư sự kiện đợt 1", 2_000_000), invoice("0005007", "Mua vật tư sự kiện đợt 2", 3_000_000)), advance_amount=6_000_000, settlement_amount=1_000_000, settlement_direction="Nhân viên hoàn trả công ty"),
        case(g5, g5n, 5, "hoa_don_va_chuyen_khoan", "Hợp lệ - hóa đơn gốc kèm bằng chứng thanh toán", lines=(Line("L01", "Thuê địa điểm hội thảo", 12_000_000, "OPERATIONS", reference="0005008"),), evidence=(invoice("0005008", "Thuê địa điểm hội thảo", 12_000_000), receipt("GD-5008", "Chuyển khoản thuê địa điểm hội thảo", 12_000_000, doc_type="PAYMENT_PROOF", seller_name="Ngân hàng Demo", seller_tax_code=None, buyer_name=None, buyer_tax_code=None, template_number=None, serial_number=None, note="Trạng thái: Hoàn tất")), advance_amount=12_500_000, settlement_amount=500_000, settlement_direction="Nhân viên hoàn trả công ty", implementation_status="PLANNED", expected_findings=("PAYMENT_PROOF_NOT_DOUBLE_COUNTED",)),
        case(g5, g5n, 6, "hoa_don_trung_voi_ho_so_truoc", "Không hợp lệ - hóa đơn trùng định danh hồ sơ trước", lines=(Line("L01", "Mua mực in", 1_850_000, "OFFICE_SUPPLIES", reference="0005009"),), evidence=(invoice("0005009", "Mua mực in", 1_850_000),), advance_amount=2_000_000, settlement_amount=150_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="RECOMMEND_REJECT", expected_rule="SET_DUPLICATE_001", implementation_status="PLANNED", expected_findings=("DUPLICATE_INVOICE_IDENTITY",)),
        case(g5, g5n, 7, "file_doi_ten_nhung_trung_noi_dung", "Không hợp lệ - file đổi tên nhưng nội dung hóa đơn trùng", lines=(Line("L01", "Mua thiết bị trình chiếu", 6_600_000, "OPERATIONS", reference="0005010"),), evidence=(invoice("0005010", "Mua thiết bị trình chiếu", 6_600_000, stem="ban_sao_hoa_don_0005010"),), advance_amount=7_000_000, settlement_amount=400_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="RECOMMEND_REJECT", expected_rule="SET_DUPLICATE_001", implementation_status="PLANNED", expected_findings=("DUPLICATE_INVOICE_CONTENT",)),
        case(g5, g5n, 8, "hon_hop_goc_thay_the_khong_chung_tu", "Ngoại lệ - hồ sơ có chứng từ gốc, thay thế và không chứng từ", lines=(Line("L01", "Ăn uống tiếp khách", 2_400_000, "CLIENT_MEAL", reference="0005011"), Line("L02", "Phí gửi xe", 180_000, "TRAVEL", reference="VDT-5012", note="Vé điện tử thay thế hóa đơn"), Line("L03", "Phí bốc xếp", 300_000, "OPERATIONS", reference="", note="Không có chứng từ: nhà cung cấp nhỏ lẻ không xuất chứng từ")), evidence=(invoice("0005011", "Ăn uống tiếp khách", 2_400_000), receipt("VDT-5012", "Vé điện tử gửi xe", 180_000, doc_type="TRANSPORT_TICKET", seller_name="Bãi xe Trung tâm", seller_tax_code=None, buyer_name=EMPLOYEE_NAME, buyer_tax_code=None, template_number=None, serial_number=None)), advance_amount=3_500_000, settlement_amount=620_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="ACCOUNTANT_REVIEW", expected_rule="SET_PAPER_EVIDENCE_EXCEPTION", expected_findings=("SET_PAPER_EVIDENCE_EXCEPTION",)),
        case(g5, g5n, 9, "chung_tu_dinh_kem_du_thua", "Không hợp lệ - có chứng từ dư chưa được khai trong báo cáo", lines=(Line("L01", "Thuê xe đi công tác", 1_900_000, "TAXI", reference="0005013"), Line("L02", "Khách sạn công tác", 2_700_000, "HOTEL", reference="0005014")), evidence=(invoice("0005013", "Thuê xe đi công tác", 1_900_000), invoice("0005014", "Khách sạn công tác", 2_700_000), invoice("0005015", "Mua quà tặng không khai báo", 600_000)), advance_amount=6_000_000, settlement_amount=1_400_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="REQUEST_INFO", expected_rule="SET_PAPER_UNMATCHED_001", expected_findings=("SET_PAPER_UNMATCHED_001",)),
        case(g5, g5n, 10, "sai_mst_va_lech_so_tien", "Không hợp lệ - MST người mua sai đồng thời lệch số tiền", lines=(Line("L01", "Mua thiết bị hội nghị", 9_500_000, "OPERATIONS", reference="0005016"),), evidence=(invoice("0005016", "Mua thiết bị hội nghị", 8_900_000, buyer_tax_code="0309876543", buyer_name="CÔNG TY TNHH ĐÔNG NAM"),), advance_amount=10_000_000, settlement_amount=500_000, settlement_direction="Nhân viên hoàn trả công ty", expected_decision="RECOMMEND_REJECT", expected_rule="SET_BUYER_IDENTITY_001", expected_findings=("BUYER_TAX_CODE_MISMATCH", "SET_PAPER_AMOUNT_001")),
    )


def configure_doc(document: Document) -> None:
    section = document.sections[0]
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.8)
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)
    style = document.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(10)


def add_docx_table(document: Document, headers: list[str], rows: list[list[str]]) -> None:
    table = document.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        cell.text = header
        for run in cell.paragraphs[0].runs:
            run.bold = True
            run.font.size = Pt(9)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = value
            for run in cells[index].paragraphs[0].runs:
                run.font.size = Pt(9)
            cells[index].paragraphs[0].alignment = (
                WD_ALIGN_PARAGRAPH.RIGHT if index == len(row) - 2 else WD_ALIGN_PARAGRAPH.LEFT
            )


def report_lines(case_spec: Case) -> list[list[str]]:
    rows: list[list[str]] = []
    for index, line in enumerate(case_spec.lines, start=1):
        rows.append([
            str(index),
            line.description,
            line.reference or "Không có",
            money(line.amount),
            line.note,
        ])
    rows.append(["", "Tổng cộng", "", money(case_spec.report_total) if case_spec.report_total else "", ""])
    return rows


def create_report_docx(case_spec: Case, output_path: Path) -> None:
    document = Document()
    configure_doc(document)
    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("GIẤY ĐỀ NGHỊ HOÀN ỨNG")
    run.bold = True
    run.font.size = Pt(16)
    document.add_paragraph("Kính gửi: Ban Giám đốc và Phòng Kế toán")
    document.add_paragraph(f"Người đề nghị: {EMPLOYEE_NAME}")
    document.add_paragraph(f"Chức vụ: {EMPLOYEE_POSITION}")
    document.add_paragraph(f"Bộ phận: {EMPLOYEE_DEPARTMENT}")
    document.add_paragraph(f"Nội dung: {report_business_purpose(case_spec)}")
    document.add_paragraph("")
    add_docx_table(
        document,
        ["STT", "NỘI DUNG", "HÓA ĐƠN", "SỐ TIỀN (VND)", "GHI CHÚ"],
        report_lines(case_spec),
    )
    document.add_paragraph(
        f"Bằng chữ: {case_spec.total_in_words or 'Theo số tiền tổng cộng nêu trên.'}"
    )
    if case_spec.settlement_type == "ADVANCE_SETTLEMENT":
        if case_spec.advance_amount:
            document.add_paragraph(f"Số tiền đã tạm ứng: {money(case_spec.advance_amount)} đồng")
        else:
            document.add_paragraph("Số tiền đã tạm ứng: ........................................")
    if case_spec.settlement_amount is not None:
        document.add_paragraph(
            f"{case_spec.settlement_direction or 'Số tiền quyết toán'}: "
            f"{money(case_spec.settlement_amount)} đồng"
        )
    document.add_paragraph("Thông tin chuyển khoản: 0123456789 - Ngân hàng Demo - Donal Trump")
    document.add_paragraph("")
    signatures = document.add_table(rows=2, cols=3)
    signatures.alignment = WD_TABLE_ALIGNMENT.CENTER
    signature_labels = ["NGƯỜI ĐỀ NGHỊ HOÀN ỨNG", "KẾ TOÁN", "GIÁM ĐỐC"]
    signature_states = ["(Đã ký)", "(Đang chờ xác nhận)", "(Đang chờ xác nhận)"]
    for index, label in enumerate(signature_labels):
        signatures.cell(0, index).text = label
        signatures.cell(1, index).text = signature_states[index]
        for row_index in range(2):
            paragraph = signatures.cell(row_index, index).paragraphs[0]
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in paragraph.runs:
                run.font.size = Pt(9)
                if row_index == 0:
                    run.bold = True
    document.save(output_path)


def create_evidence_docx(evidence: Evidence, output_path: Path) -> None:
    if evidence.document_type == "E_INVOICE":
        create_invoice_docx(evidence, output_path)
        return

    document = Document()
    configure_doc(document)
    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    name = {
        "E_INVOICE": "HÓA ĐƠN GIÁ TRỊ GIA TĂNG",
        "TRANSPORT_TICKET": "VÉ ĐIỆN TỬ",
        "PAYMENT_PROOF": "XÁC NHẬN GIAO DỊCH THANH TOÁN",
        "PAPER_RECEIPT": "PHIẾU THANH TOÁN",
    }.get(evidence.document_type, "CHỨNG TỪ THANH TOÁN")
    run = title.add_run(name)
    run.bold = True
    run.font.size = Pt(15)
    document.add_paragraph(f"Đơn vị phát hành: {evidence.seller_name}")
    if evidence.seller_tax_code is not None:
        document.add_paragraph(f"Mã số thuế người bán: {evidence.seller_tax_code}")
    if evidence.buyer_name is not None:
        document.add_paragraph(f"Người mua: {evidence.buyer_name}")
    if evidence.buyer_tax_code is not None:
        document.add_paragraph(f"Mã số thuế người mua: {evidence.buyer_tax_code}")
    if evidence.template_number is not None:
        document.add_paragraph(f"Mẫu số: {evidence.template_number}")
    if evidence.serial_number is not None:
        document.add_paragraph(f"Ký hiệu: {evidence.serial_number}")
    if evidence.document_number:
        document.add_paragraph(f"Số chứng từ: {evidence.document_number}")
    if evidence.document_date:
        document.add_paragraph(f"Ngày chứng từ: {evidence.document_date}")
    add_docx_table(
        document,
        ["NỘI DUNG", "SỐ LƯỢNG", "ĐƠN GIÁ", "THÀNH TIỀN"],
        [[evidence.description, "1", money(evidence.amount), money(evidence.amount)]],
    )
    document.add_paragraph(f"Tổng thanh toán: {money(evidence.amount)} đồng")
    if evidence.note:
        document.add_paragraph(f"Ghi chú: {evidence.note}")
    document.save(output_path)


def create_invoice_docx(evidence: Evidence, output_path: Path) -> None:
    """Create a synthetic Vietnamese e-invoice with the fields needed by UC-03."""
    subtotal, vat, total = invoice_amounts(evidence)
    document = Document()
    configure_doc(document)

    top = document.add_table(rows=1, cols=3)
    top.alignment = WD_TABLE_ALIGNMENT.CENTER
    top.cell(0, 0).text = "BN\nTECH"
    top.cell(0, 1).text = f"{evidence.seller_name}\nHÓA ĐƠN GIÁ TRỊ GIA TĂNG\n(BẢN THỂ HIỆN CỦA HÓA ĐƠN ĐIỆN TỬ)"
    top.cell(0, 2).text = (
        f"Mẫu số: {evidence.template_number or ''}\n"
        f"Ký hiệu: {evidence.serial_number or ''}\n"
        f"Số: {evidence.document_number or ''}"
    )
    for index, cell in enumerate(top.rows[0].cells):
        for paragraph in cell.paragraphs:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if index != 2 else WD_ALIGN_PARAGRAPH.LEFT
            for run in paragraph.runs:
                run.font.size = Pt(10 if index == 1 else 9)
                run.bold = True
    document.add_paragraph(vietnamese_date(evidence.document_date)).alignment = WD_ALIGN_PARAGRAPH.CENTER

    seller_rows = [["Tên người bán", evidence.seller_name], ["Địa chỉ", evidence.seller_address]]
    if evidence.seller_tax_code is not None:
        seller_rows.append(["Mã số thuế", evidence.seller_tax_code])
    add_docx_table(document, ["THÔNG TIN BÊN BÁN", ""], seller_rows)

    buyer_rows: list[list[str]] = []
    if evidence.buyer_name is not None:
        buyer_rows.append(["Tên người mua / Tên đơn vị", evidence.buyer_name])
    if evidence.buyer_name is not None:
        buyer_rows.append(["Địa chỉ", evidence.buyer_address])
    if evidence.buyer_tax_code is not None:
        buyer_rows.append(["Mã số thuế", evidence.buyer_tax_code])
    if buyer_rows:
        add_docx_table(document, ["THÔNG TIN BÊN MUA", ""], buyer_rows)

    add_docx_table(
        document,
        ["NƠI GIAO HÀNG", "THAM CHIẾU / THANH TOÁN"],
        [[f"Xuất tại kho: {evidence.warehouse_address}", f"Số tham chiếu: {evidence.purchase_order}\nHình thức thanh toán: {evidence.payment_method}"]],
    )
    add_docx_table(
        document,
        ["STT", "TÊN HÀNG HÓA, DỊCH VỤ", "ĐVT", "THUẾ SUẤT", "SL", "ĐƠN GIÁ", "THÀNH TIỀN"],
        [["1", evidence.description, unit_for(evidence.description), f"{evidence.tax_rate}%", "1", money(subtotal), money(subtotal)]],
    )
    totals = document.add_table(rows=4, cols=2)
    totals.alignment = WD_TABLE_ALIGNMENT.CENTER
    for row, label, value in (
        (0, "Tiền hàng hóa, dịch vụ", money(subtotal)),
        (1, f"Thuế GTGT ({evidence.tax_rate}%)", money(vat)),
        (2, "Tổng cộng tiền thanh toán", money(total)),
        (3, "Số tiền bằng chữ", vietnamese_money_words(total)),
    ):
        totals.cell(row, 0).text = label
        totals.cell(row, 1).text = value
        totals.cell(row, 1).paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        for cell in totals.rows[row].cells:
            for run in cell.paragraphs[0].runs:
                run.font.size = Pt(9)
                if row == 2:
                    run.bold = True

    signature = document.add_table(rows=2, cols=2)
    signature.alignment = WD_TABLE_ALIGNMENT.CENTER
    signature.cell(0, 0).text = "Người mua hàng\n(Ký, ghi rõ họ tên)"
    signature.cell(0, 1).text = "Người bán hàng\n(Ký điện tử)"
    signature.cell(1, 0).text = ""
    signature.cell(1, 1).text = f"Đã ký điện tử ngày {evidence.document_date or '...'}"
    for row in signature.rows:
        for cell in row.cells:
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in cell.paragraphs[0].runs:
                run.font.size = Pt(9)
    document.add_paragraph(
        f"Mã tra cứu hóa đơn: BN-{evidence.document_number or 'CHUA_CO_SO'}"
    ).alignment = WD_ALIGN_PARAGRAPH.CENTER
    if evidence.note:
        document.add_paragraph(f"Ghi chú: {evidence.note}")
    document.save(output_path)


def setup_pdf_fonts() -> str:
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    if not font_path.exists():
        raise RuntimeError(f"Không tìm thấy font hỗ trợ tiếng Việt: {font_path}")
    font_name = "FixtureArial"
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
    return font_name


def pdf_styles(font_name: str) -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("FixtureTitle", parent=styles["Normal"], fontName=font_name, fontSize=14, leading=18, alignment=TA_CENTER, spaceAfter=12),
        "body": ParagraphStyle("FixtureBody", parent=styles["Normal"], fontName=font_name, fontSize=9, leading=13, alignment=TA_LEFT),
        "small": ParagraphStyle("FixtureSmall", parent=styles["Normal"], fontName=font_name, fontSize=8, leading=10, alignment=TA_LEFT),
        "bold": ParagraphStyle("FixtureBold", parent=styles["Normal"], fontName=font_name, fontSize=9, leading=13, alignment=TA_LEFT),
    }


def pdf_table(data: list[list[str]], widths: list[float], styles: dict[str, ParagraphStyle]) -> Table:
    rows = [[Paragraph(escape(value), styles["small"]) for value in row] for row in data]
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#808080")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), styles["small"].fontName),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def create_report_pdf(case_spec: Case, output_path: Path, font_name: str) -> None:
    styles = pdf_styles(font_name)
    document = SimpleDocTemplate(str(output_path), pagesize=A4, rightMargin=1.6 * cm, leftMargin=1.6 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    flow = [Paragraph("GIẤY ĐỀ NGHỊ HOÀN ỨNG", styles["title"])]
    for text in (
        "Kính gửi: Ban Giám đốc và Phòng Kế toán",
        f"Người đề nghị: {EMPLOYEE_NAME}",
        f"Chức vụ: {EMPLOYEE_POSITION} - Bộ phận: {EMPLOYEE_DEPARTMENT}",
        f"Nội dung: {report_business_purpose(case_spec)}",
    ):
        flow.append(Paragraph(escape(text), styles["body"]))
    flow.append(Spacer(1, 8))
    table_data = [["STT", "NỘI DUNG", "HÓA ĐƠN", "SỐ TIỀN", "GHI CHÚ"]] + report_lines(case_spec)
    flow.append(pdf_table(table_data, [0.7 * cm, 6.0 * cm, 2.6 * cm, 2.7 * cm, 4.0 * cm], styles))
    flow.append(Spacer(1, 8))
    flow.append(Paragraph(escape(f"Bằng chữ: {case_spec.total_in_words or 'Theo số tiền tổng cộng nêu trên.'}"), styles["body"]))
    if case_spec.settlement_type == "ADVANCE_SETTLEMENT":
        advance = money(case_spec.advance_amount) if case_spec.advance_amount else "........................................"
        flow.append(Paragraph(escape(f"Số tiền đã tạm ứng: {advance} đồng"), styles["body"]))
    if case_spec.settlement_amount is not None:
        flow.append(Paragraph(escape(f"{case_spec.settlement_direction or 'Số tiền quyết toán'}: {money(case_spec.settlement_amount)} đồng"), styles["body"]))
    flow.append(Paragraph("Thông tin chuyển khoản: 0123456789 - Ngân hàng Demo - Donal Trump", styles["body"]))
    flow.append(Spacer(1, 16))
    signature_rows = [
        ["NGƯỜI ĐỀ NGHỊ HOÀN ỨNG", "KẾ TOÁN", "GIÁM ĐỐC"],
        ["(Đã ký)", "(Đang chờ xác nhận)", "(Đang chờ xác nhận)"],
    ]
    signature_table = Table(
        [[Paragraph(escape(value), styles["small"]) for value in row] for row in signature_rows],
        colWidths=[5.7 * cm, 5.7 * cm, 5.7 * cm],
    )
    signature_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow.append(signature_table)
    document.build(flow)


def create_evidence_pdf(evidence: Evidence, output_path: Path, font_name: str) -> None:
    if evidence.document_type == "E_INVOICE":
        create_invoice_pdf(evidence, output_path, font_name)
        return

    styles = pdf_styles(font_name)
    document = SimpleDocTemplate(str(output_path), pagesize=A4, rightMargin=1.8 * cm, leftMargin=1.8 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    label = {
        "E_INVOICE": "HÓA ĐƠN GIÁ TRỊ GIA TĂNG",
        "TRANSPORT_TICKET": "VÉ ĐIỆN TỬ",
        "PAYMENT_PROOF": "XÁC NHẬN GIAO DỊCH THANH TOÁN",
        "PAPER_RECEIPT": "PHIẾU THANH TOÁN",
    }.get(evidence.document_type, "CHỨNG TỪ THANH TOÁN")
    flow = [Paragraph(label, styles["title"])]
    fields = [
        ("Đơn vị phát hành", evidence.seller_name),
        ("Mã số thuế người bán", evidence.seller_tax_code),
        ("Người mua", evidence.buyer_name),
        ("Mã số thuế người mua", evidence.buyer_tax_code),
        ("Mẫu số", evidence.template_number),
        ("Ký hiệu", evidence.serial_number),
        ("Số chứng từ", evidence.document_number),
        ("Ngày chứng từ", evidence.document_date),
    ]
    for label_text, value in fields:
        if value is not None and str(value):
            flow.append(Paragraph(escape(f"{label_text}: {value}"), styles["body"]))
    flow.append(Spacer(1, 8))
    flow.append(pdf_table(
        [["NỘI DUNG", "SỐ LƯỢNG", "ĐƠN GIÁ", "THÀNH TIỀN"], [evidence.description, "1", money(evidence.amount), money(evidence.amount)]],
        [7.8 * cm, 2.2 * cm, 3.0 * cm, 3.5 * cm],
        styles,
    ))
    flow.append(Spacer(1, 8))
    flow.append(Paragraph(escape(f"Tổng thanh toán: {money(evidence.amount)} đồng"), styles["body"]))
    if evidence.note:
        flow.append(Paragraph(escape(f"Ghi chú: {evidence.note}"), styles["body"]))
    document.build(flow)


def create_invoice_pdf(evidence: Evidence, output_path: Path, font_name: str) -> None:
    """Render the invoice fixture with a layout close to Vietnamese e-invoices."""
    subtotal, vat, total = invoice_amounts(evidence)
    styles = pdf_styles(font_name)
    small = ParagraphStyle("InvoiceSmall", parent=styles["small"], fontSize=7.2, leading=9)
    body = ParagraphStyle("InvoiceBody", parent=styles["body"], fontSize=8.2, leading=10.5)
    heading = ParagraphStyle("InvoiceHeading", parent=styles["title"], fontSize=13, leading=15, spaceAfter=3)
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=1.35 * cm,
        leftMargin=1.35 * cm,
        topMargin=1.15 * cm,
        bottomMargin=1.15 * cm,
    )
    def p(value: str, style: ParagraphStyle = body) -> Paragraph:
        # Invoice templates use only controlled text plus basic ReportLab markup.
        return Paragraph(value if "<" in value and ">" in value else escape(value), style)

    flow: list[object] = []
    header = Table(
        [[
            p("<b>BN</b><br/>TECH", ParagraphStyle("Mark", parent=heading, fontSize=18, leading=19)),
            p(f"<b>{evidence.seller_name}</b><br/><b>HÓA ĐƠN GIÁ TRỊ GIA TĂNG</b><br/><i>(BẢN THỂ HIỆN CỦA HÓA ĐƠN ĐIỆN TỬ)</i>", ParagraphStyle("HeaderCenter", parent=small, alignment=TA_CENTER, fontSize=9, leading=11)),
            p(f"Mẫu số: {evidence.template_number or ''}<br/>Ký hiệu: {evidence.serial_number or ''}<br/>Số: {evidence.document_number or ''}", ParagraphStyle("HeaderMeta", parent=small, fontSize=8.5, leading=11)),
        ]],
        colWidths=[2.5 * cm, 11.2 * cm, 4.4 * cm],
    )
    header.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#273A73")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    flow.append(header)
    flow.append(Spacer(1, 4))
    flow.append(Paragraph(escape(vietnamese_date(evidence.document_date)), ParagraphStyle("InvoiceDate", parent=small, alignment=TA_CENTER)))
    flow.append(Spacer(1, 3))

    seller_rows = [[p("<b>Tên người bán</b>", small), p(evidence.seller_name, small)], [p("Địa chỉ", small), p(evidence.seller_address, small)]]
    if evidence.seller_tax_code is not None:
        seller_rows.append([p("Mã số thuế", small), p(evidence.seller_tax_code, small)])
    seller_table = Table(seller_rows, colWidths=[3.1 * cm, 15.0 * cm])
    seller_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#707070")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    flow.append(seller_table)
    flow.append(Spacer(1, 3))

    buyer_rows: list[list[Paragraph]] = []
    if evidence.buyer_name is not None:
        buyer_rows.append([p("<b>Tên người mua / Tên đơn vị</b>", small), p(evidence.buyer_name, small)])
        buyer_rows.append([p("Địa chỉ", small), p(evidence.buyer_address, small)])
    if evidence.buyer_tax_code is not None:
        buyer_rows.append([p("Mã số thuế", small), p(evidence.buyer_tax_code, small)])
    if buyer_rows:
        buyer_table = Table(buyer_rows, colWidths=[3.8 * cm, 14.3 * cm])
        buyer_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#707070")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        flow.append(buyer_table)
        flow.append(Spacer(1, 3))

    logistics = Table(
        [[p(f"Xuất tại kho: {evidence.warehouse_address}", small), p(f"Số tham chiếu: {evidence.purchase_order}<br/>Hình thức thanh toán: {evidence.payment_method}", small)]],
        colWidths=[9.6 * cm, 8.5 * cm],
    )
    logistics.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#707070")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    flow.append(logistics)
    flow.append(Spacer(1, 3))

    item_data = [
        ["STT", "Tên hàng hóa, dịch vụ", "ĐVT", "Thuế suất", "SL", "Đơn giá", "Thành tiền"],
        ["1", evidence.description, unit_for(evidence.description), f"{evidence.tax_rate}%", "1", money(subtotal), money(subtotal)],
    ]
    item_rows = [[p(value, small) for value in row] for row in item_data]
    items = Table(item_rows, colWidths=[0.8 * cm, 6.2 * cm, 1.2 * cm, 1.6 * cm, 0.8 * cm, 3.6 * cm, 3.9 * cm])
    items.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#707070")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F6F9")),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("ALIGN", (5, 1), (6, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow.append(items)
    flow.append(Spacer(1, 3))

    total_rows = [
        [p("Tiền hàng hóa, dịch vụ", small), p(money(subtotal), small)],
        [p(f"Thuế GTGT ({evidence.tax_rate}%)", small), p(money(vat), small)],
        [p("<b>Tổng cộng tiền thanh toán</b>", small), p(f"<b>{money(total)}</b>", small)],
        [p("Số tiền bằng chữ", small), p(vietnamese_money_words(total), small)],
    ]
    totals = Table(total_rows, colWidths=[12.0 * cm, 6.1 * cm])
    totals.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#707070")),
        ("ALIGN", (1, 0), (1, 2), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    flow.append(totals)
    flow.append(Spacer(1, 8))

    signatures = Table(
        [[p("<b>Người mua hàng</b><br/><i>(Ký, ghi rõ họ tên)</i>", small), p(f"<b>Người bán hàng</b><br/>Đã ký điện tử ngày {evidence.document_date or '...'}", small)]],
        colWidths=[9.0 * cm, 9.1 * cm],
    )
    signatures.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    flow.append(signatures)
    flow.append(Paragraph(
        escape(f"Mã tra cứu hóa đơn: BN-{evidence.document_number or 'CHUA_CO_SO'}"),
        ParagraphStyle("InvoiceFooter", parent=small, alignment=TA_CENTER, fontSize=6.8, leading=8),
    ))
    if evidence.note:
        flow.append(Paragraph(escape(f"Ghi chú: {evidence.note}"), ParagraphStyle("InvoiceNote", parent=small, fontSize=6.8, leading=8)))
    document.build(flow)


def expected_payload(case_spec: Case) -> dict[str, object]:
    evidence_names = [f"{item.file_stem}.pdf" for item in case_spec.evidence]
    return {
        "schema_version": "2.0",
        "case_id": case_spec.case_id,
        "group_id": case_spec.group_id,
        "title": case_spec.title,
        "data_classification": "SYNTHETIC",
        "submission": {
            "settlement_type": case_spec.settlement_type,
            "source_type": "PAPER_SCAN",
            "employee": {"name": EMPLOYEE_NAME, "department": EMPLOYEE_DEPARTMENT, "position": EMPLOYEE_POSITION},
            "request_form": "request_form.pdf",
            "evidence_files": evidence_names,
        },
        "expected": {
            "automation_decision": case_spec.expected_decision,
            "primary_rule_id": case_spec.expected_rule,
            "implementation_status": case_spec.implementation_status,
            "expected_findings": list(case_spec.expected_findings),
            "workflow_status": "PENDING_APPROVAL" if case_spec.expected_decision == "READY_FOR_APPROVAL" else "NEEDS_REVIEW",
        },
        "facts": {
            "report_total_vnd": case_spec.report_total,
            "advance_amount_vnd": case_spec.advance_amount,
            "settlement_amount_vnd": case_spec.settlement_amount,
            "settlement_direction": case_spec.settlement_direction,
            "line_count": len(case_spec.lines),
        },
        "line_support_expectations": [
            {
                "item_id": line.item_id,
                "description": line.description,
                "amount_vnd": line.amount,
                "reference": line.reference or None,
                "note": line.note,
            }
            for line in case_spec.lines
        ],
        "generator_notes": list(case_spec.notes),
    }


def group_readme(group_cases: list[Case]) -> str:
    lines = [
        f"# {group_cases[0].group_name}",
        "",
        "Mỗi thư mục con là một hồ sơ hoàn ứng giả lập. Tải `request_form.pdf` làm đơn chính và tải toàn bộ file PDF còn lại làm evidence.",
        "",
        "| Case | Tình huống | Kết quả kỳ vọng | Rule chính |",
        "| --- | --- | --- | --- |",
    ]
    for item in group_cases:
        lines.append(
            f"| {item.case_id} | {item.title} | {item.expected_decision} | {item.expected_rule or '-'} |"
        )
    return "\n".join(lines) + "\n"


def root_readme(cases: tuple[Case, ...]) -> str:
    groups: dict[str, list[Case]] = {}
    for item in cases:
        groups.setdefault(item.group_id, []).append(item)
    lines = [
        "# Bộ testcase UC-03 v2",
        "",
        "Bộ dữ liệu giả lập cho luồng hoàn ứng/quyết toán tạm ứng. Không dùng cho nghiệp vụ thật.",
        "",
        "## Cách chạy một case",
        "",
        "1. Vào thư mục case.",
        "2. Tải `request_form.pdf` làm đơn giấy chính.",
        "3. Tải toàn bộ PDF còn lại làm chứng từ chi phí/evidence.",
        "4. Không tải `expected.json`; file này là oracle cho kiểm thử.",
        "",
        "## Nhóm nghiệp vụ",
        "",
        "| Nhóm | Số case | Mục tiêu |",
        "| --- | ---: | --- |",
    ]
    for group_id, group_cases in groups.items():
        lines.append(f"| `{group_id}` | {len(group_cases)} | {group_cases[0].group_name} |")
    lines.extend([
        "",
        "`COVERED` là rule đã có trong Rule Engine; `PLANNED` là regression specification cho rule chưa triển khai đủ. Tên file không được dùng làm định danh chứng từ; định danh dựa trên nội dung OCR và trường chứng từ.",
        "",
    ])
    return "\n".join(lines)


def generate(output_root: Path, *, replace: bool) -> None:
    cases = build_cases()
    if len(cases) != 50:
        raise RuntimeError(f"Catalog phải có đúng 50 case, đang có {len(cases)}.")
    group_counts: dict[str, int] = {}
    for item in cases:
        group_counts[item.group_id] = group_counts.get(item.group_id, 0) + 1
    if any(count != 10 for count in group_counts.values()) or len(group_counts) != 5:
        raise RuntimeError(f"Mỗi nhóm phải có 10 case: {group_counts}")

    if output_root.exists():
        if not replace:
            raise FileExistsError(f"Thư mục đã tồn tại: {output_root}. Dùng --replace để tạo lại.")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    font_name = setup_pdf_fonts()
    manifest: list[dict[str, object]] = []
    grouped: dict[str, list[Case]] = {}

    for case_spec in cases:
        grouped.setdefault(case_spec.group_id, []).append(case_spec)
        folder_name = f"{case_spec.case_id.lower()}_{case_spec.slug}"
        case_dir = output_root / case_spec.group_id / folder_name
        case_dir.mkdir(parents=True)
        create_report_docx(case_spec, case_dir / "request_form.docx")
        create_report_pdf(case_spec, case_dir / "request_form.pdf", font_name)
        for evidence in case_spec.evidence:
            create_evidence_docx(evidence, case_dir / f"{evidence.file_stem}.docx")
            create_evidence_pdf(evidence, case_dir / f"{evidence.file_stem}.pdf", font_name)
        (case_dir / "expected.json").write_text(
            json.dumps(expected_payload(case_spec), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest.append({
            "case_id": case_spec.case_id,
            "group_id": case_spec.group_id,
            "folder": str(Path(case_spec.group_id) / folder_name).replace("\\", "/"),
            "title": case_spec.title,
            "expected_decision": case_spec.expected_decision,
            "expected_primary_rule": case_spec.expected_rule,
            "implementation_status": case_spec.implementation_status,
        })

    for group_id, group_cases in grouped.items():
        (output_root / group_id / "README.md").write_text(group_readme(group_cases), encoding="utf-8")
    (output_root / "README.md").write_text(root_readme(cases), encoding="utf-8")
    (output_root / "manifest.json").write_text(
        json.dumps({"schema_version": "2.0", "case_count": len(cases), "groups": list(grouped), "cases": manifest}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Sinh bộ testcase UC-03 v2.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--replace", action="store_true", help="Xóa đúng thư mục output rồi tạo lại.")
    args = parser.parse_args()
    generate(args.output.resolve(), replace=args.replace)
    print(f"Generated testcase corpus: {args.output.resolve()}")


if __name__ == "__main__":
    main()
