"""Fixture transport for provider-free reads (S6, 18/10/2026).

Dev/test-only: canned OCR pages (+block boxes/word confidences) and canned
LLM extraction payloads, keyed by explicit fixture markers. Wired ONLY through
`scripts/dev.py --fake-llm-dir` / tests — never the production composition.
Reports produced this way are labelled RECORDED_REPLAY.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import hashlib

from invoice_referee.evidence.fake_transport import (
    FakeLLM,
    FakeReader,
    OCR_HEIGHT,
    OCR_WIDTH,
    amount_block_box,
    load_llm_dir,
    write_llm_dir,
    write_pages_json,
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_docs(
    *,
    consistent_parties: bool = False,
    variant: str = "M",
    parts_total: int = 2700000,
    labor_total: int = 1500000,
) -> dict[str, dict]:
    """The TC18-shaped fixture set. Mismatch variant by default (TC18 gốc).

    Amounts are parameters so synthetic variants (e.g. a self-expense case
    sized under the self-issue ceiling) stay internally consistent.
    """
    issuer = "Công ty An Thịnh" if consistent_parties else "Trung tâm Kỹ thuật Phúc An"
    payee = "Công ty An Thịnh"
    m = lambda name: f"FIXTURE-S6-{variant}-{name}"
    parts, labor, total = (
        str(parts_total),
        str(labor_total),
        str(parts_total + labor_total),
    )
    subtotal = str(parts_total - 200000)
    amounts = {"parts": parts, "labor": labor, "total": total, "subtotal": subtotal}
    return {
        "paper": {
            "marker": m("PAPER"),
            "lines": [
                "GIẤY ĐỀ NGHỊ HOÀN ỨNG",
                "Người đề nghị: NGUYỄN MINH AN",
                "Mục đích: Sửa chữa máy in văn phòng",
                f"Mua linh kiện máy in | {parts} | 00001801 | Đính kèm hóa đơn",
                f"Nhân công sửa chữa | {labor} | BBNT-181026-02 / FT262918104578 | Biên bản nghiệm thu và chuyển khoản",
                f"Tổng cộng: {total}",
                "Tạm ứng đã nhận: 5000000",
            ],
        },
        "invoice": {
            "marker": m("INV"),
            "lines": [
                "HÓA ĐƠN GIÁ TRỊ GIA TĂNG",
                "Số hóa đơn: 00001801",
                "Bên bán: Trung tâm Kỹ thuật Phúc An",
                "Bên mua: CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
                "Người mua: NGUYỄN MINH AN",
                f"Linh kiện sửa máy in: {subtotal}",
                "Thuế GTGT: 200000",
                f"Tổng tiền: {parts}",
                "Ngày: 08/10/2026",
            ],
        },
        "acceptance": {
            "marker": m("ACC"),
            "lines": [
                "BIÊN BẢN NGHIỆM THU",
                "Số biên bản: BBNT-181026-02",
                f"Bên cung cấp: {issuer}",
                "Bên nhận: CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
                "Nội dung: Nhân công sửa chữa máy in",
                f"Trị giá: {labor}",
                "Ngày: 09/10/2026",
            ],
        },
        "transfer": {
            "marker": m("TRF"),
            "lines": [
                "XÁC NHẬN CHUYỂN KHOẢN",
                "Mã giao dịch: FT262918104578",
                "Ngân hàng: Ngân hàng Demo",
                "Người chuyển: NGUYỄN MINH AN",
                f"Người nhận: {payee}",
                f"Số tiền: {labor}",
                "Trạng thái: Thành công",
                "Ngày giao dịch: 09/10/2026",
            ],
        },
        "_amounts": amounts,
    }


def _payload_fields(lines: list[str], wanted: list[tuple[str, str, str]]) -> list[dict]:
    """Build extraction field entries whose quotes are exact OCR lines."""
    out = []
    for field, value, quote in wanted:
        assert quote in lines, f"quote not an OCR line: {quote}"
        out.append(
            {
                "field": field,
                "state": "FOUND",
                "value": value,
                "quote": quote,
                "page": 1,
            }
        )
    return out


def llm_payloads(specs: dict[str, dict]) -> dict[str, dict]:
    """Canned extraction payloads keyed by fixture marker."""
    amounts = specs.get("_amounts", {})
    parts = amounts.get("parts", "2700000")
    labor = amounts.get("labor", "1500000")
    total = amounts.get("total", "4200000")
    advance = amounts.get("advance", "5000000")
    subtotal = amounts.get("subtotal", "2500000")
    paper_lines = specs["paper"]["lines"]
    inv_lines = specs["invoice"]["lines"]
    acc_lines = specs["acceptance"]["lines"]
    trf_lines = specs["transfer"]["lines"]
    return {
        specs["paper"]["marker"]: {
            "role_fit": "FIT",
            "fields": _payload_fields(
                paper_lines,
                [
                    (
                        "declared_name",
                        "NGUYỄN MINH AN",
                        "Người đề nghị: NGUYỄN MINH AN",
                    ),
                    (
                        "purpose",
                        "Sửa chữa máy in văn phòng",
                        "Mục đích: Sửa chữa máy in văn phòng",
                    ),
                    ("printed_total", total, f"Tổng cộng: {total}"),
                    ("declared_advance", advance, f"Tạm ứng đã nhận: {advance}"),
                ],
            ),
            "line_items": [
                {
                    "fields": _payload_fields(
                        paper_lines,
                        [
                            (
                                "description",
                                "Mua linh kiện máy in",
                                f"Mua linh kiện máy in | {parts} | 00001801 | Đính kèm hóa đơn",
                            ),
                            (
                                "amount",
                                parts,
                                f"Mua linh kiện máy in | {parts} | 00001801 | Đính kèm hóa đơn",
                            ),
                            (
                                "invoice_refs",
                                ["00001801"],
                                f"Mua linh kiện máy in | {parts} | 00001801 | Đính kèm hóa đơn",
                            ),
                            (
                                "note",
                                "Đính kèm hóa đơn",
                                f"Mua linh kiện máy in | {parts} | 00001801 | Đính kèm hóa đơn",
                            ),
                        ],
                    )
                },
                {
                    "fields": _payload_fields(
                        paper_lines,
                        [
                            (
                                "description",
                                "Nhân công sửa chữa",
                                f"Nhân công sửa chữa | {labor} | BBNT-181026-02 / FT262918104578 | Biên bản nghiệm thu và chuyển khoản",
                            ),
                            (
                                "amount",
                                labor,
                                f"Nhân công sửa chữa | {labor} | BBNT-181026-02 / FT262918104578 | Biên bản nghiệm thu và chuyển khoản",
                            ),
                            (
                                "invoice_refs",
                                ["BBNT-181026-02", "FT262918104578"],
                                f"Nhân công sửa chữa | {labor} | BBNT-181026-02 / FT262918104578 | Biên bản nghiệm thu và chuyển khoản",
                            ),
                            (
                                "note",
                                "Biên bản nghiệm thu và chuyển khoản",
                                f"Nhân công sửa chữa | {labor} | BBNT-181026-02 / FT262918104578 | Biên bản nghiệm thu và chuyển khoản",
                            ),
                        ],
                    )
                },
            ],
        },
        specs["invoice"]["marker"]: {
            "document_type": "E_INVOICE",
            "fields": _payload_fields(
                inv_lines,
                [
                    ("document_number", "00001801", "Số hóa đơn: 00001801"),
                    (
                        "issuer_name",
                        "Trung tâm Kỹ thuật Phúc An",
                        "Bên bán: Trung tâm Kỹ thuật Phúc An",
                    ),
                    (
                        "buyer_person_name",
                        "NGUYỄN MINH AN",
                        "Người mua: NGUYỄN MINH AN",
                    ),
                    ("total_amount", parts, f"Tổng tiền: {parts}"),
                    ("document_date", "2026-10-08", "Ngày: 08/10/2026"),
                ],
            ),
            "line_items": [],
        },
        specs["acceptance"]["marker"]: {
            "document_type": "ACCEPTANCE_RECORD",
            "fields": _payload_fields(
                acc_lines,
                [
                    (
                        "document_number",
                        "BBNT-181026-02",
                        "Số biên bản: BBNT-181026-02",
                    ),
                    ("issuer_name", acc_lines[2].split(": ", 1)[1], acc_lines[2]),
                    ("total_amount", labor, f"Trị giá: {labor}"),
                    ("document_date", "2026-10-09", "Ngày: 09/10/2026"),
                ],
            ),
            "line_items": [],
        },
        specs["transfer"]["marker"]: {
            "document_type": "PAYMENT_PROOF",
            "fields": _payload_fields(
                trf_lines,
                [
                    (
                        "document_number",
                        "FT262918104578",
                        "Mã giao dịch: FT262918104578",
                    ),
                    ("payment_provider", "Ngân hàng Demo", "Ngân hàng: Ngân hàng Demo"),
                    ("payer_name", "NGUYỄN MINH AN", "Người chuyển: NGUYỄN MINH AN"),
                    ("payee_name", trf_lines[4].split(": ", 1)[1], trf_lines[4]),
                    ("amount", labor, f"Số tiền: {labor}"),
                    ("transaction_status", "Thành công", "Trạng thái: Thành công"),
                    (
                        "transaction_reference",
                        "FT262918104578",
                        "Mã giao dịch: FT262918104578",
                    ),
                    ("event_at", "2026-10-09", "Ngày giao dịch: 09/10/2026"),
                ],
            ),
            "line_items": [],
        },
    }


def make_fixture_pdfs(outdir: Path, specs: dict[str, dict]) -> dict[str, Path]:
    """Generate one-page text PDFs mirroring the OCR lines (reportlab)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    font_path = Path("assets/fonts/NotoSans-Regular.ttf")
    pdfmetrics.registerFont(TTFont("FixtureNoto", str(font_path)))
    width, height = A4
    paths: dict[str, Path] = {}
    for name, spec in specs.items():
        if name.startswith("_"):
            continue
        path = outdir / f"{name}.pdf"
        doc = canvas.Canvas(str(path), pagesize=A4)
        doc.setFont("FixtureNoto", 13)
        y = height - 70
        for line in spec["lines"]:
            doc.drawString(60, y, line)
            y -= 26
        doc.setFont("FixtureNoto", 8)
        doc.setFillGray(0.5)
        doc.drawString(60, 40, spec["marker"])
        doc.showPage()
        doc.save()
        paths[name] = path
    return paths


def build_fake_ocr_pages(
    specs: dict[str, dict], digests: dict[str, str], *, with_confidence: bool = True
) -> dict[str, dict]:
    """Canned OCR pages: markdown + one boxed block per doc; the transfer
    amount word carries a meaningful low confidence (0.62) so the confidence
    stage yields exactly one candidate."""
    pages: dict[str, dict] = {}
    labor = specs.get("_amounts", {}).get("labor", "1500000")
    for name, spec in specs.items():
        if name.startswith("_"):
            continue
        markdown = "\n".join([*spec["lines"], spec["marker"]])
        blocks = []
        for index, line in enumerate(spec["lines"]):
            words = [{"text": token, "confidence": 0.99} for token in line.split()]
            blocks.append(
                {
                    "id": f"b{index}",
                    "kind": "text",
                    "content": line,
                    "bbox": None,
                    "words": words,
                }
            )
        if with_confidence and name == "transfer":
            for block in blocks:
                if block["content"].startswith("Số tiền:"):
                    block["bbox"] = amount_block_box()
                    block["words"] = [
                        {"text": "Số", "confidence": 0.99},
                        {"text": "tiền:", "confidence": 0.99},
                        {"text": labor, "confidence": 0.62},
                    ]
        pages[name] = {"digest": digests[name], "markdown": markdown, "blocks": blocks}
    return pages
