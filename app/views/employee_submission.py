"""Employee-facing expense submission view."""

from __future__ import annotations

import streamlit as st

from app.components.submission_form import format_size, render_submission_form
from app.state.submission_state import (
    current_form_version,
    pop_receipt,
    remember_receipt,
    reset_submission_form,
)
from invoice_referee.application import SubmitCaseService


def render_employee_submission(service: SubmitCaseService) -> None:
    st.markdown(
        """
        <div class="ir-page-heading">
          <div class="page-kicker">Dành cho nhân viên</div>
          <h1>Nộp hồ sơ chi phí</h1>
          <p>Gửi chứng từ và nội dung đề nghị đến Phòng Kế toán.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    receipt = pop_receipt()
    if receipt:
        total_files = int(receipt["primary_document_count"]) + int(
            receipt["supporting_document_count"]
        )
        status_labels = {
            "PASS": "Đã pass",
            "NEEDS_HUMAN": "Cần kế toán xử lý",
            "RECEIVED": "Đã tiếp nhận",
        }
        status = str(receipt.get("status") or "RECEIVED")
        st.markdown(
            '<div class="receipt-strip">'
            f'<strong>Đã tiếp nhận {receipt["case_id"]}</strong><br>'
            f'{total_files} tệp · {format_size(int(receipt["total_size_bytes"]))} · '
            f'Trạng thái: {status_labels.get(status, status)}'
            "</div>",
            unsafe_allow_html=True,
        )
        for warning in receipt.get("warnings", []):
            st.warning(str(warning), icon=":material/warning:")

    action, payload = render_submission_form(
        service=service,
        form_version=current_form_version(),
    )

    if action == "reset":
        reset_submission_form()
        st.rerun()
    elif action == "invalid" and isinstance(payload, list):
        for issue in payload:
            st.error(issue, icon=":material/error:")
    elif action == "submitted" and isinstance(payload, dict):
        remember_receipt(payload)
        reset_submission_form()
        st.rerun()
