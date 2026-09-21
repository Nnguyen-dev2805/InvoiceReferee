"""State transitions for the employee submission form."""

from __future__ import annotations

import streamlit as st

FORM_VERSION_KEY = "submission_form_version"
LAST_RECEIPT_KEY = "last_submission_receipt"


def initialize_submission_state() -> None:
    st.session_state.setdefault(FORM_VERSION_KEY, 0)
    st.session_state.setdefault(LAST_RECEIPT_KEY, None)


def current_form_version() -> int:
    return int(st.session_state[FORM_VERSION_KEY])


def reset_submission_form() -> None:
    st.session_state[FORM_VERSION_KEY] += 1


def remember_receipt(receipt: dict[str, object]) -> None:
    st.session_state[LAST_RECEIPT_KEY] = receipt


def pop_receipt() -> dict[str, object] | None:
    receipt = st.session_state.get(LAST_RECEIPT_KEY)
    st.session_state[LAST_RECEIPT_KEY] = None
    return receipt
