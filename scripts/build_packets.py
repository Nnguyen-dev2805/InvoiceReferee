"""Generate the raw evaluation packets (contracts §7, §11; plan T4).

Produces development (15 travel roots) and holdout (20 roots: 10 routine + 10
human) datasets, each root a three-layer packet: input/ (raw + organization +
submission), gold/ (latent + observable + allowed) and a dataset manifest.

PDFs are built with ReportLab + a bundled Noto Sans (Vietnamese glyphs); scans
are rendered with pypdfium2 into image-only PDFs whose numeric text is stripped
so no hidden seed truth rides along. Nothing here is measured against a model;
this only creates the frozen inputs/gold before the M0 baseline.

Usage:
    uv run python scripts/build_packets.py --out data/evaluation
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from invoice_referee.evaluation.models import (
    ManifestEntry,
    PacketMetadata,
    Split,
    Strata,
)
from invoice_referee.evaluation.packets import digest_packet_input, write_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "NotoSans-Regular.ttf"
FROZEN_AT = "2026-10-13T03:00:00+00:00"


@dataclass(frozen=True)
class RootSpec:
    """One evaluation root: its strata, grouping axes and gold outcome."""

    slug: str
    strata: Strata
    profile: str
    economic_key: str
    family: str
    template: str
    layout: str
    issuer: str
    route: str
    latent: dict[str, object] = field(default_factory=dict)
    observable: dict[str, object] = field(default_factory=dict)
    expected_amounts: dict[str, int] = field(default_factory=dict)
    owner: str | None = None
    scan: bool = False
    # STUB hand-transcription facts (contracts §5); the runner seeds these so a
    # STUB run assesses real input without a provider.
    facts: tuple[dict[str, object], ...] = ()


# 15 development travel roots — distinct sources/roots (mutations don't count).
def _facts(incurred, *, paid_employee=0, paid_company=0, advance=0, coverage=True, key=None):
    out = [{"field": "incurred", "value": incurred, "role": "INVOICE", "quote": f"Tổng chi {incurred}"}]
    if paid_employee:
        out.append({"field": "paid_employee", "value": paid_employee, "role": "PAYMENT", "quote": f"Nhân viên trả {paid_employee}"})
    if paid_company:
        out.append({"field": "paid_company", "value": paid_company, "role": "PAYMENT", "quote": f"Công ty trả {paid_company}"})
    if advance:
        out.append({"field": "advance", "value": advance, "role": "ADVANCE", "quote": f"Ứng {advance}"})
    if coverage:
        out.append({"field": "coverage", "value": 1, "role": "LEDGER", "quote": "Đối chiếu đủ giai đoạn"})
    if key:
        out.append({"field": "economic_key", "value": key, "role": "INVOICE", "quote": key})
    return tuple(out)


DEVELOPMENT: tuple[RootSpec, ...] = (
    RootSpec("dev-clean-chi", "routine", "TRAVEL", "inv:dev:01", "fam:chi", "tpl:chi", "lay:a", "iss:vn-air", "AUTO",
             observable={"amount": 3_000_000}, expected_amounts={"PAY": 3_000_000},
             facts=_facts(8_000_000, paid_employee=5_000_000, paid_company=3_000_000, advance=2_000_000, key="inv:dev:01")),
    RootSpec("dev-clean-thu", "routine", "TRAVEL", "inv:dev:02", "fam:thu", "tpl:thu", "lay:b", "iss:hotel-b", "AUTO",
             observable={"amount": 1_500_000}, expected_amounts={"COLLECT": 500_000},
             facts=_facts(1_500_000, paid_employee=1_500_000, advance=2_000_000, key="inv:dev:02")),
    RootSpec("dev-balanced", "routine", "TRAVEL", "inv:dev:03", "fam:bal", "tpl:bal", "lay:c", "iss:taxi-c", "AUTO",
             observable={"amount": 2_000_000},
             facts=_facts(2_000_000, paid_employee=2_000_000, advance=2_000_000, key="inv:dev:03")),
    RootSpec("dev-payer-unknown", "FACT", "TRAVEL", "inv:dev:04", "fam:unk", "tpl:unk", "lay:a", "iss:misc-d", "FACT",
             owner="employee", facts=_facts(5_000_000, key="inv:dev:04")),
    RootSpec("dev-relation-conflict", "FACT", "TRAVEL", "inv:dev:05", "fam:rel", "tpl:rel", "lay:b", "iss:hotel-e", "FACT",
             owner="accountant", facts=_facts(5_000_000, paid_employee=5_000_000, coverage=False, key="inv:dev:05")),
    RootSpec("dev-over-budget", "POLICY", "TRAVEL", "inv:dev:06", "fam:over", "tpl:over", "lay:c", "iss:venue-f", "POLICY",
             observable={"T": 10_000_000, "B": 8_000_000}, owner="approver",
             facts=_facts(10_000_000, paid_employee=10_000_000, key="inv:dev:06")),
    RootSpec("dev-cost-authority", "AUTHORITY", "TRAVEL", "inv:dev:07", "fam:auth", "tpl:auth", "lay:a", "iss:air-g", "AUTHORITY",
             observable={"E": 12_000_000}, owner="approver",
             facts=_facts(12_000_000, paid_employee=12_000_000, key="inv:dev:07")),
    RootSpec("dev-action-authority", "AUTHORITY", "TRAVEL", "inv:dev:08", "fam:auth2", "tpl:auth2", "lay:b", "iss:rail-h", "AUTHORITY",
             observable={"S": 6_000_000}, owner="approver",
             facts=_facts(8_000_000, paid_employee=8_000_000, advance=2_000_000, key="inv:dev:08")),
    RootSpec("dev-missing-history", "FACT", "TRAVEL", "inv:dev:09", "fam:hist", "tpl:hist", "lay:c", "iss:hotel-i", "FACT",
             owner="accountant", facts=_facts(5_000_000, paid_employee=5_000_000, coverage=False, key="inv:dev:09")),
    RootSpec("dev-duplicate", "FACT", "TRAVEL", "inv:dev:10", "fam:dup", "tpl:dup", "lay:a", "iss:misc-j", "FACT",
             owner="accountant", facts=_facts(5_000_000, paid_employee=5_000_000, coverage=False, key="inv:dev:10")),
    RootSpec("dev-personal", "routine", "TRAVEL", "inv:dev:11", "fam:per", "tpl:per", "lay:b", "iss:shop-k", "AUTO",
             observable={"excluded": 500_000},
             facts=_facts(2_000_000, paid_employee=2_000_000, advance=2_000_000, key="inv:dev:11")),
    RootSpec("dev-material-unsupported", "TECHNICAL", "TRAVEL", "inv:dev:12", "fam:uns", "tpl:uns", "lay:c", "iss:fx-l", "UNSUPPORTED",
             owner="accountant", facts=_facts(5_000_000, paid_employee=5_000_000, coverage=False, key="inv:dev:12")),
    RootSpec("dev-pending-bank", "FACT", "TRAVEL", "inv:dev:13", "fam:bank", "tpl:bank", "lay:a", "iss:bank-m", "FACT",
             owner="accountant", facts=_facts(5_000_000, paid_employee=5_000_000, coverage=False, key="inv:dev:13")),
    RootSpec("dev-mixed-pdf", "routine", "TRAVEL", "inv:dev:14", "fam:mix", "tpl:mix", "lay:b", "iss:multi-n", "AUTO",
             observable={"amount": 4_500_000}, scan=True,
             facts=_facts(4_500_000, paid_employee=4_500_000, advance=4_500_000, key="inv:dev:14")),
    RootSpec("dev-supplementary", "routine", "TRAVEL", "inv:dev:15", "fam:sup", "tpl:sup", "lay:c", "iss:hotel-o", "AUTO",
             observable={"T": 10_000_000, "E": 7_000_000, "C": 3_000_000}, expected_amounts={"PAY": 4_000_000},
             facts=_facts(10_000_000, paid_employee=7_000_000, paid_company=3_000_000, advance=3_000_000, key="inv:dev:15")),
)


def _holdout() -> tuple[RootSpec, ...]:
    specs: list[RootSpec] = []
    for i in range(1, 11):
        specs.append(
            RootSpec(f"hold-routine-{i:02d}", "routine", "TRAVEL", f"inv:hold:r{i:02d}",
                     f"fam:hr{i:02d}", f"tpl:hr{i:02d}", "lay:a", f"iss:hr{i:02d}", "AUTO",
                     observable={"amount": 1_000_000 * i})
        )
    # 10 human-required: FACT4 / POLICY3 / AUTHORITY3.
    for i in range(1, 5):
        specs.append(RootSpec(f"hold-fact-{i:02d}", "FACT", "TRAVEL", f"inv:hold:f{i:02d}",
                              f"fam:hf{i:02d}", f"tpl:hf{i:02d}", "lay:b", f"iss:hf{i:02d}", "FACT",
                              owner="employee" if i % 2 else "accountant"))
    for i in range(1, 4):
        specs.append(RootSpec(f"hold-policy-{i:02d}", "POLICY", "TRAVEL", f"inv:hold:p{i:02d}",
                              f"fam:hp{i:02d}", f"tpl:hp{i:02d}", "lay:c", f"iss:hp{i:02d}", "POLICY",
                              owner="approver", observable={"T": 9_000_000, "B": 8_000_000}))
    for i in range(1, 4):
        specs.append(RootSpec(f"hold-auth-{i:02d}", "AUTHORITY", "TRAVEL", f"inv:hold:a{i:02d}",
                              f"fam:ha{i:02d}", f"tpl:ha{i:02d}", "lay:a", f"iss:ha{i:02d}", "AUTHORITY",
                              owner="approver", observable={"E": 9_000_000 + i * 100_000}))
    return tuple(specs)


HOLDOUT: tuple[RootSpec, ...] = _holdout()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_text_pdf(path: Path, lines: list[str]) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(TTFont("NotoSans", str(FONT_PATH)))
    canvas_obj = canvas.Canvas(str(path), pagesize=A4)
    canvas_obj.setFont("NotoSans", 12)
    y = A4[1] - 60
    for line in lines:
        canvas_obj.drawString(60, y, line)
        y -= 22
    canvas_obj.showPage()
    canvas_obj.save()


def _make_scan_pdf(path: Path) -> None:
    """Render a text page to an image-only PDF (no hidden text layer)."""
    import io

    import pypdfium2 as pdfium
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    # 1. Build the source page as a normal PDF.
    tmp = path.with_suffix(".src.pdf")
    pdfmetrics.registerFont(TTFont("NotoSans", str(FONT_PATH)))
    c = canvas.Canvas(str(tmp), pagesize=A4)
    c.setFont("NotoSans", 14)
    c.drawString(60, A4[1] - 80, "HÓA ĐƠN GIÁ TRỊ GIA TĂNG")
    c.drawString(60, A4[1] - 110, "Số tiền: 4.500.000 VND")
    c.drawString(60, A4[1] - 140, "Người thanh toán: Ẩn")
    c.showPage()
    c.save()

    # 2. Render to a bitmap and embed it as an image-only page.
    pdf = pdfium.PdfDocument(str(tmp))
    page = pdf[0]
    bitmap = page.render(scale=2.0)
    image = bitmap.to_pil()

    img_path = path.with_suffix(".png")
    image.save(img_path, "PNG")
    from reportlab.lib.utils import ImageReader

    c2 = canvas.Canvas(str(path), pagesize=A4)
    c2.drawImage(ImageReader(str(img_path)), 0, 0, width=A4[0], height=A4[1])
    c2.showPage()
    c2.save()

    tmp.unlink(missing_ok=True)
    img_path.unlink(missing_ok=True)


def build_root(base: Path, spec: RootSpec) -> ManifestEntry:
    packet = base / spec.slug
    input_dir = packet / "input"
    sources_dir = input_dir / "sources"
    gold_dir = packet / "gold"
    sources_dir.mkdir(parents=True, exist_ok=True)
    gold_dir.mkdir(parents=True, exist_ok=True)

    (input_dir / "organization.json").write_text(
        json.dumps(
            {
                "tenant": "tenant:demo",
                "profile": spec.profile,
                "records": [
                    "ledger:opening:2026-09 — số dư theo dõi 0 VND",
                    "ledger:coverage:2026-10 — đối chiếu đủ giai đoạn",
                    "budget — 8.000.000 VND (hiệu lực 01/10/2026)",
                ],
                "budget_amount": 8_000_000,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # STUB hand-transcription (input layer, contracts §5): a literal reading the
    # runner seeds so a STUB run assesses real input without a provider.
    (input_dir / "transcription.json").write_text(
        json.dumps(
            {
                "data_origin": "STUB_TRANSCRIPTION",
                "facts": [
                    {
                        "field": f["field"],
                        "value": f["value"],
                        "role": f.get("role", "INVOICE"),
                        "page": 1,
                        "quote": f.get("quote", "hand-transcription"),
                    }
                    for f in spec.facts
                ],
                "relations": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (input_dir / "submission.json").write_text(
        json.dumps(
            {
                "employee": "employee:employee-a",
                "activity": f"activity:{spec.slug}",
                "declared_purpose": f"Hoạt động {spec.slug}",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # No seed truth in the filename, metadata, or the document body: the slug
    # names the scenario (e.g. "dev-over-budget") and must never appear in a
    # source a model reads.
    pdf_name = "chung-tu.pdf"
    pdf_path = sources_dir / pdf_name
    if spec.scan:
        _make_scan_pdf(pdf_path)
    else:
        _make_text_pdf(
            pdf_path,
            [
                "HÓA ĐƠN / CHỨNG TỪ",
                "Đơn vị cung cấp: Công ty Demo",
                "Nội dung: Chi phí phục vụ hoạt động",
                "Ngày: 05/10/2026",
            ],
        )

    (gold_dir / "latent.json").write_text(
        json.dumps({"facts": spec.latent}, ensure_ascii=False), encoding="utf-8"
    )
    (gold_dir / "observable.json").write_text(
        json.dumps({"facts": spec.observable}, ensure_ascii=False), encoding="utf-8"
    )
    (gold_dir / "allowed.json").write_text(
        json.dumps(
            {
                "route": spec.route,
                "expected_amounts": spec.expected_amounts,
                "owner": spec.owner,
                "question_required": spec.route in ("FACT", "POLICY", "AUTHORITY"),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return ManifestEntry(
        root_id=spec.slug,
        split="development",
        strata=spec.strata,
        profile=spec.profile,
        economic_key=spec.economic_key,
        family=spec.family,
        template=spec.template,
        layout=spec.layout,
        issuer=spec.issuer,
        input_digest=digest_packet_input(packet),
        gold_digest=_sha256((gold_dir / "latent.json").read_bytes()),
    )


def build_split(base: Path, specs: tuple[RootSpec, ...], split: Split) -> PacketMetadata:
    entries: list[ManifestEntry] = []
    for spec in specs:
        entry = build_root(base, spec)
        entries.append(entry.model_copy(update={"split": split}))
    return PacketMetadata(dataset=f"invoice-referee-{split}", frozen_at=FROZEN_AT, entries=tuple(entries))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build InvoiceReferee evaluation packets")
    parser.add_argument("--out", default=str(PROJECT_ROOT / "data" / "evaluation"))
    args = parser.parse_args(argv)
    out = Path(args.out)

    dev_dir = out / "development"
    dev_meta = build_split(dev_dir, DEVELOPMENT, "development")
    write_manifest(dev_dir / "manifest.json", dev_meta)

    hold_dir = out / "holdout"
    hold_meta = build_split(hold_dir, HOLDOUT, "holdout")
    write_manifest(hold_dir / "manifest.json", hold_meta)

    print(f"development: {len(dev_meta.entries)} roots -> {dev_dir}")
    print(f"holdout: {len(hold_meta.entries)} roots -> {hold_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
