"""Streamlit entrypoint for the InvoiceReferee submission experience."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from app.components.sidebar import EMPLOYEE_PAGE, render_sidebar
from app.state.submission_state import initialize_submission_state
from app.styles import APP_CSS
from app.views.employee_submission import render_employee_submission
from app.views.ocr_debug import render_ocr_debug
from invoice_referee.application import SubmitCaseService
from invoice_referee.config import AppSettings
from invoice_referee.extraction import MistralOcrAdapter
from invoice_referee.storage import LocalCaseStore, LocalEvidenceRepository

st.set_page_config(
    page_title="Nộp hồ sơ | InvoiceReferee",
    page_icon=":material/receipt_long:",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(APP_CSS, unsafe_allow_html=True)
initialize_submission_state()


@st.cache_resource
def build_submission_service(submissions_root: str) -> SubmitCaseService:
    settings_root = Path(submissions_root)
    store = LocalCaseStore(settings_root)
    return SubmitCaseService(store)


@st.cache_resource
def build_ocr_adapter() -> MistralOcrAdapter | None:
    import os

    api_key = os.getenv("MISTRAL_API_KEY", "").strip()
    if not api_key:
        return None
    return MistralOcrAdapter(api_key=api_key)


settings = AppSettings.from_environment(PROJECT_ROOT)
repository = LocalEvidenceRepository(settings.submissions_root)

selected_page = render_sidebar()

if selected_page == EMPLOYEE_PAGE:
    render_employee_submission(
        build_submission_service(str(settings.submissions_root))
    )
else:
    render_ocr_debug(repository, build_ocr_adapter())
