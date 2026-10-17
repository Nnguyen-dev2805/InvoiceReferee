"""Generate 3 hard/adversarial test cases for InvoiceReferee stress testing.

HARD-01: Multi-rate VAT (8% and 10%) with trade discount before tax.
HARD-02: Client meal with personal/inadmissible line items (cigarettes, liquor) under threshold.
HARD-03: Twin invoices with same vendor, same date, and near-identical amounts (340k vs 345k).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

COMPANY_NAME = "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH"
COMPANY_TAX_CODE = "0319999996"
COMPANY_ADDRESS = "128 Nguyễn Văn Linh, Phường Tân Hưng, Thành phố Hồ Chí Minh"
EMPLOYEE_NAME = "NGUYỄN MINH AN"
EMPLOYEE_DEPARTMENT = "Hành chính nhân sự"
ACCOUNTANT_NAME = "TRẦN THỊ THU HÀ"
DIRECTOR_NAME = "LÊ QUANG HUY"


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


def money(value: int | Decimal | str) -> str:
    return f"{Decimal(str(value)):,.0f}".replace(",", ".")


def _pdf_styles() -> dict[str, ParagraphStyle]:
    register_fonts()
    base = getSampleStyleSheet()["Normal"]
    return {
        "title": ParagraphStyle("TitleVN", parent=base, fontName="TimesVN-Bold", fontSize=15, leading=19, alignment=TA_CENTER),
        "center": ParagraphStyle("CenterVN", parent=base, fontName="TimesVN", fontSize=9, leading=13, alignment=TA_CENTER),
        "center_bold": ParagraphStyle("CenterBoldVN", parent=base, fontName="TimesVN-Bold", fontSize=9, leading=13, alignment=TA_CENTER),
        "right": ParagraphStyle("RightVN", parent=base, fontName="TimesVN-Italic", fontSize=9, leading=13, alignment=TA_RIGHT),
        "body": ParagraphStyle("BodyVN", parent=base, fontName="TimesVN", fontSize=9, leading=14, alignment=TA_LEFT),
        "small": ParagraphStyle("SmallVN", parent=base, fontName="TimesVN", fontSize=8, leading=11, alignment=TA_LEFT),
        "small_center": ParagraphStyle("SmallCenterVN", parent=base, fontName="TimesVN", fontSize=8, leading=11, alignment=TA_CENTER),
        "small_right": ParagraphStyle("SmallRightVN", parent=base, fontName="TimesVN", fontSize=8, leading=11, alignment=TA_RIGHT),
        "small_bold": ParagraphStyle("SmallBoldVN", parent=base, fontName="TimesVN-Bold", fontSize=8, leading=11, alignment=TA_LEFT),
        "small_bold_right": ParagraphStyle("SmallBoldRightVN", parent=base, fontName="TimesVN-Bold", fontSize=8, leading=11, alignment=TA_RIGHT),
    }


def _pdf_table(data: list[list[Any]], widths: list[float], *, header: bool = True) -> Table:
    table = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="CENTER")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9A9A9A")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        commands.extend([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF2")),
            ("FONTNAME", (0, 0), (-1, 0), "TimesVN-Bold"),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ])
    table.setStyle(TableStyle(commands))
    return table


def build_hard_invoice(
    output_path: Path,
    *,
    seller_name: str,
    seller_tax_code: str,
    seller_address: str,
    invoice_no: str,
    serial: str,
    invoice_date_str: str,
    items: list[dict],
    subtotal: int,
    discount: int | None = None,
    tax_details: list[tuple[str, int]],
    total_tax: int,
    total_amount: int,
    amount_in_words: str,
) -> None:
    styles = _pdf_styles()
    doc = SimpleDocTemplate(str(output_path), pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=10 * mm, bottomMargin=12 * mm)
    story: list[Any] = []

    header_table = Table([[
        Paragraph(f"<b>{seller_name}</b><br/>MST: {seller_tax_code}<br/>Địa chỉ: {seller_address}", styles["body"]),
        Paragraph(f"<b>HÓA ĐƠN ĐIỆN TỬ</b><br/>Ký hiệu: <b>{serial}</b><br/>Số: <font color='red'><b>{invoice_no}</b></font><br/>Ngày: {invoice_date_str}", styles["small_right"]),
    ]], colWidths=[115 * mm, 65 * mm])
    header_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.extend([header_table, Spacer(1, 4 * mm)])

    buyer_table = Table([
        [Paragraph(f"<b>Tên đơn vị mua hàng:</b> {COMPANY_NAME}", styles["body"])],
        [Paragraph(f"<b>Mã số thuế:</b> {COMPANY_TAX_CODE}", styles["body"])],
        [Paragraph(f"<b>Địa chỉ:</b> {COMPANY_ADDRESS}", styles["body"])],
        [Paragraph("<b>Hình thức thanh toán:</b> Chuyển khoản", styles["body"])],
    ], colWidths=[180 * mm])
    buyer_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F9F9F9")),
        ("PADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([buyer_table, Spacer(1, 3 * mm)])

    # Table items
    table_data = [[
        Paragraph("STT", styles["small_center"]),
        Paragraph("Tên hàng hóa, dịch vụ", styles["small_center"]),
        Paragraph("ĐVT", styles["small_center"]),
        Paragraph("Số lượng", styles["small_center"]),
        Paragraph("Đơn giá", styles["small_center"]),
        Paragraph("Thuế", styles["small_center"]),
        Paragraph("Thành tiền", styles["small_center"]),
    ]]
    for idx, it in enumerate(items, 1):
        table_data.append([
            Paragraph(str(idx), styles["small_center"]),
            Paragraph(it["name"], styles["small"]),
            Paragraph(it.get("unit", "Cái"), styles["small_center"]),
            Paragraph(str(it["qty"]), styles["small_center"]),
            Paragraph(money(it["price"]), styles["small_right"]),
            Paragraph(it.get("tax_rate", "10%"), styles["small_center"]),
            Paragraph(money(it["amount"]), styles["small_right"]),
        ])

    table = _pdf_table(table_data, [10 * mm, 66 * mm, 14 * mm, 16 * mm, 24 * mm, 16 * mm, 34 * mm])
    story.extend([table, Spacer(1, 2 * mm)])

    # Summary table
    summary_data = [
        [Paragraph("Cộng tiền hàng:", styles["small_bold"]), Paragraph(money(subtotal), styles["small_bold_right"])],
    ]
    if discount:
        summary_data.append([
            Paragraph("Chiết khấu thương mại:", styles["small"]),
            Paragraph(f"-{money(discount)}", styles["small_right"]),
        ])
    for rate_label, tax_val in tax_details:
        summary_data.append([
            Paragraph(f"Tiền thuế GTGT ({rate_label}):", styles["small"]),
            Paragraph(money(tax_val), styles["small_right"]),
        ])
    summary_data.append([
        Paragraph("Tổng cộng tiền thanh toán:", styles["small_bold"]),
        Paragraph(f"<b>{money(total_amount)}</b>", styles["small_bold_right"]),
    ])

    sum_table = Table(summary_data, colWidths=[130 * mm, 50 * mm])
    sum_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
        ("PADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([sum_table, Spacer(1, 2 * mm)])
    story.append(Paragraph(f"<b>Số tiền viết bằng chữ:</b> <i>{amount_in_words}</i>", styles["body"]))
    story.append(Spacer(1, 4 * mm))

    sig_table = Table([[
        Paragraph("<b>NGƯỜI MUA HÀNG</b><br/>(Ký, ghi rõ họ tên)", styles["center"]),
        Paragraph(f"<b>NGƯỜI BÁN HÀNG</b><br/>(Đã ký điện tử)<br/><b>{seller_name}</b>", styles["center"]),
    ]], colWidths=[90 * mm, 90 * mm])
    story.append(sig_table)

    doc.build(story)


def build_hard_settlement_paper(
    output_path: Path,
    *,
    purpose: str,
    invoice_date_str: str,
    lines: list[dict],
    total_amount: int,
    advance_amount: int,
    amount_in_words: str,
) -> None:
    styles = _pdf_styles()
    doc = SimpleDocTemplate(str(output_path), pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=10 * mm, bottomMargin=12 * mm)
    story: list[Any] = []

    header = Table([[
        Paragraph(f"<b>{COMPANY_NAME}</b>", styles["center"]),
        Paragraph("<b>CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM</b><br/>Độc lập - Tự do - Hạnh phúc", styles["center"]),
    ]], colWidths=[90 * mm, 90 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.extend([
        header,
        Paragraph(f"TP. Hồ Chí Minh, {invoice_date_str}", styles["right"]),
        Spacer(1, 2 * mm),
        Paragraph("GIẤY ĐỀ NGHỊ THANH TOÁN / HOÀN ỨNG", styles["title"]),
        Paragraph(f"<i>Về việc: {purpose}</i>", styles["center"]),
        Spacer(1, 3 * mm),
        Paragraph(f"<b>Kính gửi:</b> Ban Giám đốc {COMPANY_NAME}", styles["body"]),
        Paragraph(f"<b>Người đề nghị:</b> {EMPLOYEE_NAME} - <b>Bộ phận:</b> {EMPLOYEE_DEPARTMENT}", styles["body"]),
        Paragraph(f"<b>Nội dung thanh toán:</b> {purpose}", styles["body"]),
        Spacer(1, 2 * mm),
    ])

    rows = [[
        Paragraph("STT", styles["small_center"]),
        Paragraph("Nội dung chi phí", styles["small_center"]),
        Paragraph("Số hóa đơn / Chứng từ", styles["small_center"]),
        Paragraph("Số tiền (VNĐ)", styles["small_center"]),
        Paragraph("Ghi chú", styles["small_center"]),
    ]]
    for idx, l in enumerate(lines, 1):
        rows.append([
            Paragraph(str(idx), styles["small_center"]),
            Paragraph(l["description"], styles["small"]),
            Paragraph(l.get("invoice_ref", ""), styles["small_center"]),
            Paragraph(money(l["amount"]), styles["small_right"]),
            Paragraph(l.get("note", ""), styles["small"]),
        ])
    rows.append([
        "",
        Paragraph("<b>Tổng cộng</b>", styles["small_bold"]),
        "",
        Paragraph(f"<b>{money(total_amount)}</b>", styles["small_bold_right"]),
        "",
    ])

    tbl = _pdf_table(rows, [10 * mm, 65 * mm, 35 * mm, 35 * mm, 35 * mm])
    tbl.setStyle(TableStyle([
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
        ("SPAN", (0, -1), (0, -1)),
    ]))
    story.extend([tbl, Spacer(1, 2 * mm)])

    diff = abs(total_amount - advance_amount)
    diff_label = "Số tiền nhân viên hoàn trả công ty" if advance_amount > total_amount else "Số tiền công ty thanh toán thêm"
    if total_amount == advance_amount:
        diff_label = "Chênh lệch quyết toán"

    story.extend([
        Paragraph(f"<b>Bằng chữ:</b> {amount_in_words}.", styles["body"]),
        Paragraph(f"<b>Số tiền tạm ứng:</b> {money(advance_amount)} đồng", styles["body"]),
        Paragraph(f"<b>{diff_label}:</b> {money(diff)} đồng", styles["body"]),
        Spacer(1, 5 * mm),
    ])

    sig = Table([[
        Paragraph(f"<b>NGƯỜI ĐỀ NGHỊ</b><br/>(Đã ký)<br/>{EMPLOYEE_NAME}", styles["center"]),
        Paragraph(f"<b>KẾ TOÁN</b><br/>(Đã ký)<br/>{ACCOUNTANT_NAME}", styles["center"]),
        Paragraph(f"<b>GIÁM ĐỐC</b><br/>(Đã ký, đóng dấu)<br/>{DIRECTOR_NAME}", styles["center"]),
    ]], colWidths=[60 * mm] * 3)
    story.append(sig)

    doc.build(story)


def main():
    base_dir = Path(".runtime/hard_cases")
    base_dir.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # CASE 1: HARD-01 Multi-rate VAT (8% and 10%) with Trade Discount
    # =========================================================================
    c1_dir = base_dir / "HARD01"
    c1_dir.mkdir(exist_ok=True)
    build_hard_invoice(
        c1_dir / "hoa_don_dien_tu.pdf",
        seller_name="CÔNG TY CỔ PHẦN CÔNG NGHỆ THÔNG TIN TOÀN PHÁT",
        seller_tax_code="0108876543",
        seller_address="15 Huỳnh Thúc Kháng, Đống Đa, Hà Nội",
        invoice_no="0008892",
        serial="1C26TTP",
        invoice_date_str="15/10/2026",
        items=[
            {"name": "Máy chủ server lưu trữ Dell PowerEdge R750", "qty": 1, "price": 10000000, "tax_rate": "10%", "amount": 10000000},
            {"name": "Gói bảo trì và phụ kiện nâng cấp mạng", "qty": 1, "price": 5000000, "tax_rate": "8%", "amount": 5000000},
        ],
        subtotal=15000000,
        discount=1000000,  # 1.000.000 discount
        tax_details=[("Thuế suất 10%", 900000), ("Thuế suất 8%", 400000)],
        total_tax=1300000,
        total_amount=15300000,
        amount_in_words="Mười lăm triệu ba trăm nghìn đồng",
    )
    build_hard_settlement_paper(
        c1_dir / "report_hoan_ung.pdf",
        purpose="Mua sắm máy chủ và thiết bị nâng cấp hạ tầng",
        invoice_date_str="Ngày 16 tháng 10 năm 2026",
        lines=[{
            "description": "Mua sắm máy chủ và phụ kiện công nghệ",
            "invoice_ref": "0008892",
            "amount": 15300000,
            "note": "HĐ số 0008892 ngày 15/10/2026",
        }],
        total_amount=15300000,
        advance_amount=16000000,
        amount_in_words="Mười lăm triệu ba trăm nghìn đồng",
    )
    print("Generated HARD-01 (Multi-rate VAT + Discount) in", c1_dir)

    # =========================================================================
    # CASE 2: HARD-02 Inadmissible personal items (Cigarettes, Liquor) in Client Meal
    # =========================================================================
    c2_dir = base_dir / "HARD02"
    c2_dir.mkdir(exist_ok=True)
    build_hard_invoice(
        c2_dir / "hoa_don_dien_tu.pdf",
        seller_name="CÔNG TY TNHH NHÀ HÀNG ẨM THỰC HOÀNG GIA",
        seller_tax_code="0314567890",
        seller_address="45 Lê Duẩn, Quận 1, TP. Hồ Chí Minh",
        invoice_no="0004521",
        serial="1C26THG",
        invoice_date_str="14/10/2026",
        items=[
            {"name": "Set ẩm thực tiếp khách đối tác", "unit": "Set", "qty": 1, "price": 2800000, "tax_rate": "8%", "amount": 2800000},
            {"name": "Nước suối và khăn lạnh", "unit": "Gói", "qty": 1, "price": 200000, "tax_rate": "8%", "amount": 200000},
            {"name": "Rượu mạnh Chivas 18", "unit": "Chai", "qty": 1, "price": 1200000, "tax_rate": "8%", "amount": 1200000},
            {"name": "Thuốc lá ngoại cao cấp", "unit": "Bao", "qty": 4, "price": 100000, "tax_rate": "8%", "amount": 400000},
        ],
        subtotal=4600000,
        discount=None,
        tax_details=[("Thuế suất 8%", 368000)],
        total_tax=368000,
        total_amount=4968000,
        amount_in_words="Bốn triệu chín trăm sáu mươi tám nghìn đồng",
    )
    build_hard_settlement_paper(
        c2_dir / "report_hoan_ung.pdf",
        purpose="Tiếp khách đối tác nghiệm thu giai đoạn dự án",
        invoice_date_str="Ngày 15 tháng 10 năm 2026",
        lines=[{
            "description": "Chi phí tiếp khách đối tác",
            "invoice_ref": "0004521",
            "amount": 4968000,
            "note": "Bàn giao nghiệm thu",
        }],
        total_amount=4968000,
        advance_amount=5000000,
        amount_in_words="Bốn triệu chín trăm sáu mươi tám nghìn đồng",
    )
    print("Generated HARD-02 (Client meal with personal items) in", c2_dir)

    # =========================================================================
    # CASE 3: HARD-03 Twin Invoices collision (Near-identical amounts & same vendor)
    # =========================================================================
    c3_dir = base_dir / "HARD03"
    c3_dir.mkdir(exist_ok=True)
    # Invoice 1: 340.000 VNĐ
    build_hard_invoice(
        c3_dir / "hoa_don_taxi_01.pdf",
        seller_name="CÔNG TY CỔ PHẦN TẬP ĐOÀN MAI LINH",
        seller_tax_code="0302525252",
        seller_address="64 Hai Bà Trưng, Quận 1, TP. Hồ Chí Minh",
        invoice_no="0019280",
        serial="1C26TML",
        invoice_date_str="12/10/2026",
        items=[
            {"name": "Cước taxi di chuyển làm việc quận 7", "unit": "Chuyến", "qty": 1, "price": 314815, "tax_rate": "8%", "amount": 314815},
        ],
        subtotal=314815,
        discount=None,
        tax_details=[("Thuế suất 8%", 25185)],
        total_tax=25185,
        total_amount=340000,
        amount_in_words="Ba trăm bốn mươi nghìn đồng",
    )
    # Invoice 2: 345.000 VNĐ (Twin invoice)
    build_hard_invoice(
        c3_dir / "hoa_don_taxi_02.pdf",
        seller_name="CÔNG TY CỔ PHẦN TẬP ĐOÀN MAI LINH",
        seller_tax_code="0302525252",
        seller_address="64 Hai Bà Trưng, Quận 1, TP. Hồ Chí Minh",
        invoice_no="0019281",
        serial="1C26TML",
        invoice_date_str="12/10/2026",
        items=[
            {"name": "Cước taxi di chuyển làm việc quận Bình Thạnh", "unit": "Chuyến", "qty": 1, "price": 319444, "tax_rate": "8%", "amount": 319444},
        ],
        subtotal=319444,
        discount=None,
        tax_details=[("Thuế suất 8%", 25556)],
        total_tax=25556,
        total_amount=345000,
        amount_in_words="Ba trăm bốn mươi lăm nghìn đồng",
    )
    # Settlement paper maps ONLY the 340.000 trip but attaches both
    build_hard_settlement_paper(
        c3_dir / "report_hoan_ung.pdf",
        purpose="Chi phí taxi di chuyển công tác trong thành phố",
        invoice_date_str="Ngày 13 tháng 10 năm 2026",
        lines=[{
            "description": "Taxi di chuyển gặp khách hàng quận 7",
            "invoice_ref": "0019280",
            "amount": 340000,
            "note": "Mai Linh số 0019280",
        }],
        total_amount=340000,
        advance_amount=500000,
        amount_in_words="Ba trăm bốn mươi nghìn đồng",
    )
    print("Generated HARD-03 (Twin invoices) in", c3_dir)


if __name__ == "__main__":
    main()
