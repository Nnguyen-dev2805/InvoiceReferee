"""Role-aware workflow: persistence, partial technical handling, resume (16/10/2026)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tests.factories import clear_ocr_page

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import (
    ActivityData,
    AttachSources,
    CreateDraft,
    Declaration,
    SourceUpload,
    Submit,
)
from invoice_referee.domain.documents import OcrSourceResult
from invoice_referee.evidence.reader import FileOcrReader
from invoice_referee.evidence.trace import RunBudget
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

PAPER_MD = (
    "GIẤY QUYẾT TOÁN\nNgười đề nghị: NGUYEN VAN A\n"
    "Di chuyển nội thành 900000 ref PT-251026-016\nTổng cộng: 900000\nTạm ứng: 1000000"
)
RECEIPT_MD = (
    "PHIẾU THU\nSố phiếu: PT-251026-016\nNgười nộp: NGUYEN VAN A\n"
    "Số tiền: 700000\nĐã nhận đủ số tiền"
)


class FakeOcrProvider:
    def __init__(self, texts: dict[str, str]) -> None:
        self.texts = texts
        self.calls = 0

    async def ocr_file(
        self,
        source,
        *,
        budget,
        artifacts,
        source_bytes,
        expected_pages=None,
        root_id="",
    ):
        self.calls += 1
        budget.charge_ocr()
        return OcrSourceResult(
            source_id=source.id,
            source_digest=source.digest,
            provider="fake",
            model="m",
            pages=(clear_ocr_page(self.texts[source.id]),),
        )


class RoleFake:
    def __init__(self) -> None:
        self.systems: list[str] = []
        self.paper_calls = 0
        self.evidence_calls = 0

    async def complete_json(self, *, system: str, user: str, budget: RunBudget) -> dict:
        import json

        budget.charge_llm()
        self.systems.append(system)
        if "role 'paper'" in system:
            self.paper_calls += 1
            return {
                "fields": [
                    {
                        "field": "declared_name",
                        "state": "FOUND",
                        "value": "NGUYEN VAN A",
                        "quote": "Người đề nghị: NGUYEN VAN A",
                        "page": 1,
                    },
                    {
                        "field": "printed_total",
                        "state": "FOUND",
                        "value": "900000",
                        "quote": "Tổng cộng: 900000",
                        "page": 1,
                    },
                    {
                        "field": "declared_advance",
                        "state": "FOUND",
                        "value": "1000000",
                        "quote": "Tạm ứng: 1000000",
                        "page": 1,
                    },
                ],
                "line_items": [
                    {
                        "fields": [
                            {
                                "field": "description",
                                "state": "FOUND",
                                "value": "Di chuyển nội thành",
                                "quote": "Di chuyển nội thành 900000 ref PT-251026-016",
                                "page": 1,
                            },
                            {
                                "field": "amount",
                                "state": "FOUND",
                                "value": "900000",
                                "quote": "Di chuyển nội thành 900000 ref PT-251026-016",
                                "page": 1,
                            },
                            {
                                "field": "invoice_refs",
                                "state": "FOUND",
                                "value": ["PT-251026-016"],
                                "quote": "Di chuyển nội thành 900000 ref PT-251026-016",
                                "page": 1,
                            },
                        ]
                    }
                ],
                "role_fit": "FIT",
                "actual_type": "SETTLEMENT_FORM",
                "role_note": "",
            }
        if "role 'evidence'" in system:
            self.evidence_calls += 1
            return {
                "document_type": "COLLECTION_RECEIPT",
                "fields": [
                    {
                        "field": "document_number",
                        "state": "FOUND",
                        "value": "PT-251026-016",
                        "quote": "Số phiếu: PT-251026-016",
                        "page": 1,
                    },
                    {
                        "field": "total_amount",
                        "state": "FOUND",
                        "value": "700000",
                        "quote": "Số tiền: 700000",
                        "page": 1,
                    },
                ],
                "line_items": [],
            }
        raise AssertionError("no standalone classification on the role-aware path")


def _workflow(tmp_path: Path) -> CaseWorkflow:
    db = Database(tmp_path / "r.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "up")
    wf.import_demo_context(
        Path("tests/fixtures/legacy-company-context.json"), origin="SIMULATED"
    )
    return wf


def _ctx(wf: CaseWorkflow, command_id: str, version: int = 1) -> CommandContext:
    session = wf.start_session(
        tenant="tenant:demo", persona="employee", actor_id="employee:employee-a"
    )
    return CommandContext(
        session_id=session.session_id,
        actor_id="employee:employee-a",
        command_id=command_id,
        expected_case_version=version,
    )


async def _root_with_roles(
    wf: CaseWorkflow, activity: str = "activity:travel-a"
) -> str:
    created = await wf.execute(
        _ctx(wf, f"cmd:create:{activity}"),
        CreateDraft(
            activity_data=ActivityData(
                activity_id=activity,
                name=activity,
                occurred_at=datetime(2026, 10, 1, tzinfo=UTC),
                declared_purpose="Công tác",
            )
        ),
    )
    root = created.case_view.id
    uploads = []
    for filename, role in (("paper.pdf", "paper"), ("receipt.pdf", "evidence")):
        storage_key = f"tenant:demo/{root}/{filename}"
        stored = wf.uploads_dir / storage_key
        stored.parent.mkdir(parents=True, exist_ok=True)
        stored.write_bytes(b"%PDF-1.4 evidence")
        import hashlib

        digest = hashlib.sha256(b"%PDF-1.4 evidence" + filename.encode()).hexdigest()
        uploads.append(
            SourceUpload(
                filename=filename,
                media="PDF",
                digest=digest,
                storage_key=storage_key,
                upload_role=role,  # type: ignore[arg-type]
            )
        )
    await wf.execute(
        _ctx(wf, f"cmd:attach:{root}", version=wf.view(_ctx(wf, "r"), root).version),
        AttachSources(root_id=root, uploads=tuple(uploads)),
    )
    return root


def _wire(
    wf: CaseWorkflow, tmp_path: Path, fake: RoleFake, texts: dict[str, str]
) -> None:
    wf.enable_evidence_read(
        reader=FileOcrReader(provider=FakeOcrProvider(texts)),
        classifier=fake,
        artifacts_root=tmp_path / "artifacts",
        provider_mode="LIVE",
    )


async def _submit(wf: CaseWorkflow, root: str, command_id: str):
    return await wf.execute(
        _ctx(wf, command_id, version=wf.view(_ctx(wf, "r2"), root).version),
        Submit(
            root_id=root,
            declaration=Declaration(
                activity_id="activity:travel-a", declared_purpose="Công tác"
            ),
        ),
    )


async def test_upload_roles_persist_and_survive_restart(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root = await _root_with_roles(wf)
    with wf.db.connect() as cx:
        roles = {
            str(r["filename"]): str(r["upload_role"])
            for r in cx.execute(
                "SELECT filename, upload_role FROM case_sources WHERE root_id = ?",
                (root,),
            )
        }
    assert roles == {"paper.pdf": "paper", "receipt.pdf": "evidence"}
    # Restart: a new workflow on the same DB sees the same roles.
    wf2 = CaseWorkflow(Database(tmp_path / "r.sqlite"), uploads_dir=tmp_path / "up")
    with wf2.db.connect() as cx:
        jobs = cx.execute("SELECT id FROM jobs LIMIT 1").fetchall()
    assert jobs == []  # no job yet; context load below needs a job id
    from invoice_referee.workflow.jobs import JobStore

    with wf2.db.transaction() as cx:
        job_id = JobStore(wf2.db).enqueue(
            cx, tenant="tenant:demo", root_id=root, kind="SUBMIT", now=wf2._now_iso()
        )
    context = wf2._evidence_context(job_id)
    assert context is not None
    _, _, sources, _, _ = context
    assert {s.filename: s.upload_role for s in sources} == {
        "paper.pdf": "paper",
        "receipt.pdf": "evidence",
    }


async def test_role_aware_submit_needs_no_standalone_classify(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root = await _root_with_roles(wf)
    source_ids = [
        r["source_id"]
        for r in wf.db.connect().execute(
            "SELECT source_id FROM case_sources WHERE root_id = ? ORDER BY filename",
            (root,),
        )
    ]
    texts = {source_ids[0]: PAPER_MD, source_ids[1]: RECEIPT_MD}
    fake = RoleFake()
    _wire(wf, tmp_path, fake, texts)
    await _submit(wf, root, "cmd:submit")
    await wf.run_evidence_job_for(root)
    view = wf.view(_ctx(wf, "r3"), root)
    assert view.evidence_report is not None
    assert {d.document_type for d in view.evidence_report.documents} == {
        "SETTLEMENT_FORM",
        "COLLECTION_RECEIPT",
    }
    assert not any("classify documents" in s.lower() for s in fake.systems)
    assert fake.paper_calls == 1 and fake.evidence_calls == 1


async def test_partial_budget_is_technical_no_money_no_fake_fact(
    tmp_path: Path, monkeypatch
) -> None:
    import invoice_referee.workflow.evidence_jobs as jobs_mod

    real_budget = jobs_mod.RunBudget

    def _one_call(*args, **kwargs):
        budget = real_budget(*args, **kwargs)
        budget.max_llm_attempts = 1
        return budget

    monkeypatch.setattr(jobs_mod, "RunBudget", _one_call)
    wf = _workflow(tmp_path)
    root = await _root_with_roles(wf)
    source_ids = [
        r["source_id"]
        for r in wf.db.connect().execute(
            "SELECT source_id FROM case_sources WHERE root_id = ? ORDER BY filename",
            (root,),
        )
    ]
    fake = RoleFake()
    _wire(wf, tmp_path, fake, {source_ids[0]: PAPER_MD, source_ids[1]: RECEIPT_MD})
    await _submit(wf, root, "cmd:submit")
    await wf.run_evidence_job_for(root)
    view = wf.view(_ctx(wf, "r3"), root)
    assert view.state == "TECHNICAL_ERROR"
    assert view.instructions == ()
    problems = list(view.evidence_report.problems) if view.evidence_report else []
    assert any(
        p.kind == "TECHNICAL" and p.blocking and p.next_action == "resume_extraction"
        for p in problems
    )
    # No fake missing-source FACT and no money effect.
    assert not any(
        i.kind == "FACT" and "thiếu chứng từ" in (i.basis or "") for i in view.issues
    )


async def test_resume_completes_missing_without_rereading_done(
    tmp_path: Path, monkeypatch
) -> None:
    import invoice_referee.workflow.evidence_jobs as jobs_mod

    real_budget = jobs_mod.RunBudget
    calls = {"n": 0}

    def _one_call(*args, **kwargs):
        budget = real_budget(*args, **kwargs)
        if calls["n"] == 0:
            budget.max_llm_attempts = 1
        return budget

    monkeypatch.setattr(jobs_mod, "RunBudget", _one_call)
    wf = _workflow(tmp_path)
    root = await _root_with_roles(wf)
    source_ids = [
        r["source_id"]
        for r in wf.db.connect().execute(
            "SELECT source_id FROM case_sources WHERE root_id = ? ORDER BY filename",
            (root,),
        )
    ]
    fake = RoleFake()
    _wire(wf, tmp_path, fake, {source_ids[0]: PAPER_MD, source_ids[1]: RECEIPT_MD})
    await _submit(wf, root, "cmd:submit")
    await wf.run_evidence_job_for(root)
    assert wf.view(_ctx(wf, "r3"), root).state == "TECHNICAL_ERROR"
    calls["n"] = 1
    await _submit(wf, root, "cmd:submit2")
    await wf.run_evidence_job_for(root)
    view = wf.view(_ctx(wf, "r4"), root)
    assert view.evidence_report is not None
    assert {d.document_type for d in view.evidence_report.documents} == {
        "SETTLEMENT_FORM",
        "COLLECTION_RECEIPT",
    }
    # Paper was checkpointed: exactly one paper extraction across both passes.
    assert fake.paper_calls == 1
    assert fake.evidence_calls == 1
    assert view.state != "TECHNICAL_ERROR"


async def test_docx_attach_and_read_end_to_end(tmp_path: Path) -> None:
    import hashlib
    import io
    import zipfile
    from datetime import UTC, datetime

    from invoice_referee.domain.commands import (
        ActivityData,
        AttachSources,
        CreateDraft,
        SourceUpload,
    )
    from invoice_referee.evidence.reader import FileOcrReader

    wf = _workflow(tmp_path)
    created = await wf.execute(
        _ctx(wf, "cmd:create:docx"),
        CreateDraft(
            activity_data=ActivityData(
                activity_id="activity:travel-docx",
                name="activity:travel-docx",
                occurred_at=datetime(2026, 10, 1, tzinfo=UTC),
                declared_purpose="Công tác",
            )
        ),
    )
    root = created.case_view.id
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("[Content_Types].xml", "<Types/>")
        handle.writestr(
            "word/document.xml",
            '<?xml version="1.0"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Tổng cộng: 900000</w:t></w:r></w:p></w:body></w:document>",
        )
    data = buffer.getvalue()
    from invoice_referee.api.routes import _sniff_media

    assert _sniff_media(data, "report.docx") == "DOCX"
    storage_key = f"tenant:demo/{root}/report.docx"
    stored = wf.uploads_dir / storage_key
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    await wf.execute(
        _ctx(wf, "cmd:attach:docx", version=wf.view(_ctx(wf, "r"), root).version),
        AttachSources(
            root_id=root,
            uploads=(
                SourceUpload(
                    filename="report.docx",
                    media="DOCX",
                    digest=digest,
                    storage_key=storage_key,
                    upload_role="paper",
                ),
            ),
        ),
    )
    with wf.db.connect() as cx:
        media = cx.execute(
            "SELECT media FROM case_sources WHERE root_id = ?", (root,)
        ).fetchone()["media"]
    assert media == "DOCX"

    class ExplodingProvider:
        async def ocr_file(self, *args, **kwargs):
            raise AssertionError("must not reach the OCR provider")

    wf.enable_evidence_read(
        reader=FileOcrReader(provider=ExplodingProvider()),
        classifier=RoleFake(),
        artifacts_root=tmp_path / "artifacts",
        provider_mode="LIVE",
    )
    draft = await wf.read_settlement_draft(
        wf.start_session(
            tenant="tenant:demo", persona="employee", actor_id="employee:employee-a"
        ),
        root,
        (),
    )
    assert draft["processing_status"] in ("ready", "needs_supplement")
