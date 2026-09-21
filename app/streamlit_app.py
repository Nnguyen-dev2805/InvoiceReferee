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

from app.components.sidebar import ACCOUNTING_PAGE, EMPLOYEE_PAGE, render_sidebar
from app.state.submission_state import initialize_submission_state
from app.styles import APP_CSS
from app.views.accounting_review import render_accounting_review
from app.views.employee_submission import render_employee_submission
from app.views.ocr_debug import render_ocr_debug
from invoice_referee.application import CaseProcessingService, SubmitCaseService
from invoice_referee.config import AppSettings
from invoice_referee.extraction import KimiReasoningAdapter, MistralOcrAdapter
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
def build_submission_service(
    submissions_root: str,
    word_confidence_threshold: float,
) -> SubmitCaseService:
    settings_root = Path(submissions_root)
    store = LocalCaseStore(settings_root)
    repository = LocalEvidenceRepository(settings_root)
    processor = CaseProcessingService(
        repository,
        build_ocr_adapter(),
        build_kimi_adapter(),
        word_confidence_threshold=word_confidence_threshold,
    )
    return SubmitCaseService(store, processor=processor)


@st.cache_resource
def build_ocr_adapter() -> MistralOcrAdapter | None:
    import os

    api_key = os.getenv("MISTRAL_API_KEY", "").strip()
    if not api_key:
        return None
    return MistralOcrAdapter(api_key=api_key)


@st.cache_resource
def build_kimi_adapter() -> KimiReasoningAdapter | None:
    import os

    token = os.getenv("KIMI_TOKEN", "").strip()
    secret = os.getenv("KIMI_SECRET", "").strip()
    base_url = os.getenv("KIMI_BASE_URL", "").strip()
    model = os.getenv("KIMI_MODEL", "moonshotai/Kimi-K3").strip()
    if not token or not secret or not base_url or not model:
        return None
    return KimiReasoningAdapter(
        token=token,
        secret=secret,
        base_url=base_url,
        model=model,
    )


settings = AppSettings.from_environment(PROJECT_ROOT)
repository = LocalEvidenceRepository(settings.submissions_root)

selected_page = render_sidebar()

if selected_page == EMPLOYEE_PAGE:
    render_employee_submission(
        build_submission_service(
            str(settings.submissions_root),
            settings.ocr_word_review_threshold,
        )
    )
elif selected_page == ACCOUNTING_PAGE:
    render_accounting_review(repository)
else:
    render_ocr_debug(repository)
