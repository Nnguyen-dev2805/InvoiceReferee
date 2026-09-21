"""Accounting review queues for processed expense cases."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from invoice_referee.storage import LocalEvidenceRepository, StoredCase

IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png", ".webp"}


def _case_title(case: StoredCase, result: dict[str, Any]) -> str:
    subject = case.subject or "Không có chủ đề"
    return f"{case.case_id} · {subject} · {result.get('decision', 'UNKNOWN')}"


def _render_evidence(case: StoredCase) -> None:
    if not case.evidence:
        st.caption("Không có evidence đính kèm.")
        return

    st.markdown("**Evidence**")
    columns = st.columns(min(3, len(case.evidence)))
    for index, evidence in enumerate(case.evidence):
        with columns[index % len(columns)]:
            suffix = evidence.absolute_path.suffix.lower()
            if suffix in IMAGE_SUFFIXES:
                st.image(
                    evidence.absolute_path.read_bytes(),
                    caption=evidence.original_name,
                    width="stretch",
                )
            else:
                st.download_button(
                    evidence.original_name,
                    data=evidence.absolute_path.read_bytes(),
                    file_name=evidence.original_name,
                    mime=evidence.mime_type,
                    icon=":material/download:",
                    key=f"accounting-download-{case.case_id}-{evidence.evidence_id}",
                    use_container_width=True,
                )


def _render_case(case: StoredCase, result: dict[str, Any]) -> None:
    with st.expander(_case_title(case, result)):
        st.markdown("**Business context**")
        st.write(case.body or "Không có nội dung.")

        summary_columns = st.columns(2)
        summary_columns[0].metric("Quyết định", result.get("decision", "UNKNOWN"))
        summary_columns[1].metric(
            "Evidence đã OCR",
            len(result.get("ocr_evidence_ids") or []),
        )

        st.markdown("**Kết luận**")
        st.write(result.get("summary") or "Không có tóm tắt.")
        st.markdown("**Reasoning**")
        st.write(result.get("reasoning") or "Không có reasoning.")

        findings = result.get("findings") or []
        if findings:
            st.markdown("**Rule checks**")
            st.dataframe(
                [
                    {
                        "Rule": finding.get("rule_id"),
                        "Trạng thái": finding.get("status"),
                        "Kết quả": finding.get("message"),
                        "Nguồn": ", ".join(finding.get("source_refs") or []),
                    }
                    for finding in findings
                ],
                hide_index=True,
                width="stretch",
            )

        conflicts = ((result.get("kimi_analysis") or {}).get("conflicts") or [])
        if conflicts:
            st.markdown("**Dữ kiện mâu thuẫn**")
            st.json(conflicts, expanded=True)

        for error in result.get("processing_errors") or []:
            st.warning(error)
        _render_evidence(case)


def _render_queue(items: list[tuple[StoredCase, dict[str, Any]]]) -> None:
    if not items:
        st.info("Chưa có hồ sơ trong nhóm này.")
        return
    for case, result in items:
        _render_case(case, result)


def render_accounting_review(repository: LocalEvidenceRepository) -> None:
    st.markdown(
        """
        <div class="ir-page-heading">
          <div class="page-kicker">Dành cho kế toán</div>
          <h1>Kiểm tra hồ sơ</h1>
          <p>Xem kết quả rule, OCR và reasoning đã được lưu cho từng hồ sơ.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    processed = []
    for case in repository.list_cases():
        result = repository.load_processing_result(case.case_id)
        if result is not None:
            processed.append((case, result))

    passed = [item for item in processed if item[1].get("decision") == "PASS"]
    needs_human = [
        item for item in processed if item[1].get("decision") == "NEEDS_HUMAN"
    ]

    passed_tab, human_tab = st.tabs(
        [f"Đã pass ({len(passed)})", f"Cần xử lý ({len(needs_human)})"]
    )
    with passed_tab:
        _render_queue(passed)
    with human_tab:
        _render_queue(needs_human)
