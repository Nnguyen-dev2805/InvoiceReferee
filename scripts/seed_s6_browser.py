"""Seed S6 browser fixtures: PDFs + replay pages/LLM + 4 context variants + DBs.

Deterministic, 0 provider calls. Everything lands under .runtime/s6-browser/.
Contexts are seed-only variants (SIMULATED labels kept); company-context.json
and the user DB are untouched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from s6_transport import (  # noqa: E402
    build_fake_ocr_pages,
    fixture_docs,
    llm_payloads,
    make_fixture_pdfs,
    sha256_file,
    write_llm_dir,
    write_pages_json,
)

OUT = ROOT / ".runtime" / "s6-browser"
BASE_CTX = json.loads(
    (
        ROOT
        / "data"
        / "demo"
        / "cases"
        / "tc18-hop-le-mot-dong-dung-hai-tai-lieu-thay-the"
        / "context.json"
    ).read_text(encoding="utf-8")
)


def _grant(actor: str, max_amount: int) -> dict:
    return {
        "id": f"grant:seed:{actor.split(':')[-1]}:except",
        "version": "seed-v1",
        "actor": actor,
        "actions": ["EXCEPT_POLICY"],
        "scope": "activity:tc18",
        "max_amount": max_amount,
        "effective_from": "2026-10-01T00:00:00+07:00",
        "effective_to": "2026-12-31T23:59:59+07:00",
    }


def main() -> None:
    pdf_dir = OUT / "pdfs"
    llm_dir = OUT / "fake-llm"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    specs_m = fixture_docs(consistent_parties=False, variant="M")
    specs_c = fixture_docs(consistent_parties=True, variant="C")
    # A2 is a synthetic clean self-expense case sized under the 4m self-issue
    # ceiling (E=3.7m): same shapes/refs, smaller labor. TC18 truth (2.7/1.5)
    # stays intact in the M/C sets, unit fixtures and dossier B.
    specs_s = fixture_docs(
        consistent_parties=True, variant="S", parts_total=2700000, labor_total=1000000
    )
    specs_s["paper"]["lines"] = [line.replace("Tạm ứng đã nhận: 5000000", "Tạm ứng đã nhận: 0") for line in specs_s["paper"]["lines"]]
    specs_s["_amounts"]["advance"] = "0"
    pdfs_m = make_fixture_pdfs(pdf_dir, specs_m)
    for name, path in list(pdfs_m.items()):
        path.rename(pdf_dir / f"{name}-mismatch.pdf")
    pdfs_m = {name: pdf_dir / f"{name}-mismatch.pdf" for name in pdfs_m}
    pdfs_c = make_fixture_pdfs(pdf_dir, specs_c)
    for name, path in list(pdfs_c.items()):
        if path.name == f"{name}.pdf":
            path.rename(pdf_dir / f"{name}-consistent.pdf")
    pdfs_c = {name: pdf_dir / f"{name}-consistent.pdf" for name in pdfs_c}
    pdfs_s = make_fixture_pdfs(pdf_dir, specs_s)
    for name, path in list(pdfs_s.items()):
        if path.name == f"{name}.pdf":
            path.rename(pdf_dir / f"{name}-self.pdf")
    pdfs_s = {name: pdf_dir / f"{name}-self.pdf" for name in pdfs_s}

    # UI execution fixtures are separate from employee -> supplier payment proof.
    payouts = {
        name: {"marker": f"FIXTURE-S6-PAYOUT-{name}", "lines": [
            "XÁC NHẬN CHUYỂN KHOẢN HOÀN CHI (MÔ PHỎNG)",
            "Người chuyển: CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
            "Người nhận: NGUYỄN MINH AN", f"Số tiền: {amount}",
            f"Mã giao dịch: {reference}", "Ngày giao dịch: 12/10/2026", "Trạng thái: Thành công",
        ]}
        for name,amount,reference in [("payout-partial",1000000,"FT-PAY-PARTIAL-01"),("payout-final",2700000,"FT-PAY-FINAL-02")]
    }
    make_fixture_pdfs(pdf_dir, payouts)

    digests = {f"M-{n}": sha256_file(p) for n, p in pdfs_m.items()}
    digests.update({f"C-{n}": sha256_file(p) for n, p in pdfs_c.items()})
    digests.update({f"S-{n}": sha256_file(p) for n, p in pdfs_s.items()})
    pages_m = build_fake_ocr_pages(specs_m, {n: digests[f"M-{n}"] for n in pdfs_m})
    pages_c = build_fake_ocr_pages(specs_c, {n: digests[f"C-{n}"] for n in pdfs_c})
    pages_s = build_fake_ocr_pages(specs_s, {n: digests[f"S-{n}"] for n in pdfs_s})
    pages_m = {f"M-{n}": p for n, p in pages_m.items()}
    pages_c = {f"C-{n}": p for n, p in pages_c.items()}
    pages_s = {f"S-{n}": p for n, p in pages_s.items()}
    write_pages_json(llm_dir, {**pages_m, **pages_c, **pages_s})
    write_llm_dir(
        llm_dir,
        {**llm_payloads(specs_m), **llm_payloads(specs_c), **llm_payloads(specs_s)},
    )

    import copy

    ctx_a = copy.deepcopy(BASE_CTX)
    ctx_a2 = copy.deepcopy(BASE_CTX)
    ctx_a2["ledger"] = []
    ctx_a2["grants"] = [
        *ctx_a2["grants"],
        _grant("employee:accountant-demo", 2_000_000),
    ]
    ctx_b = copy.deepcopy(BASE_CTX)
    ctx_c = copy.deepcopy(BASE_CTX)
    ctx_c["grants"] = [*ctx_c["grants"], _grant("employee:accountant-demo", 100_000)]
    contexts = {"a": ctx_a, "a2": ctx_a2, "b": ctx_b, "c": ctx_c, "d": copy.deepcopy(ctx_a2)}
    for key, ctx in contexts.items():
        (OUT / f"context-{key}.json").write_text(
            json.dumps(ctx, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    from invoice_referee.domain.organization import OrganizationContext
    from invoice_referee.workflow.db import Database
    from invoice_referee.workflow.service import CaseWorkflow

    for key, ctx in contexts.items():
        db_path = OUT / f"{key}.sqlite"
        if db_path.exists():
            db_path.unlink()
        uploads = OUT / f"uploads-{key}"
        db = Database(db_path)
        db.migrate()
        wf = CaseWorkflow(db, uploads_dir=uploads)
        wf.import_company_context(
            OrganizationContext.model_validate_json(
                json.dumps(ctx, ensure_ascii=False)
            ),
            origin="SIMULATED",
        )
        print(f"seeded {db_path.name} + context-{key}.json")

    print(
        json.dumps(
            {"pdfs": len(pdfs_m) + len(pdfs_c), "digests": digests},
            ensure_ascii=False,
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
