"""S6 digital intake at the workflow boundary: save -> read -> submit."""

from __future__ import annotations

from pathlib import Path

import pytest

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import (
    ActivityData,
    AttachSources,
    CreateDraft,
    Declaration,
    SourceUpload,
    Submit,
)
from invoice_referee.evidence.trace import RunBudget
from invoice_referee.workflow.service import UnsupportedCommandError
from tests.s6_seeding import (
    ACTIVITY,
    AS_OF,
    EMPLOYEE,
    TENANT,
    _context,
    _workflow,
)
from tests.s6_transport import (
    FakeLLM,
    FakeReader,
    build_fake_ocr_pages,
    fixture_docs,
    llm_payloads,
    make_fixture_pdfs,
    sha256_file,
)

ACTOR = EMPLOYEE


def _wired(tmp_path: Path, **ctx_kw):
    wf = _workflow(tmp_path, **ctx_kw)
    specs = fixture_docs(consistent_parties=True, variant="C")
    pdfdir = tmp_path / "pdfs"
    pdfdir.mkdir()
    pdfs = make_fixture_pdfs(pdfdir, specs)
    digests = {n: sha256_file(p) for n, p in pdfs.items()}
    wf.enable_evidence_read(
        reader=FakeReader(build_fake_ocr_pages(specs, digests)),
        classifier=FakeLLM(llm_payloads(specs)),
        artifacts_root=tmp_path / "artifacts",
        provider_mode="RECORDED_REPLAY",
    )
    return wf, pdfs


async def _case_with_evidence(wf, pdfs: dict) -> tuple[str, object, dict[str, str]]:
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=ACTOR)
    created = await wf.execute(
        CommandContext(
            session_id=session.session_id,
            actor_id=ACTOR,
            command_id="cmd:1",
            expected_case_version=0,
        ),
        CreateDraft(
            activity_data=ActivityData(
                activity_id=ACTIVITY,
                name="a",
                occurred_at="2026-10-06T09:00:00+07:00",
                declared_purpose="p",
            )
        ),
    )
    root = created.case_view.id
    uploads, version = [], created.case_view.version
    ids: dict[str, str] = {}
    for name in ("invoice", "acceptance", "transfer"):
        data = pdfs[name].read_bytes()
        storage_key = f"{TENANT}/{root}/{name}.pdf"
        (wf.uploads_dir / storage_key).parent.mkdir(parents=True, exist_ok=True)
        (wf.uploads_dir / storage_key).write_bytes(data)
        uploads.append(
            SourceUpload(
                filename=f"{name}.pdf",
                media="PDF",
                digest=sha256_file(pdfs[name]),
                storage_key=storage_key,
                upload_role="evidence",
            )
        )
    result = await wf.execute(
        CommandContext(
            session_id=session.session_id,
            actor_id=ACTOR,
            command_id="cmd:2",
            expected_case_version=version,
        ),
        AttachSources(root_id=root, uploads=tuple(uploads)),
    )
    for source in result.case_view.sources:
        ids[source.filename.replace(".pdf", "")] = source.id
    return root, session, ids


def _declaration(ids: dict[str, str], **over) -> dict:
    base = {
        "declared_purpose": "Sửa chữa máy in",
        "settlement_type": "EMPLOYEE_REIMBURSEMENT",
        "digital_lines": [
            {
                "item_id": "L01",
                "description": "Mua linh kiện máy in",
                "expense_date": "2026-10-08",
                "amount": 2700000,
                "evidence_status": "ORIGINAL",
                "source_ids": [ids["invoice"]],
            },
            {
                "item_id": "L02",
                "description": "Nhân công sửa chữa",
                "expense_date": "2026-10-09",
                "amount": 1500000,
                "evidence_status": "ALTERNATIVE",
                "alternative_type": "PAYMENT_PROOF",
                "exception_reason": "Nhà cung cấp không xuất hóa đơn",
                "note": "Biên bản nghiệm thu và chuyển khoản",
                "source_ids": [ids["acceptance"], ids["transfer"]],
            },
        ],
        "no_advance_asserted": True,
        "no_advance_reason": "Tự chi, không nhận ứng",
    }
    base.update(over)
    return base


async def _submit(wf, session, root: str, payload: dict, command_id: str):
    from invoice_referee.domain.commands import DigitalExpenseLine

    def _line(line: dict) -> DigitalExpenseLine:
        return DigitalExpenseLine(**{**line, "source_ids": tuple(line["source_ids"])})

    decl = Declaration(
        declared_purpose=payload["declared_purpose"],
        settlement_type=payload["settlement_type"],  # type: ignore[arg-type]
        submission_source="DIGITAL_FORM",  # type: ignore[arg-type]
        digital_lines=tuple(_line(line) for line in payload["digital_lines"]),
        no_advance_asserted=payload["no_advance_asserted"],
        no_advance_reason=payload["no_advance_reason"],
    )
    view = wf.view(
        CommandContext(
            session_id=session.session_id,
            actor_id=ACTOR,
            command_id=f"{command_id}:v",
            expected_case_version=0,
        ),
        root,
    )
    return await wf.execute(
        CommandContext(
            session_id=session.session_id,
            actor_id=ACTOR,
            command_id=command_id,
            expected_case_version=view.version,
        ),
        Submit(root_id=root, declaration=decl),
    )


async def test_digital_save_read_submit_roundtrip(tmp_path: Path) -> None:
    wf, pdfs = _wired(tmp_path)
    root, session, ids = await _case_with_evidence(wf, pdfs)
    payload = _declaration(ids)
    saved = wf.save_digital_declaration(session, root, payload)
    assert saved["revision"] == 1 and len(saved["canonical_hash"]) == 64
    draft = await wf.read_digital_draft(session, root)
    expenses = draft["expenses"]
    assert len(expenses) == 2
    labor = next(e for e in expenses if e["description"] == "Nhân công sửa chữa")
    assert labor["status"] == "ALTERNATIVE"
    assert labor["exception_reason"] == "Nhà cung cấp không xuất hóa đơn"
    assert len(labor["evidence_files"]) == 2
    assert draft["processing_status"] in ("ready", "needs_supplement")
    # Submit with the identical declaration is accepted for assessment.
    result = await _submit(wf, session, root, payload, "cmd:3")
    assert result.case_view.id == root


async def test_digital_submit_rejects_edited_declaration(tmp_path: Path) -> None:
    wf, pdfs = _wired(tmp_path)
    root, session, ids = await _case_with_evidence(wf, pdfs)
    wf.save_digital_declaration(session, root, _declaration(ids))
    await wf.read_digital_draft(session, root)
    tampered = _declaration(ids)
    tampered["digital_lines"][1]["amount"] = 1600000
    with pytest.raises(UnsupportedCommandError):
        await _submit(wf, session, root, tampered, "cmd:9")
