"""Temporary OCR inspection page for submitted evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from app.components.bbox_overlay import render_bbox_overlay
from app.components.submission_form import format_size
from invoice_referee.extraction import (
    REVIEW_CONFIDENCE_THRESHOLD,
    extract_word_confidence_rows,
    restructure_mistral_ocr,
)
from invoice_referee.storage import LocalEvidenceRepository, StoredCase, StoredEvidence

OCR_SUFFIXES = {".jpeg", ".jpg", ".pdf", ".png", ".webp"}


def _case_label(case: StoredCase) -> str:
    date = case.submitted_at[:16].replace("T", " ") if case.submitted_at else "Không rõ ngày"
    return f"{case.case_id} · {case.subject} · {date}"


def _evidence_label(evidence: StoredEvidence) -> str:
    role = "Chứng từ chính" if evidence.role == "PRIMARY_DOCUMENT" else "Tài liệu bổ sung"
    return f"{evidence.original_name} · {role} · {format_size(evidence.size_bytes)}"


def _render_preview(
    evidence: StoredEvidence,
    result: dict[str, Any] | None = None,
) -> None:
    suffix = evidence.absolute_path.suffix.lower()
    if suffix in {".jpeg", ".jpg", ".png", ".webp"}:
        preview: bytes | Any = evidence.absolute_path.read_bytes()
        caption = evidence.original_name
        if result:
            try:
                hierarchy = restructure_mistral_ocr(result)
                first_page = hierarchy["pages"][0]
                preview = render_bbox_overlay(evidence.absolute_path, first_page)
                caption = (
                    f"{evidence.original_name} · "
                    f"{len(first_page['blocks'])} blocks"
                )
            except (IndexError, OSError, ValueError):
                pass
        st.image(
            preview,
            caption=caption,
            width="stretch",
        )
    else:
        st.markdown(
            '<div class="pdf-preview">PDF đã sẵn sàng để gửi đến OCR.</div>',
            unsafe_allow_html=True,
        )
        st.download_button(
            "Mở tệp PDF",
            data=evidence.absolute_path.read_bytes(),
            file_name=evidence.original_name,
            mime="application/pdf",
            icon=":material/download:",
            use_container_width=True,
        )


def _markdown_from_result(result: dict[str, Any]) -> str:
    response = result.get("response") or {}
    pages = response.get("pages") or []
    sections = []
    for index, page in enumerate(pages, start=1):
        markdown = page.get("markdown") or ""
        sections.append(f"### Trang {index}\n\n{markdown}")
    return "\n\n---\n\n".join(sections)


def _render_word_confidence(result: dict[str, Any]) -> None:
    rows = extract_word_confidence_rows(result)
    if not rows:
        st.info(
            "Kết quả này chưa có confidence theo từng từ. "
            "Hãy chạy lại OCR để lấy dữ liệu mới."
        )
        return

    confidence_values = [row["confidence"] for row in rows]
    review_count = sum(
        confidence < REVIEW_CONFIDENCE_THRESHOLD
        for confidence in confidence_values
    )
    metric_columns = st.columns(3)
    metric_columns[0].metric("Số từ", len(rows))
    metric_columns[1].metric(
        "Confidence trung bình",
        f"{sum(confidence_values) / len(confidence_values):.1%}",
    )
    metric_columns[2].metric("Cần kiểm tra", review_count)

    only_review = st.toggle(
        "Chỉ hiện từ có confidence dưới 0,85",
        value=True,
    )
    visible_rows = rows
    if only_review:
        visible_rows = [
            row
            for row in rows
            if row["confidence"] < REVIEW_CONFIDENCE_THRESHOLD
        ]

    level_labels = {
        "low": "Thấp",
        "review": "Cần xem",
        "good": "Tốt",
    }
    display_rows = [
        {
            "Trang": row["page"],
            "Từ": row["text"],
            "Confidence": row["confidence"],
            "Mức": level_labels[row["level"]],
            "Vị trí": row["start_index"],
        }
        for row in sorted(visible_rows, key=lambda row: row["confidence"])
    ]

    if not display_rows:
        st.success("Không có từ nào dưới ngưỡng 0,85.")
        return

    st.dataframe(
        display_rows,
        hide_index=True,
        width="stretch",
        column_config={
            "Confidence": st.column_config.ProgressColumn(
                "Confidence",
                min_value=0.0,
                max_value=1.0,
                format="%.3f",
            ),
            "Vị trí": st.column_config.NumberColumn("Vị trí", format="%d"),
        },
    )


def _block_word_rows(block: dict[str, Any]) -> list[dict[str, Any]]:
    level_labels = {
        "low": "Thấp",
        "review": "Cần xem",
        "good": "Tốt",
    }
    source_words = block.get("words") or block.get("references") or []
    return [
        {
            "Từ": word.get("text") or "",
            "Confidence": word.get("confidence"),
            "Mức": level_labels.get(word.get("level"), "Tham chiếu"),
            "Bắt đầu": word.get("start_index"),
            "Kết thúc": word.get("end_index"),
        }
        for word in source_words
    ]


def _render_block(block: dict[str, Any], number: int) -> None:
    confidence = block.get("confidence") or {}
    mapping = block.get("mapping") or {}
    minimum = confidence.get("minimum")
    minimum_label = f"{minimum:.1%}" if isinstance(minimum, (int, float)) else "N/A"
    label = (
        f"Block {number:02d} · {block.get('type', 'unknown')} · "
        f"{mapping.get('status', 'unknown')} · min {minimum_label}"
    )

    with st.expander(label):
        st.caption(
            f"{block.get('block_id')} · "
            f"mapping: {mapping.get('method')} · "
            f"confidence source: {confidence.get('source')}"
        )
        metric_columns = st.columns(3)
        average = confidence.get("average")
        metric_columns[0].metric(
            "Confidence trung bình",
            f"{average:.1%}" if isinstance(average, (int, float)) else "N/A",
        )
        metric_columns[1].metric("Confidence thấp nhất", minimum_label)
        metric_columns[2].metric(
            "Từ cần kiểm tra",
            confidence.get("review_word_count", 0),
        )

        st.code(block.get("content") or "", language=None)
        word_rows = _block_word_rows(block)
        if word_rows:
            table_label = "Table reference" if block.get("references") else "Words"
            st.markdown(f"**{table_label}**")
            st.dataframe(
                word_rows,
                hide_index=True,
                width="stretch",
                column_config={
                    "Confidence": st.column_config.ProgressColumn(
                        "Confidence",
                        min_value=0.0,
                        max_value=1.0,
                        format="%.3f",
                    ),
                    "Bắt đầu": st.column_config.NumberColumn("Bắt đầu", format="%d"),
                    "Kết thúc": st.column_config.NumberColumn("Kết thúc", format="%d"),
                },
            )
        else:
            st.info("Block này chưa ánh xạ được word confidence.")

        st.json(
            {
                "bounding_box": block.get("bounding_box"),
                "text_span": block.get("text_span"),
                "mapping": mapping,
            },
            expanded=False,
        )


def _render_hierarchical_blocks(
    result: dict[str, Any],
    evidence: StoredEvidence,
) -> None:
    try:
        hierarchy = restructure_mistral_ocr(result)
    except ValueError as exc:
        st.error(f"Không thể tái cấu trúc block: {exc}")
        return

    st.download_button(
        "Tải JSON phân cấp",
        data=json.dumps(hierarchy, ensure_ascii=False, indent=2),
        file_name="mistral-ocr-hierarchical.json",
        mime="application/json",
        icon=":material/download:",
        use_container_width=True,
    )

    for page_position, page in enumerate(hierarchy["pages"], start=1):
        if page_position > 1:
            st.divider()
        st.markdown(f"#### Trang {page['page_index'] + 1}")
        if evidence.absolute_path.suffix.lower() in {".jpeg", ".jpg", ".png", ".webp"}:
            if page_position == 1:
                try:
                    overlay = render_bbox_overlay(evidence.absolute_path, page)
                    st.image(
                        overlay,
                        caption="Các block OCR trên ảnh gốc",
                        width="stretch",
                    )
                except (OSError, ValueError) as exc:
                    st.warning(f"Không thể vẽ bounding box: {exc}")
            else:
                st.info("Ảnh nguồn chỉ có một trang; không có preview cho trang này.")
        elif evidence.absolute_path.suffix.lower() == ".pdf":
            st.info("Preview bounding box cho PDF chưa được hỗ trợ.")

        page_metrics = st.columns(3)
        page_metrics[0].metric("Blocks", len(page["blocks"]))
        page_metrics[1].metric("Word chưa gán", len(page["unassigned_words"]))
        page_metrics[2].metric("Warnings", len(page["warnings"]))

        for block_number, block in enumerate(page["blocks"], start=1):
            _render_block(block, block_number)

        if page["unassigned_words"]:
            st.warning("Có word chưa được gán vào block.")
            st.dataframe(
                page["unassigned_words"],
                hide_index=True,
                width="stretch",
            )
        for warning in page["warnings"]:
            st.warning(f"{warning['code']}: {warning['message']}")


def _render_result(result: dict[str, Any], evidence: StoredEvidence) -> None:
    text_tab, confidence_tab, blocks_tab, json_tab = st.tabs(
        ["Văn bản", "Confidence theo từ", "Blocks", "JSON"]
    )
    with text_tab:
        markdown = _markdown_from_result(result)
        if markdown:
            st.markdown(markdown)
        else:
            st.info("OCR chưa trả về nội dung văn bản.")
    with confidence_tab:
        _render_word_confidence(result)
    with blocks_tab:
        _render_hierarchical_blocks(result, evidence)
    with json_tab:
        st.json(result, expanded=1)


def render_ocr_debug(
    repository: LocalEvidenceRepository,
) -> None:
    st.markdown(
        """
        <div class="ir-page-heading">
          <div class="page-kicker debug">Công cụ nội bộ</div>
          <h1>OCR kiểm thử</h1>
          <p>Xem lại kết quả của những evidence đã được Mistral OCR xử lý.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cases = [
        case
        for case in repository.list_cases()
        if any(repository.load_ocr_result(evidence) for evidence in case.evidence)
    ]
    if not cases:
        st.info("Chưa có hồ sơ nào đã chạy OCR.")
        return

    selected_case = st.selectbox(
        "Hồ sơ",
        options=cases,
        format_func=_case_label,
    )
    supported_evidence = [
        evidence
        for evidence in selected_case.evidence
        if Path(evidence.original_name).suffix.lower() in OCR_SUFFIXES
        and repository.load_ocr_result(evidence) is not None
    ]
    if not supported_evidence:
        st.warning("Hồ sơ này chưa có kết quả OCR.")
        return

    selected_evidence = st.selectbox(
        "Evidence",
        options=supported_evidence,
        format_func=_evidence_label,
    )

    result = repository.load_ocr_result(selected_evidence)

    preview_col, result_col = st.columns([0.78, 1.22], gap="large")
    with preview_col:
        with st.container(border=True):
            st.markdown('<div class="section-heading">Evidence</div>', unsafe_allow_html=True)
            st.caption(
                f"{selected_evidence.evidence_id} · {selected_evidence.mime_type}"
            )
            _render_preview(selected_evidence, result)

    with result_col:
        with st.container(border=True):
            st.markdown('<div class="section-heading">Kết quả OCR</div>', unsafe_allow_html=True)
            st.caption(
                f"Model: {result.get('model', 'mistral-ocr-latest')} · confidence: word"
            )
            _render_result(result, selected_evidence)
