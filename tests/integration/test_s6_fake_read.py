"""Fake-transport read: role-aware pipeline over fixture PDFs, 0 providers."""

from __future__ import annotations

from pathlib import Path

from invoice_referee.domain.evidence import SourceRef
from invoice_referee.evidence.pipeline import read_root_role_aware
from invoice_referee.evidence.trace import RunBudget
from tests.s6_transport import (
    FakeLLM,
    FakeReader,
    build_fake_ocr_pages,
    fixture_docs,
    llm_payloads,
    make_fixture_pdfs,
    sha256_file,
)


async def _read(
    tmp_path: Path,
    *,
    consistent_parties: bool = False,
    parts_total: int = 2700000,
    labor_total: int = 1500000,
    variant: str = "M",
):
    specs = fixture_docs(
        consistent_parties=consistent_parties,
        variant=variant,
        parts_total=parts_total,
        labor_total=labor_total,
    )
    outdir = tmp_path / "pdfs"
    outdir.mkdir()
    pdfs = make_fixture_pdfs(outdir, specs)
    digests = {name: sha256_file(path) for name, path in pdfs.items()}
    sources, payloads = [], {}
    roles = {
        "paper": "paper",
        "invoice": "evidence",
        "acceptance": "evidence",
        "transfer": "evidence",
    }
    for name, path in pdfs.items():
        sources.append(
            SourceRef(
                id=f"source:{name}",
                digest=digests[name],
                tenant="t",
                media="PDF",
                storage_key=f"k/{name}",
                filename=f"{name}.pdf",
                upload_role=roles[name],  # type: ignore[arg-type]
            )
        )
        payloads[f"source:{name}"] = path.read_bytes()
    reader = FakeReader(build_fake_ocr_pages(specs, digests))
    report = await read_root_role_aware(
        sources=tuple(sources),
        reader=reader,
        classifier=FakeLLM(llm_payloads(specs)),
        artifacts=None,
        source_bytes=payloads,
        budget=RunBudget(),
        provider_mode="RECORDED_REPLAY",
        root_id="root:1",
        activity_profile="WORK_EXPENSE",
    )
    return report, reader


async def test_fake_read_yields_tc18_shaped_documents(tmp_path: Path) -> None:
    report, _ = await _read(tmp_path)
    by_type = {}
    for doc in report.documents:
        by_type.setdefault(doc.document_type, []).append(doc)
    assert set(by_type) >= {
        "SETTLEMENT_FORM",
        "E_INVOICE",
        "ACCEPTANCE_RECORD",
        "PAYMENT_PROOF",
    }, [d.document_type for d in report.documents]
    paper = by_type["SETTLEMENT_FORM"][0]
    assert len([line for line in paper.line_items]) == 2
    labor = next(
        line
        for line in paper.line_items
        if any(
            f.field == "description" and f.value == "Nhân công sửa chữa"
            for f in line.fields
        )
    )
    refs = next(f.value for f in labor.fields if f.field == "invoice_refs")
    assert set(refs) == {"BBNT-181026-02", "FT262918104578"}
    transfer = by_type["PAYMENT_PROOF"][0]
    amount = next(f for f in transfer.fields if f.field == "amount")
    assert amount.value == "1500000" or int(str(amount.value)) == 1_500_000
    # The boxed amount block flows into the field ref (OCR region view).
    assert amount.refs and amount.refs[0].bbox is not None
    assert report.provider_mode == "RECORDED_REPLAY"


async def test_fake_read_has_no_provider_problems(tmp_path: Path) -> None:
    report, _ = await _read(tmp_path)
    assert not [p for p in report.problems if p.kind == "TECHNICAL"], report.problems


async def test_scaled_self_expense_variant_reads_clean(tmp_path: Path) -> None:
    report, _ = await _read(
        tmp_path,
        consistent_parties=True,
        parts_total=2700000,
        labor_total=1000000,
        variant="S",
    )
    by_type = {d.document_type: d for d in report.documents}
    assert by_type["PAYMENT_PROOF"].profile_status == "CLEAR"
    assert by_type["ACCEPTANCE_RECORD"].profile_status == "CLEAR"
    labor_amount = next(
        f for f in by_type["PAYMENT_PROOF"].fields if f.field == "amount"
    )
    assert int(str(labor_amount.value)) == 1_000_000


async def test_fake_confidence_review_is_assessed_not_technical(tmp_path: Path) -> None:
    report, _ = await _read(tmp_path)
    transfer = next(d for d in report.documents if d.document_type == "PAYMENT_PROOF")
    assert transfer.profile_status == "CLEAR", transfer.profile_findings
    # The boxed amount word keeps its source bbox for the region view.
    amount = next(f for f in transfer.fields if f.field == "amount")
    assert amount.refs and amount.refs[0].bbox is not None
