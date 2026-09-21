"""Employee submission form and its presentation helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import streamlit as st

from invoice_referee.application import SubmitCaseService
from invoice_referee.domain import (
    ClaimDraft,
    EvidenceRole,
    SubmissionValidationError,
    UploadPayload,
)

PRIMARY_FILE_TYPES = ["jpg", "jpeg", "png", "webp", "pdf", "xml", "json"]
SUPPORTING_FILE_TYPES = PRIMARY_FILE_TYPES + [
    "doc",
    "docx",
    "xls",
    "xlsx",
    "csv",
    "txt",
]


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _render_file_summary(files: Sequence[Any], label: str) -> None:
    if not files:
        return
    total_size = sum(int(file.size) for file in files)
    st.markdown(
        f'<div class="file-summary">{len(files)} {label} · '
        f"{format_size(total_size)}</div>",
        unsafe_allow_html=True,
    )


def _to_payloads(files: Sequence[Any], role: EvidenceRole) -> list[UploadPayload]:
    return [
        UploadPayload(
            original_name=file.name,
            content=file.getvalue(),
            mime_type=file.type or "application/octet-stream",
            role=role,
        )
        for file in files
    ]


def render_submission_form(
    service: SubmitCaseService,
    form_version: int,
) -> tuple[str, dict[str, object] | list[str] | None]:
    """Render the form and return an action with a receipt or validation issues."""

    form_key = f"employee-submission-{form_version}"
    with st.form(form_key, border=False):
        left, right = st.columns([0.84, 1.16], gap="large")

        with left:
            with st.container(border=True):
                st.markdown(
                    '<div class="section-heading">Chứng từ chính</div>'
                    '<div class="section-caption">Hóa đơn, bill, vé, phiếu thu hoặc bằng chứng thanh toán.</div>',
                    unsafe_allow_html=True,
                )
                primary_files = st.file_uploader(
                    "Tải chứng từ",
                    type=PRIMARY_FILE_TYPES,
                    accept_multiple_files=True,
                    key=f"primary-files-{form_version}",
                    label_visibility="collapsed",
                )
                _render_file_summary(primary_files, "chứng từ")
                st.caption("Không bắt buộc. Hồ sơ chỉ có nội dung mô tả vẫn được tiếp nhận.")

        with right:
            with st.container(border=True):
                st.markdown(
                    '<div class="section-heading">Nội dung đề nghị</div>'
                    '<div class="section-caption">Thông tin nhân viên gửi đến Phòng Kế toán.</div>',
                    unsafe_allow_html=True,
                )
                st.text_input(
                    "Đến",
                    value="Phòng Kế toán",
                    disabled=True,
                    key=f"recipient-{form_version}",
                )
                identity_left, identity_right = st.columns(2, gap="medium")
                with identity_left:
                    employee_name = st.text_input(
                        "Người gửi *",
                        placeholder="Nguyễn Văn A",
                        key=f"employee-name-{form_version}",
                    )
                with identity_right:
                    employee_email = st.text_input(
                        "Email *",
                        placeholder="nguyenvana@company.vn",
                        key=f"employee-email-{form_version}",
                    )

                subject = st.text_input(
                    "Chủ đề",
                    placeholder="Đề nghị hoàn ứng chi phí tiếp khách",
                    key=f"subject-{form_version}",
                )
                body = st.text_area(
                    "Nội dung",
                    placeholder=(
                        "Mô tả khoản chi, mục đích kinh doanh, khách hàng hoặc dự án "
                        "liên quan..."
                    ),
                    height=190,
                    key=f"body-{form_version}",
                )

                st.markdown(
                    '<div class="section-heading" style="margin-top:0.55rem">Tài liệu bổ sung</div>'
                    '<div class="section-caption">Kiểm kê, PO, report, biên bản hoặc tài liệu đối chiếu.</div>',
                    unsafe_allow_html=True,
                )
                supporting_files = st.file_uploader(
                    "Đính kèm tài liệu bổ sung",
                    type=SUPPORTING_FILE_TYPES,
                    accept_multiple_files=True,
                    key=f"supporting-files-{form_version}",
                    label_visibility="collapsed",
                )
                _render_file_summary(supporting_files, "tài liệu bổ sung")

        st.markdown("<div style='height:0.25rem'></div>", unsafe_allow_html=True)
        spacer, reset_col, submit_col = st.columns([5.4, 1.3, 1.7], gap="small")
        with reset_col:
            reset_clicked = st.form_submit_button(
                "Xóa nội dung",
                icon=":material/delete_sweep:",
                use_container_width=True,
            )
        with submit_col:
            submit_clicked = st.form_submit_button(
                "Gửi kiểm tra",
                type="primary",
                icon=":material/send:",
                use_container_width=True,
            )

    if reset_clicked:
        return "reset", None
    if not submit_clicked:
        return "idle", None

    claim = ClaimDraft(
        recipient="Phòng Kế toán",
        employee_name=employee_name,
        employee_email=employee_email,
        subject=subject,
        body=body,
    )
    uploads = [
        *_to_payloads(primary_files, EvidenceRole.PRIMARY_DOCUMENT),
        *_to_payloads(supporting_files, EvidenceRole.SUPPORTING_DOCUMENT),
    ]
    try:
        receipt = service.submit(claim, uploads)
    except SubmissionValidationError as exc:
        return "invalid", exc.issues
    return "submitted", receipt.model_dump(mode="json")
