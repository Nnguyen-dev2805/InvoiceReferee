# Danh mục phân công đọc code Hoangha

Snapshot: `1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8`. Phạm vi ban đầu: **94 file**, **21.196 dòng**. Phạm vi cuối: **97 file**, xem phần bổ sung cuối tài liệu.

Danh mục này là phạm vi đọc, chưa phải xác nhận đã đọc. Mỗi báo cáo phải có marker reviewed-file cho từng file thực sự đọc đầy đủ.

| File | Dòng | Báo cáo phụ trách |
| --- | ---: | --- |
| `.env.example` | 20 | [01-domain-config](01-domain-config.md) |
| `.gitignore` | 16 | [01-domain-config](01-domain-config.md) |
| `.streamlit/config.toml` | 13 | [07-streamlit-inventory](07-streamlit-inventory.md) |
| `app/__init__.py` | 1 | [06-fastapi-frontend](06-fastapi-frontend.md) |
| `app/components/__init__.py` | 1 | [07-streamlit-inventory](07-streamlit-inventory.md) |
| `app/components/bbox_overlay.py` | 118 | [07-streamlit-inventory](07-streamlit-inventory.md) |
| `app/components/sidebar.py` | 34 | [07-streamlit-inventory](07-streamlit-inventory.md) |
| `app/components/submission_form.py` | 164 | [07-streamlit-inventory](07-streamlit-inventory.md) |
| `app/fastapi_app.py` | 62 | [06-fastapi-frontend](06-fastapi-frontend.md) |
| `app/state/__init__.py` | 1 | [07-streamlit-inventory](07-streamlit-inventory.md) |
| `app/state/submission_state.py` | 31 | [07-streamlit-inventory](07-streamlit-inventory.md) |
| `app/static/css/app.css` | 363 | [06-fastapi-frontend](06-fastapi-frontend.md) |
| `app/static/js/settlement-form.js` | 353 | [06-fastapi-frontend](06-fastapi-frontend.md) |
| `app/streamlit_app.py` | 99 | [07-streamlit-inventory](07-streamlit-inventory.md) |
| `app/styles.py` | 270 | [07-streamlit-inventory](07-streamlit-inventory.md) |
| `app/templates/accounting/_finding_body.html` | 68 | [06-fastapi-frontend](06-fastapi-frontend.md) |
| `app/templates/accounting/case_detail.html` | 390 | [06-fastapi-frontend](06-fastapi-frontend.md) |
| `app/templates/accounting/queue.html` | 97 | [06-fastapi-frontend](06-fastapi-frontend.md) |
| `app/templates/base.html` | 37 | [06-fastapi-frontend](06-fastapi-frontend.md) |
| `app/templates/employee/case_status.html` | 36 | [06-fastapi-frontend](06-fastapi-frontend.md) |
| `app/templates/employee/new_settlement.html` | 141 | [06-fastapi-frontend](06-fastapi-frontend.md) |
| `app/views/__init__.py` | 1 | [07-streamlit-inventory](07-streamlit-inventory.md) |
| `app/views/accounting_review.py` | 560 | [07-streamlit-inventory](07-streamlit-inventory.md) |
| `app/views/employee_submission.py` | 65 | [07-streamlit-inventory](07-streamlit-inventory.md) |
| `app/views/ocr_debug.py` | 369 | [07-streamlit-inventory](07-streamlit-inventory.md) |
| `app/web/__init__.py` | 1 | [06-fastapi-frontend](06-fastapi-frontend.md) |
| `app/web/ocr_preview.py` | 103 | [06-fastapi-frontend](06-fastapi-frontend.md) |
| `app/web/routes.py` | 871 | [06-fastapi-frontend](06-fastapi-frontend.md) |
| `app/web/runtime.py` | 72 | [06-fastapi-frontend](06-fastapi-frontend.md) |
| `docs/new/assets/employee_workflow.html` | 93 | [09-data-tooling](09-data-tooling.md) |
| `docs/new/assets/system_workflow.html` | 103 | [09-data-tooling](09-data-tooling.md) |
| `pyproject.toml` | 29 | [01-domain-config](01-domain-config.md) |
| `scripts/generate_uc3_testcases.py` | 1981 | [09-data-tooling](09-data-tooling.md) |
| `scripts/qa_uc3_testcases.py` | 184 | [09-data-tooling](09-data-tooling.md) |
| `scripts/restructure_mistral_ocr.py` | 55 | [09-data-tooling](09-data-tooling.md) |
| `src/invoice_referee/__init__.py` | 3 | [01-domain-config](01-domain-config.md) |
| `src/invoice_referee/application/__init__.py` | 18 | [04-settlement-matching-policy](04-settlement-matching-policy.md) |
| `src/invoice_referee/application/decision_guard.py` | 90 | [07-streamlit-inventory](07-streamlit-inventory.md) |
| `src/invoice_referee/application/paper_evidence_matching.py` | 434 | [04-settlement-matching-policy](04-settlement-matching-policy.md) |
| `src/invoice_referee/application/process_case.py` | 837 | [07-streamlit-inventory](07-streamlit-inventory.md) |
| `src/invoice_referee/application/process_settlement.py` | 1008 | [04-settlement-matching-policy](04-settlement-matching-policy.md) |
| `src/invoice_referee/application/review_settlement.py` | 101 | [05-storage-lifecycle](05-storage-lifecycle.md) |
| `src/invoice_referee/application/settlement_summary.py` | 90 | [05-storage-lifecycle](05-storage-lifecycle.md) |
| `src/invoice_referee/application/submit_case.py` | 121 | [05-storage-lifecycle](05-storage-lifecycle.md) |
| `src/invoice_referee/application/submit_settlement.py` | 167 | [05-storage-lifecycle](05-storage-lifecycle.md) |
| `src/invoice_referee/config.py` | 53 | [01-domain-config](01-domain-config.md) |
| `src/invoice_referee/domain/__init__.py` | 125 | [01-domain-config](01-domain-config.md) |
| `src/invoice_referee/domain/decisions.py` | 52 | [01-domain-config](01-domain-config.md) |
| `src/invoice_referee/domain/errors.py` | 9 | [01-domain-config](01-domain-config.md) |
| `src/invoice_referee/domain/processing.py` | 224 | [01-domain-config](01-domain-config.md) |
| `src/invoice_referee/domain/settlement.py` | 339 | [01-domain-config](01-domain-config.md) |
| `src/invoice_referee/domain/submission.py` | 67 | [01-domain-config](01-domain-config.md) |
| `src/invoice_referee/extraction/__init__.py` | 41 | [02-ocr-quality](02-ocr-quality.md) |
| `src/invoice_referee/extraction/confidence.py` | 42 | [02-ocr-quality](02-ocr-quality.md) |
| `src/invoice_referee/extraction/conflict_reasoning.py` | 130 | [03-llm-contracts](03-llm-contracts.md) |
| `src/invoice_referee/extraction/evidence_reconciliation.py` | 27 | [03-llm-contracts](03-llm-contracts.md) |
| `src/invoice_referee/extraction/kimi_reasoning.py` | 572 | [03-llm-contracts](03-llm-contracts.md) |
| `src/invoice_referee/extraction/mistral_ocr.py` | 86 | [02-ocr-quality](02-ocr-quality.md) |
| `src/invoice_referee/extraction/network_resilience.py` | 104 | [02-ocr-quality](02-ocr-quality.md) |
| `src/invoice_referee/extraction/ocr_quality.py` | 89 | [02-ocr-quality](02-ocr-quality.md) |
| `src/invoice_referee/extraction/word_block_mapper.py` | 355 | [02-ocr-quality](02-ocr-quality.md) |
| `src/invoice_referee/policy/__init__.py` | 20 | [04-settlement-matching-policy](04-settlement-matching-policy.md) |
| `src/invoice_referee/policy/document_validity.py` | 627 | [04-settlement-matching-policy](04-settlement-matching-policy.md) |
| `src/invoice_referee/policy/inventory.py` | 568 | [07-streamlit-inventory](07-streamlit-inventory.md) |
| `src/invoice_referee/policy/settlement.py` | 338 | [04-settlement-matching-policy](04-settlement-matching-policy.md) |
| `src/invoice_referee/storage/__init__.py` | 19 | [05-storage-lifecycle](05-storage-lifecycle.md) |
| `src/invoice_referee/storage/base.py` | 17 | [05-storage-lifecycle](05-storage-lifecycle.md) |
| `src/invoice_referee/storage/local_case_store.py` | 158 | [05-storage-lifecycle](05-storage-lifecycle.md) |
| `src/invoice_referee/storage/local_evidence_repository.py` | 158 | [05-storage-lifecycle](05-storage-lifecycle.md) |
| `src/invoice_referee/storage/sqlite_settlement_repository.py` | 1279 | [05-storage-lifecycle](05-storage-lifecycle.md) |
| `tests/integration/test_fastapi_app.py` | 274 | [08-tests](08-tests.md) |
| `tests/integration/test_streamlit_app.py` | 190 | [08-tests](08-tests.md) |
| `tests/unit/test_accounting_case_view.py` | 159 | [08-tests](08-tests.md) |
| `tests/unit/test_accounting_review.py` | 132 | [08-tests](08-tests.md) |
| `tests/unit/test_bbox_overlay.py` | 43 | [08-tests](08-tests.md) |
| `tests/unit/test_document_validity.py` | 315 | [08-tests](08-tests.md) |
| `tests/unit/test_evidence_repository.py` | 68 | [08-tests](08-tests.md) |
| `tests/unit/test_inventory_policy.py` | 395 | [08-tests](08-tests.md) |
| `tests/unit/test_kimi_reasoning.py` | 350 | [08-tests](08-tests.md) |
| `tests/unit/test_local_case_store.py` | 39 | [08-tests](08-tests.md) |
| `tests/unit/test_mistral_ocr.py` | 82 | [08-tests](08-tests.md) |
| `tests/unit/test_network_resilience.py` | 58 | [08-tests](08-tests.md) |
| `tests/unit/test_ocr_preview.py` | 54 | [08-tests](08-tests.md) |
| `tests/unit/test_ocr_quality.py` | 78 | [08-tests](08-tests.md) |
| `tests/unit/test_paper_evidence_matching.py` | 312 | [08-tests](08-tests.md) |
| `tests/unit/test_process_case.py` | 904 | [08-tests](08-tests.md) |
| `tests/unit/test_settlement_policy.py` | 291 | [08-tests](08-tests.md) |
| `tests/unit/test_settlement_summary.py` | 55 | [08-tests](08-tests.md) |
| `tests/unit/test_sqlite_settlement_repository.py` | 902 | [08-tests](08-tests.md) |
| `tests/unit/test_submit_case.py` | 79 | [08-tests](08-tests.md) |
| `tests/unit/test_uc3_testcase_catalog.py` | 55 | [08-tests](08-tests.md) |
| `tests/unit/test_word_block_mapper.py` | 135 | [08-tests](08-tests.md) |
| `tests/unit/test_word_confidence.py` | 65 | [08-tests](08-tests.md) |
| `tools/generate_uc3_testcases_v2.py` | 991 | [09-data-tooling](09-data-tooling.md) |

## Bổ sung từ kiểm kê cuối

Phát hiện thêm dependency manifest và hai notebook experiments ngoài các hậu tố code ban đầu. Tổng phạm vi cuối **97 file**. Notebook review đọc toàn bộ code cells/markdown/metadata; persisted outputs không được coi là bằng chứng runtime mới. Debug log và hai PNG asset tĩnh không phải source code.

| File | Dòng vật lý | Báo cáo |
| --- | ---: | --- |
| `requirements.txt` | 11 | [15](15-experiments-environment.md) |
| `notebooks/easyocr_hoa_don.ipynb` | 399 | [15](15-experiments-environment.md) |
| `notebooks/test_kimi_vision.ipynb` | 243 | [15](15-experiments-environment.md) |
