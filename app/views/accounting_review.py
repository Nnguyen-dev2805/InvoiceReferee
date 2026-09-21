"""Accounting review queues for processed expense cases."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from app.components.bbox_overlay import render_bbox_overlay
from invoice_referee.extraction import restructure_mistral_ocr
from invoice_referee.storage import LocalEvidenceRepository, StoredCase

IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png", ".webp"}
DELETE_STATE_PREFIX = "accounting-confirm-delete-"
ACCOUNTING_FIELD_LABELS = {
    "seller_name": "tên người bán",
    "seller_tax_code": "mã số thuế người bán",
    "buyer_name": "tên người mua",
    "buyer_tax_code": "mã số thuế người mua",
    "invoice_date": "ngày chứng từ",
    "invoice_number": "số hóa đơn",
    "template_number": "mẫu số hóa đơn",
    "serial_number": "ký hiệu hóa đơn",
    "quantity": "số lượng",
    "unit_price": "đơn giá",
    "line_amount": "thành tiền",
    "tax_amount": "tiền thuế",
    "total_amount": "tổng thanh toán",
    "transaction_reference": "mã giao dịch",
}
TECHNICAL_MARKERS = ("candidate", "block", "page-", "confidence", "ocr", "ev-")


def _case_title(case: StoredCase, result: dict[str, Any]) -> str:
    subject = case.subject or "Không có chủ đề"
    return f"{case.case_id} · {subject} · {result.get('decision', 'UNKNOWN')}"


def _friendly_field_text(fields: list[str]) -> str:
    labels = [
        ACCOUNTING_FIELD_LABELS.get(field, field.replace("_", " "))
        for field in fields
    ] or ["thông tin chưa rõ"]
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + f" và {labels[-1]}"


def _accounting_summary(result: dict[str, Any]) -> str:
    inventory_findings = [
        finding
        for finding in result.get("findings") or []
        if str(finding.get("rule_id") or "").startswith("INVENTORY_")
    ]
    if inventory_findings:
        if any(
            finding.get("status") in {"FAIL", "ERROR"}
            for finding in inventory_findings
        ):
            return result.get("summary") or (
                "Hóa đơn và nguồn kiểm kê có dữ liệu cần kế toán xác nhận."
            )
        inventory_analysis = result.get("inventory_analysis") or {}
        if inventory_analysis.get("applicability") == "APPLICABLE":
            return result.get("summary") or (
                "Hóa đơn và nguồn nhận hàng thống nhất ở policy kiểm kê."
            )

    analysis = result.get("confidence_analysis") or {}
    assessments = analysis.get("block_assessments") or []
    if not assessments:
        return result.get("summary") or "Không có tóm tắt."
    if result.get("decision") == "NEEDS_HUMAN":
        return "Chứng từ có thông tin quan trọng cần kế toán xác nhận."
    policy_count = sum(
        item.get("review_action") == "DEFER_TO_POLICY" for item in assessments
    )
    if policy_count:
        return f"Có {policy_count} nội dung cần kiểm tra theo chính sách chi phí."
    return "Các thông tin chưa rõ không ảnh hưởng đến việc đọc chứng từ."


def _accounting_reasoning(case: StoredCase, result: dict[str, Any]) -> str:
    inventory_questions: list[str] = []
    inventory_analysis = (
        result.get("conflict_analysis")
        or result.get("inventory_analysis")
        or {}
    )
    extracted_ids = {
        document.get("evidence_id")
        for document in inventory_analysis.get("document_facts") or []
        if document.get("evidence_id")
    }
    for finding in result.get("findings") or []:
        rule_id = str(finding.get("rule_id") or "")
        if not rule_id.startswith("INVENTORY_") or finding.get("status") not in {
            "FAIL",
            "ERROR",
        }:
            continue
        if rule_id == "INVENTORY_EXTRACTION_COVERAGE_INVALID":
            missing_evidence = [
                evidence
                for evidence in case.evidence
                if evidence.evidence_id not in extracted_ids
            ]
            for evidence in missing_evidence:
                role_label = (
                    "chứng từ chính"
                    if evidence.role == "PRIMARY_DOCUMENT"
                    else "chứng từ hỗ trợ"
                )
                inventory_questions.append(
                    f"Policy kiểm kê chưa trích xuất {role_label} "
                    f"'{evidence.original_name}'. Các thông tin chưa có gồm: loại "
                    "chứng từ; nhà cung cấp và MST; ngày chứng từ; trạng thái nhận "
                    "hàng; danh sách hàng hóa với tên, số lượng, đơn vị, đơn giá "
                    "và thành tiền."
                )
            if missing_evidence:
                continue
        message = str(finding.get("message") or "").strip()
        if message:
            inventory_questions.append(message)
    if inventory_questions:
        return " ".join(inventory_questions)

    analysis = result.get("confidence_analysis") or {}
    assessments = analysis.get("block_assessments") or []
    if not assessments:
        return result.get("reasoning") or "Không có nội dung cần xử lý."
    if result.get("decision") != "NEEDS_HUMAN":
        if any(
            item.get("review_action") == "DEFER_TO_POLICY"
            for item in assessments
        ):
            return (
                "Chứng từ vẫn có thể tiếp tục xử lý; nội dung được đánh dấu sẽ "
                "được xem xét ở bước kiểm tra chính sách."
            )
        return "Không có thông tin nào cần kế toán xác nhận ở bước này."

    candidates = {
        item.get("candidate_id"): item
        for item in result.get("low_confidence_candidates") or []
    }
    filenames = {
        evidence.evidence_id: evidence.original_name for evidence in case.evidence
    }
    questions: list[str] = []
    for assessment in assessments:
        if assessment.get("review_action") != "ASK_HUMAN":
            continue
        question = str(assessment.get("human_question") or "").strip()
        if question and not any(
            marker in question.lower() for marker in TECHNICAL_MARKERS
        ):
            questions.append(question)
            continue

        candidate = candidates.get(assessment.get("candidate_id")) or {}
        source_file = (
            candidate.get("source_file")
            or filenames.get(candidate.get("evidence_id"))
            or "chứng từ"
        )
        field_text = _friendly_field_text(assessment.get("canonical_fields") or [])
        questions.append(
            f"Vui lòng kiểm tra {source_file} và xác nhận {field_text}."
        )

    return " ".join(questions) or (
        result.get("reasoning") or "Vui lòng kiểm tra lại chứng từ."
    )


def _render_evidence(
    case: StoredCase,
    repository: LocalEvidenceRepository,
) -> None:
    if not case.evidence:
        st.caption("Không có evidence đính kèm.")
        return

    st.markdown("**Evidence**")
    show_bounding_boxes = st.toggle(
        "Hiện bounding boxes",
        value=False,
        key=f"accounting-bbox-{case.case_id}",
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
                st.image(
                    preview,
                    caption=caption,
                    width="stretch",
                )
            else:
                st.download_button(
                    evidence.original_name,
                    data=evidence.absolute_path.read_bytes(),
                    file_name=evidence.original_name,
                    mime=evidence.mime_type,
                    icon=":material/download:",
                    key=f"accounting-download-{case.case_id}-{evidence.evidence_id}",
                    use_container_width=True,
                )


def _render_quality_review(result: dict[str, Any]) -> None:
    evidence_quality = result.get("evidence_quality") or []
    if evidence_quality:
        st.markdown("**Chất lượng từng chứng từ**")
        st.dataframe(
            [
                {
                    "Chứng từ": item.get("filename"),
                    "Trạng thái": item.get("status"),
                    "Vùng cần đánh giá": item.get("candidate_count"),
                    "Field chặn": ", ".join(item.get("blocking_fields") or []),
                    "Cảnh báo": ", ".join(item.get("warning_fields") or []),
                }
                for item in evidence_quality
            ],
            hide_index=True,
            width="stretch",
        )

    candidates = result.get("low_confidence_candidates") or []
    if not candidates:
        return
    confidence_analysis = result.get("confidence_analysis")
    legacy_analysis = result.get("kimi_analysis")
    if not confidence_analysis and not legacy_analysis:
        rule_ids = {
            finding.get("rule_id") for finding in result.get("findings") or []
        }
        if {
            "CONFIDENCE_AGENT_ERROR",
            "KIMI_PROCESSING_ERROR",
        }.intersection(rule_ids):
            st.warning(
                "Confidence Quality Agent không hoàn thành nên chưa có assessment "
                "cho các block confidence thấp."
            )
        else:
            st.info(
                "Hồ sơ này chưa có kết quả Confidence Quality Agent. Có thể đây "
                "là kết quả được tạo trước workflow hiện tại."
            )
        return

    assessments = {
        item.get("candidate_id"): item
        for item in (
            (confidence_analysis or {}).get("block_assessments")
            or (legacy_analysis or {}).get("block_assessments")
            or []
        )
    }
    st.markdown("**Chi tiết Confidence Quality Agent**")
    st.dataframe(
        [
            {
                "Candidate": candidate.get("candidate_id"),
                "Nội dung block": candidate.get("content"),
                "Word thấp": ", ".join(
                    f"{word.get('text', '').strip()} ({word.get('confidence', 0):.3f})"
                    for word in candidate.get("low_words") or []
                ),
                "Mức quan trọng": (
                    assessments.get(candidate.get("candidate_id"), {}).get("importance")
                    or "UNKNOWN"
                ),
                "Chất lượng": (
                    assessments.get(candidate.get("candidate_id"), {}).get("quality_state")
                    or "UNKNOWN"
                ),
                "Hành động": (
                    assessments.get(candidate.get("candidate_id"), {}).get("review_action")
                    or "ASK_HUMAN"
                ),
                "Nhóm ngữ nghĩa": assessments.get(
                    candidate.get("candidate_id"), {}
                ).get("semantic_category"),
                "Canonical fields": ", ".join(
                    assessments.get(candidate.get("candidate_id"), {}).get(
                        "canonical_fields", []
                    )
                ),
                "Phân tích kỹ thuật": assessments.get(candidate.get("candidate_id"), {}).get(
                    "reason", "Thiếu assessment cho candidate này."
                ),
                "Câu hỏi cho người kiểm tra": assessments.get(
                    candidate.get("candidate_id"), {}
                ).get("human_question"),
            }
            for candidate in candidates
        ],
        hide_index=True,
        width="stretch",
    )


def _render_inventory_review(result: dict[str, Any]) -> None:
    analysis = result.get("conflict_analysis") or result.get("inventory_analysis")
    if not analysis:
        return

    st.markdown("**Đối chiếu bill và report**")
    applicability = analysis.get("applicability") or "UNKNOWN"
    reason = analysis.get("applicability_reason") or "Không có giải thích."
    if applicability == "APPLICABLE":
        st.caption(f"Áp dụng · {reason}")
    elif applicability == "NOT_APPLICABLE":
        st.caption(f"Không áp dụng · {reason}")
    else:
        st.warning(f"Chưa xác định được phạm vi áp dụng: {reason}")

    rows: list[dict[str, Any]] = []
    for document in analysis.get("document_facts") or []:
        items = document.get("items") or []
        if not items:
            rows.append(
                {
                    "Nguồn": document.get("evidence_id"),
                    "Loại": document.get("document_type"),
                    "Nhà cung cấp": document.get("supplier_name"),
                    "Trạng thái nhận": document.get("receipt_status"),
                    "Hàng hóa": None,
                    "Số lượng": None,
                    "Đơn vị": None,
                    "Đơn giá": None,
                    "Thành tiền": None,
                }
            )
            continue
        for item in items:
            rows.append(
                {
                    "Nguồn": document.get("evidence_id"),
                    "Loại": document.get("document_type"),
                    "Nhà cung cấp": document.get("supplier_name"),
                    "Trạng thái nhận": document.get("receipt_status"),
                    "Hàng hóa": item.get("raw_name"),
                    "Số lượng": item.get("quantity"),
                    "Đơn vị": item.get("unit"),
                    "Đơn giá": item.get("unit_price"),
                    "Thành tiền": item.get("line_amount"),
                }
            )
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")

    comparisons = analysis.get("comparisons") or []
    if comparisons:
        st.markdown("**Các phép so sánh do Conflict Agent đề xuất**")
        st.dataframe(
            [
                {
                    "Field": item.get("field"),
                    "Hàng hóa": item.get("item_name"),
                    "Nguồn trái": (item.get("left") or {}).get("source_id"),
                    "Giá trị trái": (item.get("left") or {}).get("value"),
                    "Nguồn phải": (item.get("right") or {}).get("source_id"),
                    "Giá trị phải": (item.get("right") or {}).get("value"),
                    "Trạng thái đề xuất": item.get("status"),
                    "Giải thích": item.get("reason"),
                }
                for item in comparisons
            ],
            hide_index=True,
            width="stretch",
        )

    text_report = analysis.get("text_report") or {}
    if text_report.get("is_inventory_report"):
        st.caption(
            "Báo cáo nhân viên: "
            f"{text_report.get('receipt_status') or 'UNKNOWN'}"
        )

    warnings = analysis.get("extraction_warnings") or []
    for warning in warnings:
        st.warning(warning)


def _render_delete_controls(
    case: StoredCase,
    repository: LocalEvidenceRepository,
) -> None:
    state_key = f"{DELETE_STATE_PREFIX}{case.case_id}"
    st.divider()

    if not st.session_state.get(state_key, False):
        _, action_column = st.columns([4, 1])
        with action_column:
            if st.button(
                "Xóa hồ sơ",
                icon=":material/delete:",
                key=f"delete-case-{case.case_id}",
                use_container_width=True,
            ):
                st.session_state[state_key] = True
                st.rerun()
        return

    st.warning(
        f"Xóa vĩnh viễn {case.case_id}? Evidence, kết quả OCR và kết quả xử lý "
        "của hồ sơ này sẽ bị xóa."
    )
    _, confirm_column, cancel_column = st.columns([3, 1, 1])
    with confirm_column:
        if st.button(
            "Xác nhận xóa",
            icon=":material/delete_forever:",
            type="primary",
            key=f"confirm-delete-case-{case.case_id}",
            use_container_width=True,
        ):
            try:
                repository.delete_case(case.case_id)
            except (OSError, ValueError) as exc:
                st.error(f"Không thể xóa hồ sơ: {exc}")
            else:
                st.session_state.pop(state_key, None)
                st.session_state.pop("accounting-case-selector-passed", None)
                st.session_state.pop("accounting-case-selector-needs-human", None)
                st.toast(f"Đã xóa {case.case_id}.")
                st.rerun()
    with cancel_column:
        if st.button(
            "Hủy",
            icon=":material/close:",
            key=f"cancel-delete-case-{case.case_id}",
            use_container_width=True,
        ):
            st.session_state.pop(state_key, None)
            st.rerun()


def _render_case(
    case: StoredCase,
    result: dict[str, Any],
    repository: LocalEvidenceRepository,
) -> None:
    with st.expander(_case_title(case, result), expanded=True):
        st.markdown("**Business context**")
        st.write(case.body or "Không có nội dung.")

        summary_columns = st.columns(2)
        summary_columns[0].metric("Kết quả xử lý", result.get("decision", "UNKNOWN"))
        summary_columns[1].metric(
            "Evidence đã OCR",
            len(result.get("ocr_evidence_ids") or []),
        )

        st.markdown("**Tóm tắt cho kế toán**")
        st.write(_accounting_summary(result))
        st.markdown("**Nội dung cần xử lý**")
        st.write(_accounting_reasoning(case, result))

        findings = result.get("findings") or []
        if findings:
            st.markdown("**Rule checks**")
            st.dataframe(
                [
                    {
                        "Rule": finding.get("rule_id"),
                        "Trạng thái": finding.get("status"),
                        "Kết quả": finding.get("message"),
                        "Nguồn": ", ".join(finding.get("source_refs") or []),
                    }
                    for finding in findings
                ],
                hide_index=True,
                width="stretch",
            )

        _render_quality_review(result)
        _render_inventory_review(result)

        conflicts = ((result.get("kimi_analysis") or {}).get("conflicts") or [])
        if conflicts:
            st.markdown("**Dữ kiện mâu thuẫn**")
            st.json(conflicts, expanded=True)

        for error in result.get("processing_errors") or []:
            st.warning(error)
        _render_evidence(case, repository)
        _render_delete_controls(case, repository)


def _render_queue(
    items: list[tuple[StoredCase, dict[str, Any]]],
    repository: LocalEvidenceRepository,
    *,
    queue_key: str,
) -> None:
    if not items:
        st.info("Chưa có hồ sơ trong nhóm này.")
        return

    item_by_case_id = {case.case_id: (case, result) for case, result in items}
    selected_case_id = st.selectbox(
        "Chọn hồ sơ",
        options=list(item_by_case_id),
        format_func=lambda case_id: _case_title(*item_by_case_id[case_id]),
        key=f"accounting-case-selector-{queue_key}",
    )
    case, result = item_by_case_id[selected_case_id]
    _render_case(case, result, repository)


def render_accounting_review(repository: LocalEvidenceRepository) -> None:
    st.markdown(
        """
        <div class="ir-page-heading">
          <div class="page-kicker">Dành cho kế toán</div>
          <h1>Kiểm tra hồ sơ</h1>
          <p>Xem kết quả rule, OCR và reasoning đã được lưu cho từng hồ sơ.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    processed = []
    for case in repository.list_cases():
        result = repository.load_processing_result(case.case_id)
        if result is not None:
            processed.append((case, result))

    passed = [item for item in processed if item[1].get("decision") == "PASS"]
    needs_human = [
        item for item in processed if item[1].get("decision") == "NEEDS_HUMAN"
    ]

    passed_tab, human_tab = st.tabs(
        [f"Đã pass ({len(passed)})", f"Cần xác minh ({len(needs_human)})"]
    )
    with passed_tab:
        _render_queue(passed, repository, queue_key="passed")
    with human_tab:
        _render_queue(needs_human, repository, queue_key="needs-human")
