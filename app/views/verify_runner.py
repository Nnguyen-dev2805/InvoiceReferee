"""Verify page: run every fixture case in data/testcase through the real pipeline."""

from __future__ import annotations

import mimetypes
import shutil
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from time import monotonic
from typing import Any

import streamlit as st

from app.components.evidence_preview import render_evidence_preview
from invoice_referee.application import SubmitCaseService
from invoice_referee.domain import (
    ClaimDraft,
    EvidenceRole,
    SubmissionValidationError,
    UploadPayload,
)
from invoice_referee.storage import LocalEvidenceRepository

STATUS_BADGES = {
    "PENDING": "⏳ Đang chạy",
    "PASS": "✅ PASS",
    "NEEDS_HUMAN": "🟠 NEEDS_HUMAN",
    "ERROR": "⛔ Lỗi",
    "SKIPPED": "⚪ Bỏ qua",
}


def discover_testcases(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name)


def _files_to_payloads(folder: Path, role: EvidenceRole) -> list[UploadPayload]:
    if not folder.is_dir():
        return []
    payloads: list[UploadPayload] = []
    for file_path in sorted(folder.iterdir()):
        if not file_path.is_file():
            continue
        mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        payloads.append(
            UploadPayload(
                original_name=file_path.name,
                content=file_path.read_bytes(),
                mime_type=mime_type,
                role=role,
            )
        )
    return payloads


def load_testcase(folder: Path) -> tuple[ClaimDraft, list[UploadPayload]] | None:
    """Load one data/testcase/<name> folder into (claim, uploads), or None if empty."""

    content_file = folder / "content" / "content.txt"
    primary_uploads = _files_to_payloads(folder / "evidence", EvidenceRole.PRIMARY_DOCUMENT)
    has_content = content_file.is_file()

    if not has_content and not primary_uploads:
        return None

    subject, body = "", ""
    if has_content:
        lines = content_file.read_text(encoding="utf-8").splitlines()
        subject = lines[0].strip() if lines else ""
        body = "\n".join(lines[1:]).strip()

    supporting_uploads = _files_to_payloads(
        folder / "content" / "attach_file", EvidenceRole.SUPPORTING_DOCUMENT
    )
    claim = ClaimDraft(subject=subject, body=body)
    return claim, [*primary_uploads, *supporting_uploads]


def _run_one(
    service: SubmitCaseService,
    repository: LocalEvidenceRepository,
    claim: ClaimDraft,
    uploads: list[UploadPayload],
) -> dict[str, Any]:
    started = monotonic()
    try:
        receipt = service.submit(claim, uploads)
    except SubmissionValidationError as exc:
        return {"status": "ERROR", "reason": "; ".join(exc.issues), "elapsed": monotonic() - started}
    except Exception as exc:  # noqa: BLE001 - one failing case must not sink the batch
        return {"status": "ERROR", "reason": str(exc), "elapsed": monotonic() - started}

    elapsed = monotonic() - started
    result = repository.load_processing_result(receipt.case_id) or {}
    return {
        "status": receipt.status,
        "case_id": receipt.case_id,
        "summary": result.get("summary", ""),
        "reasoning": result.get("reasoning", ""),
        "findings": result.get("findings") or [],
        "elapsed": elapsed,
    }


def _render_detail(outcome: dict[str, Any], repository: LocalEvidenceRepository) -> None:
    status = outcome["status"]
    if status == "SKIPPED":
        st.caption("Thiếu content.txt và evidence trong thư mục case này.")
        return
    if status == "ERROR":
        st.error(outcome.get("reason") or "Không rõ lỗi.", icon=":material/error:")
        return
    if status == "PENDING":
        st.caption("Đang chờ kết quả...")
        return

    elapsed = outcome.get("elapsed")
    if isinstance(elapsed, (int, float)):
        st.caption(f"Thời gian chạy: {elapsed:.1f}s · Mã case: {outcome.get('case_id')}")

    case = None
    case_id = outcome.get("case_id")
    if case_id:
        try:
            case = repository.get_case(case_id)
        except FileNotFoundError:
            case = None

    if case is not None:
        st.markdown("**Nội dung đề nghị**")
        st.write(case.body or "Không có nội dung.")

    st.markdown("**Tóm tắt**")
    st.write(outcome.get("summary") or "Không có tóm tắt.")

    if status == "NEEDS_HUMAN":
        st.markdown("**Lý do cần xác minh**")
        st.warning(
            outcome.get("reasoning") or "Không có lý do cụ thể.",
            icon=":material/help:",
        )

    if case is not None:
        render_evidence_preview(case, repository, key_prefix="verify", show_bbox_toggle=False)


def _draw_row(placeholder: Any, name: str, outcome: dict[str, Any], repository: LocalEvidenceRepository) -> None:
    badge = STATUS_BADGES.get(outcome["status"], outcome["status"])
    with placeholder.container():
        with st.expander(f"{name} — {badge}", expanded=False):
            _render_detail(outcome, repository)


def render_verify(
    service: SubmitCaseService,
    repository: LocalEvidenceRepository,
    testcase_root: Path,
    verify_runs_root: Path,
) -> None:
    st.markdown(
        """
        <div class="ir-page-heading">
          <div class="page-kicker">Chấm điểm nhanh</div>
          <h1>Verify</h1>
          <p>Chạy toàn bộ case trong data/testcase qua đúng luồng OCR + policy thật.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    folders = discover_testcases(testcase_root)
    if not folders:
        st.info(f"Không tìm thấy case nào trong {testcase_root}.")
        return

    st.caption(f"{len(folders)} case trong `{testcase_root}`. Bấm vào 1 dòng để xem chi tiết.")
    run_clicked = st.button(
        "Chạy tất cả case",
        type="primary",
        icon=":material/play_arrow:",
    )
    if not run_clicked:
        return

    if verify_runs_root.exists():
        shutil.rmtree(verify_runs_root)
    verify_runs_root.mkdir(parents=True, exist_ok=True)

    loaded_by_folder = {folder: load_testcase(folder) for folder in folders}

    summary_placeholder = st.empty()
    placeholders = {folder: st.empty() for folder in folders}

    counts = {"PASS": 0, "NEEDS_HUMAN": 0, "ERROR": 0, "SKIPPED": 0}

    runnable: dict[Path, tuple[ClaimDraft, list[UploadPayload]]] = {}
    for folder, loaded in loaded_by_folder.items():
        if loaded is None:
            counts["SKIPPED"] += 1
            _draw_row(placeholders[folder], folder.name, {"status": "SKIPPED"}, repository)
        else:
            runnable[folder] = loaded
            _draw_row(placeholders[folder], folder.name, {"status": "PENDING"}, repository)

    max_workers = min(len(runnable), 16) or 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_folder: dict[Future[dict[str, Any]], Path] = {
            executor.submit(_run_one, service, repository, claim, uploads): folder
            for folder, (claim, uploads) in runnable.items()
        }
        for future in as_completed(future_to_folder):
            folder = future_to_folder[future]
            outcome = future.result()
            counts[outcome["status"]] = counts.get(outcome["status"], 0) + 1
            _draw_row(placeholders[folder], folder.name, outcome, repository)

    summary_placeholder.markdown(
        f"**Kết quả**: {counts['PASS']} PASS · {counts['NEEDS_HUMAN']} NEEDS_HUMAN · "
        f"{counts['ERROR']} lỗi · {counts['SKIPPED']} bỏ qua"
    )
