"""Headless smoke tests for the Streamlit app via AppTest."""

from pathlib import Path

import pytest

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py")


def _fresh():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def test_app_runs_without_exception():
    at = _fresh()
    assert not at.exception
    assert at.title[0].value.startswith("🧾")


def test_run_full_verify_button_reports_all_pass():
    at = _fresh()
    btn = next(b for b in at.button if b.label == "▶ Run Full Verify")
    btn.click().run()
    assert not at.exception
    successes = [s.value for s in at.success]
    assert any("9/9 cases passed" in s for s in successes)


def test_core_verify_button_reports_pass():
    at = _fresh()
    next(b for b in at.button if b.label == "Core Verify").click().run()
    assert not at.exception
    assert any("4/4 cases passed" in s.value for s in at.success)


def test_sample_review_shows_decision():
    at = _fresh()
    # Default sample is the first (TC01); click Review.
    next(b for b in at.button if b.label == "Review").click().run()
    assert not at.exception
    markdown_blob = " ".join(md.value for md in at.markdown)
    assert "AUTO_PROCESS" in markdown_blob


def test_document_mode_rejects_missing_upload_without_exception():
    at = _fresh()
    at.radio[0].set_value("Invoice Document").run()
    next(b for b in at.button if b.label == "Process invoice").click().run()
    assert not at.exception
    assert any("Upload" in w.value for w in at.warning)
