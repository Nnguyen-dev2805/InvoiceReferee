"""The UI must supply an LLM client to the extractor.

Extraction is LLM-first and only. If the UI calls `extract_invoice` without a
client, every document fails closed with no fields — the app would look broken
rather than safe. These tests pin the wiring without calling a real provider.
"""

from __future__ import annotations

import inspect

from app import streamlit_app


def test_extract_document_passes_an_llm_client():
    """`_extract_document` must build and pass a client, or extraction yields nothing."""
    source = inspect.getsource(streamlit_app._extract_document)
    assert "llm_client=" in source, (
        "the UI must pass llm_client to extract_invoice; without it every "
        "document fails closed and no field is ever extracted"
    )


def test_extract_document_reports_a_missing_client_clearly():
    """A missing key is a configuration error the user can act on, not silence."""
    source = inspect.getsource(streamlit_app._extract_document)
    assert "client_from_env" in source
    assert "LLM_API_KEY" in source or "client is None" in source
