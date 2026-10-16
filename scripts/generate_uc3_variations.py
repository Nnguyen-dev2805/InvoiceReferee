"""Portable generator for UC-03 demo variations (TC05 to TC10).

Creates deterministic variations of testcases TC05-TC10 with distinct work purposes
and distinct advance amounts while strictly preserving testing invariants and error semantics.
Supports both macOS, Linux, and Windows environments without hardcoded font paths.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

try:
    from docx import Document
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

COMPANY_NAME = "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH"
COMPANY_TAX_CODE = "0319999996"
COMPANY_ADDRESS = "128 Nguyễn Văn Linh, Phường Tân Hưng, Thành phố Hồ Chí Minh"
EMPLOYEE_NAME = "NGUYỄN MINH AN"
EMPLOYEE_DEPARTMENT = "Hành chính nhân sự"
ACCOUNTANT_NAME = "TRẦN THỊ THU HÀ"
DIRECTOR_NAME = "LÊ QUANG HUY"
SELLER_SIGNER_NAME = "PHẠM HOÀNG NAM"
SELLER_NAME = "CÔNG TY TNHH THƯƠNG MẠI VÀ DỊCH VỤ MINH PHÁT"
SELLER_TAX_CODE = "0101234565"
SELLER_ADDRESS = "86 Trần Thái Tông, Phường Cầu Giấy, Thành phố Hà Nội"


def _find_font(candidates: list[str]) -> Path:
    search_dirs = [
        Path("/System/Library/Fonts/Supplemental"),
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
        Path(r"C:\Windows\Fonts"),
        Path("/usr/share/fonts/truetype"),
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
    ]
    for d in search_dirs:
        if not d.exists():
            continue
        for cand in candidates:
            p = d / cand
            if p.is_file():
                return p
            # Case insensitive search
            for match in d.glob(f"**/{cand}"):
                if match.is_file():
                    return match
    raise FileNotFoundError(f"Could not locate font among candidates: {candidates}")


def register_fonts() -> None:
    reg_font = _find_font(["Times New Roman.ttf", "times.ttf", "Times.ttf", "LiberationSerif-Regular.ttf"])
    bold_font = _find_font(["Times New Roman Bold.ttf", "timesbd.ttf", "Times Bold.ttf", "LiberationSerif-Bold.ttf"])
    italic_font = _find_font(["Times New Roman Italic.ttf", "timesi.ttf", "Times Italic.ttf", "LiberationSerif-Italic.ttf"])

    pdfmetrics.registerFont(TTFont("TimesVN", str(reg_font)))
    pdfmetrics.registerFont(TTFont("TimesVN-Bold", str(bold_font)))
    pdfmetrics.registerFont(TTFont("TimesVN-Italic", str(italic_font)))


def money(value: Decimal | int | str) -> str:
    return f"{Decimal(str(value)):,.0f}".replace(",", ".")


def vietnamese_number(value: Decimal | int | str) -> str:
    number = int(Decimal(str(value)))
    if number == 0:
        return "Không đồng"
    digits = [
        "không", "một", "hai", "ba", "bốn",
        "năm", "sáu", "bảy", "tám", "chín",
    ]

    def triad(n: int, full: bool) -> str:
        hundred = n // 100
        ten = (n % 100) // 10
        unit = n % 10
        parts: list[str] = []
        if hundred or full:
            parts.extend([digits[hundred], "trăm"])
        if ten > 1:
            parts.extend([digits[ten], "mươi"])
            if unit == 1:
                parts.append("mốt")
            elif unit == 4:
                parts.append("tư")
            elif unit == 5:
                parts.append("lăm")
            elif unit:
                parts.append(digits[unit])
        elif ten == 1:
            parts.append("mười")
            if unit == 5:
                parts.append("lăm")
            elif unit:
                parts.append(digits[unit])
        elif unit:
            if hundred or full:
                parts.append("lẻ")
            parts.append(digits[unit])
        return " ".join(parts)

    groups: list[int] = []
    remaining = number
    while remaining:
        groups.append(remaining % 1000)
        remaining //= 1000
    scales = ["", "nghìn", "triệu", "tỷ"]
    words: list[str] = []
    for index in range(len(groups) - 1, -1, -1):
        group = groups[index]
        if group == 0:
            continue
        full = bool(words) and group < 100
        words.append(triad(group, full))
        scale_index = index % 4
        billion_cycle = index // 4
        if scale_index:
            words.append(scales[scale_index])
        if billion_cycle:
            words.extend(["tỷ"] * billion_cycle)
    result = " ".join(words).strip()
    return result[:1].upper() + result[1:] + " đồng"


@dataclass
class Line:
    description: str
    unit: str
    quantity: Decimal
    unit_price: Decimal

    @property
    def amount(self) -> Decimal:
        return self.quantity * self.unit_price


@dataclass
class TestCase:
    case_id: str
    folder: str
    title: str
    purpose: str
    invoice_number: str
    lines: list[Line]
    tax_rate: Decimal = Decimal("8")
    invoice_date: date = date(2026, 10, 10)
    template_number: str = "1C26TAA"
    serial_number: str = "IR26E"
    seller_name: str = SELLER_NAME
    seller_tax_code: str | None = SELLER_TAX_CODE
    seller_address: str = SELLER_ADDRESS
    seller_signer: str = SELLER_SIGNER_NAME
    buyer_name: str = COMPANY_NAME
    buyer_tax_code: str | None = COMPANY_TAX_CODE
    invoice_subtotal: Decimal | None = None
    invoice_tax: Decimal | None = None
    invoice_total: Decimal | None = None
    invoice_words_value: Decimal | None = None
    report_lines: list[dict[str, Any]] | None = None
    report_total: Decimal | None = None
    report_words_value: Decimal | None = None
    advance_amount: Decimal = Decimal("0")
    declared_difference: Decimal | None = None
    expected_decision: str = "REQUEST_INFO"
    expected_uncertainty: str = "FACTUAL_UNKNOWN"
    expected_primary_rule: str | None = None
    expected_findings: list[str] = field(default_factory=list)
    implementation_status: str = "COVERED"
    rationale: str = ""

    def subtotal(self) -> Decimal:
        return self.invoice_subtotal or sum((line.amount for line in self.lines), Decimal("0"))

    def tax(self) -> Decimal:
        if self.invoice_tax is not None:
            return self.invoice_tax
        return (self.subtotal() * self.tax_rate / Decimal("100")).quantize(Decimal("1"))

    def total(self) -> Decimal:
        return self.invoice_total or (self.subtotal() + self.tax())

    def settlement_lines(self) -> list[dict[str, Any]]:
        if self.report_lines is not None:
            return self.report_lines
        return [
            {
                "description": self.purpose,
                "invoice_ref": self.invoice_number,
                "amount": self.total(),
                "note": "Đính kèm hóa đơn điện tử",
            }
        ]

    def settlement_total(self) -> Decimal:
        if self.report_total is not None:
            return self.report_total
        return sum((Decimal(str(line["amount"])) for line in self.settlement_lines()), Decimal("0"))

    def difference(self) -> Decimal:
        if self.declared_difference is not None:
            return self.declared_difference
        return abs(self.advance_amount - self.settlement_total())


def _pdf_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "body": ParagraphStyle("BodyVN", parent=base["BodyText"], fontName="TimesVN", fontSize=9.5, leading=12, spaceAfter=3),
        "small": ParagraphStyle("SmallVN", parent=base["BodyText"], fontName="TimesVN", fontSize=8, leading=9.5),
        "center": ParagraphStyle("CenterVN", parent=base["BodyText"], fontName="TimesVN", fontSize=9.5, leading=12, alignment=TA_CENTER),
        "title": ParagraphStyle("TitleVN", parent=base["Title"], fontName="TimesVN-Bold", fontSize=16, leading=19, alignment=TA_CENTER, textColor=colors.black, spaceAfter=4),
        "right": ParagraphStyle("RightVN", parent=base["BodyText"], fontName="TimesVN", fontSize=9, alignment=TA_RIGHT),
    }


def _pdf_table(data: list[list[Any]], widths: list[float], *, header: bool = True) -> Table:
    table = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="CENTER")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.55, colors.HexColor("#9A9A9A")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        commands.extend([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF2")),
            ("FONTNAME", (0, 0), (-1, 0), "TimesVN-Bold"),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ])
    table.setStyle(TableStyle(commands))
    return table


def create_report_pdf(case: TestCase, output: Path) -> None:
    styles = _pdf_styles()
    doc = SimpleDocTemplate(str(output), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=14 * mm)
    story: list[Any] = []
    header = Table([[
        Paragraph(f"<b>{COMPANY_NAME}</b>", styles["center"]),
        Paragraph("<b>CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM</b><br/>Độc lập - Tự do - Hạnh phúc", styles["center"]),
    ]], colWidths=[88 * mm, 88 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.extend([
        header,
        Paragraph(f"Thành phố Hồ Chí Minh, ngày {case.invoice_date.day:02d} tháng {case.invoice_date.month:02d} năm {case.invoice_date.year}", styles["right"]),
        Spacer(1, 2 * mm),
        Paragraph("GIẤY ĐỀ NGHỊ HOÀN ỨNG", styles["title"]),
        Paragraph(f"<i>Về việc: {case.purpose}</i>", styles["center"]),
        Spacer(1, 2 * mm),
        Paragraph(f"<b>Kính gửi:</b> Ban Giám đốc {COMPANY_NAME}", styles["body"]),
        Paragraph(f"<b>Người đề nghị:</b> {EMPLOYEE_NAME}", styles["body"]),
        Paragraph("<b>Chức vụ:</b> Nhân viên", styles["body"]),
        Paragraph(f"<b>Bộ phận:</b> {EMPLOYEE_DEPARTMENT}", styles["body"]),
        Paragraph(f"<b>Nội dung:</b> {case.purpose}", styles["body"]),
        Spacer(1, 2 * mm),
    ])
    rows: list[list[Any]] = [
        [
            Paragraph("STT", styles["small"]),
            Paragraph("NỘI DUNG", styles["small"]),
            Paragraph("HÓA ĐƠN", styles["small"]),
            Paragraph("SỐ TIỀN", styles["small"]),
            Paragraph("GHI CHÚ", styles["small"]),
        ]
    ]
    for index, line in enumerate(case.settlement_lines(), start=1):
        rows.append([
            Paragraph(str(index), styles["small"]),
            Paragraph(str(line["description"]), styles["small"]),
            Paragraph(str(line["invoice_ref"]), styles["small"]),
            Paragraph(money(line["amount"]), styles["small"]),
            Paragraph(str(line.get("note") or ""), styles["small"]),
        ])
    rows.append([
        "",
        Paragraph("<b>Tổng cộng</b>", styles["small"]),
        "",
        Paragraph(f"<b>{money(case.settlement_total())}</b>", styles["small"]),
        "",
    ])
    report_table = _pdf_table(rows, [10 * mm, 61 * mm, 26 * mm, 31 * mm, 48 * mm])
    report_table.setStyle(TableStyle([
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("ALIGN", (2, 1), (2, -1), "CENTER"),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
        ("SPAN", (0, -1), (0, -1)),
    ]))
    story.extend([report_table, Spacer(1, 2 * mm)])
    words_value = case.report_words_value or case.settlement_total()
    story.append(Paragraph(f"<b>Bằng chữ:</b> {vietnamese_number(words_value)}.", styles["body"]))
    story.append(Paragraph(f"<b>Số tiền đã tạm ứng:</b> {money(case.advance_amount)} đồng", styles["body"]))
    if case.advance_amount > case.settlement_total():
        label = "Số tiền nhân viên hoàn trả công ty"
    elif case.advance_amount < case.settlement_total():
        label = "Số tiền công ty thanh toán thêm"
    else:
        label = "Chênh lệch quyết toán"
    story.extend([
        Paragraph(f"<b>{label}:</b> {money(case.difference())} đồng", styles["body"]),
        Paragraph(f"<b>Bằng chữ:</b> {vietnamese_number(case.difference())}.", styles["body"]),
        Spacer(1, 6 * mm),
    ])
    signature_data = [[
        Paragraph(f"<b>NGƯỜI ĐỀ NGHỊ HOÀN ỨNG</b><br/>(Đã ký)<br/>{EMPLOYEE_NAME}", styles["center"]),
        Paragraph(f"<b>KẾ TOÁN</b><br/>(Đã ký)<br/>{ACCOUNTANT_NAME}", styles["center"]),
        Paragraph(f"<b>GIÁM ĐỐC</b><br/>(Đã ký, đóng dấu)<br/>{DIRECTOR_NAME}", styles["center"]),
    ]]
    signature_table = Table(signature_data, colWidths=[58 * mm] * 3)
    signature_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 28)]))
    story.append(signature_table)
    doc.build(story)


def create_invoice_pdf(case: TestCase, output: Path) -> None:
    styles = _pdf_styles()
    doc = SimpleDocTemplate(str(output), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=14 * mm)
    story: list[Any] = [
        Paragraph("HÓA ĐƠN GIÁ TRỊ GIA TĂNG ĐIỆN TỬ", styles["title"]),
        Paragraph(f"Ngày {case.invoice_date.day:02d} tháng {case.invoice_date.month:02d} năm {case.invoice_date.year}", styles["center"]),
        Spacer(1, 2 * mm),
    ]
    meta = Table([[
        Paragraph(f"<b>Mẫu số:</b> {case.template_number}", styles["small"]),
        Paragraph(f"<b>Ký hiệu:</b> {case.serial_number}", styles["small"]),
        Paragraph(f"<b>Số:</b> {case.invoice_number}", styles["small"]),
    ]], colWidths=[58 * mm] * 3)
    story.extend([
        meta,
        Spacer(1, 2 * mm),
        Paragraph(f"<b>Đơn vị bán hàng:</b> {case.seller_name}", styles["body"]),
        Paragraph(f"<b>Mã số thuế:</b> {case.seller_tax_code or ''}", styles["body"]),
        Paragraph(f"<b>Địa chỉ:</b> {case.seller_address}", styles["body"]),
        Spacer(1, 1 * mm),
        Paragraph(f"<b>Đơn vị mua hàng:</b> {case.buyer_name}", styles["body"]),
        Paragraph(f"<b>Mã số thuế:</b> {case.buyer_tax_code or ''}", styles["body"]),
        Paragraph(f"<b>Địa chỉ:</b> {COMPANY_ADDRESS}", styles["body"]),
        Paragraph("<b>Hình thức thanh toán:</b> Chuyển khoản", styles["body"]),
        Spacer(1, 2 * mm),
    ])
    rows: list[list[Any]] = [
        [
            Paragraph("STT", styles["small"]),
            Paragraph("TÊN HÀNG HÓA, DỊCH VỤ", styles["small"]),
            Paragraph("ĐVT", styles["small"]),
            Paragraph("SL", styles["small"]),
            Paragraph("ĐƠN GIÁ", styles["small"]),
            Paragraph("THÀNH TIỀN", styles["small"]),
        ]
    ]
    for index, line in enumerate(case.lines, start=1):
        rows.append([
            Paragraph(str(index), styles["small"]),
            Paragraph(line.description, styles["small"]),
            Paragraph(line.unit, styles["small"]),
            Paragraph(money(line.quantity), styles["small"]),
            Paragraph(money(line.unit_price), styles["small"]),
            Paragraph(money(line.amount), styles["small"]),
        ])
    invoice_table = _pdf_table(rows, [10 * mm, 63 * mm, 15 * mm, 13 * mm, 34 * mm, 41 * mm])
    invoice_table.setStyle(TableStyle([
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("ALIGN", (2, 1), (3, -1), "CENTER"),
        ("ALIGN", (4, 1), (5, -1), "RIGHT"),
    ]))
    story.extend([invoice_table, Spacer(1, 3 * mm)])
    summary_rows = [
        ["Cộng tiền hàng chưa thuế:", money(case.subtotal())],
        [f"Thuế GTGT ({money(case.tax_rate)}%):", money(case.tax())],
        ["TỔNG CỘNG THANH TOÁN:", money(case.total()) + " VND"],
    ]
    summary = Table(summary_rows, colWidths=[120 * mm, 55 * mm])
    summary.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -2), "TimesVN"),
        ("FONTNAME", (0, -1), (-1, -1), "TimesVN-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    invoice_words = case.invoice_words_value or case.total()
    story.extend([
        summary,
        Paragraph(f"<b>Số tiền bằng chữ:</b> {vietnamese_number(invoice_words)}.", styles["body"]),
        Spacer(1, 5 * mm),
    ])
    signatures = Table([[
        Paragraph("<b>NGƯỜI MUA HÀNG</b><br/>(Ký, ghi rõ họ tên)", styles["center"]),
        Paragraph(
            f"<b>NGƯỜI BÁN HÀNG</b><br/>{case.seller_name}<br/>Ký bởi: {case.seller_name}<br/>"
            f"Người ký: {case.seller_signer}<br/>Ký ngày: {case.invoice_date:%d/%m/%Y}",
            styles["center"],
        ),
    ]], colWidths=[87 * mm] * 2)
    signatures.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 24)]))
    story.append(signatures)
    doc.build(story)


def create_report_docx(case: TestCase, output: Path) -> None:
    if not HAS_DOCX:
        return
    document = Document()
    section = document.sections[0]
    section.top_margin = Cm(1.35)
    section.bottom_margin = Cm(1.25)
    section.left_margin = Cm(1.45)
    section.right_margin = Cm(1.45)

    def _cell_text(cell, text, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT, size=9):
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = align
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(text)
        run.bold = bold
        run.font.name = "Times New Roman"
        run.font.size = Pt(size)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

    header = document.add_table(rows=1, cols=2)
    header.alignment = WD_TABLE_ALIGNMENT.CENTER
    _cell_text(header.cell(0, 0), COMPANY_NAME, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=10)
    _cell_text(header.cell(0, 1), "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nĐộc lập - Tự do - Hạnh phúc", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=10)

    p_date = document.add_paragraph(f"Thành phố Hồ Chí Minh, ngày {case.invoice_date.day:02d} tháng {case.invoice_date.month:02d} năm {case.invoice_date.year}")
    p_date.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    p_title = document.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_t = p_title.add_run("GIẤY ĐỀ NGHỊ HOÀN ỨNG")
    run_t.bold = True
    run_t.font.size = Pt(16)
    p_sub = document.add_paragraph(f"Về việc: {case.purpose}")
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sub.runs[0].italic = True

    for label, val in [
        ("Kính gửi: ", f"Ban Giám đốc {COMPANY_NAME}"),
        ("Người đề nghị: ", EMPLOYEE_NAME),
        ("Chức vụ: ", "Nhân viên"),
        ("Bộ phận: ", EMPLOYEE_DEPARTMENT),
        ("Nội dung: ", case.purpose),
    ]:
        p = document.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        p.add_run(label).bold = True
        p.add_run(val)

    report_lines = case.settlement_lines()
    table = document.add_table(rows=1, cols=5)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    headers = ["STT", "NỘI DUNG", "HÓA ĐƠN", "SỐ TIỀN (VND)", "GHI CHÚ"]
    widths = [Cm(1.0), Cm(6.3), Cm(2.6), Cm(3.3), Cm(3.6)]
    for i, h in enumerate(headers):
        c = table.rows[0].cells[i]
        c.width = widths[i]
        _cell_text(c, h, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=9)
    for i, line in enumerate(report_lines, start=1):
        cells = table.add_row().cells
        vals = [str(i), str(line["description"]), str(line["invoice_ref"]), money(line["amount"]), str(line.get("note") or "")]
        for col_idx, v in enumerate(vals):
            align = WD_ALIGN_PARAGRAPH.RIGHT if col_idx == 3 else WD_ALIGN_PARAGRAPH.CENTER if col_idx in {0, 2} else WD_ALIGN_PARAGRAPH.LEFT
            _cell_text(cells[col_idx], v, align=align, size=9)
    total_cells = table.add_row().cells
    merged = total_cells[0].merge(total_cells[2])
    _cell_text(merged, "Tổng cộng", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=9)
    _cell_text(total_cells[3], money(case.settlement_total()), bold=True, align=WD_ALIGN_PARAGRAPH.RIGHT, size=9)
    _cell_text(total_cells[4], "", size=9)

    words_val = case.report_words_value or case.settlement_total()
    for label, val in [
        ("Bằng chữ: ", vietnamese_number(words_val) + "."),
        ("Số tiền đã tạm ứng: ", money(case.advance_amount) + " đồng"),
        (
            "Số tiền nhân viên hoàn trả công ty: " if case.advance_amount > case.settlement_total() else "Số tiền công ty thanh toán thêm: ",
            money(case.difference()) + " đồng",
        ),
        ("Bằng chữ: ", vietnamese_number(case.difference()) + "."),
    ]:
        p = document.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        p.add_run(label).bold = True
        p.add_run(val)

    signatures = document.add_table(rows=1, cols=3)
    signatures.alignment = WD_TABLE_ALIGNMENT.CENTER
    labels = [
        f"NGƯỜI ĐỀ NGHỊ HOÀN ỨNG\n(Đã ký)\n{EMPLOYEE_NAME}",
        f"KẾ TOÁN\n(Đã ký)\n{ACCOUNTANT_NAME}",
        f"GIÁM ĐỐC\n(Đã ký, đóng dấu)\n{DIRECTOR_NAME}",
    ]
    for i, lbl in enumerate(labels):
        _cell_text(signatures.cell(0, i), lbl, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=9)
        signatures.cell(0, i).paragraphs[0].paragraph_format.space_after = Pt(34)
    document.save(output)


def create_invoice_docx(case: TestCase, output: Path) -> None:
    if not HAS_DOCX:
        return
    document = Document()
    section = document.sections[0]
    section.top_margin = Cm(1.35)
    section.bottom_margin = Cm(1.25)
    section.left_margin = Cm(1.45)
    section.right_margin = Cm(1.45)

    def _cell_text(cell, text, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT, size=8.5):
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = align
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(text)
        run.bold = bold
        run.font.name = "Times New Roman"
        run.font.size = Pt(size)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

    p_title = document.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_t = p_title.add_run("HÓA ĐƠN GIÁ TRỊ GIA TĂNG ĐIỆN TỬ")
    run_t.bold = True
    run_t.font.size = Pt(16)
    p_date = document.add_paragraph(f"Ngày {case.invoice_date.day:02d} tháng {case.invoice_date.month:02d} năm {case.invoice_date.year}")
    p_date.alignment = WD_ALIGN_PARAGRAPH.CENTER

    meta = document.add_table(rows=1, cols=3)
    meta.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_values = [f"Mẫu số: {case.template_number}", f"Ký hiệu: {case.serial_number}", f"Số: {case.invoice_number}"]
    for i, v in enumerate(meta_values):
        _cell_text(meta.cell(0, i), v, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=9)

    for label, val in [
        ("Đơn vị bán hàng: ", case.seller_name),
        ("Mã số thuế: ", case.seller_tax_code or ""),
        ("Địa chỉ: ", case.seller_address),
        ("Đơn vị mua hàng: ", case.buyer_name),
        ("Mã số thuế: ", case.buyer_tax_code or ""),
        ("Địa chỉ: ", COMPANY_ADDRESS),
        ("Hình thức thanh toán: ", "Chuyển khoản"),
    ]:
        p = document.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        p.add_run(label).bold = True
        p.add_run(val)

    table = document.add_table(rows=1, cols=6)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    headers = ["STT", "TÊN HÀNG HÓA, DỊCH VỤ", "ĐVT", "SL", "ĐƠN GIÁ", "THÀNH TIỀN"]
    for i, h in enumerate(headers):
        c = table.rows[0].cells[i]
        _cell_text(c, h, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=8.5)
    for i, line in enumerate(case.lines, start=1):
        cells = table.add_row().cells
        vals = [str(i), line.description, line.unit, money(line.quantity), money(line.unit_price), money(line.amount)]
        for col_idx, v in enumerate(vals):
            align = WD_ALIGN_PARAGRAPH.RIGHT if col_idx in {3, 4, 5} else WD_ALIGN_PARAGRAPH.CENTER if col_idx in {0, 2} else WD_ALIGN_PARAGRAPH.LEFT
            _cell_text(cells[col_idx], v, align=align, size=8.5)

    totals = [
        ("Cộng tiền hàng chưa thuế:", case.subtotal()),
        (f"Thuế GTGT ({money(case.tax_rate)}%):", case.tax()),
        ("TỔNG CỘNG THANH TOÁN:", case.total()),
    ]
    for lbl, val in totals:
        p = document.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        p.add_run(lbl).bold = (lbl.startswith("TỔNG"))
        p.add_run(f" {money(val)} VND").bold = (lbl.startswith("TỔNG"))

    invoice_words = case.invoice_words_value or case.total()
    p = document.add_paragraph()
    p.add_run("Số tiền bằng chữ: ").bold = True
    p.add_run(vietnamese_number(invoice_words) + ".")

    signatures = document.add_table(rows=1, cols=2)
    signatures.alignment = WD_TABLE_ALIGNMENT.CENTER
    _cell_text(signatures.cell(0, 0), "NGƯỜI MUA HÀNG\n(Ký, ghi rõ họ tên)", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=9)
    _cell_text(signatures.cell(0, 1), f"NGƯỜI BÁN HÀNG\nKý bởi: {case.seller_name}\nNgười ký: {case.seller_signer}\nKý ngày: {case.invoice_date:%d/%m/%Y}", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=9)
    document.save(output)


def expected_payload(case: TestCase) -> dict[str, Any]:
    report_sum = sum((Decimal(str(line["amount"])) for line in case.settlement_lines()), Decimal("0"))
    return {
        "schema_version": "1.0",
        "case_id": case.case_id,
        "title": case.title,
        "synthetic_test_data": True,
        "submission": {
            "settlement_type": "ADVANCE_SETTLEMENT",
            "source_type": "PAPER_SCAN",
            "request_document": "report_hoan_ung.pdf",
            "evidence_documents": ["hoa_don_dien_tu.pdf"],
        },
        "expected": {
            "automation_decision": case.expected_decision,
            "uncertainty_type": case.expected_uncertainty,
            "primary_rule": case.expected_primary_rule,
            "findings": case.expected_findings,
            "followup": "PENDING_APPROVAL" if case.expected_decision == "AUTO_PROCESS" else None,
        },
        "implementation_status": case.implementation_status,
        "accounting_facts": {
            "report_line_sum": str(report_sum),
            "report_total": str(case.settlement_total()),
            "advance_amount": str(case.advance_amount),
            "declared_difference": str(case.difference()),
            "invoice_subtotal": str(case.subtotal()),
            "invoice_tax": str(case.tax()),
            "invoice_total": str(case.total()),
            "buyer_tax_code": case.buyer_tax_code,
            "expected_company_tax_code": COMPANY_TAX_CODE,
        },
        "rationale": case.rationale,
    }


def build_varied_cases() -> list[TestCase]:
    cases: list[TestCase] = []

    # TC05: Tổng các dòng trên báo cáo không khớp (lệch đúng 500.000 đ)
    # Subtotal 3.200.000 + 8% (256.000) = 3.456.000 HĐ.
    # Hai dòng chi: 2.200.000 + 1.000.000 = 3.200.000.
    # Tổng in trên giấy: 3.700.000 (lệch đúng 500.000 đ so với tổng dòng).
    # Ứng: 4.500.000; Hoàn khai: 800.000.
    tc05 = TestCase(
        case_id="TC05",
        folder="tc05-tong-cac-dong-tren-bao-cao-khong-khop",
        title="Tổng các dòng trên báo cáo không khớp",
        purpose="Chi phí tiếp khách làm việc với đối tác logistics Tân Cảng",
        invoice_number="00000501",
        lines=[Line("Dịch vụ ăn uống tiếp khách đối tác", "Suất", Decimal("8"), Decimal("400000"))],
        tax_rate=Decimal("8"),
        advance_amount=Decimal("4500000"),
        report_lines=[
            {"description": "Chi phí tiệc tiếp khách đối tác", "invoice_ref": "00000501", "amount": Decimal("2200000"), "note": "Đính kèm hóa đơn"},
            {"description": "Chi phí phòng tiếp khách riêng", "invoice_ref": "00000501", "amount": Decimal("1000000"), "note": "Đính kèm hóa đơn"},
        ],
        report_total=Decimal("3700000"),
        expected_decision="REQUEST_INFO",
        expected_uncertainty="FACTUAL_UNKNOWN",
        expected_primary_rule="SET_PAPER_TOTAL_001",
        expected_findings=["SET_PAPER_TOTAL_001"],
        implementation_status="COVERED",
        rationale="Hai dòng cộng 3.200.000 VND nhưng tổng báo cáo ghi 3.700.000 VND.",
    )
    cases.append(tc05)

    # TC06: Chênh lệch quyết toán ghi sai (A - chi khác hoàn kê khai đúng 60.000 đ)
    # HĐ: 5 suất * 550.000 = 2.750.000 + 8% (220.000) = 2.970.000.
    # Giấy: tổng chi 2.970.000 (khớp HĐ).
    # Ứng A: 3.800.000.
    # Đúng: 3.800.000 - 2.970.000 = 830.000 đ.
    # Khai sai: 770.000 đ (lệch đúng 60.000 đ).
    tc06 = TestCase(
        case_id="TC06",
        folder="tc06-chenh-lech-quyet-toan-ghi-sai",
        title="Chênh lệch quyết toán ghi sai",
        purpose="Chi phí tiếp khách đoàn kiểm toán hệ thống an toàn thông tin",
        invoice_number="00000601",
        lines=[Line("Dịch vụ tiệc tiếp khách đoàn kiểm toán", "Suất", Decimal("5"), Decimal("550000"))],
        tax_rate=Decimal("8"),
        advance_amount=Decimal("3800000"),
        declared_difference=Decimal("770000"),
        expected_decision="REQUEST_INFO",
        expected_uncertainty="FACTUAL_UNKNOWN",
        expected_primary_rule="SET_SETTLEMENT_DIFF_001",
        expected_findings=["SET_SETTLEMENT_DIFF_001"],
        implementation_status="COVERED",
        rationale="Chênh lệch đúng là 830.000 VND nhưng báo cáo ghi 770.000 VND.",
    )
    cases.append(tc06)

    # TC07: Số tiền bằng chữ trên báo cáo không khớp (lệch đúng 260.000 đ)
    # HĐ: 10 suất * 350.000 = 3.500.000 + 8% (280.000) = 3.780.000.
    # Giấy bằng số: 3.780.000.
    # Giấy bằng chữ cố ý: 4.040.000 ("Bốn triệu không trăm bốn mươi nghìn đồng").
    # Lệch chữ vs số: 4.040.000 - 3.780.000 = 260.000 đ.
    # Ứng: 4.800.000; Hoàn khai: 1.020.000.
    tc07 = TestCase(
        case_id="TC07",
        folder="tc07-so-tien-bang-chu-tren-bao-cao-khong-khop",
        title="Số tiền bằng chữ trên báo cáo không khớp",
        purpose="Chi phí tiếp khách hội thảo chuyên đề chuyển đổi số ngành bán lẻ",
        invoice_number="00000701",
        lines=[Line("Dịch vụ ăn uống tiếp khách hội thảo", "Suất", Decimal("10"), Decimal("350000"))],
        tax_rate=Decimal("8"),
        advance_amount=Decimal("4800000"),
        report_words_value=Decimal("4040000"),
        expected_decision="REQUEST_INFO",
        expected_uncertainty="FACTUAL_UNKNOWN",
        expected_primary_rule="SET_PAPER_CONSISTENCY_001",
        expected_findings=["SET_PAPER_CONSISTENCY_001"],
        implementation_status="COVERED",
        rationale="Tổng bằng số là 3.780.000 VND nhưng bằng chữ thể hiện 4.040.000 VND.",
    )
    cases.append(tc07)

    # TC08: Báo cáo và hóa đơn lệch số tiền (giấy cao hơn hóa đơn đúng 260.000 đ)
    # HĐ: 8 suất * 350.000 = 2.800.000 + 8% (224.000) = 3.024.000.
    # Giấy khai: 3.284.000 (cao hơn đúng 260.000 đ: 3.024.000 + 260.000 = 3.284.000).
    # Ứng: 4.200.000; Hoàn khai: 916.000 (4.200.000 - 3.284.000 = 916.000, khớp nội bộ giấy).
    tc08 = TestCase(
        case_id="TC08",
        folder="tc08-bao-cao-va-hoa-don-lech-so-tien",
        title="Báo cáo và hóa đơn lệch số tiền",
        purpose="Chi phí tiếp khách đại diện đối tác phần mềm tài chính MISA",
        invoice_number="00000801",
        lines=[Line("Dịch vụ ăn uống tiếp khách đối tác", "Suất", Decimal("8"), Decimal("350000"))],
        tax_rate=Decimal("8"),
        advance_amount=Decimal("4200000"),
        report_lines=[
            {"description": "Chi phí tiếp khách đại diện đối tác phần mềm tài chính MISA", "invoice_ref": "00000801", "amount": Decimal("3284000"), "note": "Đính kèm hóa đơn điện tử"},
        ],
        report_total=Decimal("3284000"),
        expected_decision="REQUEST_INFO",
        expected_uncertainty="FACTUAL_UNKNOWN",
        expected_primary_rule="SET_PAPER_AMOUNT_001",
        expected_findings=["SET_PAPER_AMOUNT_001"],
        implementation_status="COVERED",
        rationale="Báo cáo ghi 3.284.000 VND, hóa đơn ghi 3.024.000 VND.",
    )
    cases.append(tc08)

    # TC09: Mã số thuế người mua thuộc công ty khác (7777777777)
    # HĐ: 6 suất * 450.000 = 2.700.000 + 8% (216.000) = 2.916.000.
    # MST bên mua: 7777777777.
    # Giấy: 2.916.000. Ứng: 3.600.000; Hoàn: 684.000.
    tc09 = TestCase(
        case_id="TC09",
        folder="tc09-ma-so-thue-nguoi-mua-thuoc-cong-ty-khac",
        title="Mã số thuế người mua thuộc công ty khác",
        purpose="Chi phí tiếp khách chuyên gia tư vấn kiến trúc giải pháp Cloud",
        invoice_number="00000901",
        lines=[Line("Dịch vụ tiệc tiếp khách chuyên gia", "Suất", Decimal("6"), Decimal("450000"))],
        tax_rate=Decimal("8"),
        advance_amount=Decimal("3600000"),
        buyer_tax_code="7777777777",
        expected_decision="ESCALATE",
        expected_uncertainty="OUTSIDE_POLICY",
        expected_primary_rule="SET_BUYER_TAX_001",
        expected_findings=["SET_BUYER_TAX_001"],
        implementation_status="GAP_EXPECTED",
        rationale=f"MST người mua là 7777777777, khác MST đã cấu hình của công ty {COMPANY_TAX_CODE}.",
    )
    cases.append(tc09)

    # TC10: Hóa đơn thiếu mã số thuế người mua (buyer_tax_code = None)
    # HĐ: 8 suất * 420.000 = 3.360.000 + 8% (268.800) = 3.628.800.
    # MST bên mua: None (trống).
    # Giấy: 3.628.800. Ứng: 4.600.000; Hoàn: 971.200.
    tc10 = TestCase(
        case_id="TC10",
        folder="tc10-hoa-don-thieu-ma-so-thue-nguoi-mua",
        title="Hóa đơn thiếu mã số thuế người mua",
        purpose="Chi phí tiếp khách đại diện nhà cung cấp dịch vụ hạ tầng mạng",
        invoice_number="00001001",
        lines=[Line("Dịch vụ ăn uống tiếp khách đối tác hạ tầng", "Suất", Decimal("8"), Decimal("420000"))],
        tax_rate=Decimal("8"),
        advance_amount=Decimal("4600000"),
        buyer_tax_code=None,
        expected_decision="REQUEST_INFO",
        expected_uncertainty="FACTUAL_UNKNOWN",
        expected_primary_rule="SET_REQUIRED_FIELD_001",
        expected_findings=["SET_REQUIRED_FIELD_001"],
        implementation_status="GAP_EXPECTED",
        rationale="Hóa đơn điện tử không có MST người mua.",
    )
    cases.append(tc10)

    return cases


def generate_cases(output_dir: Path, case_filter: list[str] | None = None) -> list[TestCase]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    register_fonts()
    cases = build_varied_cases()
    if case_filter:
        cases = [c for c in cases if c.case_id in case_filter]

    for case in cases:
        target = output_dir / case.folder
        target.mkdir(parents=True, exist_ok=True)
        create_report_pdf(case, target / "report_hoan_ung.pdf")
        create_invoice_pdf(case, target / "hoa_don_dien_tu.pdf")
        if HAS_DOCX:
            create_report_docx(case, target / "report_hoan_ung.docx")
            create_invoice_docx(case, target / "hoa_don_dien_tu.docx")
        payload = expected_payload(case)
        (target / "expected.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Generated {case.case_id} -> {target.name}")

    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".runtime/staging-uc03-variations"))
    parser.add_argument("--cases", nargs="*", default=None, help="Filter case IDs (e.g. TC05 TC06)")
    args = parser.parse_args()
    generate_cases(args.output, args.cases)


if __name__ == "__main__":
    main()
