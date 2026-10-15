"""Generate three synthetic UC03 travel inputs. Never reads or writes gold.

Run with the repository's uv environment. ReportLab and the OFL NotoSans font
are already declared/bundled in this project. Existing unmanaged directories
are refused; regeneration only updates an explicit input-file allowlist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "assets/fonts/NotoSans-Regular.ttf"
MARKER = ".uc03-pilot-managed"
DATE = "2026-10-10T18:00:00+07:00"
TENANT = "tenant:uc03-pilot"
EMPLOYEE = "employee:employee-a"
ACCOUNTANT = "employee:accountant-demo"
APPROVER = "employee:approver"
CLAIMANT_NAME = "NGUYỄN MINH AN"
COMPANY_NAME = "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH"
# The two advance-basis documents are alternative test choices for F01 only; both
# describe the SAME 4.000.000 đ advance and must never be summed into 8.000.000.
TRANSFER_DOC = "03-bien-nhan-chuyen-khoan.pdf"
CASH_DOC = "04-phieu-chi-tien-mat.pdf"
FILES = {"01-giay-quyet-toan.pdf", "02-hoa-don-dich-vu.pdf", "organization.json",
         "organization-cash.json", "submission.json", "employee-confirmation.json", TRANSFER_DOC, CASH_DOC}
# Source specifications, not expected outcomes. Hidden gold is authored separately.
CASES = (
    ("UC03-F01", "f01-cong-tac-thu-lai-tien-thua", "IR26101001", "Bữa ăn phục vụ công việc trong chuyến công tác", "Suất", 10, 300_000, 3_240_000, 4_000_000, "Ba triệu hai trăm bốn mươi nghìn đồng"),
    ("UC03-F02", "f02-cong-tac-cong-ty-chi-them", "IR26101002", "Dịch vụ lưu trú công tác từ 06/10 đến 10/10/2026", "Đêm", 4, 1_250_000, 5_400_000, 5_000_000, "Năm triệu bốn trăm nghìn đồng"),
    ("UC03-F03", "f03-cong-tac-can-bang", "IR26101003", "Dịch vụ lưu trú công tác từ 06/10 đến 10/10/2026", "Đêm", 4, 1_000_000, 4_320_000, 4_320_000, "Bốn triệu ba trăm hai mươi nghìn đồng"),
)


def money(n: int) -> str:
    return f"{n:,}".replace(",", ".") + " đ"


def paragraph(text: str, *, size: int = 10, center: bool = False) -> Paragraph:
    return Paragraph(escape(text).replace("\n", "<br/>"), ParagraphStyle(
        "body", fontName="PilotNoto", fontSize=size, leading=size * 1.5,
        textColor=colors.HexColor("#172b3a"), alignment=1 if center else 0,
        spaceAfter=7,
    ))


def table(rows, widths, *, header: bool = True):
    data = [[paragraph(str(cell), size=9) for cell in row] for row in rows]
    result = Table(data, colWidths=widths, hAlign="LEFT")
    rules = [("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 8),
             ("RIGHTPADDING", (0, 0), (-1, -1), 8),
             ("TOPPADDING", (0, 0), (-1, -1), 7),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
             ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bdcbd4"))]
    if header:
        rules.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf3f6")))
    result.setStyle(TableStyle(rules))
    return result


def signature_row(columns) -> Table:
    """Signature blocks on ONE horizontal row, centered, with NO border/grid."""
    data = [[paragraph("\n".join(lines), size=9, center=True) for lines in columns]]
    result = Table(data, colWidths=[503 / len(columns)] * len(columns), hAlign="CENTER")
    result.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return result


def write_pdf(path: Path, title: str, story, *, left_margin: float = 46, right_margin: float = 46,
              top_margin: float = 42, bottom_margin: float = 40) -> None:
    def canvas_factory(*args, **kwargs):
        kwargs["invariant"] = 1
        return Canvas(*args, **kwargs)
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=left_margin, rightMargin=right_margin,
                            topMargin=top_margin, bottomMargin=bottom_margin, title=title,
                            author="InvoiceReferee synthetic corpus")
    doc.build(story, canvasmaker=canvas_factory)


def render_settlement_form(case, inp: Path) -> None:
    cid, _, number, description, unit, qty, price, total, advance, words = case
    form = [paragraph(COMPANY_NAME, size=10),
            paragraph("GIẤY ĐỀ NGHỊ QUYẾT TOÁN CÔNG TÁC", size=17, center=True),
            paragraph(f"Số: QT-{number}   |   Hà Nội, ngày 10 tháng 10 năm 2026", center=True),
            Spacer(1, 8), paragraph(f"Kính gửi: Bộ phận kế toán {COMPANY_NAME}"),
            paragraph(f"Người đề nghị: {CLAIMANT_NAME}"),
            paragraph("Nơi công tác: Hà Nội"),
            paragraph("Thời gian công tác: từ 06/10/2026 đến 10/10/2026"),
            paragraph("Mục đích: Làm việc với khách hàng tại Hà Nội"),
            paragraph("Loại tiền: VND"),
            table([["STT", "Nội dung chi phí", "Số hóa đơn", "Số tiền"],
                   ["1", description, number, money(total)]], [32, 241, 96, 134]),
            Spacer(1, 12), paragraph(f"Tổng chi phí đề nghị quyết toán: {money(total)}"),
            paragraph(f"Bằng chữ: {words}."),
            paragraph(f"Số tiền đã tạm ứng theo khai báo: {money(advance)}"),
            paragraph(f"Số tiền đề nghị công ty chi thêm: {money(max(total - advance, 0))}"),
            paragraph(f"Số tiền đề nghị nhân viên hoàn lại: {money(max(advance - total, 0))}"),
            Spacer(1, 12),
            signature_row([[f"Người đề nghị", "(Ký, ghi rõ họ tên)", CLAIMANT_NAME]])]
    write_pdf(inp / "01-giay-quyet-toan.pdf", "Giấy quyết toán công tác", form)


def render_invoice(case, inp: Path) -> None:
    cid, _, number, description, unit, qty, price, total, advance, words = case
    net = qty * price
    invoice = [paragraph("CÔNG TY TNHH DỊCH VỤ AN BÌNH", size=12),
               paragraph("HÓA ĐƠN GIÁ TRỊ GIA TĂNG", size=18, center=True),
               paragraph(f"Mẫu số: 1C26TAA   |   Ký hiệu: IR26E   |   Số hóa đơn: {number}", center=True),
               paragraph("Ngày lập: 10/10/2026", center=True),
               Spacer(1, 8), paragraph("Đơn vị bán: Công ty TNHH Dịch vụ An Bình"),
               paragraph("Mã số thuế bên bán: 0101234565"),
               paragraph("Địa chỉ bên bán: 86 Trần Thái Tông, Cầu Giấy, Hà Nội"),
               paragraph(f"Đơn vị mua: {COMPANY_NAME}"),
               paragraph("Mã số thuế bên mua: 0319999996"),
               paragraph("Địa chỉ bên mua: 128 Nguyễn Văn Linh, Thành phố Hồ Chí Minh"),
               paragraph(f"Họ tên người mua: {CLAIMANT_NAME}"),
               paragraph("Hình thức thanh toán: Chuyển khoản"),
               paragraph("Loại tiền: VND"),
               table([["STT", "Nội dung dịch vụ", "ĐVT", "SL", "Đơn giá", "Thành tiền"],
                      ["1", description, unit, str(qty), money(price), money(net)]],
                     [40, 174, 42, 30, 102, 115]),
               Spacer(1, 14),
               table([["Cộng tiền hàng chưa thuế", money(net)],
                      ["Thuế suất GTGT", "8%"],
                      ["Tiền thuế GTGT", money(total - net)],
                      ["Tổng cộng thanh toán", money(total)]], [369, 134], header=False),
               Spacer(1, 12), paragraph(f"Số tiền bằng chữ: {words}."),
               Spacer(1, 14),
               signature_row([
                   ["NGƯỜI MUA HÀNG", f"Ký bởi: {CLAIMANT_NAME}", "Ký ngày: 10/10/2026"],
                   ["NGƯỜI BÁN HÀNG", "Công ty TNHH Dịch vụ An Bình",
                    "Người ký: Phạm Hoàng Nam", "Ký ngày: 10/10/2026"],
               ])]
    write_pdf(inp / "02-hoa-don-dich-vu.pdf", "Hóa đơn dịch vụ", invoice)


def _advance_paragraph(text: str, *, size: float = 10, center: bool = False, right: bool = False,
                       color=colors.HexColor("#0f172a"), leading: float | None = None) -> Paragraph:
    lead = leading if leading is not None else (size * 1.38)
    align = 1 if center else (2 if right else 0)
    style = ParagraphStyle(
        f"adv_{size}_{align}_{color.hexval()}_{lead}",
        fontName="PilotNoto",
        fontSize=size,
        leading=lead,
        textColor=color,
        alignment=align,
    )
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)


def render_advance_documents(
    case, inp: Path, *, status: str = "Hoàn tất", purpose: str | None = None,
    claimant: str = CLAIMANT_NAME, company: str = COMPANY_NAME,
    accountant: str = "Trần Bình", approver: str = "Lê Minh",
    advance_reference: str | None = None,
) -> None:
    """Two alternative advance-basis documents for the SAME 4m advance.

    One transfer receipt and one cash voucher; only one is used per test branch,
    so the 4.000.000 đ advance is never counted twice.
    """
    cid, _, number, _, _, _, _, total, advance, _ = case
    purpose = purpose or "Ứng tiền cho chuyến công tác Hà Nội từ 06/10/2026 đến 10/10/2026"
    advance_reference = advance_reference or f"ADV-{cid}"
    advance_words = "Bốn triệu đồng"

    adv_margin = 52.0  # 18.3 mm
    usable_w = 595.275 - 2 * adv_margin  # 491.275 pt

    c_text = colors.HexColor("#0f172a")        # Slate 900
    c_text_sec = colors.HexColor("#334155")    # Slate 700
    c_muted = colors.HexColor("#64748b")       # Slate 500
    c_border = colors.HexColor("#cbd5e1")      # Slate 300
    c_border_light = colors.HexColor("#e2e8f0") # Slate 200
    c_card_bg = colors.HexColor("#f8fafc")     # Slate 50
    c_header_bg = colors.HexColor("#f1f5f9")   # Slate 100
    c_success = colors.HexColor("#15803d")     # Emerald 700

    # 1. BIÊN NHẬN CHUYỂN KHOẢN
    transfer_story = []

    # A. Header công ty; metadata mã giao dịch/ngày đặt gọn
    t_header = Table([
        [_advance_paragraph(company, size=9, color=c_text),
         _advance_paragraph(f"Mã giao dịch: FT-{cid}-0001", size=9, right=True, color=c_text)],
        [_advance_paragraph("Địa chỉ: 128 Nguyễn Văn Linh, TP. Hồ Chí Minh", size=8, color=c_muted),
         _advance_paragraph("Ngày giao dịch: 05/10/2026", size=9, right=True, color=c_text_sec)],
    ], colWidths=[usable_w * 0.56, usable_w * 0.44], hAlign="LEFT")
    t_header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEBELOW", (0, 0), (-1, -1), 0.75, c_border),
    ]))
    transfer_story.append(t_header)
    transfer_story.append(Spacer(1, 18))

    # B. Tiêu đề
    transfer_story.append(_advance_paragraph("BIÊN NHẬN CHUYỂN KHOẢN", size=19, center=True, color=c_text, leading=24))
    transfer_story.append(Spacer(1, 16))

    # C. Khối số tiền nổi bật, kèm trạng thái giao dịch bằng chữ
    status_color = c_success if any(w in status.casefold() for w in ("hoàn tất", "thành công")) else c_text_sec
    t_amount = Table([
        [_advance_paragraph("SỐ TIỀN THỰC NHẬN", size=9, center=True, color=c_muted, leading=12)],
        [_advance_paragraph(money(advance), size=25, center=True, color=c_text, leading=34)],
        [_advance_paragraph(f"Trạng thái giao dịch: {status}", size=10.5, center=True, color=status_color, leading=15)],
    ], colWidths=[usable_w])
    t_amount.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), c_card_bg),
        ("BOX", (0, 0), (-1, -1), 0.75, c_border),
        ("TOPPADDING", (0, 0), (-1, 0), 12),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 12),
    ]))
    transfer_story.append(t_amount)
    transfer_story.append(Spacer(1, 18))

    # D. Hai cột cân đối: Bên chuyển & Bên nhận
    half_w = (usable_w - 12) / 2
    left_inner = Table([
        [_advance_paragraph("Bên chuyển", size=8.5, color=c_muted)],
        [_advance_paragraph(company, size=10.5, color=c_text, leading=14)],
        [Spacer(1, 6)],
        [_advance_paragraph("Tài khoản chuyển", size=8.5, color=c_muted)],
        [_advance_paragraph("Ngân hàng Demo — 0123456789", size=10, color=c_text_sec, leading=14)],
    ], colWidths=[half_w - 20], style=[
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 0),
    ])

    t_left = Table([
        [_advance_paragraph("THÔNG TIN BÊN CHUYỂN", size=9.5, color=c_text_sec, leading=14)],
        [left_inner],
    ], colWidths=[half_w])
    t_left.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), c_header_bg),
        ("BACKGROUND", (0, 1), (-1, 1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, c_border_light),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, c_border_light),
        ("PADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    right_inner = Table([
        [_advance_paragraph("Bên nhận", size=8.5, color=c_muted)],
        [_advance_paragraph(claimant, size=10.5, color=c_text, leading=14)],
        [Spacer(1, 6)],
        [_advance_paragraph("Tài khoản nhận", size=8.5, color=c_muted)],
        [_advance_paragraph("Ngân hàng Demo — 9876543210", size=10, color=c_text_sec, leading=14)],
    ], colWidths=[half_w - 20], style=[
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 0),
    ])

    t_right = Table([
        [_advance_paragraph("THÔNG TIN BÊN NHẬN", size=9.5, color=c_text_sec, leading=14)],
        [right_inner],
    ], colWidths=[half_w])
    t_right.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), c_header_bg),
        ("BACKGROUND", (0, 1), (-1, 1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, c_border_light),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, c_border_light),
        ("PADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    t_cols = Table([[t_left, "", t_right]], colWidths=[half_w, 12, half_w])
    t_cols.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    transfer_story.append(t_cols)
    transfer_story.append(Spacer(1, 18))

    # E. Nội dung chuyển tiền và tham chiếu khoản ứng, dùng toàn chiều rộng
    t_details = Table([
        [_advance_paragraph("Nội dung chuyển tiền", size=9.5, color=c_muted),
         _advance_paragraph(purpose, size=10, color=c_text, leading=14)],
        [_advance_paragraph("Tham chiếu khoản ứng", size=9.5, color=c_muted),
         _advance_paragraph(advance_reference, size=10, color=c_text, leading=14)],
    ], colWidths=[145, usable_w - 145])
    t_details.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, c_border_light),
        ("BACKGROUND", (0, 0), (0, -1), c_card_bg),
        ("PADDING", (0, 0), (-1, -1), 9),
    ]))
    transfer_story.append(t_details)
    transfer_story.append(Spacer(1, 36))

    # F. Người lập: “Ký bởi: …”, “Ký ngày: …”
    sig_w = 200
    sig_table = Table([
        [_advance_paragraph("Người lập biên nhận", size=10, center=True, color=c_text)],
        [_advance_paragraph("(Ký, ghi rõ họ tên)", size=8.5, center=True, color=c_muted)],
        [Spacer(1, 46)],
        [_advance_paragraph(f"Ký bởi: {accountant}", size=9.5, center=True, color=c_text)],
        [_advance_paragraph("Ký ngày: 05/10/2026", size=8.5, center=True, color=c_muted)],
    ], colWidths=[sig_w], style=[
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ])
    t_sig = Table([["", sig_table]], colWidths=[usable_w - sig_w, sig_w])
    t_sig.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 0),
    ]))
    transfer_story.append(t_sig)

    write_pdf(inp / TRANSFER_DOC, "Biên nhận chuyển khoản", transfer_story,
              left_margin=adv_margin, right_margin=adv_margin, top_margin=adv_margin, bottom_margin=adv_margin)

    # 2. PHIẾU CHI TIỀN MẶT
    cash_story = []

    # A. Header công ty; số phiếu/ngày
    t_cash_header = Table([
        [_advance_paragraph(company, size=9, color=c_text),
         _advance_paragraph(f"Số phiếu: PC-{cid}-0001", size=9, right=True, color=c_text)],
        [_advance_paragraph("Địa chỉ: 128 Nguyễn Văn Linh, TP. Hồ Chí Minh", size=8, color=c_muted),
         _advance_paragraph("Ngày: 05/10/2026", size=9, right=True, color=c_text_sec)],
    ], colWidths=[usable_w * 0.56, usable_w * 0.44], hAlign="LEFT")
    t_cash_header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEBELOW", (0, 0), (-1, -1), 0.75, c_border),
    ]))
    cash_story.append(t_cash_header)
    cash_story.append(Spacer(1, 18))

    # B. Tiêu đề
    cash_story.append(_advance_paragraph("PHIẾU CHI TIỀN MẶT", size=19, center=True, color=c_text, leading=24))
    cash_story.append(Spacer(1, 16))

    # C. Số tiền chi nổi bật; số tiền bằng chữ ngay bên dưới
    t_cash_amount = Table([
        [_advance_paragraph("SỐ TIỀN CHI", size=9, center=True, color=c_muted, leading=12)],
        [_advance_paragraph(money(advance), size=25, center=True, color=c_text, leading=34)],
        [_advance_paragraph(f"Số tiền bằng chữ: {advance_words}.", size=10.5, center=True, color=c_text_sec, leading=15)],
    ], colWidths=[usable_w])
    t_cash_amount.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), c_card_bg),
        ("BOX", (0, 0), (-1, -1), 0.75, c_border),
        ("TOPPADDING", (0, 0), (-1, 0), 12),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 12),
    ]))
    cash_story.append(t_cash_amount)
    cash_story.append(Spacer(1, 18))

    # D. Người nhận, lý do chi, tham chiếu khoản ứng
    t_cash_details = Table([
        [_advance_paragraph("Công ty chi", size=9.5, color=c_muted),
         _advance_paragraph(company, size=10, color=c_text, leading=14)],
        [_advance_paragraph("Người nhận tiền", size=9.5, color=c_muted),
         _advance_paragraph(claimant, size=10, color=c_text, leading=14)],
        [_advance_paragraph("Lý do chi", size=9.5, color=c_muted),
         _advance_paragraph(purpose, size=10, color=c_text, leading=14)],
        [_advance_paragraph("Tham chiếu khoản ứng", size=9.5, color=c_muted),
         _advance_paragraph(advance_reference, size=10, color=c_text, leading=14)],
    ], colWidths=[145, usable_w - 145])
    t_cash_details.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, c_border_light),
        ("BACKGROUND", (0, 0), (0, -1), c_card_bg),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    cash_story.append(t_cash_details)
    cash_story.append(Spacer(1, 16))

    # E. Nhóm xác nhận giao nhận: số tiền đã giao, số tiền đã nhận, ngày giao nhận
    handover_w = usable_w / 3
    col1_content = Table([
        [_advance_paragraph("Số tiền đã giao", size=8.5, center=True, color=c_muted)],
        [_advance_paragraph(money(advance), size=10.5, center=True, color=c_text, leading=14)],
    ], colWidths=[handover_w - 16], style=[("ALIGN", (0, 0), (-1, -1), "CENTER"), ("PADDING", (0, 0), (-1, -1), 0)])

    col2_content = Table([
        [_advance_paragraph("Số tiền đã nhận", size=8.5, center=True, color=c_muted)],
        [_advance_paragraph(money(advance), size=10.5, center=True, color=c_text, leading=14)],
    ], colWidths=[handover_w - 16], style=[("ALIGN", (0, 0), (-1, -1), "CENTER"), ("PADDING", (0, 0), (-1, -1), 0)])

    col3_content = Table([
        [_advance_paragraph("Ngày giao nhận", size=8.5, center=True, color=c_muted)],
        [_advance_paragraph("05/10/2026", size=10.5, center=True, color=c_text, leading=14)],
    ], colWidths=[handover_w - 16], style=[("ALIGN", (0, 0), (-1, -1), "CENTER"), ("PADDING", (0, 0), (-1, -1), 0)])

    t_handover = Table([[col1_content, col2_content, col3_content]], colWidths=[handover_w, handover_w, handover_w])
    t_handover.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, c_border_light),
        ("BACKGROUND", (0, 0), (-1, -1), c_card_bg),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    cash_story.append(t_handover)
    cash_story.append(Spacer(1, 32))

    # F. Ba block chữ ký bằng nhau trên MỘT HÀNG NGANG:
    #    Người phê duyệt | Kế toán/người giao tiền | Người nhận tiền
    sig_cols = [
        [
            _advance_paragraph("Người phê duyệt", size=9.5, center=True, color=c_text),
            _advance_paragraph("(Ký, ghi rõ họ tên)", size=8.5, center=True, color=c_muted),
            Spacer(1, 46),
            _advance_paragraph(f"Ký bởi: {approver}", size=9.5, center=True, color=c_text),
            _advance_paragraph("Ký ngày: 05/10/2026", size=8.5, center=True, color=c_muted),
        ],
        [
            _advance_paragraph("Kế toán / người giao tiền", size=9.5, center=True, color=c_text),
            _advance_paragraph("(Ký, ghi rõ họ tên)", size=8.5, center=True, color=c_muted),
            Spacer(1, 46),
            _advance_paragraph(f"Ký bởi: {accountant}", size=9.5, center=True, color=c_text),
            _advance_paragraph("Ký ngày: 05/10/2026", size=8.5, center=True, color=c_muted),
        ],
        [
            _advance_paragraph("Người nhận tiền", size=9.5, center=True, color=c_text),
            _advance_paragraph("(Ký, ghi rõ họ tên)", size=8.5, center=True, color=c_muted),
            Spacer(1, 46),
            _advance_paragraph(f"Ký bởi: {claimant}", size=9.5, center=True, color=c_text),
            _advance_paragraph("Ký ngày: 05/10/2026", size=8.5, center=True, color=c_muted),
        ],
    ]
    sub_tables = [
        Table([[item] for item in col], colWidths=[handover_w], style=[
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ])
        for col in sig_cols
    ]
    t_sig_cash = Table([sub_tables], colWidths=[handover_w, handover_w, handover_w])
    t_sig_cash.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 0),
    ]))
    cash_story.append(t_sig_cash)

    write_pdf(inp / CASH_DOC, "Phiếu chi tiền mặt", cash_story,
              left_margin=adv_margin, right_margin=adv_margin, top_margin=adv_margin, bottom_margin=adv_margin)


def json_write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def context_for(case, *, method: str = "TRANSFER"):
    cid, _, number, _, _, _, _, total, advance, _ = case
    activity = f"activity:{cid.lower()}"
    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    grants = [dict(id=f"grant:{cid}:{name}", version="v1", actor=actor, actions=actions,
                   scope=activity, max_amount=maximum, effective_from=interval[0],
                   effective_to=interval[1], allowed_profiles=["TRAVEL"])
              for name, actor, actions, maximum in (
                  ("recognize", "system:referee", ["RECOGNIZE_COST"], 8_000_000),
                  ("issue", "system:referee", ["ISSUE_PAYMENT", "ISSUE_COLLECTION"], 4_000_000),
                  ("approver", APPROVER, ["AUTHORIZE_ACTIVITY", "RECOGNIZE_COST",
                   "EXCEPT_POLICY", "ISSUE_PAYMENT", "ISSUE_COLLECTION"], 20_000_000),
                  ("accountant", ACCOUNTANT, ["CONFIRM_FINANCIAL_FACT", "RECORD_ACTUAL", "STOP", "RESUME"], 20_000_000))]
    quote = f"Ứng đã hoàn tất cho {CLAIMANT_NAME}, hoạt động {activity}: {money(advance)}."
    fund = "company:cash-demo" if method == "CASH" else "company:bank-demo"
    transaction = f"company:bank-demo:ADV-{cid}"
    if cid == "UC03-F01":
        transaction = f"cash:PC-{cid}-0001" if method == "CASH" else f"transfer:FT-{cid}-0001"
    organization = dict(
        organization_id=TENANT, tenant=TENANT, profile="TRAVEL", data_origin="SIMULATED",
        company_name=COMPANY_NAME,
        financial_as_of=DATE, records=[],
        activity=dict(activity_id=activity, name="Công tác Hà Nội", occurred_at="2026-10-06T09:00:00+07:00",
                      purpose="Làm việc với khách hàng tại Hà Nội", profile="TRAVEL",
                      authorization=dict(id=f"auth:{cid}", actor=APPROVER,
                          grant_ref=f"grant:{cid}:approver", effect_range=interval,
                          reason="Cho phép chuyến công tác Hà Nội", record_key=f"auth:{cid}")),
        people=[dict(id=EMPLOYEE, name=CLAIMANT_NAME), dict(id=ACCOUNTANT, name="Trần Bình"),
                dict(id=APPROVER, name="Lê Minh")],
        policies=[dict(id="policy:pilot", version="q32-v1", effective_from=interval[0],
                       effective_to=interval[1], profile="TRAVEL", rules=["EMPLOYEE_PAID_INVOICE_BOUNDED"])],
        grants=grants,
        ledger=[dict(id=f"advance:{cid}", external_key=transaction,
                     kind="ADVANCE_RECEIVED", scope=activity, payer=COMPANY_NAME, payee=EMPLOYEE,
                     amount=advance, event_at="2026-10-05T09:00:00+07:00",
                     recorded_at="2026-10-05T10:00:00+07:00", verification_state="CONFIRMED",
                     allocation_state="ALLOCATED", reverses_event_id=None,
                     witness_keys=[f"advance:{cid}"])],
        coverage=dict(employee=EMPLOYEE, activity=activity, start="2026-09-01T00:00:00+07:00",
                      as_of=DATE, fund_ids=[fund],
                      flow_kinds=["ADVANCE_RECEIVED", "REIMBURSEMENT_RECEIVED", "EMPLOYEE_RETURN",
                                  "REVERSAL", "OBSERVED_UNALLOCATED"],
                      opening_by_fund={fund: 0}, ledger_version="ledger:v1",
                      witness_keys=[f"coverage:{cid}"]),
        witnesses=[dict(record_key=f"advance:{cid}", quote=quote, actor=ACCOUNTANT,
                        scope=activity, observed_at="2026-10-05T10:00:00+07:00"),
                   dict(record_key=f"coverage:{cid}", quote="Đã đối chiếu đủ sổ ứng/hoàn, "
                        "số dư đầu kỳ 0; chưa có hoàn trả hoặc thu lại trong scope đến 10/10/2026 18:00.",
                        actor=ACCOUNTANT, scope=activity, observed_at=DATE)])
    return organization


def _managed_output(output: Path, marker: str, stamp: str) -> Path:
    output = output.absolute()
    if output.is_symlink() or output.resolve() in {ROOT, ROOT / "data", Path("/"), Path.home()}:
        raise ValueError("unsafe output directory")
    if any((output / name).is_symlink() for name in (marker, "manifest.json")):
        raise ValueError("managed marker/manifest must not be a symlink")
    if (output / marker).exists() and (output / marker).read_text() != stamp:
        raise ValueError("foreign managed marker; refusing overwrite")
    if output.exists() and any(output.iterdir()) and not (output / marker).is_file():
        raise ValueError("refusing unmanaged non-empty output; no files deleted")
    output.mkdir(parents=True, exist_ok=True)
    (output / marker).write_text(stamp)
    return output


def _register_font() -> None:
    pdfmetrics.registerFont(TTFont("PilotNoto", str(FONT)))
    pdfmetrics.registerFontFamily("PilotNoto", normal="PilotNoto", bold="PilotNoto", italic="PilotNoto", boldItalic="PilotNoto")


def generate(output: Path) -> None:
    output = _managed_output(output, MARKER, "UC03 pilot input generator v1\n")
    _register_font()
    entries = []
    for case in CASES:
        cid, folder, number, _, _, _, _, total, _, _ = case
        inp = output / folder / "input"
        if (output / folder).is_symlink() or inp.is_symlink():
            raise ValueError("case/input must not be a symlink")
        inp.mkdir(parents=True, exist_ok=True)
        unknown = {p.name for p in inp.iterdir()} - FILES
        if unknown or any(p.is_symlink() for p in inp.iterdir()):
            raise ValueError(f"unexpected input files; refusing overwrite: {unknown}")
        render_settlement_form(case, inp)
        render_invoice(case, inp)
        if cid == "UC03-F01":
            render_advance_documents(case, inp)
        json_write(inp / "organization.json", context_for(case))
        if cid == "UC03-F01":
            json_write(inp / "organization-cash.json", context_for(case, method="CASH"))
        json_write(inp / "submission.json", dict(employee=EMPLOYEE,
                   activity=f"activity:{cid.lower()}", declared_purpose="Làm việc với khách hàng tại Hà Nội",
                   notes="Nhân viên nộp giấy quyết toán và hóa đơn dịch vụ; "
                         "kế toán xác minh khoản ứng thực nhận."))
        invoice = inp / "02-hoa-don-dich-vu.pdf"
        json_write(inp / "employee-confirmation.json", dict(
            fact_key=f"expense:{number}:employee_paid", value=total, actor=EMPLOYEE,
            scope=f"activity:{cid.lower()}", reason="Hóa đơn dịch vụ hợp lệ gắn đúng nhân viên và hồ sơ; "
            "được chấp nhận làm căn cứ khoản chi nhân viên đã thanh toán theo policy demo.",
            observed_at=DATE, refs=[dict(source_id="file:02-hoa-don-dich-vu.pdf",
              source_sha256=hashlib.sha256(invoice.read_bytes()).hexdigest(), page=1,
              exact_quote=money(total))]))
        files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(inp.iterdir())}
        entries.append(dict(case_id=cid, folder=folder, inputs=files,
                            source_origin=f"Hoangha v1 TC{cid[-2:]}", profile="TRAVEL",
                            split="development", family="uc03-pilot-v1"))
    json_write(output / "manifest.json", dict(schema_version="uc03-pilot-input/v1",
        data_origin="SYNTHETIC", runtime_status="EVIDENCE_READY_FINANCE_NOT_CONNECTED",
        corpus_status="INPUTS_GENERATED_NOT_RUNTIME_PASS", entries=entries))
    print(f"generated 3 cases / 8 PDFs at {output}; gold never read or written")


def generate_tc01(output: Path, context_path: Path) -> None:
    """Read the server's TC01 fixture, not gold, and render two alternatives."""
    from copy import deepcopy
    from invoice_referee.domain.organization import OrganizationContext

    context = OrganizationContext.model_validate_json(context_path.read_bytes())
    events = [e for e in context.ledger if e.get("kind") == "ADVANCE_RECEIVED"]
    if len(events) != 1 or int(events[0]["amount"]) != 4_000_000:
        raise ValueError("TC01 renderer requires exactly one 4m advance")
    people = {str(p["id"]): str(p["name"]) for p in context.people}
    activity = context.activity or {}
    claimant = people[str(events[0]["payee"])]
    company = context.company_name
    if not company or not activity.get("purpose"):
        raise ValueError("TC01 company identity and work purpose are required")
    marker = ".tc01-advance-managed"
    allowed = {marker, TRANSFER_DOC, CASH_DOC, "context-chuyen-khoan.json", "context-tien-mat.json", "manifest.json"}
    output = _managed_output(output, marker, "TC01 advance generator v1\n")
    if any(p.is_symlink() or p.name not in allowed for p in output.iterdir()):
        raise ValueError("unexpected files/symlinks in TC01 output; refusing overwrite")
    _register_font()
    case = ("TC01", "", "", "", "", 0, 0, 0, 4_000_000, "")
    render_advance_documents(
        case, output, purpose=f"Ứng tiền {str(activity['purpose']).removeprefix('Chi phí ')}",
        claimant=claimant, company=company, accountant=people[ACCOUNTANT].split(" (", 1)[0],
        approver=people[APPROVER].split(" (", 1)[0], advance_reference="TU-TC01",
    )
    for label, method, reference, fund in (
        ("chuyen-khoan", "TRANSFER", "FT-TC01-0001", "company:bank-demo"),
        ("tien-mat", "CASH", "PC-TC01-0001", "company:cash-demo"),
    ):
        variant = deepcopy(context.model_dump(mode="json"))
        variant["ledger"][0].update(external_key=f"{method.lower()}:{reference}", payer=company)
        variant["coverage"]["fund_ids"] = [fund]
        variant["coverage"]["opening_by_fund"] = {fund: 0}
        json_write(output / f"context-{label}.json", variant)
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())
             if p.name not in {marker, "manifest.json"}}
    json_write(output / "manifest.json", dict(data_origin="SYNTHETIC", case_id="TC01", files=files,
               alternatives=True, instruction="Use one payment method and its matching context; never sum both advances."))
    print(f"generated TC01 transfer/cash alternatives at {output}; gold never read or written")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/test-kit/uc03-pilot")
    parser.add_argument("--tc01-output", type=Path, help="Generate only the TC01 advance alternatives here")
    parser.add_argument("--tc01-context", type=Path, default=ROOT / "data/demo/tc01-company-context.json")
    args = parser.parse_args()
    if args.tc01_output is not None:
        generate_tc01(args.tc01_output, args.tc01_context)
    else:
        generate(args.output)


if __name__ == "__main__":
    main()
