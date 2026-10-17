# InvoiceReferee — RUNBOOK (clean clone → public pilot)

Trạng thái: cấu hình/one-entry đã có; **deploy lên hosting công khai và pilot
người thật CHƯA chạy** (xem §5 "Còn thiếu"). Đây là runbook tái lập, không phải
bằng chứng runtime.

## 1. Prerequisites

- Python **3.12** (`.python-version`), resolver **uv**.
- Node **24** (`.node-version`) + npm (chỉ để build frontend một lần).
- (Tuỳ chọn) Docker + compose cho container single-process.
- (Chỉ LIVE) credentials: `MISTRAL_API_KEY`, `MISTRAL_OCR_MODEL`,
  `XKIRO_API_KEY`, `XKIRO_BASE_URL`, `INVOICE_REFEREE_LLM_MODEL`.
  LangSmith là **opt-in**, không bắt buộc.

### Kiểm chứng evidence prompt hardening (16/10/2026)

Các prompt nằm trong `src/invoice_referee/evidence/prompts.py`; reader identity
bao gồm prompt/profile/model và representation `ocr-pages-block-words-v2`.
Đổi prompt/model làm bản đọc cũ hết điều kiện reuse; không cần xóa DB. GET bản
nháp vẫn không gọi provider; đọc lại tường minh mới dùng cấu hình mới. Không tự
ghi nhận ứng/hoàn chỉ vì OCR đọc được biên nhận.

Chạy audit cô lập (đủ tám development case, không dùng DB web):

```bash
rtk proxy uv run --frozen python scripts/run_prompt_hardening_audit.py \
  --mode LIVE --manifest data/demo/manifest.json \
  --as-of 2026-10-16T12:00:00+07:00 \
  --output-dir .runtime/prompt-hardening/new-audit
```

Output directory phải mới. Cần provider keys thật; thiếu key trả NOT_RUN, không
hạ STUB. Mỗi case có DB/uploads/artifacts riêng. `--baseline-ref 08acde6` chạy thêm
baseline frozen; gold/scoring chỉ ở harness ngoài runtime. Luôn giữ các lượt lỗi.
Exit1 có thể gồm gap dữ liệu như TC03: profile TRAVEL thiếu nơi/thời gian trên giấy,
nên chưa đạt mục tiêu BALANCED; không sửa nguồn hoặc tự điền ngày để ép PASS.
Xem [acceptance report](reviews/2026-10-16-evidence-prompt-hardening-acceptance.md)
để biết bản code và gate thực sự được kiểm, không dùng hướng dẫn này làm proof.

## 2. Clean clone → chạy mặc định (LIVE)

**Mặc định là LIVE**: server đọc tài liệu bạn upload (Mistral OCR + model). Điền
`.env` trước (xem §3).

```bash
git clone <repo> && cd InvoiceReferee
cp .env.example .env            # điền key để chạy LIVE (xem §3)
uv sync --frozen                # cài đúng uv.lock
npm --prefix frontend ci        # cài frontend
npm --prefix frontend run build # tạo frontend/dist (server phục vụ tĩnh)
uv run python scripts/dev.py --port 8000   # mặc định LIVE
```

Mở `http://127.0.0.1:8000`. Thao tác chính nằm trong <1 phút: chọn hoạt động →
Tạo hồ sơ → đính kèm chứng từ → Nộp hồ sơ → xem yêu cầu/câu hỏi.

Ba chế độ (đều tường minh, không tự hạ cấp):

| Chế độ | Lệnh | Ý nghĩa |
| --- | --- | --- |
| **LIVE** (mặc định) | `scripts/dev.py` | Đọc tài liệu thật; cần key trong `.env`. |
| **STUB** | `scripts/dev.py --mode stub` | Bản ghi tay có sẵn, chạy offline (không cần key). |
| **RECORDED_REPLAY** | `scripts/dev.py --mode replay` | Phát lại bản ghi provider; không recording thì read miss (không bịa). |
| **REPLAY fixture (S6)** | xem dưới | Đọc fixture deterministic không provider (dev/test). |

> Lưu ý: ở LIVE, sau khi pipeline chứng cứ đọc xong, consumer typed (plan A5) chạy
> admission mapper thuần → Reconciler và phát hành yêu cầu chi/thu thật khi mọi gate
> đủ căn cứ (ví dụ pilot F01 → COLLECT 760.000, F02 → PAY 400.000). Nếu report đã
> publish nhưng consumer chưa chạy, case ở `EVIDENCE_READY`
> (`assessment_blocker=EVIDENCE_ASSESSMENT_PENDING`). Q32 là lời xác nhận của nhân
> viên (không phải xác minh ngân hàng), chỉ trong ngưỡng E≤8tr/|S|≤4tr.

Kiểm tra health (đã lọc secret):

```bash
curl -s http://127.0.0.1:8000/api/health
```

## 3. Chạy LIVE

Điền `.env` (5 key, xem `.env.example`) rồi chạy mặc định — không cần cờ `--mode`:

```bash
uv run python scripts/dev.py --port 8000
# hoặc tường minh: uv run python scripts/dev.py --mode live --port 8000
```

Thiếu key ⇒ lệnh **dừng (exit 2) và in tên biến thiếu**, không tự hạ cấp. Không có
chế độ giả lập ngầm. Chạy offline để demo/test: thêm `--mode stub`.

Luồng kế toán ghi nhận khoản ứng, xác nhận đã đối chiếu lịch sử tiền và kiểm tra
lệnh thu/chi nằm trong [runbook kế toán](ACCOUNTANT_ADVANCE_COVERAGE_RUNBOOK.md).
Không dùng coverage mẫu để khẳng định đã kiểm tra sổ ngân hàng thực tế.

## 4. Container (single process, volume bền)

```bash
docker compose build
docker compose up
```

- Ảnh chạy **một** Uvicorn process phục vụ cả API và frontend tĩnh.
- DB + uploads ở volume `/data` (sống qua restart).
- Secret lấy từ `.env` (đã gitignore), không nhúng vào image.
- Healthcheck gọi `/api/health`.

Reset sandbox (xoá dữ liệu local):

```bash
docker compose down -v && docker compose up
```

## 5. Còn thiếu (capability gaps — cần người dùng)

- **Hosting công khai**: chưa được cấp URL/hạ tầng. Bàn giao image + runbook;
  cần: nhà cung cấp hosting, domain/TLS, biến môi trường secret, và (nếu muốn
  LIVE) credentials. **Không dùng localhost để claim public URL.**
- **Pilot người thật**: cần ≥3 practitioner do **người dùng mời** (protocol T2).
  Agent không mời/tạo người tham gia.
- **Calibration10/validation10**: dataset authoring đã có khung (xem
  `data/evaluation`); cần nhãn feedback thật để chốt ngưỡng ở T11.

## 6. Kiểm chứng nhanh (không phải deploy)

```bash
uv run pytest                                   # unit + integration
npm --prefix frontend run build                 # frontend build
npm --prefix frontend exec playwright test      # browser checkpoint (Chromium)
uv run invoice-referee evaluate --suite development --mode stub \
  --output .runtime/evidence/baseline
```

## 7. Browser fixture S6 (không provider, không DB người dùng)

Seed MỘT lần (PDF fixture chứa timestamp nên mỗi lần seed đổi digest —
luôn seed rồi chạy server/flow ngay sau, không seed xen giữa):

```bash
rtk proxy uv run --frozen python scripts/seed_s6_browser.py  # -> .runtime/s6-browser/
for spec in "65133:a" "65134:a2" "65132:b" "65135:c" "65136:d"; do
  port="${spec%%:*}"; key="${spec##*:}"
  rtk proxy uv run --frozen python scripts/dev.py --mode replay --port "$port" \
    --db ".runtime/s6-browser/$key.sqlite" --uploads ".runtime/s6-browser/uploads-$key" \
    --context ".runtime/s6-browser/context-$key.json" \
    --fake-llm-dir .runtime/s6-browser/fake-llm \
    --demo-as-of 2026-10-16T12:00:00+07:00 &
done
BROWSER_BASE_URL=http://127.0.0.1:65132 rtk proxy node frontend/s6-flow-b.mjs  # giấy tạm ứng
BROWSER_BASE_URL=http://127.0.0.1:65133 rtk proxy node frontend/s6-flow-a.mjs   # tự chi + type-conflict
BROWSER_BASE_URL=http://127.0.0.1:65134 rtk proxy node frontend/s6-flow-a2.mjs  # tự chi sạch + ngoại lệ + PAY + SETTLED
BROWSER_BASE_URL=http://127.0.0.1:65135 rtk proxy node frontend/s6-flow-c.mjs   # grant thấp: chặn
```

- a: tự chi + advance đã ghi → `advance:type_conflict`. a2: tự chi + ledger rỗng +
  grant EXCEPT mô phỏng 2tr → POLICY → accept → PAY 3.7tr → partial/full → SETTLED.
  b: giấy tạm ứng mismatch → ALTERNATIVE + party_mismatch + OCR bbox. c: grant 100k →
  preview uncovered + decide bị chặn.
- Hạn mức ngoại lệ production CHƯA chốt (8tr chỉ là đề xuất); các grant trên là
  fixture seed-only, không chạm company-context.json.

### S6 continuation — 17/10/2026

- Thêm `BROWSER_BASE_URL=http://127.0.0.1:65136 rtk proxy node frontend/s6-flow-d.mjs`
  cho tự chi + đơn giấy. Paper S fixture khai ứng0, vẫn thiếu lý do alternative
  nên đúng là FACT chứ không tự PASS; không sửa TC18 gốc hoặc gold.
- A2 dùng `payout-partial.pdf` 1tr + `payout-final.pdf` 2.7tr, riêng với biên nhận
  nhân viên trả nhà cung cấp. UI tải chứng từ → xác nhận actual → nếu checkpoint
  dossier stale thì đối chiếu lại → xác nhận hoàn tất thực hiện có refs/reason.
  Reload phải SETTLED, P3.7tr/S0, PAY remaining0/CLOSED_CONFIRMED.
- Flow scripts kiểm POST response + financial state, không chỉ click + sleep.
  Seed chỉ trước toàn bộ lượt; mỗi DB một lượt. Lưu DB/artifacts cũ trước reset
  DB kiểm thử riêng. Không xóa `.runtime/s6-browser` khi server đang mở DB.
- Đây là RECORDED_REPLAY synthetic fixture, không chứng minh OCR/LLM LIVE.
  Hạn mức ngoại lệ production chưa được chốt. Không gọi legacy initial-history
  endpoint từ UI; recheck mới không tạo MANAGED_HISTORY/opening0.


## 8. Verify Core4/Escalation5 — honest replay

- Open **Kiểm chuẩn**; choose Replay (default) or explicitly confirm LIVE quota.
- Current public Replay must report **Chưa có recording thật phù hợp** /
  `NEEDS_RECORDING`, completed0, releasefalse. Existing `data/verify` recording
  JSON files are **SYNTHETIC_FIXTURE**, not provider captures. Do not alter this
  label or fabricate confidence to turn the result green.
- CLI: `rtk proxy uv run --frozen --python 3.12 python -m invoice_referee.cli evaluate --suite core --mode replay`
  (or `--suite escalation`). Missing captures exit1 honestly. `--mode stub` is
  mechanism-only and cannot release the public benchmark.
- `POST /api/verify` and `GET /api/verify/last` use an isolated evaluation service,
  never the running app workflow/DB. Reports under `.runtime/verify/run-*/` are
  retained per attempt; `last.json` is atomically replaced. Single-process run
  lock +150s/case; busy requests return409.
- `data/verify/manifest.json` locks file content, suite members, explicit upload
  roles and context/gold files. No symlink/escape allowed. A deliberate dataset
  revision requires a refreshed manifest and compatible real captures.
- Exact replay protocol is documented in `data/verify/README.md`. Captures must
  match prompts/schema/model/profile/request/source inventory. Missing/mismatch
  never calls a live provider. Human question quality remains NOT_REVIEWED.
- Combined merge evidence `.runtime/verify-fix-merge-20261017/`; six known backend
  failures remain, so do not report full-regression green or model-quality success.


## 9. Escalation response rehearsal (worktree only, offline)

Use the uncommitted codex/escalation-answerability managed worktree, not the
running main DB. `rtk proxy uv run --frozen --python 3.12 python scripts/seed_escalation_browser.py`
creates isolated synthetic input DBs under .runtime/escalation-answerability/browser.
Run private source/card-only servers from the accompanying accepted browser evidence
wrapper (`serve_browser.py <name> <port>`); the wrapper is test-only and blocks
outbound network. Frontend must be built using pinned Node24. Run
`rtk proxy node frontend/escalation-browser.mjs` against ports65201–65207.
Names: authority,compound,over,fact,collect,pay,balanced. Each fresh DB gets one
mutation run; preserve artifacts/stop owned servers before reseeding. Read-only
reload tests may use the existing run. S6 compatibility uses original s6-flow-a2
on separate65208 DB and fake transport; it does not call real providers.

Decision users review amount/action/right/source on the card, enter reason and
approve. FACT arithmetic users review an explicit before/after claim revision,
check responsibility and enter reason; original PDF is retained. It never means
money was paid. Unsupported source replacement needs corrected original docs;
free text does not waive it. Missing rights25m/20m stays blocked for higher authority.

Current main/production does not include this uncommitted worktree until an
explicit integration step. Acceptance logs and all failures remain in the worktree.
