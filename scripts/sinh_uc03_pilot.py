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
CLAIMANT_NAME = "Nguyễn An"
# The two advance-basis documents are alternative test choices for F01 only; both
# describe the SAME 4.000.000 đ advance and must never be summed into 8.000.000.
TRANSFER_DOC = "03-bien-nhan-chuyen-khoan.pdf"
CASH_DOC = "04-phieu-chi-tien-mat.pdf"
FILES = {"01-giay-quyet-toan.pdf", "02-hoa-don-dich-vu.pdf", "organization.json",
         "submission.json", "employee-confirmation.json", TRANSFER_DOC, CASH_DOC}
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


def write_pdf(path: Path, title: str, story) -> None:
    def canvas_factory(*args, **kwargs):
        kwargs["invariant"] = 1
        return Canvas(*args, **kwargs)
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=46, rightMargin=46,
                            topMargin=42, bottomMargin=40, title=title,
                            author="InvoiceReferee synthetic corpus")
    doc.build(story, canvasmaker=canvas_factory)


def render_settlement_form(case, inp: Path) -> None:
    cid, _, number, description, unit, qty, price, total, advance, words = case
    form = [paragraph("CÔNG TY INVOICEREFEREE", size=12),
            paragraph("GIẤY ĐỀ NGHỊ QUYẾT TOÁN CÔNG TÁC", size=17, center=True),
            paragraph(f"Số: QT-{number}   |   Hà Nội, ngày 10 tháng 10 năm 2026", center=True),
            Spacer(1, 8), paragraph("Kính gửi: Bộ phận kế toán Công ty InvoiceReferee"),
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
               paragraph("Đơn vị mua: Công ty InvoiceReferee"),
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


def render_advance_documents(case, inp: Path) -> None:
    """F01-only: two alternative advance-basis documents for the SAME 4m advance.

    One transfer receipt and one cash voucher; only one is used per test branch,
    so the 4.000.000 đ advance is never counted twice.
    """
    cid, _, number, _, _, _, _, total, advance, _ = case
    purpose = "Ứng tiền cho chuyến công tác Hà Nội từ 06/10/2026 đến 10/10/2026"
    advance_words = "Bốn triệu đồng"
    transfer = [paragraph("CÔNG TY INVOICEREFEREE", size=12),
                paragraph("BIÊN NHẬN CHUYỂN KHOẢN", size=16, center=True),
                paragraph("(Bản ghi mô phỏng — không phải giao dịch ngân hàng thật)", size=9, center=True),
                Spacer(1, 8),
                table([["Mã giao dịch", f"FT-{cid}-0001"],
                       ["Ngày giao dịch", "05/10/2026"],
                       ["Trạng thái", "Hoàn tất"],
                       ["Bên chuyển", "Công ty InvoiceReferee"],
                       ["Tài khoản chuyển", "Ngân hàng Demo — 0123456789"],
                       ["Bên nhận", CLAIMANT_NAME],
                       ["Tài khoản nhận", "Ngân hàng Demo — 9876543210"],
                       ["Số tiền", money(advance)],
                       ["Nội dung", purpose],
                       ["Tham chiếu khoản ứng", f"ADV-{cid}"]], [150, 353], header=False),
                Spacer(1, 14),
                signature_row([["Người lập", "Ký bởi: Trần Bình", "Ký ngày: 05/10/2026"]])]
    write_pdf(inp / TRANSFER_DOC, "Biên nhận chuyển khoản", transfer)

    cash = [paragraph("CÔNG TY INVOICEREFEREE", size=12),
            paragraph("PHIẾU CHI TIỀN MẶT", size=16, center=True),
            paragraph("(Bản ghi mô phỏng — không phải giao dịch ngân hàng thật)", size=9, center=True),
            Spacer(1, 8),
            table([["Số phiếu", f"PC-{cid}-0001"],
                   ["Ngày", "05/10/2026"],
                   ["Công ty chi", "Công ty InvoiceReferee"],
                   ["Người nhận", CLAIMANT_NAME],
                   ["Lý do", purpose],
                   ["Số tiền", money(advance)],
                   ["Số tiền bằng chữ", advance_words],
                   ["Số tiền đã giao", money(advance)],
                   ["Số tiền đã nhận", money(advance)],
                   ["Ngày giao nhận", "05/10/2026"],
                   ["Tham chiếu khoản ứng", f"ADV-{cid}"]], [150, 353], header=False),
            Spacer(1, 14),
            signature_row([
                ["Người phê duyệt", "Ký bởi: Lê Minh", "Ký ngày: 05/10/2026"],
                ["Kế toán / người giao tiền", "Ký bởi: Trần Bình", "Ký ngày: 05/10/2026"],
                ["Người nhận tiền", f"Ký bởi: {CLAIMANT_NAME}", "Ký ngày: 05/10/2026"],
            ])]
    write_pdf(inp / CASH_DOC, "Phiếu chi tiền mặt", cash)


def json_write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def context_for(case):
    cid, _, number, _, _, _, _, total, advance, _ = case
    activity = f"activity:{cid.lower()}"
    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    grants = [dict(id=f"grant:{cid}:{name}", version="v1", actor=actor, actions=actions,
                   scope=activity, max_amount=maximum, effective_from=interval[0],
                   effective_to=interval[1], allowed_profiles=["TRAVEL"])
              for name, actor, actions, maximum in (
                  ("recognize", "system:referee", ["RECOGNIZE_COST"], 8_000_000),
                  ("issue", "system:referee", ["ISSUE_PAYMENT", "ISSUE_COLLECTION"], 4_000_000),
                  ("approver", APPROVER, ["AUTHORIZE_ACTIVITY", "SET_BUDGET", "RECOGNIZE_COST",
                   "EXCEPT_POLICY", "ISSUE_PAYMENT", "ISSUE_COLLECTION"], 20_000_000),
                  ("accountant", ACCOUNTANT, ["CONFIRM_FINANCIAL_FACT", "RECORD_ACTUAL", "STOP", "RESUME"], 20_000_000))]
    quote = f"Ứng đã hoàn tất cho {CLAIMANT_NAME}, hoạt động {activity}: {money(advance)}."
    organization = dict(
        organization_id=TENANT, tenant=TENANT, profile="TRAVEL", data_origin="SIMULATED",
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
        budgets=[dict(id=f"budget:{cid}", activity=activity, amount=8_000_000,
                      effect_range=interval, actor=APPROVER, grant_ref=f"grant:{cid}:approver")],
        ledger=[dict(id=f"advance:{cid}", external_key=f"company:bank-demo:ADV-{cid}",
                     kind="ADVANCE_RECEIVED", scope=activity, payer="company:demo", payee=EMPLOYEE,
                     amount=advance, event_at="2026-10-05T09:00:00+07:00",
                     recorded_at="2026-10-05T10:00:00+07:00", verification_state="CONFIRMED",
                     allocation_state="ALLOCATED", reverses_event_id=None,
                     witness_keys=[f"advance:{cid}"])],
        coverage=dict(employee=EMPLOYEE, activity=activity, start="2026-09-01T00:00:00+07:00",
                      as_of=DATE, fund_ids=["company:bank-demo"],
                      flow_kinds=["ADVANCE_RECEIVED", "REIMBURSEMENT_RECEIVED", "EMPLOYEE_RETURN",
                                  "REVERSAL", "OBSERVED_UNALLOCATED"],
                      opening_by_fund={"company:bank-demo": 0}, ledger_version="ledger:v1",
                      witness_keys=[f"coverage:{cid}"]),
        witnesses=[dict(record_key=f"advance:{cid}", quote=quote, actor=ACCOUNTANT,
                        scope=activity, observed_at="2026-10-05T10:00:00+07:00"),
                   dict(record_key=f"coverage:{cid}", quote="Đã đối chiếu đủ sổ ứng/hoàn, "
                        "số dư đầu kỳ 0; chưa có hoàn trả hoặc thu lại trong scope đến 10/10/2026 18:00.",
                        actor=ACCOUNTANT, scope=activity, observed_at=DATE)])
    return organization


def generate(output: Path) -> None:
    output = output.absolute()
    if output.is_symlink() or output.resolve() in {ROOT, ROOT / "data", Path("/"), Path.home()}:
        raise ValueError("unsafe output directory")
    if any((output / name).is_symlink() for name in (MARKER, "manifest.json")):
        raise ValueError("managed marker/manifest must not be a symlink")
    if (output / MARKER).exists() and (output / MARKER).read_text() != "UC03 pilot input generator v1\n":
        raise ValueError("foreign managed marker; refusing overwrite")
    if output.exists() and any(output.iterdir()) and not (output / MARKER).is_file():
        raise ValueError("refusing unmanaged non-empty output; no files deleted")
    output.mkdir(parents=True, exist_ok=True)
    (output / MARKER).write_text("UC03 pilot input generator v1\n")
    pdfmetrics.registerFont(TTFont("PilotNoto", str(FONT)))
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
    print(f"generated 3 cases / 6 PDFs at {output}; gold never read or written")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/test-kit/uc03-pilot")
    args = parser.parse_args()
    generate(args.output)


if __name__ == "__main__":
    main()
