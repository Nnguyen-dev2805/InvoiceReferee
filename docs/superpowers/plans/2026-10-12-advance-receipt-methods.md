# Ghi nhận ứng qua ngân hàng / tiền mặt — Implementation Plan

> **For agentic workers:** Dùng `executing-plans`, làm P1–P4 tuần tự, regression RED trước sửa. Không tự commit/LIVE/publish/subagent. Chủ dự án yêu cầu plan cho coding agent; đợt soạn này chỉ dọn test-kit và viết tài liệu, chưa triển khai ứng dụng.

**Goal:** Kế toán ghi nhận khoản ứng đã thực hiện bằng form đúng phương thức, có căn cứ; không để một status/checkbox hoặc lệnh chuyển tiền tự thành tiền thực nhận.

**Architecture:** Giữ một `AdvanceReceiptPanel`, hai nhánh BANK_TRANSFER/CASH và các route B5 hiện có. Backend giữ raw event, phân loại theo evidence trước khi cộng funding; metadata khác phương thức được lưu trong money JSON, không thêm bảng/ngân hàng/role mới. PDF test tạo theo nhu cầu bên trong L01, không dựng sẵn thêm case toàn cục.

**Tech Stack:** React/TypeScript; FastAPI/Pydantic/SQLite hiện có. Authoring PDF dùng reportlab/pypdf/Pillow/pypdfium2 trong runtime có sẵn, không thêm dependency vào app để làm test data.

**Spec:** Bố cục đã chốt với chủ dự án ngày12/10/2026 ở D1–D4 bên dưới; [Product P2a/P3](../../settlement/PRODUCT.md), [Rulebook R1/R6/R9](../../settlement/RULEBOOK.md), [System S6/S10](../../settlement/SYSTEM.md). Chứng từ chuyển khoản tham khảo [Vietcombank](https://www.vietcombank.com.vn/upload/HDSD%20VCB-ib%40nking%20KHTC_VNI.pdf); tiền mặt tham khảo [MISA SME2026](https://helpsme.misa.vn/2026/kb/tam_ung_cho_nhan_vien_bang_tien_mat/). Đây là thiết kế ghi nhận cho MVP, không cam kết pháp lý/xác thực ngân hàng hoặc chữ ký.

**Status:** IMPLEMENTED (P1–P4 code + tests + data); UI/LIVE not executed.
Snapshot `0010329`, branch `rebuild`; working tree có UI sửa dở và các deletion
data/pdf của writer khác. Đọc current diff, không reset/restore/ghi đè các phần đó.
CodeGraph có source/trace, nhưng generation/coverage API không exposed; không
claim audit toàn repo.

## Tiến độ thực thi (2026-10-12)

- **P1 (xong)**: RED `test_received_without_evidence_never_fulfills` tái hiện
  probe; GREEN thêm `B3BankReceiptDetails`/`B3CashReceiptDetails`/`receipt_details`/
  `evidence_issues`, `B3ReceiptSource` + `B3CompanyContext.receipt_sources`,
  `validate_advance_receipt`, `derive_classification(evidence_ok=...)` (không default
  True), API `receipt_details` + `demo-context.receipt_sources`. Matrix P1.3 (10 test)
  bank pending/debit-only, cash acknowledged/unsigned, missing-config, duplicate
  evidence, unread, kind-mismatch 422, old-view compat.
- **P2 (xong)**: `AdvanceReceiptPanel` hai nhánh BANK/CASH, bắt buộc proof +
  receiver_name + proof_scope/acknowledgement, nguồn chi từ config, người nhận theo
  tên; mirror TS; wiring `people`/`receiptSources` qua CaseActionsPanel/App. +6 test.
- **P3 (xong)**: `tools/build_advance_receipt_variants.py` (reportlab/pypdf/Pillow)
  chỉ tạo biến thể được yêu cầu; đã tạo **bank received**; `config/b3-receipt-methods.json`
  (`BANK:L01-COMPANY`, `CASH:L01-QUY-CHINH`); L01 manifest append hash (giữ file cũ);
  CHECKLIST §5.2/§5.4 cập nhật; biến thể khác chỉ trong plan.
- **P4 (xong phần code/test)**: integration `test_b3_receipt_methods.py` (10 test);
  SYSTEM.md B5 gate + PRODUCT.md B5 hai nhánh. Checks: backend **514 passed**,
  frontend **153 passed**, build OK, golden identical, `pip check` sạch.
- **Chưa chạy (USER_UI_UNEXECUTED / LIVE_UNEXECUTED)**: browser UI, LIVE Mistral/xkiro,
  full L01 workflow trên app; P4.2/P4.3-UI cần người dùng thực thi.
- **Phát hiện ngoài phạm vi (writer khác)**: `App.tsx` có `b7PathMode` khai báo chết
  (không dùng) làm `tsc` fail; đã xoá **một dòng** đó để build xanh (không reset/restore
  phần khác của họ). `70-b7-desk.css` có blank line EOF của họ — không đụng.

## 0. Bằng chứng và việc đã làm lúc soạn plan

- `AdvanceReceiptPanel.tsx:50–65` không yêu cầu proofId khi bật nút ghi; method CASH vẫn hiện namespace/mã giao dịch ngân hàng.
- `contracts/advance.py:201–217` chỉ check ghi chú/amount dương. `record_receipt` kiểm source ownership nếu có evidence nhưng bỏ qua khi evidence rỗng; `derive_classification` không check evidence.
- Probe **FAKE_TEMP_DB** đã chạy qua Service/Store/fixture approved_b3: gửi RECEIVED2 triệu, COMPANY, đúng payee, **evidence=[]** → CONFIRMED_RECEIPT, funding FULFILLED, stage AWAITING_WORK_SETTLEMENT. Đây là lỗi đã tái hiện, không phải giả định UI.
- Theo yêu cầu chủ dự án đã xóa **47 thư mục case trống** trong `data/test-kit/cases`; giữ A02/L01, giữ nguyên hash của46 files bên trong. Checklist/manifest chỉ còn hai case hiện làm. Chưa xóa input/output nào, chưa sinh PDF phương thức mới.

## Global constraints

- Scope khoảng5 người, HUMAN_SOURCE_REVIEW; không login/ERP/bank API, không thêm role Thủ quỹ. Người giao tiền là dữ kiện trên phiếu; kế toán vẫn là người ghi trong app.
- Phê duyệt ≠ thực nhận ≠ đóng. Địa chỉ/định khoản/quyển phiếu có thể nằm trên giấy gốc; không bắt nhân viên nhập lại trên form ghi nhận.
- Không auto đọc receipt bằng LLM trong đợt này. Proof route vẫn tách khỏi Reader/basis B3; không tăng input_revision chỉ vì upload chứng từ thực hiện.
- Unknown giữ null; StrictInt VND; không đồng nhất phí ngân hàng với tiền nhân viên nhận, không clip gross hoặc tự phục hồi khoản sai bên nhận.
- Căn cứ người nhận lấy từ chứng từ + đối chiếu của kế toán; profile không chứng minh payer/payee. Không nhận diện chữ ký rồi tuyên bố chữ ký thật.
- New command guards ownership/role/decision/version/Stop/idempotency giữ nguyên. Actual fact dưới Stop vẫn lưu nhưng không tiến stage/handoff.
- Dữ liệu/history cũ không rewrite hoặc bổ sung evidence/metadata giả. Hiển thị records cũ thiếu căn cứ là cần rà soát; không claim đợt này đã adjudicate lịch sử.
- Không sửa các corpus frozen, expected/gold hoặc original A02 để làm xanh. Giữ chỉ A02/L01 trong kit; chọn biến thể nào tới lượt mới tạo folder/file biến thể đó.

## D. Form và hợp đồng đã chốt

### D1. Chung cho hai phương thức

Ở **Kế toán → Hồ sơ B3 đã duyệt → Ghi nhận tiền ứng thực nhận**. Header readonly:
người đề nghị (tên), mã hồ sơ chung, đã duyệt/đã nhận/còn lại. Select phương thức
trước upload; nút cuối **Ghi nhận kết quả thực tế**. Người khác chỉ xem summary.

Source upload + viewer/đường mở original; ghi số tiền/thời điểm từ nguồn. Không
bắt ghi chú cho mọi happy case: service có thể lưu mô tả ngắn việc đối chiếu,
nhưng mô tả không thay evidence. Khi thiếu/khác nguồn, ghi chú giải thích cần có.

Người nhận chọn bằng tên: người liên quan trong demo people, **Người khác**,
**Chưa xác định**; mặc định chưa chọn, không prefill nhân viên. Giữ tên nguyên
văn từ chứng từ trong metadata. Chọn người khác dùng payee_ref=`OTHER`, không
giả account; vẫn giữ receiver_name. Chưa rõ dùng null. Không cho nhập actor ID.

Bên chi theo nguồn chọn Công ty/Người khác/Chưa rõ; không hardcode COMPANY làm
READ evidence dù chưa đọc nguồn. Chỉ COMPANY có căn cứ mới là ứng công ty.

Chọn **Nguồn chi** bằng label người dùng hiểu (tài khoản chi hoặc quỹ tiền mặt),
value là namespace backend đã cấu hình. Không ô namespace tự nhập trên màn thường.
Số tham chiếu giao dịch/số phiếu là dữ kiện chứng từ, không tự sinh bằng UUID để
che thiếu identity. Evidence có source/locator/raw/value/read_state thực, không
lấy giá trị tự điền làm READ khi nguồn chưa rõ.

### D2. Chuyển khoản

Nhóm bên chuyển/bên hưởng: tên đọc được, ngân hàng/tài khoản ghi trên nguồn (có
thể masked); nhóm giao dịch: số thực nhận/chuyển đủ căn cứ, thời điểm, số tham
chiếu, nội dung, trạng thái nguyên văn. Các trường tài khoản/ngân hàng là context
đối chiếu, không bắt mỗi chứng từ phải có mọi field khi căn cứ khác đã đủ.

Kế toán xác định phạm vi nguồn: **lệnh mới tạo**, **chỉ trích nợ bên gửi**,
**đủ căn cứ người hưởng nhận**, **chưa rõ**. Đây là source review có refs, không
checkbox vô nguồn. Chỉ scope người hưởng nhận + core facts rõ cho RECEIVED.
Trạng thái ngân hàng giữ nguyên văn và không có mapping từ chữ “thành công”
sang received toàn cục. Không bắt bổ sung sao kê nhân viên nếu nguồn bank đã đủ.

### D3. Tiền mặt

Nhóm phiếu chi: source PDF/ảnh, số phiếu, quỹ chi, người giao, ngày giao nhận;
nhóm người nhận: tên, số thực nhận, căn cứ xác nhận giao/nhận. Giữ tiền bằng chữ
và vùng ký trên original; không thêm parser tiếng Việt/forensic engine.

Kết quả: **đã giao, có xác nhận nhận tiền**, **chưa giao**, **chưa đủ căn cứ**.
Chưa giao map PENDING, chưa đủ map UNCONFIRMED; không bịa ngân hàng/TX. Có dòng
duyệt hoặc tên in sẵn chưa là xác nhận giao nhận. Number scope là quỹ+số phiếu,
không số phiếu đơn lẻ toàn công ty. Sai người nhận giữ raw/incident, không auto chi bù.

### D4. Backend extensions (không SQL migration)

Thêm records ở `contracts/advance.py`, export qua `models.py` facade và mirror TS:

```python
class B3BankReceiptDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["BANK_TRANSFER"]
    receiver_name: str | None = None
    sender_name: str | None = None
    bank_name: str | None = None
    sender_account: str | None = None
    recipient_bank: str | None = None
    recipient_account: str | None = None
    bank_status_text: str | None = None
    proof_scope: Literal["ORDER_ONLY", "SENDER_DEBIT", "RECEIVER_CONFIRMED", "UNCONFIRMED"]

class B3CashReceiptDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["CASH"]
    voucher_number: str | None = None
    cashbook_label: str | None = None
    handed_by_name: str | None = None
    receiver_name: str | None = None
    acknowledgement: Literal["ACKNOWLEDGED", "NOT_HANDED", "UNCONFIRMED"]
```

`B3AdvanceEventPayload.receipt_details` và `B3AdvanceEventView.receipt_details`:
union hai records trên, default None cho read compatibility; validator cấm
kind khác method. Event view thêm `evidence_issues: list[str]` default []; persisted
JSON lưu details/reasons của new events. Không default missing detail thành confirmed.

Mở rộng `B3MoneyFieldName` cho `proof_scope`, `bank_status_text`, `receiver_name`,
`voucher_number`, `handed_by_name`, `acknowledgement`. Giữ core9 keys hiện có;
đúng proof theo phương thức bổ sung field cần thiết. Required evidence cho new
RECEIVED: amount/currency/payer/payee/time/ns/ref/method/receiver_outcome, receiver_name;
bank thêm proof_scope; cash thêm voucher_number/acknowledgement. Người giao tiền
lưu khi đọc rõ; thiếu tên đầy đủ của người giao không tự chặn nếu nguồn đã đủ
căn cứ công ty chi và đúng người nhận, số tiền, giao nhận.
Metadata bank optional không vì vắng mà tự UNCONFIRMED nếu các căn cứ cần đã đủ.

Thêm `B3ReceiptSource` ở `contracts/b3_contracts.py` gồm `method`, `namespace`,
`label` nonblank; `B3CompanyContext.receipt_sources` default []. Validate namespace
unique trong context. `GET /api/demo-context` thêm read-only receipt_sources.
Đây là2 lựa chọn nguồn cấu hình cho pilot, không kho tài khoản ngân hàng/quản trị.
Fixture mới L01 dùng `BANK:L01-COMPANY` (Tài khoản chi công ty demo) và
`CASH:L01-QUY-CHINH` (Quỹ tiền mặt chính); khi thiếu config, giữ readonly history,
khóa ghi mới và hướng dẫn cấu hình, không sinh namespace fallback.

## P1. Khóa lỗi ghi nhận không evidence và lưu metadata theo phương thức

**Files:** Modify `contracts/advance.py`, `contracts/b3_contracts.py`, `models.py`,
`advance_reconciliation.py`, `persistence/advance_records.py`, `api/schemas.py`
(`B3AdvanceEventRequest.receipt_details`), `api/settlement.py` (demo-context
projection và chuyển tiếp request.receipt_details vào event payload). Tests
`test_b3_funding.py`, `test_b3_funding_api.py`;
update test builders liên quan receipt_payload/upload_receipt để nguồn mới đủ,
không sửa frozen datasets hoặc expected money.

**Interfaces:**
- `validate_advance_receipt(payload: B3AdvanceEventPayload, proof_source_ids: set[str], receipt_sources: list[B3ReceiptSource]) -> list[str]` trong advance_reconciliation.
- `derive_classification(payload, employee_ref, incidents, *, evidence_ok: bool) -> str`; chỉ caller record_receipt truyền kết quả guard, không default True.
- Source ownership invalid vẫn DomainError như trước. Guard thiếu/mâu thuẫn giữ
  new raw event UNCONFIRMED/CONFLICT với reasons, không cộng fulfillment. Invalid
  payload types/kind mismatch vẫn 422, không normalize số đoán.

- [ ] **P1.1 RED — regression từ probe**. Thêm vào test_b3_funding.py:

```python
def test_received_without_evidence_never_fulfills(approved_b3):
    svc, case, decision = approved_b3
    event = svc.record_b3_advance(case.id, {
        "decision_id": decision.id, "event_namespace": "BANK:DEMO-ACCOUNT",
        "event_ref": "NO-PROOF", "method": "BANK_TRANSFER",
        "gross_vnd": 2_000_000, "payer_side": "COMPANY",
        "payee_ref": "NV-DEMO-01", "event_at": "2026-10-10T10:00:00+07:00",
        "reported_status": "RECEIVED", "evidence": [],
        "allocation_note": "Chưa có chứng từ",
    }, command("no-proof", "ACC-DEMO-01", "ACCOUNTANT", case.case_version))
    view = svc.get_case(case.id)
    assert event.classification != "CONFIRMED_RECEIPT"
    assert view.b3_workflow.funding.recorded_received_vnd is None
    assert view.b3_workflow.funding.status != "FULFILLED"
    assert view.stage != "AWAITING_WORK_SETTLEMENT"
```

Run `rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b3_funding.py::test_received_without_evidence_never_fulfills -q`; expected behavioral FAIL trước sửa, không collection error.

- [ ] **P1.2 GREEN — guard có nguồn**. Required fields đúng một evidence mỗi
  field; source thuộc dedicated proof_ids do B3_ADVANCE_PROOF audit ghi, locator/raw
  nonblank, origin HUMAN_SOURCE_REVIEW, read_state READ, value tương thích payload.
  Normalize time về aware instant trước so, không so local string với UTC string.
  Bank RECEIVED cần scope RECEIVER_CONFIRMED có source support; cash RECEIVED cần
  ACKNOWLEDGED có source support, voucher khớp event_ref; nguồn chi đúng method.

```python
evidence_issues = validate_advance_receipt(
    payload, advance_proof_source_ids(conn, case_id), context.receipt_sources)
classification = derive_classification(
    payload, submission.employee_ref, incidents,
    evidence_ok=not evidence_issues)
# Persist raw payload + receipt_details + evidence_issues, even when unconfirmed.
```

Không gọi OCR/LLM/đọc chữ ký tự động để chữa gate. Source review đủ nghĩa không
là xác thực nội dung ngân hàng. Các fields khác nhau có thể refs nhiều chứng từ
trong cùng case; không ép tất cả phải cùng source_id. Thiếu evidence nghĩa nguồn
chưa đủ, không giả confirmed hoặc sửa source gốc.

- [ ] **P1.3 Regression matrix**: bank confirmed→nhận2; pending/debit-only→không nhận;
  cash acknowledged→nhận2; unsigned→không nhận; OTHER payee→raw2/incident;
  partial1 giữ approved2/remain1; duplicate same source/event không nhận thêm;
  duplicate/extra evidence keys reject hoặc conflict trước aggregation; source
  input đề nghị không phải proof→unconfirmed; source khác case→BASIS_MISMATCH;
  mixed details→422; missing/negative/float/money unclear fail-safe; proof upload
  không stale approval; dưới Stop raw lưu, không tiến stage. Restart parse new và
  old view records không bịa details; old confirmed thiếu proof phải hiển thị cần
  rà soát, không tự chứng nhận an toàn hồi tố.

Run focused `test_b3_funding.py`, `test_b3_funding_api.py`, `test_b3_workflow.py`,
`test_b7_linked_context.py` bằng pytest fake. Cùng namespace/ref B5 và packet phải
vẫn một sự kiện; không đổi số expected để tránh sửa builder evidence.

## P2. Form hai nhánh và proof review có tên người dùng hiểu

**Files:** Modify `AdvanceReceiptPanel.tsx`, `AdvanceReceiptPanel.test.tsx`,
`types.ts`, `api.ts`, `CaseActionsPanel.tsx` (pass people/receipt_sources từ App),
`App.tsx` chỉ wiring props, `displayText.ts` chỉ labels nếu cần; style nhỏ ở CSS
panel hiện có. Không rewrite App/Report hay tạo form framework.

**Interfaces:** props thêm `people?: B3Person[]`, `receiptSources?: B3ReceiptSource[]`;
types mirror D4; upload/event endpoints giữ nguyên. Actor/role từ persona có sẵn;
recipient selector value nội bộ, hiển thị tên, chưa chọn không gửi employee mặc định.

- [ ] **P2.1 RED — branch + no-proof**. Dùng makeView/noop hiện có trong test:

```tsx
test('received đủ fields nhưng chưa đính kèm chứng từ không bật nút ghi', () => {
  render(<AdvanceReceiptPanel view={makeView()} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  const fill = (label: string, value: string) =>
    fireEvent.change(screen.getByLabelText(label), {target: {value}});
  fill('Số tiền nguồn ghi (VND)', '2000000');
  fill('Kết quả giao dịch (theo nguồn)', 'RECEIVED');
  fill('Người nhận thực tế (đọc từ nguồn)', 'NV-DEMO-01');
  fill('Không gian giao dịch (namespace)', 'BANK:DEMO-ACCOUNT');
  fill('Mã giao dịch (event_ref)', 'TX-1');
  fill('Thời điểm giao dịch', '2026-10-10T10:00');
  fill('Ghi chú đối chiếu', 'Đã đọc nguồn');
  expect(screen.getByRole('button', {name: 'Ghi nhận sự kiện ứng'})).toBeDisabled();
});
```

Snippet dùng labels cũ để RED đúng hành vi enabled khi không proof, không RED do
đổi tên nút. Khi UI đã đổi, cập nhật selectors sang nhãn mới và fixture nguồn
chi/people/receipt_details đủ; giữ chỉ thiếu proof và assertion disabled.
Thêm test có config/people và nhập **mọi field received** nhưng không upload→disabled;
upload thành công→chỉ khi required review đủ mới enabled; upload thất bại không giữ
proof cũ. Chọn CASH: thấy Số phiếu chi/Quỹ chi/Người giao/Xác nhận nhận tiền, không
thấy ngân hàng/mã giao dịch bank/namespace. Chuyển BANK: ngược lại. Test đổi method
không gửi fields/proof của phương thức cũ; preserve server events không xóa.

- [ ] **P2.2 GREEN — conditional view**. Sections: header readonly → method →
  upload/open original → fields D2/D3 → review result/reasons → Ghi nhận kết quả thực tế.
  Bank metadata account/bank optional; core missing→unconfirmed, không bắt tiền
  mặt điền bank. Proof/case/method change reset draft support đã gắn hoặc yêu cầu
  người dùng xác nhận lại, không auto đổi source thành đúng phương thức mới.
  Ngày/số tiền/người nhận không prefill từ approved; summary hiển thị raw/accepted
  riêng khi incident. Namespace chọn từ nguồn chi, không nhập technical code.

- [ ] **P2.3 Source review và statuses**. Có vùng nhập/trích lại trạng thái nguyên
  văn và locator (ví dụ trang1, phần kết quả). Không gắn toàn bộ field với một
  locator giả mặc định, không self-stamp READ cho unknown. Form cho lưu PENDING/
  UNCONFIRMED với amount null theo nguồn; không bắt có amount rồi đoán0. Note default
  chỉ là mô tả thao tác, không evidence. Person Other giữ raw_name và incident;
  receiver chưa rõ không tự choose người trong hồ sơ. Hiện tiền đã nhận bằng
  tiếng Việt; raw codes/ref trong chi tiết đóng mặc định. Thủ quỹ trên phiếu là
  dữ kiện, không role picker mới. Nhân viên/người duyệt readonly.

Run `rtk proxy npm --prefix frontend run test -- --run src/settlement/AdvanceReceiptPanel.test.tsx src/settlement/CaseActionsPanel.test.tsx src/settlement/App.test.tsx`.

## P3. Tạo PDF test khi đến lượt, trong L01 hiện có

**Files:** Create lúc triển khai `data/test-kit/cases/L01/tools/build_advance_receipt_variants.py`;
modify root CHECKLIST và L01 manifest/expected khi chọn biến thể; clone config
`cases/L01/config/b3-receipt-methods.json` từ context hiện có, version synthetic
mới và hai nguồn chi D4. Không sửa original A02/context hashes hoặc PDF cũ.

**CLI:** `--method BANK_TRANSFER|CASH --variant received|pending|debit-only|unsigned|wrong-recipient --out-dir PATH`.
Validate variant/method hợp lệ; refuse output dir không trống; chỉ tạo đúng biến
thể được yêu cầu. Mỗi lần gồm source PDF, PNG/scan nếu chọn variant representation,
expected.json và manifest hash; actual output vẫn NOT_RUN. Không xây sẵn6 folders.

| Phương thức / biến thể | Nội dung PDF | Expected B5 |
| --- | --- | --- |
| BANK / received | nguồn tài khoản công ty, Nguyễn An + TK hưởng, 2 triệu, refTX-L01-ADV-001, 10/10 10:00; kết quả đủ căn cứ ghi có người hưởng | received2/remain0/chờ quyết toán |
| BANK / pending | cùng nội dung yêu cầu2 triệu; “lập lệnh thành công, chờ duyệt”, chưa nhận | PENDING, không received2 |
| BANK / debit-only | ghi nợ nguồn, chưa có kết quả phía hưởng | UNCONFIRMED, không fulfilled |
| CASH / received | PC-L01-001, quỹ chính, Trần Bình giao, Nguyễn An nhận2 triệu; phần giao nhận hoàn tất có ký nhận minh họa | received2/remain0 |
| CASH / unsigned | phiếu đã duyệt2 triệu, phần giao nhận/người nhận trống | không received/fulfilled |
| CASH / wrong-recipient | người nhận thực tế Trần Nam, số2 triệu, giữ phần giao nhận | OTHER/incident, không actual của Nguyễn An |

Ngày/tiền nghiệp vụ nhất quán L01. Bank source là thiết kế minh họa, không dùng
logo/giả chứng nhận của ngân hàng thật. Cash dùng phiếu chi với đầu phiếu/nội dung/
ký kiểm soát và phần giao nhận; chữ ký synthetic không đánh giá forensic. Không
đưa “expected/pass/received enum” hoặc chỉ đạo model vào PDF, chỉ dữ kiện nghiệp vụ.
Danh tính/định danh nguồn được metadata riêng; signed template minh họa không chữ
ký thật. Các field có bank semantics khác thì raw phải khác, không chỉ đổi title.

### Recipe authoring tối thiểu

Load `pdf:pdf` trước authoring; gọi marker operation create đúng một lần ngay trước
lần generate PDF đầu tiên, số count bằng output PDF của lần đó. Dùng runtime đã
có reportlab/pypdf/Pillow và font tiếng Việt; không cài vào .venv app. Code mẫu
cốt lõi để implement generator, `rows` do variant mapping bảng trên cung cấp:

```python
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from html import escape

def write_receipt_pdf(path: Path, title: str, rows: list[tuple[str, str]], font_path: Path):
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont('VNReceipt', str(font_path)))
    body = ParagraphStyle('receipt', fontName='VNReceipt', fontSize=11, leading=16)
    heading = ParagraphStyle('heading', parent=body, fontSize=17, leading=23, alignment=1)
    story = [Paragraph(escape(title), heading), Spacer(1, 16)]
    for label, value in rows:
        story += [Paragraph(escape(f'{label}: {value}'), body), Spacer(1, 7)]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=40, rightMargin=40,
                      topMargin=42, bottomMargin=42).build(story)
```

Cash layout phải có phần giao nhận/chỗ ký, unsigned để trống có chủ ý; không chỉ
đổi title của ngân hàng thành Phiếu chi. Native PDF extract text để kiểm số/tên;
render mọi trang và view PNG kiểm glyph/overlap. Scan dùng ảnh render đóng thành
PDF không text layer, source page mappings giữ. Không sửa ảnh để sinh số khác
rồi coi original đủ bằng chứng. Không cần imagegen để render/viết PDF.

Sau implement, khi bắt đầu chuyển khoản confirmed mới chạy:

```bash
rtk proxy /Users/tnhatnguyendev2805/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 data/test-kit/cases/L01/tools/build_advance_receipt_variants.py --method BANK_TRANSFER --variant received --out-dir data/test-kit/cases/L01/input/02-advance/bank-received
```

Khi tới tiền mặt mới chạy:

```bash
rtk proxy /Users/tnhatnguyendev2805/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 data/test-kit/cases/L01/tools/build_advance_receipt_variants.py --method CASH --variant received --out-dir data/test-kit/cases/L01/input/02-advance/cash-received
```

Hai lệnh là planned: script chưa tồn tại trong lượt viết plan. Nếu không có bundled
runtime trên máy coding agent, dùng load_workspace_dependencies tìm đường thật,
không suy đã cài hoặc install dependency cho read-only checks.

Bank received dùng nguyên namespace/ref đang có của L01 để không nhân đôi ứng.
Cash B5 thử trên hồ sơ riêng, không cộng cash2 và bank2 vào cùng approval2 rồi gọi
happy. Nếu đi tiếp full L01 cash, tạo sổ company before/after và packet khớp CASH
namespace+PC thật; không dùng sổ bank TX-L01-ADV-001 để chứng minh cash. Binder phải
gắn actual source IDs/hashes và giữ prepared/expected/output ngoài Reader.

- [ ] **P3.1 Implement + check generator:** pytest/temp dir hoặc stdlib check output
  exists/page count/Vietnamese values/scan text-empty/ref/hash; duplicate path
  bị chặn. Check schema config + bound metadata bằng Pydantic app, không dùng
  production money engine để sinh oracle. Trước sửa L01 manifest ghi hash files
  cũ, sau chỉ append variant mới, giữ output hiện có.
- [ ] **P3.2 Chỉ tạo biến thể đang test:** bank received trước; render/view, đối chiếu
  source arithmetic/phạm vi; bổ sung đúng một checkbox B5 trong L01 section của
  CHECKLIST. Các variant khác chỉ trong plan này cho tới lúc chọn; không tạo
  case folder/status giả. No proof required after create không còn; không gọi
  native PDF test HUMAN_SOURCE_REVIEW là OCR quality nếu B5 không gọi model.

## P4. Kiểm UI, L01 integration và cập nhật hiện trạng

**Files:** Existing `CHECKLIST.md` section5.4, `L01/expected`, manifests và output
actual khi thật sự test; `PRODUCT.md` P2a/B5, `SYSTEM.md` B5 contract. Không tạo
thêm review/report MD hoặc xóa file lịch sử để làm context ngắn.

- [ ] **P4.1 Required checks sau focused tests**:

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q
rtk proxy .venv/bin/python -m pip check
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
```

Report actual exit/counts/mode; worker checkbox không là acceptance. Không tự
gọi LIVE vì đang chạy plan; real provider cần authorization tương ứng.

- [ ] **P4.2 UI acceptance**: kế toán có đúng nhánh, proof mở đúng; bank pending/
  debit-only và cash unsigned không fulfilled; confirmed đúng source nhận2;
  amount1 partial giữ approved2; wrong receiver giữ raw, không auto bù; switch
  method/case/person không gửi evidence cũ; người khác readonly; reload giữ
  metadata, source, audit. Browser policy chặn thì không bypass, ghi USER_UI_UNEXECUTED.
- [ ] **P4.3 Full L01**: phương thức bank confirmed cùng canonical event identity;
  A2 không4, E5/T8/S3; receipt P3 sau B8 vẫnS0/revalidation đúng rồi đóng. Cash
  variant chỉ claim fullworkflow nếu company packet/nguồn cash cũng đã chuẩn bị
  và chạy; mốc B7 gap section5.6 vẫn là gap riêng, không âm thầm đổi dates hoặc
  mở rộng task để refactor tất cả lifecycle.
- [ ] **P4.4 Current docs**: ghi IMPLEMENTED sau wired code, VERIFIED theo actual
  evidence; actual outputs không overwrite templates/failures. Kiểm CHECKLIST
  links và manifest SHA; test-kit chỉ có A02/L01. Không nâng synthetic mẫu rõ số
  thành baseline OCR/quality, không nói chữ ký/ngân hàng đã xác thực.

## Prompt giao coding agent

```text
Đọc AGENTS.md và docs/superpowers/plans/2026-10-12-advance-receipt-methods.md.
Triển khai P1–P4: sửa gate backend trước, rồi form phương thức, PDF test theo nhu
cầu và UI/integration. Có probe FAKE_TEMP_DB: RECEIVED2 triệu không evidence vẫn
FULFILLED — khóa regression đó, không chỉ disable frontend. Giữ raw/unknown,
authority/Stop/version/idempotency/B3-vs-B7 boundaries. Đọc dirty diff của writer
khác, không reset/deletion/restore ngoài phạm vi. Giữ A02/L01; không dựng thêm
folder cho case chưa đến lượt, không xóa output/source hiện có. Generator chỉ
tạo biến thể đang test; giữ original PDFs và hashes. Không thêm bank integration/
login/form framework/role mới, không tự Git/LIVE/publish. Báo thực chạy và những
phần USER_UI_UNEXECUTED; không coi fake/source/worker checkbox là chất lượng AI.
```
