"""Deterministic generator for synthetic scenario VFY-BAL-01.

Scenario:
- Organization: CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH (MST: 0319999996)
- Employee: NGUYỄN MINH AN
- Purpose: Quyết toán chi phí mua văn phòng phẩm và vật tư dự án Quý 4/2026
- Expenses: 2.160.000 VND (Subtotal 2.000.000 VND + VAT 8% 160.000 VND)
- Advance: 2.160.000 VND
- Difference S = 0 VND (Routine balanced settlement, no money moved, conclusion BALANCED)
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "NotoSans-Regular.ttf"


def _register_font() -> str:
    pdfmetrics.registerFont(TTFont("NotoSans", str(FONT_PATH)))
    return "NotoSans"


def render_report_hoan_ung(out_path: Path) -> Path:
    font = _register_font()
    c = canvas.Canvas(str(out_path), pagesize=A4, invariant=1)
    c.setTitle("GIẤY ĐỀ NGHỊ HOÀN ỨNG - VFY-BAL-01")
    c.setAuthor("InvoiceReferee Synthetic Generator")
    c.setSubject("invariant=1")
    c._doc.info.producer = "InvoiceReferee"

    width, height = A4

    # Header
    c.setFont(font, 10)
    c.drawString(50, height - 50, "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH")
    c.drawRightString(width - 50, height - 50, "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")
    c.drawRightString(width - 50, height - 65, "Độc lập - Tự do - Hạnh phúc")

    c.setFont(font, 9)
    c.drawRightString(width - 50, height - 85, "Thành phố Hồ Chí Minh, ngày 10 tháng 10 năm 2026")

    # Title
    c.setFont(font, 16)
    c.drawCentredString(width / 2, height - 120, "GIẤY ĐỀ NGHỊ HOÀN ỨNG")
    c.setFont(font, 11)
    c.drawCentredString(width / 2, height - 140, "Về việc: Quyết toán chi phí mua văn phòng phẩm và vật tư dự án Quý 4/2026")

    # Metadata
    c.setFont(font, 10)
    y = height - 175
    c.drawString(50, y, "Kính gửi: Ban Giám đốc CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH")
    y -= 20
    c.drawString(50, y, "Người đề nghị: NGUYỄN MINH AN")
    c.drawString(320, y, "Bộ phận: Hành chính nhân sự")
    y -= 20
    c.drawString(50, y, "Chức vụ: Nhân viên")
    c.drawString(320, y, "Mã nhân viên: NV-01")
    y -= 20
    c.drawString(50, y, "Nội dung: Quyết toán chi phí mua văn phòng phẩm và vật tư dự án Quý 4/2026")

    # Table Header
    y -= 30
    c.setStrokeColor(HexColor("#333333"))
    c.setLineWidth(1)
    c.line(50, y, width - 50, y)
    c.line(50, y - 25, width - 50, y - 25)

    c.setFont(font, 9)
    c.drawString(55, y - 17, "STT")
    c.drawString(85, y - 17, "NỘI DUNG")
    c.drawString(310, y - 17, "HÓA ĐƠN")
    c.drawString(390, y - 17, "SỐ TIỀN")
    c.drawString(470, y - 17, "GHI CHÚ")

    # Table Row 1
    y -= 25
    c.line(50, y - 30, width - 50, y - 30)
    c.drawString(60, y - 18, "1")
    c.drawString(85, y - 18, "Chi phí văn phòng phẩm phục vụ dự án Q4/2026")
    c.drawString(315, y - 18, "00000888")
    c.drawRightString(455, y - 18, "2.160.000")
    c.drawString(470, y - 18, "Đính kèm HĐĐT")

    # Table Total Row
    y -= 30
    c.line(50, y - 25, width - 50, y - 25)
    c.setFont(font, 10)
    c.drawString(85, y - 17, "Tổng cộng")
    c.drawRightString(455, y - 17, "2.160.000")

    # Vertical grid lines
    c.line(50, y + 55, 50, y - 25)
    c.line(80, y + 55, 80, y - 25)
    c.line(305, y + 55, 305, y - 25)
    c.line(380, y + 55, 380, y - 25)
    c.line(465, y + 55, 465, y - 25)
    c.line(width - 50, y + 55, width - 50, y - 25)

    # Words and Settlement details
    y -= 45
    c.setFont(font, 10)
    c.drawString(50, y, "Số tiền bằng chữ: Hai triệu một trăm sáu mươi nghìn đồng.")
    y -= 22
    c.drawString(50, y, "Số tiền đã tạm ứng: 2.160.000 đồng")
    y -= 20
    c.drawString(50, y, "Chênh lệch quyết toán (hoàn ứng / thanh toán thêm): 0 đồng")
    y -= 20
    c.drawString(50, y, "Bằng chữ: Không đồng (Quyết toán cân bằng).")

    # Signatures
    y -= 50
    c.setFont(font, 10)
    c.drawCentredString(110, y, "NGƯỜI ĐỀ NGHỊ")
    c.drawCentredString(width / 2, y, "KẾ TOÁN THANH TOÁN")
    c.drawCentredString(width - 110, y, "GIÁM ĐỐC DUYỆT")

    y -= 15
    c.setFont(font, 8)
    c.drawCentredString(110, y, "(Ký, họ tên)")
    c.drawCentredString(width / 2, y, "(Ký, họ tên)")
    c.drawCentredString(width - 110, y, "(Ký, họ tên, đóng dấu)")

    y -= 65
    c.setFont(font, 10)
    c.drawCentredString(110, y, "NGUYỄN MINH AN")
    c.drawCentredString(width / 2, y, "TRẦN THỊ B")
    c.drawCentredString(width - 110, y, "LÊ VĂN C")

    c.showPage()
    c.save()
    return out_path


def render_hoa_don_dien_tu(out_path: Path) -> Path:
    font = _register_font()
    c = canvas.Canvas(str(out_path), pagesize=A4, invariant=1)
    c.setTitle("HÓA ĐƠN ĐIỆN TỬ - VFY-BAL-01")
    c.setAuthor("InvoiceReferee Synthetic Generator")
    c.setSubject("invariant=1")
    c._doc.info.producer = "InvoiceReferee"

    width, height = A4

    # Header
    c.setFont(font, 14)
    c.drawCentredString(width / 2, height - 50, "HÓA ĐƠN GIÁ TRỊ GIA TĂNG ĐIỆN TỬ")
    c.setFont(font, 9)
    c.drawCentredString(width / 2, height - 68, "Ngày 10 tháng 10 năm 2026")

    # Invoice info (top right)
    c.setFont(font, 9)
    c.drawString(width - 200, height - 90, "Mẫu số: 1C26TAA")
    c.drawString(width - 200, height - 105, "Ký hiệu: HH26E")
    c.drawString(width - 200, height - 120, "Số: 00000888")

    # Seller
    y = height - 95
    c.drawString(50, y, "Đơn vị bán hàng: CÔNG TY CỔ PHẦN VĂN PHÒNG PHẨM HỒNG HÀ")
    y -= 17
    c.drawString(50, y, "Mã số thuế: 0100108637")
    y -= 17
    c.drawString(50, y, "Địa chỉ: 25 Lý Thường Kiệt, Quận Hoàn Kiếm, Thành phố Hà Nội")
    y -= 17
    c.drawString(50, y, "Điện thoại: 024.3856.1234")

    # Divider
    y -= 15
    c.setStrokeColor(HexColor("#666666"))
    c.setLineWidth(0.5)
    c.line(50, y, width - 50, y)

    # Buyer
    y -= 20
    c.drawString(50, y, "Đơn vị mua hàng: CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH")
    y -= 17
    c.drawString(50, y, "Mã số thuế: 0319999996")
    y -= 17
    c.drawString(50, y, "Địa chỉ: 128 Nguyễn Văn Linh, Phường Tân Hưng, Quận 7, TP. Hồ Chí Minh")
    y -= 17
    c.drawString(50, y, "Họ tên người mua hàng: NGUYỄN MINH AN")
    y -= 17
    c.drawString(50, y, "Hình thức thanh toán: Chuyển khoản")

    # Items table
    y -= 25
    c.setStrokeColor(HexColor("#333333"))
    c.setLineWidth(1)
    c.line(50, y, width - 50, y)
    c.line(50, y - 25, width - 50, y - 25)

    c.setFont(font, 9)
    c.drawString(55, y - 17, "STT")
    c.drawString(85, y - 17, "TÊN HÀNG HÓA, DỊCH VỤ")
    c.drawString(300, y - 17, "ĐVT")
    c.drawString(340, y - 17, "SL")
    c.drawString(380, y - 17, "ĐƠN GIÁ")
    c.drawString(460, y - 17, "THÀNH TIỀN")

    # Row 1
    y -= 25
    c.line(50, y - 30, width - 50, y - 30)
    c.drawString(60, y - 18, "1")
    c.drawString(85, y - 18, "Văn phòng phẩm và vật tư phục vụ dự án Q4")
    c.drawString(305, y - 18, "Bộ")
    c.drawString(345, y - 18, "4")
    c.drawRightString(445, y - 18, "500.000")
    c.drawRightString(540, y - 18, "2.000.000")

    # Table grid vertical lines
    c.line(50, y + 25, 50, y - 30)
    c.line(80, y + 25, 80, y - 30)
    c.line(295, y + 25, 295, y - 30)
    c.line(335, y + 25, 335, y - 30)
    c.line(375, y + 25, 375, y - 30)
    c.line(455, y + 25, 455, y - 30)
    c.line(width - 50, y + 25, width - 50, y - 30)

    # Subtotals & Tax
    y -= 30
    c.setFont(font, 9)
    c.drawString(85, y - 18, "Cộng tiền hàng chưa thuế:")
    c.drawRightString(540, y - 18, "2.000.000")
    c.line(50, y - 25, width - 50, y - 25)

    y -= 25
    c.drawString(85, y - 18, "Thuế suất GTGT (8%):")
    c.drawString(305, y - 18, "Tiền thuế GTGT:")
    c.drawRightString(540, y - 18, "160.000")
    c.line(50, y - 25, width - 50, y - 25)

    y -= 25
    c.setFont(font, 10)
    c.drawString(85, y - 18, "Tổng cộng tiền thanh toán:")
    c.drawRightString(540, y - 18, "2.160.000")
    c.line(50, y - 25, width - 50, y - 25)

    # Grid lines for subtotal box
    c.line(50, y + 75, 50, y - 25)
    c.line(width - 50, y + 75, width - 50, y - 25)

    # Words
    y -= 45
    c.drawString(50, y, "Số tiền viết bằng chữ: Hai triệu một trăm sáu mươi nghìn đồng.")

    # Signatures
    y -= 50
    c.drawCentredString(130, y, "NGƯỜI MUA HÀNG")
    c.drawCentredString(width - 130, y, "NGƯỜI BÁN HÀNG")
    y -= 15
    c.setFont(font, 8)
    c.drawCentredString(130, y, "(Ký, ghi rõ họ tên)")
    c.drawCentredString(width - 130, y, "(Chữ ký số điện tử hợp lệ)")
    y -= 50
    c.setFont(font, 9)
    c.drawCentredString(130, y, "NGUYỄN MINH AN")
    c.drawCentredString(width - 130, y, "ĐÃ KÝ ĐIỆN TỬ BỞI CTY CP VĂN PHÒNG PHẨM HỒNG HÀ")

    c.showPage()
    c.save()
    return out_path


def sha256_of(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic VFY-BAL-01 PDFs")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "verify" / "cases" / "vfy-bal-01" / "dau-vao" / "01-nop-ban-dau")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    report_pdf = render_report_hoan_ung(args.output / "report_hoan_ung.pdf")
    invoice_pdf = render_hoa_don_dien_tu(args.output / "hoa_don_dien_tu.pdf")

    print(f"Generated VFY-BAL-01 report: {report_pdf} (sha256: {sha256_of(report_pdf)})")
    print(f"Generated VFY-BAL-01 invoice: {invoice_pdf} (sha256: {sha256_of(invoice_pdf)})")


if __name__ == "__main__":
    main()
