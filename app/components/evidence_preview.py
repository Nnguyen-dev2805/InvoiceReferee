"""Shared evidence preview: original bill images/downloads, with optional OCR bbox."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz
import streamlit as st

from app.components.bbox_overlay import render_bbox_overlay
from invoice_referee.extraction import restructure_mistral_ocr
from invoice_referee.storage import LocalEvidenceRepository, StoredCase

IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png", ".webp"}
PDF_RENDER_DPI = 150


def _render_pdf_first_page(path: Path) -> tuple[bytes, int] | None:
    """Rasterize page 1 of a PDF to PNG bytes; return None if it cannot be read."""
    try:
        with fitz.open(path) as document:
            if document.page_count == 0:
                return None
            zoom = PDF_RENDER_DPI / 72
            pixmap = document.load_page(0).get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            return pixmap.tobytes("png"), document.page_count
    except Exception:  # noqa: BLE001 - a broken/encrypted PDF must not crash the page
        return None


def _download_button(
    evidence: Any,
    case: StoredCase,
    *,
    key_prefix: str,
    label: str | None = None,
) -> None:
    st.download_button(
        label or evidence.original_name,
        data=evidence.absolute_path.read_bytes(),
        file_name=evidence.original_name,
        mime=evidence.mime_type,
        icon=":material/download:",
        key=f"{key_prefix}-download-{case.case_id}-{evidence.evidence_id}",
        use_container_width=True,
    )


def render_evidence_preview(
    case: StoredCase,
    repository: LocalEvidenceRepository,
    *,
    key_prefix: str,
    show_bbox_toggle: bool = True,
) -> None:
    if not case.evidence:
        st.caption("Không có evidence đính kèm.")
        return

    st.markdown("**Evidence**")
    show_bounding_boxes = False
    if show_bbox_toggle:
        show_bounding_boxes = st.toggle(
            "Hiện bounding boxes",
            value=False,
            key=f"{key_prefix}-bbox-{case.case_id}",
        )
    columns = st.columns(min(3, len(case.evidence)))
    for index, evidence in enumerate(case.evidence):
        with columns[index % len(columns)]:
            suffix = evidence.absolute_path.suffix.lower()
            if suffix in IMAGE_SUFFIXES:
                preview: Any = evidence.absolute_path
                caption = evidence.original_name
                if show_bounding_boxes:
                    ocr_result = repository.load_ocr_result(evidence)
                    try:
                        if ocr_result:
                            page = restructure_mistral_ocr(ocr_result)["pages"][0]
                            preview = render_bbox_overlay(evidence.absolute_path, page)
                            caption = f"{evidence.original_name} · OCR blocks"
                    except (IndexError, OSError, TypeError, ValueError):
                        st.warning("Không thể dựng bounding boxes cho ảnh này.")
                st.image(preview, caption=caption, width="stretch")
            elif suffix == ".pdf":
                rendered = _render_pdf_first_page(evidence.absolute_path)
                if rendered is None:
                    st.warning(f"Không thể xem trước {evidence.original_name}.")
                    _download_button(evidence, case, key_prefix=key_prefix)
                else:
                    image_bytes, page_count = rendered
                    caption = evidence.original_name
                    if page_count > 1:
                        caption += f" · trang 1/{page_count}"
                    st.image(image_bytes, caption=caption, width="stretch")
                    _download_button(
                        evidence, case, key_prefix=key_prefix, label="Tải file gốc"
                    )
            else:
                _download_button(evidence, case, key_prefix=key_prefix)
