"""Internal UI for testing the hybrid PaddleOCR structure pipeline."""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from app.components.bbox_overlay import render_structure_overlay
from app.components.submission_form import format_size
from invoice_referee.extraction import ModalOcrStructureAdapter

RESULT_KEY = "ocr_structure_result"
FILE_KEY = "ocr_structure_file_signature"


def _confidence_label(value: Any) -> str:
    return f"{value:.1%}" if isinstance(value, (int, float)) else "N/A"


def _render_block(block: dict[str, Any], number: int) -> None:
    confidence = block.get("confidence") or {}
    mapping = block.get("mapping") or {}
    label = (
        f"B{number:02d} · {block.get('type', 'unknown')} · "
        f"{mapping.get('status', 'unknown')} · min "
        f"{_confidence_label(confidence.get('minimum'))}"
    )
    with st.expander(label):
        metrics = st.columns(4)
        metrics[0].metric("Confidence thấp nhất", _confidence_label(confidence.get("minimum")))
        metrics[1].metric("Confidence trung bình", _confidence_label(confidence.get("average")))
        metrics[2].metric("Vùng OCR", mapping.get("region_count", 0))
        metrics[3].metric("Vùng dưới ngưỡng", confidence.get("low_region_count", 0))

        st.code(block.get("text") or "", language=None)
        if (block.get("content_comparison") or {}).get("status") == "conflict":
            st.warning("Text PP-OCR và nội dung PaddleOCR-VL không nhất quán.")
            st.caption(f"PaddleOCR-VL: {block.get('vl_text') or '(rỗng)'}")

        regions = [
            {
                "Nội dung": region.get("text") or "",
                "Confidence": region.get("confidence"),
                "Phạm vi": region.get("confidence_scope") or "text_region",
                "Containment": region.get("containment"),
                "Mapping": region.get("mapping_status"),
                "BBox": str(region.get("bbox")),
            }
            for region in block.get("ocr_regions") or []
        ]
        if regions:
            st.dataframe(
                regions,
                hide_index=True,
                width="stretch",
                column_config={
                    "Confidence": st.column_config.ProgressColumn(
                        "Confidence",
                        min_value=0.0,
                        max_value=1.0,
                        format="%.3f",
                    ),
                    "Containment": st.column_config.NumberColumn(
                        "Containment",
                        min_value=0.0,
                        max_value=1.0,
                        format="%.3f",
                    ),
                },
            )
        else:
            st.info("Block này không có OCR region được ghép vào.")

        st.json(
            {
                "bbox": block.get("bbox"),
                "reading_order": block.get("reading_order"),
                "layout_confidence": block.get("layout_confidence"),
                "text_source": block.get("text_source"),
                "content_comparison": block.get("content_comparison"),
            },
            expanded=False,
        )


def _render_result(result: dict[str, Any], file_bytes: bytes, mime_type: str) -> None:
    summary = result.get("summary") or {}
    metric_columns = st.columns(3)
    metric_columns[0].metric("Số trang", summary.get("page_count", 0))
    metric_columns[1].metric("Số block", summary.get("block_count", 0))
    metric_columns[2].metric(
        "OCR region chưa gán",
        summary.get("unmatched_ocr_region_count", 0),
    )

    overview_tab, blocks_tab, json_tab = st.tabs(["BBox", "Blocks", "JSON"])
    with overview_tab:
        pages = result.get("pages") or []
        if mime_type.startswith("image/") and pages:
            try:
                overlay = render_structure_overlay(file_bytes, pages[0])
                st.image(
                    overlay,
                    caption="Block xanh: tốt · cam: cần xem · đỏ: thấp · xám: chưa có score",
                    width="stretch",
                )
            except (OSError, ValueError) as exc:
                st.warning(f"Không thể vẽ bbox: {exc}")
        else:
            st.info("Preview bbox cho PDF sẽ được bổ sung sau; kết quả từng trang nằm ở tab Blocks.")

    with blocks_tab:
        for page in result.get("pages") or []:
            st.markdown(f"#### Trang {page.get('page_index', 0) + 1}")
            for number, block in enumerate(page.get("blocks") or [], start=1):
                _render_block(block, number)
            unmatched = page.get("unmatched_ocr_regions") or []
            if unmatched:
                st.warning(f"Có {len(unmatched)} OCR region chưa ghép được vào block.")
                st.dataframe(unmatched, hide_index=True, width="stretch")
            for warning in page.get("warnings") or []:
                st.warning(str(warning.get("code") or warning))

    with json_tab:
        st.download_button(
            "Tải structured JSON",
            data=json.dumps(result, ensure_ascii=False, indent=2),
            file_name="paddle-ocr-structure.json",
            mime="application/json",
            icon=":material/download:",
            use_container_width=True,
        )
        st.json(result, expanded=1)


def render_ocr_structure_debug(adapter: ModalOcrStructureAdapter) -> None:
    st.markdown(
        """
        <div class="ir-page-heading">
          <div class="page-kicker debug">Công cụ nội bộ</div>
          <h1>OCR cấu trúc</h1>
          <p>Chạy PP-OCR và stage PP-DocLayoutV3 của PaddleOCR-VL trên cùng một trang, sau đó ghép text region vào block.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        "Ảnh hoặc PDF",
        type=["jpg", "jpeg", "png", "webp", "pdf"],
        accept_multiple_files=False,
        help="Tối đa 20 trang đối với PDF trong tab kiểm thử.",
    )
    threshold = st.slider(
        "Ngưỡng confidence cần xem",
        min_value=0.0,
        max_value=1.0,
        value=0.85,
        step=0.01,
    )

    if uploaded is None:
        st.info("Chọn một ảnh hóa đơn hoặc PDF để bắt đầu.")
        return

    content = uploaded.getvalue()
    signature = (uploaded.name, len(content), uploaded.type)
    if st.session_state.get(FILE_KEY) != signature:
        st.session_state[FILE_KEY] = signature
        st.session_state.pop(RESULT_KEY, None)

    st.caption(f"{uploaded.name} · {uploaded.type} · {format_size(len(content))}")
    if uploaded.type.startswith("image/"):
        st.image(content, caption="Tệp đầu vào", width="stretch")

    if st.button(
        "Chạy OCR cấu trúc",
        type="primary",
        icon=":material/document_scanner:",
        use_container_width=True,
    ):
        try:
            with st.spinner("Đang chạy PP-OCR, PP-DocLayoutV3 và ghép bbox..."):
                st.session_state[RESULT_KEY] = adapter.process(
                    file_name=uploaded.name,
                    mime_type=uploaded.type or "application/octet-stream",
                    content=content,
                    review_threshold=threshold,
                )
        except Exception as exc:  # Modal surfaces remote errors through SDK exceptions.
            st.error(f"OCR cấu trúc thất bại: {exc}")

    result = st.session_state.get(RESULT_KEY)
    if isinstance(result, dict):
        st.divider()
        _render_result(result, content, uploaded.type or "application/octet-stream")


__all__ = ["render_ocr_structure_debug"]
