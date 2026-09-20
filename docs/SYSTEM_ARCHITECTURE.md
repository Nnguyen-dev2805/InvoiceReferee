# InvoiceReferee — System Architecture & Flow (as built)

> Tài liệu này mô tả **hệ thống đã được triển khai** trong Sprint 1, bám theo mã
> nguồn thực tế trong `src/invoice_referee/`, `verify/` và `app/`. Nó bổ sung cho
> `docs/ARCHITECTURE.md` (ranh giới module cấp thiết kế) bằng chi tiết luồng chạy,
> chữ ký hàm, và các quyết định thực thi. Trạng thái xác minh: `pytest` 191 passed,
> Verify `all` 9/9.

---

## 1. Tổng quan một câu

InvoiceReferee nhận bằng chứng của một giao dịch mua hàng (PO + Goods Receipt +
Invoice + Payment History), chạy **8 kiểm tra deterministic**, dựng **PolicyContext**,
để **LLM Agent** đề xuất đánh giá có cấu trúc, rồi một **Decision Guard deterministic**
phát hành đúng một trong ba hành động — `AUTO_PROCESS`, `REQUEST_INFO`, `ESCALATE` —
kèm audit trail và quyền Stop/Override của con người.

Nguyên tắc trung tâm:

> **Rule engine xác định facts kiểm chứng được · Agent diễn giải & đặt câu hỏi ·
> Decision Guard thực thi policy · Con người giữ quyền can thiệp cuối.**

---

## 2. Kiến trúc phân tầng

```text
┌─────────────────────────────────────────────────────────────────────┐
│  PRESENTATION            app/streamlit_app.py · app/presentation.py   │
│                          verify/harness.py (+ manifest.py)            │
│  – chỉ gọi review() và harness; không có business logic riêng         │
└───────────────────────────────┬───────────────────────────────────────┘
                                │  review(evidence, client, model)
┌───────────────────────────────▼───────────────────────────────────────┐
│  ORCHESTRATION           services/reviewer.py                          │
│  – tuyến sản xuất duy nhất; ghi audit ở mỗi bước                       │
└───┬───────────┬────────────┬──────────────┬───────────────┬───────────┘
    │           │            │              │               │
┌───▼───┐  ┌────▼─────┐  ┌───▼──────┐  ┌────▼──────┐  ┌─────▼───────┐
│INGEST │  │TRANSACT. │  │ CHECKS   │  │  POLICY   │  │   AGENT     │
│json_  │→ │builder   │→ │engine +  │→ │engine +   │→ │service +    │
│adapter│  │          │  │8 checks  │  │config     │  │prompts +    │
│normal.│  │          │  │          │  │(resolve)  │  │llm/openai   │
└───────┘  └──────────┘  └──────────┘  └───────────┘  └─────┬───────┘
                                                            │ AgentAssessment
                                            ┌───────────────▼───────────┐
                                            │  DECISION GUARD            │
                                            │  decision/guard.py +       │
                                            │  fallback_questions.py     │
                                            │  – re-resolve, override    │
                                            └───────────────┬───────────┘
                                                            │ Decision
                                            ┌───────────────▼───────────┐
                                            │  AUDIT  audit/store.py     │
                                            │  append-only + Stop/Override│
                                            └────────────────────────────┘
                        DOMAIN  domain/models.py  (16 contracts dùng chung mọi tầng)
```

**Quy tắc phụ thuộc:** mỗi tầng chỉ phụ thuộc schema đầu vào/đầu ra trong
`domain/models.py`, không phụ thuộc chi tiết nội bộ của tầng khác. `domain/` không
import bất kỳ module nghiệp vụ nào (chỉ chứa contract).

---

## 3. Bản đồ module → trách nhiệm → chữ ký chính

| Module | Trách nhiệm | Entry point |
| --- | --- | --- |
| `domain/models.py` | 16 dataclass contract + enum; validate integer VND, tri-state scope | — |
| `ingestion/json_adapter.py` | Raw dict → `ExtractedDocument` (giữ `source_ref`, `parse_warnings`) | `extract_document()` |
| `ingestion/normalization.py` | Chuẩn hoá money/date/id; unknown giữ `None` | `normalize_money/date/id`, `to_*()` |
| `transaction/builder.py` | Gom evidence → `Transaction`; phân loại type tri-state | `build_transaction(evidence)` |
| `checks/engine.py` + 8 file | 8 kiểm tra deterministic → `list[CheckResult]` | `run_checks(tx)` |
| `policy/config.py` | Policy v0 constants (threshold 50M, P01–P15, targets) | — |
| `policy/engine.py` | `PolicyContext` + mapping deterministic action | `build_policy_context`, `resolve_action`, `classify_scope` |
| `agent/service.py` | Gọi LLM, parse + validate strict, fallback có audit | `assess(tx, checks, ctx, client, model)` |
| `agent/prompts.py` | Prompt v1 (chỉ facts/checks/context) | `build_prompt` |
| `agent/llm_client.py` | Interface trừu tượng + `LLMError`/`LLMTimeout` | `LLMClient` |
| `agent/openai_client.py` | Client OpenAI-compatible (stdlib urllib) | `OpenAICompatibleClient` |
| `agent/config.py` | Đọc `.env`/env → client, thiếu key → `None` | `client_from_env()` |
| `decision/guard.py` | Chốt chặn cuối; re-resolve + override proposal | `guard(assessment, tx, checks, ctx)` |
| `decision/fallback_questions.py` | Template câu hỏi cụ thể theo rule/check | `build_question` |
| `audit/store.py` | Audit append-only + Stop/Override | `AuditStore` |
| `services/reviewer.py` | Orchestrator sản xuất | `review(evidence, client, model)` |
| `verify/harness.py` | Chạy fixtures qua `review()`, suites core/escalation/all | `run_verify`, `run_suite` |
| `verify/manifest.py` | Expected labels + suite membership (ngoài production) | — |
| `app/streamlit_app.py` | UI giám khảo | — |
| `app/presentation.py` | Helper thuần cho UI (testable) | `format_vnd`, `load_sample`, ... |

---

## 4. System flow chi tiết (end-to-end)

Đây là đúng chuỗi thực thi trong `services/reviewer.review()`.

```text
review(evidence, client=None, model=None)
│
├─ 1. build_transaction(evidence)                         [transaction/builder.py]
│      • po/gr/invoice/prior_invoices/payment/approvals ← normalization
│      • classify type: declared khớp → PO_GOODS_PURCHASE
│                       declared lạ    → None + declared_transaction_type
│                       không có       → suy từ PO reference / None
│      → Transaction
│      ↳ audit: TRANSACTION_CREATED
│
├─ 2. run_checks(tx)                                       [checks/engine.py]
│      • nếu type ≠ PO_GOODS_PURCHASE → 8× NOT_APPLICABLE (không bịa fail)
│      • ngược lại chạy theo thứ tự:
│        vendor→item→quantity→price→amount→duplicate→payment→po_limit
│      • mỗi check trả CheckResult{status, policy_rule_id, expected, actual, refs}
│      • PASS/FAIL/UNKNOWN/NOT_APPLICABLE — KHÔNG trả action
│      → list[CheckResult]
│      ↳ audit: CHECK_COMPLETED ×8
│
├─ 3. build_policy_context(tx, checks)                     [policy/engine.py]
│      • scope_status = classify_scope(tx): IN_SCOPE | OUTSIDE_POLICY | UNKNOWN
│      • authority_threshold_vnd = 50_000_000 (synthetic)
│      • applicable_rule_ids ← rule của các check FAIL/UNKNOWN (+P12, +P13)
│      • deterministic_uncertainties ← từ resolve_action
│      → PolicyContext (immutable với LLM)
│
├─ 4. assess(tx, checks, ctx, client, model)              [agent/service.py]
│      IF client is None:
│          → fallback assessment (resolve_action + fallback_questions)
│      ELSE:
│          prompt = build_prompt(...)          [agent/prompts.py]
│          try:
│              body = client.complete(prompt)  [openai_client.py → HTTP]
│              parse strict JSON + validate references
│                 (primary_check_id ∈ checks; evidence_refs ∈ evidence;
│                  explanation bắt buộc)
│              → AgentAssessment(fallback_used=False)
│          except (LLMError/timeout/JSON/ref-invalid):
│              → fallback assessment (fallback_used=True)
│      → AgentAssessment (proposal, KHÔNG phải quyết định cuối)
│      ↳ audit: LLM_ASSESSMENT_CREATED (+ LLM_FALLBACK_USED nếu fallback)
│
├─ 5. guard(assessment, tx, checks, ctx)                   [decision/guard.py]
│      • outcome = resolve_action(tx, checks, ctx)   ← NGUỒN SỰ THẬT
│      • nếu assessment.proposed_action == outcome.action VÀ có câu hỏi hợp lệ
│            → mượn question/target của LLM
│        ngược lại → dùng fallback_questions + target của policy (override)
│      → Decision{action, reason, uncertainty, question, target, rules, decided_at}
│      ↳ audit: DECISION_GUARD_APPLIED (proposal_overridden=?), DECISION_MADE
│
└─ 6. đóng gói ReviewResult                                [domain/models.py]
       {transaction, checks, policy_context, agent_assessment, decision, audit_events}
       ← UI và Verify dùng CHUNG object này, không tự tính lại decision
```

---

## 5. Cây quyết định deterministic (`resolve_action`)

Đây là logic ưu tiên cứng — nơi duy nhất map facts → action. Cả Decision Guard lẫn
agent fallback đều gọi nó, nên **kết quả giống hệt dù có hay không có LLM**.

```text
resolve_action(tx, checks, ctx):

  scope == UNKNOWN ─────────────────────────► REQUEST_INFO  (FACTUAL_UNKNOWN, P01)
        │ no
  scope == OUTSIDE_POLICY ──────────────────► ESCALATE      (OUTSIDE_POLICY, P13 → Accounting owner)
        │ no  (IN_SCOPE)
  PO thiếu ─────────────────────────────────► REQUEST_INFO  (P01 → Purchasing)
        │ no
  Goods Receipt thiếu ──────────────────────► REQUEST_INFO  (P04 → Warehouse)
        │ no
  Invoice flagged (amount unreadable...) ───► REQUEST_INFO  (P15 → Supplier)
        │ no
  Có check FAIL/UNKNOWN (theo thứ tự) ──────► REQUEST_INFO  (rule của check → target theo check)
        │ no  (mọi check PASS)
  amount > 50M ─────────────────────────────► ESCALATE      (BEYOND_AUTHORITY, P12 → Finance Manager)
        │ no
  └─────────────────────────────────────────► AUTO_PROCESS
```

Điểm mấu chốt:

- **FAIL ≠ sai phạm.** Một check FAIL (vd amount lệch) chỉ tạo `REQUEST_INFO` vì chưa
  biết có approval hợp lệ hay không — không kết luận vi phạm.
- **UNKNOWN = thiếu evidence** → `REQUEST_INFO`. `NOT_APPLICABLE` không kích hoạt hỏi.
- **Beyond authority chỉ xét sau khi mọi check PASS** (đúng TC13: "tất cả checks pass,
  amount 120M").
- **Suspicious/flagged (P15) được ưu tiên** trước vòng quét check → không kết luận
  chắc chắn trên dữ liệu nghi vấn.

---

## 6. Ranh giới Deterministic ↔ LLM ↔ Guard

| Việc | Ai làm | Ghi chú |
| --- | --- | --- |
| So sánh vendor/item/số lượng/đơn giá/tiền | Deterministic (`checks/`) | Integer VND, không float |
| Cumulative quantity theo item, cumulative PO amount | Deterministic (`_support.py`) | Cộng prior invoices cùng PO |
| Duplicate identity, payment status, authority threshold | Deterministic | LLM không được tính |
| Chọn issue chính để hỏi, diễn giải, sinh câu hỏi | LLM Agent | Chỉ từ facts/checks/policy đã có |
| Phát hành action cuối, enforce policy | Decision Guard | Override proposal trái policy |
| Fallback khi LLM lỗi | `agent/service.py` | `fallback_used=True`, có audit |

**LLM không bao giờ** sửa facts, tính lại số, đổi rule result, hay vượt authority.
Mọi proposal đi qua Guard; proposal không an toàn (vd `AUTO_PROCESS` khi có
`FACTUAL_UNKNOWN`/`BEYOND_AUTHORITY`/flagged) bị override — có test chứng minh
(`tests/test_decision.py`, `tests/test_reviewer.py`).

---

## 7. Tầng LLM & cấu hình provider

```text
client_from_env()                              [agent/config.py]
  ├─ đọc .env (repo root) + biến môi trường LLM_*
  ├─ không có LLM_API_KEY → return None  → agent dùng deterministic fallback
  └─ có key → OpenAICompatibleClient(base_url, api_key, model, timeout)

OpenAICompatibleClient.complete(prompt)        [agent/openai_client.py]
  POST {base_url}/chat/completions
  headers: Authorization: Bearer <key>
  body: {model, messages:[{role:user, content:prompt}], temperature}
  → data["choices"][0]["message"]["content"]
  lỗi: timeout → LLMTimeout · mạng/parse → LLMError  (agent tự fallback)
```

- **Provider-agnostic:** đổi provider chỉ bằng `LLM_BASE_URL` + `LLM_MODEL` trong
  `.env` (xKiro / DeepSeek / OpenAI / gateway nội bộ). Không sửa code.
- **Chỉ dùng stdlib** (`urllib`) — không thêm dependency nặng.
- `.env` bị `.gitignore`; chỉ `.env.example` được commit.
- **`review()` và Verify mặc định `client=None`** để test/Verify deterministic,
  offline, tái lập được. Chỉ **UI** và **Verify CLI `main()`** mới tự nạp client từ
  env. Dù đường nào, Decision Guard vẫn quyết định action → luôn policy-correct.

---

## 8. Audit & Human-in-the-loop

`AuditStore` (`audit/store.py`) là append-only ở mức logic — chỉ có `append()`, không
API xoá/sửa. Event ID tuần tự (`AUD-0001…`) + timestamp ISO 8601 UTC.

Event types phát ra trong một lượt review:
```text
TRANSACTION_CREATED → CHECK_COMPLETED×8 → LLM_ASSESSMENT_CREATED
  [→ LLM_FALLBACK_USED] → DECISION_GUARD_APPLIED → DECISION_MADE
```
Human controls (thêm sau, không xoá lịch sử cũ): `STOPPED`, `OVERRIDDEN`.

| Control | Tác động | Bảo toàn |
| --- | --- | --- |
| **Stop** | `workflow_status: ACTIVE → STOPPED` | `Decision.action` giữ nguyên; KHÔNG phải decision thứ tư |
| **Override** | Lưu `original_action` + `overridden_action` | Quyết định gốc còn nguyên trong audit; `overridden_action` phải là 1 trong 3 action (STOPPED bị reject) |

---

## 9. Contract dữ liệu (16 dataclass trong `domain/models.py`)

```text
ExtractedDocument                     ← ranh giới extraction
PurchaseOrder · GoodsReceipt · SupplierInvoice · PaymentRecord · ApprovalRecord
Transaction                           ← object trung tâm (+prior_invoices, human_*)
CheckResult · Uncertainty · PolicyContext
AgentAssessment                       ← proposal của LLM (không phải quyết định)
Decision · ReviewResult
AuditEvent · HumanStop · HumanOverride
```

Ràng buộc thực thi ở tầng contract:
- **Money = integer VND**: `_money()` từ chối `float`, `bool`, số âm.
- **Quantity = integer**: `_quantity()` tương tự.
- **`ScopeStatus` tri-state** (không dùng boolean) — `UNKNOWN`→REQUEST_INFO,
  `OUTSIDE_POLICY`→ESCALATE.
- **`SupplierInvoice.total_amount` optional**: amount không đọc được giữ `None`
  (không đoán) và invoice tự `flagged`.
- **`HumanOverride.overridden_action`** ép về `DecisionAction` — `"STOPPED"` bị loại.

---

## 10. Verify harness (đường chấm của giám khảo)

```text
python -m verify.harness --suite all       # 1 thao tác → Core + Escalation
                         --suite core       # TC01, TC07, TC13, TC14
                         --suite escalation  # TC01, TC02, TC03, TC07, TC13
```

- `verify_evidence()` gọi **đúng production `review()`** rồi so `decision.action` với
  `verify/manifest.py`. Harness **không** có logic quyết định riêng.
- Manifest (expected labels) sống trong `verify/`, production `review()` **không đọc**
  → không branch theo case ID (có test `inspect.getsource` khẳng định).
- Bảng output: suite · case · expected · actual · PASS/FAIL · uncertainty · target ·
  LLM/fallback · question · timestamp. Exit code 0/1.

Kết quả hiện tại: **core 4/4 · escalation 5/5 · all 9/9**.

---

## 11. Tính chính xác & kiểm chứng

| Hạng mục | Cách kiểm | Trạng thái |
| --- | --- | --- |
| Unit + integration + smoke | `pytest -q` | **191 passed** |
| 17 documented cases | `verify/harness` parametrized | khớp manifest |
| Core / Escalation / All | CLI + `tests/test_verify.py` | 4/4 · 5/5 · 9/9 |
| Unseen input (không sửa code) | mutation 42M→AUTO, 75M→ESCALATE | pass |
| LLM proposal không an toàn | `UnsafeClient` luôn AUTO_PROCESS | Guard vẫn ESCALATE/REQUEST_INFO |
| Provider lỗi/timeout/JSON hỏng | fake clients | fallback + policy-correct |
| Stop/Override bảo toàn lịch sử | `tests/test_audit.py` | pass |

**Giới hạn đã biết (trung thực):**
- Policy v0 và threshold 50M là **synthetic**, không phải quy định pháp lý.
- Sprint 1 chỉ hỗ trợ `PO_GOODS_PURCHASE`; loại khác → OUTSIDE_POLICY (ESCALATE).
- Chưa test với người dùng thật (thuộc Sprint 2).
- Câu hỏi fallback in số VND thô; định dạng đẹp là polish, không ảnh hưởng đúng/sai.
- Audit là in-memory + export JSON (chưa persistent storage).

---

## 12. Đối chiếu Slide 2 (Input → Xử lý → Đầu ra & điểm quyết định con người)

```text
INPUT                         XỬ LÝ (tự động)                     ĐẦU RA
PO ┐                     normalize → build tx → 8 checks     AUTO_PROCESS ─► payment review
GR ┼─► evidence JSON ──► → policy context → LLM assess ──►   REQUEST_INFO ─► câu hỏi cụ thể
INV┤                     → DECISION GUARD (deterministic)     ESCALATE ─────► người có thẩm quyền
PAY┘                                                          │
                                              ĐIỂM QUYẾT ĐỊNH CON NGƯỜI ▼
                                        Stop (giữ decision) · Override (giữ bản gốc)
```

Con người đứng ở **hai điểm rõ ràng**: (1) trả lời `REQUEST_INFO`/`ESCALATE` để hệ
thống re-evaluate, và (2) Stop/Override sau bất kỳ quyết định nào. `AUTO_PROCESS`
chỉ đưa hồ sơ sang bước payment review — **không tự chuyển tiền**.
```
