"""Sidebar navigation shared by temporary and product pages."""

from __future__ import annotations

import streamlit as st

EMPLOYEE_PAGE = "Nhân viên"
OCR_DEBUG_PAGE = "OCR kiểm thử"


def render_sidebar() -> str:
    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-brand">
              <div class="ir-brand-mark">IR</div>
              <div>
                <div class="ir-brand-name">InvoiceReferee</div>
                <div class="ir-brand-context">Accounting intake</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="sidebar-label">Không gian làm việc</div>', unsafe_allow_html=True)
        selected_page = st.radio(
            "Không gian làm việc",
            [EMPLOYEE_PAGE, OCR_DEBUG_PAGE],
            label_visibility="collapsed",
        )
        st.markdown('<div class="sidebar-spacer"></div>', unsafe_allow_html=True)
        st.caption("OCR kiểm thử là công cụ nội bộ và sẽ được gỡ khỏi bản chính thức.")
    return selected_page
