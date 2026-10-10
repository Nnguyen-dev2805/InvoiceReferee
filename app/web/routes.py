"""HTML pages and JSON API for UC-03."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.web.runtime import WebRuntime
from invoice_referee.domain import (
    SettlementDocumentRole,
    SettlementDraft,
    SettlementUpload,
    SubmissionValidationError,
)
from invoice_referee.extraction import (
    DEFAULT_WORD_REVIEW_THRESHOLD,
)


def _runtime(request: Request) -> WebRuntime:
    return request.app.state.runtime


def _template_context(request: Request, **values: Any) -> dict[str, Any]:
    return {"request": request, **values}


RULE_LABELS = {
    "SET_CONTEXT_001": "Mục đích công việc",
    "SET_INPUT_001": "Hồ sơ đề nghị",
    "SET_ADV_001": "Thông tin tạm ứng",
    "SET_DOC_001": "Chứng từ khoản chi",
    "SET_QUALITY_001": "Chất lượng chứng từ",
    "SET_EXTRACTION_001": "Đọc dữ liệu chứng từ",
    "SET_TOTAL_001": "Đối chiếu số tiền",
    "SET_SIGNATURE_001": "Xác nhận chữ ký",
    "SET_CATEGORY_001": "Danh mục chi phí",
    "SET_LIMIT_001": "Hạn mức danh mục",
    "SET_DEADLINE_001": "Thời hạn nộp",
    "SET_AUTH_001": "Thẩm quyền phê duyệt",
    "SET_DUP_001": "Trùng chứng từ",
}


def _document_preview_kind(mime_type: str, filename: str) -> str:
    normalized = mime_type.lower()
    suffix = Path(filename).suffix.lower()
    if normalized.startswith("image/") or suffix in {
        ".bmp",
        ".jpeg",
        ".jpg",
        ".png",
        ".webp",
    }:
        return "image"
    if normalized == "application/pdf" or suffix == ".pdf":
        return "pdf"
    return "file"


def _ocr_block_index(
    repository: Any,
    case_id: str,
    documents: list[dict[str, Any]],
    requested_blocks: set[str],
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for document in documents:
        document_id = document["document_id"]
        document_blocks = {
            source_ref.split(":", 1)[1]
            for source_ref in requested_blocks
            if source_ref.startswith(f"{document_id}:")
        }
        if not document_blocks:
            continue
        artifact = repository.load_ocr_artifact(case_id, document_id)
        if artifact is None:
            continue
        response = artifact.get("response") or artifact
        for fallback_page_index, page in enumerate(response.get("pages") or []):
            page_index = page.get("index", fallback_page_index)
            dimensions = page.get("dimensions") or {}
            page_width = dimensions.get("width")
            page_height = dimensions.get("height")
            markdown = str(page.get("markdown") or "")
            confidence_scores = page.get("confidence_scores") or page.get(
                "confidenceScores"
            ) or {}
            words = confidence_scores.get(
                "word_confidence_scores"
            ) or confidence_scores.get("wordConfidenceScores") or []
            search_cursor = 0
            for block_position, block in enumerate(page.get("blocks") or []):
                block_id = f"page-{page_index}-block-{block_position}"
                if block_id not in document_blocks:
                    continue
                box = block.get("bounding_box") or {}
                if not box:
                    box = {
                        "top_left_x": block.get("top_left_x", block.get("topLeftX")),
                        "top_left_y": block.get("top_left_y", block.get("topLeftY")),
                        "bottom_right_x": block.get(
                            "bottom_right_x", block.get("bottomRightX")
                        ),
                        "bottom_right_y": block.get(
                            "bottom_right_y", block.get("bottomRightY")
                        ),
                    }
                annotation_style = None
                if page_width and page_height and all(
                    isinstance(box.get(key), (int, float))
                    for key in (
                        "top_left_x",
                        "top_left_y",
                        "bottom_right_x",
                        "bottom_right_y",
                    )
                ):
                    left = max(0.0, float(box["top_left_x"]) / page_width * 100)
                    top = max(0.0, float(box["top_left_y"]) / page_height * 100)
                    width = max(
                        0.0,
                        (float(box["bottom_right_x"]) - float(box["top_left_x"]))
                        / page_width
                        * 100,
                    )
                    height = max(
                        0.0,
                        (float(box["bottom_right_y"]) - float(box["top_left_y"]))
                        / page_height
                        * 100,
                    )
                    annotation_style = (
                        f"left:{left:.3f}%;top:{top:.3f}%;"
                        f"width:{width:.3f}%;height:{height:.3f}%;"
                    )
                content = str(block.get("content") or "")
                content_start = markdown.find(content, search_cursor)
                if content_start < 0:
                    content_start = markdown.find(content)
                content_end = (
                    content_start + len(content) if content_start >= 0 else None
                )
                if content_end is not None:
                    search_cursor = content_end
                low_words = [
                    {
                        "text": str(word.get("text") or "").strip(),
                        "confidence": float(word["confidence"]),
                    }
                    for word in words
                    if isinstance(word.get("confidence"), (int, float))
                    and float(word["confidence"]) < DEFAULT_WORD_REVIEW_THRESHOLD
                    and str(word.get("text") or "").strip()
                    and (
                        (
                            content_start >= 0
                            and isinstance(
                                word.get("start_index", word.get("startIndex")), int
                            )
                            and content_start
                            <= word.get("start_index", word.get("startIndex"))
                            < content_end
                        )
                        or (
                            content_start < 0
                            and str(word.get("text") or "").strip() in content
                        )
                    )
                ]
                index[f"{document_id}:{block_id}"] = {
                    "page_index": page_index,
                    "block_id": block_id,
                    "excerpt": content.strip(),
                    "annotation_style": annotation_style,
                    "low_words": low_words,
                }
    return index


def _decorate_accounting_case(
    case: dict[str, Any],
    repository: Any,
) -> dict[str, Any]:
    """Resolve stored source references into links suitable for audit review."""

    documents_by_id: dict[str, dict[str, Any]] = {}
    for document in case["documents"]:
        document["url"] = (
            f"/api/v1/cases/{case['case_id']}/documents/"
            f"{document['document_id']}"
        )
        document["preview_kind"] = _document_preview_kind(
            document["mime_type"], document["original_name"]
        )
        documents_by_id[document["document_id"]] = document

    items_by_id = {item["item_id"]: item for item in case["expense_items"]}
    all_source_refs = [
        source_ref
        for finding in case["findings"]
        for source_ref in finding["source_refs"]
    ]
    if case["decision"]:
        all_source_refs.extend(case["decision"]["source_refs"])
    requested_blocks = {
        raw_ref
        for source_ref in all_source_refs
        for raw_ref in [source_ref.removeprefix("DOC:")]
        if raw_ref.count(":") >= 1
    }
    block_index = _ocr_block_index(
        repository,
        case["case_id"],
        case["documents"],
        requested_blocks,
    )
    case["request_documents"] = [
        document
        for document in case["documents"]
        if document["role"] == SettlementDocumentRole.SETTLEMENT_REQUEST_FORM.value
    ]
    case["evidence_documents"] = [
        document
        for document in case["documents"]
        if document["role"] == SettlementDocumentRole.EXPENSE_EVIDENCE.value
    ]
    for item in case["expense_items"]:
        item["documents"] = [
            document
            for document in case["evidence_documents"]
            if document["linked_item_id"] == item["item_id"]
        ]

    def resolve(source_ref: str) -> dict[str, Any]:
        if source_ref.startswith("FORM:EXPENSE_ITEM:"):
            item_id = source_ref.rsplit(":", 1)[-1]
            item = items_by_id.get(item_id)
            return {
                "kind": "form",
                "label": (
                    f"Khoản chi {item_id}: {item['description']}"
                    if item
                    else f"Khoản chi {item_id}"
                ),
                "source_ref": source_ref,
            }

        raw_document_ref = source_ref.removeprefix("DOC:")
        document_parts = raw_document_ref.split(":", 1)
        document_id = document_parts[0]
        document = documents_by_id.get(document_id)
        if document:
            location = document_parts[1] if len(document_parts) > 1 else ""
            resolved = {
                "kind": "document",
                "label": document["original_name"],
                "location": location,
                "url": document["url"],
                "preview_kind": document["preview_kind"],
                "source_ref": source_ref,
            }
            block = block_index.get(f"{document_id}:{location}")
            if block:
                resolved.update(block)
            return resolved
        return {
            "kind": "reference",
            "label": source_ref,
            "source_ref": source_ref,
        }

    for finding in case["findings"]:
        finding["rule_label"] = RULE_LABELS.get(
            finding["rule_id"], finding["rule_id"]
        )
        finding["evidence_refs"] = [
            resolve(source_ref) for source_ref in finding["source_refs"]
        ]
        finding["evidence_previews"] = [
            evidence
            for evidence in finding["evidence_refs"]
            if evidence["kind"] == "document"
        ]
    attention_order = {"ERROR": 0, "FAIL": 1, "WARN": 2}
    case["attention_findings"] = sorted(
        [finding for finding in case["findings"] if finding["status"] != "PASS"],
        key=lambda finding: attention_order.get(finding["status"], 3),
    )
    case["passed_findings"] = [
        finding for finding in case["findings"] if finding["status"] == "PASS"
    ]
    if case["decision"]:
        case["decision"]["evidence_refs"] = [
            resolve(source_ref)
            for source_ref in case["decision"]["source_refs"]
        ]
    return case


def build_router(templates_root: Path) -> APIRouter:
    router = APIRouter()
    templates = Jinja2Templates(directory=str(templates_root))

    @router.get("/", include_in_schema=False)
    def home() -> RedirectResponse:
        return RedirectResponse("/employee/settlements/new", status_code=303)

    @router.get(
        "/employee/settlements/new",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def employee_form(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="employee/new_settlement.html",
            context=_template_context(request, active_page="employee"),
        )

    @router.get(
        "/employee/settlements/{case_id}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def employee_status(request: Request, case_id: str) -> HTMLResponse:
        try:
            case = _runtime(request).repository.get_case(case_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(
            request=request,
            name="employee/case_status.html",
            context=_template_context(
                request,
                active_page="employee",
                case=case,
            ),
        )

    @router.get(
        "/accounting/cases",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def accounting_queue(
        request: Request,
        decision: str | None = None,
        deleted: str | None = None,
    ) -> HTMLResponse:
        repository = _runtime(request).repository
        all_cases = repository.list_cases()
        cases = (
            repository.list_cases(decision=decision)
            if decision
            else all_cases
        )
        counts = {
            key: len(repository.list_cases(decision=key))
            for key in ("AUTO_PROCESS", "REQUEST_INFO", "ESCALATE")
        }
        counts["PROCESSING"] = len(
            [case for case in all_cases if not case["automation_decision"]]
        )
        return templates.TemplateResponse(
            request=request,
            name="accounting/queue.html",
            context=_template_context(
                request,
                active_page="accounting",
                cases=cases,
                selected_decision=decision,
                counts=counts,
                deleted_case_id=deleted,
            ),
        )

    @router.get(
        "/accounting/cases/{case_id}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def accounting_detail(request: Request, case_id: str) -> HTMLResponse:
        try:
            repository = _runtime(request).repository
            case = _decorate_accounting_case(
                repository.get_case(case_id),
                repository,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(
            request=request,
            name="accounting/case_detail.html",
            context=_template_context(
                request,
                active_page="accounting",
                case=case,
                rule_labels=RULE_LABELS,
            ),
        )

    @router.post(
        "/accounting/cases/{case_id}/actions",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def accounting_action(
        request: Request,
        case_id: str,
        action_type: Annotated[str, Form()],
        reason: Annotated[str, Form()],
        override_decision: Annotated[str | None, Form()] = None,
    ):
        try:
            _runtime(request).review_service.record_action(
                case_id=case_id,
                action_type=action_type,
                reason=reason,
                override_decision=override_decision,
            )
        except (FileNotFoundError, ValueError) as exc:
            try:
                repository = _runtime(request).repository
                case = _decorate_accounting_case(
                    repository.get_case(case_id),
                    repository,
                )
            except FileNotFoundError as missing:
                raise HTTPException(status_code=404, detail=str(missing)) from missing
            return templates.TemplateResponse(
                request=request,
                name="accounting/case_detail.html",
                status_code=422,
                context=_template_context(
                    request,
                    active_page="accounting",
                    case=case,
                    action_error=str(exc),
                ),
            )
        return RedirectResponse(
            f"/accounting/cases/{case_id}",
            status_code=303,
        )

    @router.post(
        "/accounting/cases/{case_id}/delete",
        include_in_schema=False,
    )
    def delete_accounting_case(request: Request, case_id: str) -> RedirectResponse:
        try:
            _runtime(request).repository.delete_case(case_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(
            f"/accounting/cases?deleted={case_id}",
            status_code=303,
        )

    @router.post("/api/v1/settlements", status_code=202)
    async def submit_settlement(
        request: Request,
        payload: Annotated[str, Form()],
        settlement_form: Annotated[UploadFile | None, File()] = None,
        evidence_files: Annotated[list[UploadFile] | None, File()] = None,
    ) -> JSONResponse:
        try:
            draft = SettlementDraft.model_validate(json.loads(payload))
        except (json.JSONDecodeError, ValidationError) as exc:
            return JSONResponse(
                status_code=422,
                content={"issues": [f"Dữ liệu form không hợp lệ: {exc}"]},
            )

        uploads: list[SettlementUpload] = []
        if settlement_form is not None and settlement_form.filename:
            uploads.append(
                SettlementUpload(
                    original_name=settlement_form.filename,
                    content=await settlement_form.read(),
                    mime_type=settlement_form.content_type
                    or "application/octet-stream",
                    role=SettlementDocumentRole.SETTLEMENT_REQUEST_FORM,
                )
            )

        item_by_filename: dict[str, str] = {}
        for item in draft.expense_items:
            for filename in item.evidence_names:
                key = filename.casefold()
                if key in item_by_filename and item_by_filename[key] != item.item_id:
                    return JSONResponse(
                        status_code=422,
                        content={
                            "issues": [
                                f"File '{filename}' đang được gắn vào nhiều khoản chi."
                            ]
                        },
                    )
                item_by_filename[key] = item.item_id

        for evidence in evidence_files or []:
            if not evidence.filename:
                continue
            uploads.append(
                SettlementUpload(
                    original_name=evidence.filename,
                    content=await evidence.read(),
                    mime_type=evidence.content_type
                    or "application/octet-stream",
                    role=SettlementDocumentRole.EXPENSE_EVIDENCE,
                    linked_item_id=item_by_filename.get(
                        evidence.filename.casefold()
                    ),
                )
            )

        try:
            receipt = _runtime(request).submit_service.submit(draft, uploads)
        except SubmissionValidationError as exc:
            return JSONResponse(status_code=422, content={"issues": exc.issues})
        return JSONResponse(
            status_code=202,
            content=receipt.model_dump(mode="json"),
        )

    @router.get("/api/v1/cases/{case_id}")
    def get_case(request: Request, case_id: str) -> dict[str, Any]:
        try:
            return _runtime(request).repository.get_case(case_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/v1/accounting/cases")
    def list_accounting_cases(
        request: Request,
        decision: str | None = None,
    ) -> list[dict[str, Any]]:
        return _runtime(request).repository.list_cases(decision=decision)

    @router.get("/api/v1/cases/{case_id}/documents/{document_id}")
    def get_document(
        request: Request,
        case_id: str,
        document_id: str,
    ) -> FileResponse:
        try:
            path = _runtime(request).repository.document_path(
                case_id,
                document_id,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(path)

    @router.post("/internal/process-next", include_in_schema=False)
    def process_next(request: Request) -> dict[str, bool]:
        return {"processed": _runtime(request).processor.run_once()}

    return router
