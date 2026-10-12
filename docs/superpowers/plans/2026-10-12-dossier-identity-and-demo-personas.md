# Hồ sơ chung và người dùng demo — Implementation Plan

> **For agentic workers:** Dùng `executing-plans`, thực hiện T1–T5 tuần tự với regression trước thay đổi. Không tự commit, gọi LIVE, tạo subagent hoặc triển khai đăng nhập. Đây là plan để coding agent khác thực hiện; chưa có code được sửa bởi plan này.

**Goal:** Nhân viên chọn người dùng demo và nhập nội dung nghiệp vụ; hệ thống quản lý danh tính, cấp mã hồ sơ và nối tạm ứng–quyết toán, không bắt nhập mã nhân viên/người thao tác/công việc.

**Architecture:** Một hồ sơ nghiệp vụ có thể có bản ghi B3, B7 và điều chỉnh riêng. Dùng ID bản ghi gốc làm `dossier_ref` chung, giữ ID từng bản ghi để API, version, Stop và tài liệu vẫn thuộc đúng giai đoạn. Hồ sơ mới dùng cùng ID gốc cho scope nội bộ; dữ liệu cũ giữ nguyên `work_ref` và quyết định/nguồn đã lưu.

**Tech Stack:** Python/FastAPI/Pydantic/SQLite; React/TypeScript/Vitest/Testing Library hiện có. Không dependency mới.

**Spec:** Thiết kế đã thống nhất trong cuộc trao đổi ngày 12/10/2026 được cụ thể hóa ở phần D bên dưới; đối chiếu [Product P2a/P3/P7](../../settlement/PRODUCT.md), [System S6/S7/S10](../../settlement/SYSTEM.md), [Rulebook](../../settlement/RULEBOOK.md). Plan này thay cách nhận diện/hiển thị, không thay điều kiện tiền, quyền hoặc chất lượng chứng từ.

**Status:** IMPLEMENTED (T1–T4, T5 checks), 12/10/2026. Snapshot đọc ban đầu `0d683a1`; writer khác đã commit App/B3Intake/styles/DocumentViewer vào `9fa9e1f` trước khi thực hiện (working tree sạch khi bắt đầu, không reset/ghi đè). UI acceptance: **USER_UI_UNEXECUTED**.

**Evidence (fake, không LIVE/Git/publish):**

```
SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q   # 913 passed (exit 0)
.venv/bin/python -m pip check                                       # No broken requirements found
npm --prefix frontend run test -- --run                             # 177 passed (26 files)
npm --prefix frontend run build                                     # tsc --noEmit + vite build OK
git diff --check                                                    # clean
```

RED→GREEN: `test_new_b3_uses_own_id_as_dossier_scope` (KeyError dossier_ref),
`test_standalone_b7_derives_identity_without_advance` (404 route),
`chọn người dùng demo bằng tên…` (no combobox "Người dùng demo").
Frozen corpus/gold/DB/originals không đổi; không merge DB rows; không thêm
login/framework/migration/counter.

**Evidence boundary:** CodeGraph lỗi `directory_1.statInode is not a function`; generation/freshness/coverage UNKNOWN. Discovery dùng source trực tiếp, không claim graph verification hoặc đã chạy acceptance. Không dùng kết quả/checkbox plan consolidation làm bằng chứng cho plan này.

## D. Thiết kế cần thực hiện

### D1. Một người dùng, hai quan hệ với hồ sơ

- Bộ chọn duy nhất ở đầu trang: **Người dùng demo**. Các lựa chọn lấy từ `getDemoContext().people`: `Nguyễn An — Nhân viên`, `Trần Bình — Kế toán`, `Lê Chi — Người phê duyệt`; tên và vai trò, không mã hoặc phòng ban.
- `actor_ref` vẫn là value nội bộ của lựa chọn. `role` lấy từ chính người đó; không có bộ chọn vai trò độc lập/ô nhập mã người thao tác. Giữ lời nhắc ngắn: `Đang dùng tài khoản mô phỏng.`
- Người nộp tự lấy từ người đang chọn khi create; người thao tác lấy từ lựa chọn tại thời điểm lệnh. Sau đó chuyển sang kế toán/người duyệt KHÔNG thay `submission.employee_ref` của hồ sơ.
- Không thêm đăng nhập, token/session, RBAC framework hay cho phép nộp thay. Các route/grant/backend guards hiện có tiếp tục kiểm; demo picker không là authentication.
- Người dùng chưa tải/chưa có trong context: khóa mutation, báo `Chưa tải được người dùng demo.` Không tự sinh actor từ role hoặc lấy `NV-01`/`P-DEMO` làm fallback.
- Fixture cho test dùng hai nhân viên có tên khác nhau. UI không hardcode tên/mã fixture. Tên trùng được phân biệt bằng nhãn demo ổn định như `Nguyễn An — Nhân viên (2)` theo thứ tự people, không dùng department/mã để phân biệt.

### D2. Mã hồ sơ và phạm vi

| Trường | Vai trò sau sửa |
| --- | --- |
| `case.id` | ID bản ghi/giai đoạn; giữ cho URLs, sources, runs, commands, version, audit |
| `dossier_ref` | Read projection: ID B3 gốc cho B3/linked B7/adjustment; ID chính mình cho B7 độc lập |
| `submission.work_ref` | Scope tương thích nội bộ: hồ sơ mới bằng ID gốc; hồ sơ cũ giữ nguyên giá trị |
| Số trên giấy ngoài | Tham chiếu chứng từ nằm trong original; không dùng làm khóa/ghép tự động |

- B3 mới: cấp đúng một `case_id`, dùng nó cho `work_ref` và `dossier_ref`; không sinh thêm `WORK-...` độc lập. Linked B7 vẫn có ID riêng, giữ link server-owned và scope gốc. Adjustment dùng `origin_case_id` B3 đã có, không lấy ID adjustment làm scope mới.
- B7 tự chi mới: cấp ID riêng làm root/scope, không tạo B3/advance event 0. Người dùng không nhập ID.
- B3 cũ có `WORK-...`: root vẫn là `case.id`; B7 cũ root là `origin_case_id`. Không đổi raw/history/decision/config/source hashes để ép `work_ref == dossier_ref` cho dữ liệu cũ.
- Không merge B3/B7 thành cùng DB row, không bảng dossier mới, không renumber hồ sơ cũ, không thêm counter số theo năm. UI dùng nguyên mã gốc hiện có, ví dụ `Mã hồ sơ: C-...`; không tạo thêm alias HS-... có thể gây nhầm khi copy/search.
- Chính `origin_link` xác định quan hệ, không cùng tên/ngày/số giấy/amount/work_ref. Phải giữ kiểm employee, scope, parent và quyền tại boundary. Nhãn chung không gộp tiền hoặc quyền của B3 vào B7.
- Frontend không gửi `dossier_ref`, `employee_ref`, `work_ref`, grants hoặc origin links ở các route intake cá nhân mới. Legacy/evaluation `/api/cases` vẫn nhận frozen Submission theo hợp đồng cũ, nhưng không nằm trong thao tác thường ngày.

### D3. Giao diện hồ sơ

- B3 và B7 liên kết có cùng nhãn mã hồ sơ, khác nhãn giai đoạn `Đề nghị tạm ứng` / `Quyết toán chi phí`. Không hiển thị hai mã dưới cùng nhãn `Mã hồ sơ`.
- Từ B3 bấm `Nộp quyết toán`; từ B7 có `Xem đề nghị tạm ứng`. Mỗi nút dùng ID bản ghi thật, không dùng dossier_ref thay mọi endpoint.
- Inbox có tên người và mã hồ sơ chung; giữ mỗi bản ghi/giai đoạn là một item với badge rõ, không dựng trạng thái tổng mới hoặc mất các B7 adjustment. Search bằng mã hồ sơ chung phải thấy các giai đoạn liên quan.
- Mã employee/work/case-child/run/epoch chỉ có trong `Chi tiết kỹ thuật` đóng mặc định. Audit nghiệp vụ hiển thị tên và vai trò; raw actor/ref vẫn lưu và truy cập được trong chi tiết.
- Không còn ô `Mã nhân viên`, `Mã người thao tác`, `Mã công việc`, bộ chọn nhân viên nộp thứ hai hoặc department ở picker. Người đề nghị có thể hiện readonly tên trong hồ sơ.
- Không thêm field/danh mục đối tác. Mục đích là nội dung nhân viên nhập; tên đối tác nếu có nằm trong nội dung, không thành fact đã xác minh.
- Đổi nhãn người dùng không được biến profile thành actual payer/payee. Các tên/tài khoản người trả, người nhận đọc từ chứng từ vẫn phải giữ đúng nguồn; không tự sửa thành người đang chọn. Khi profile của hồ sơ cũ không còn trong demo context, hiển thị `Chưa có thông tin người đề nghị`, giữ raw ref trong chi tiết; không gán người đang đăng nhập vào hồ sơ cũ.

### D4. Giấy đề nghị bên ngoài

- Giữ nguyên giấy gốc có/không có `Số`. Thiếu Số không chặn draft/submit; cùng Số trên hai giấy không tự merge hai hồ sơ.
- Không suy số giấy thành mã nội bộ, không ghi đè Số trên original. Việc cấp số chứng từ tự tăng/xuất mẫu giấy hoặc thêm OCR field Số chưa thuộc đợt này; không quảng cáo đã có.
- Đợt này không đổi corpus A03 hoặc PDF đã chốt. Case A03 được mô tả bằng tên và nội dung cho người test; frozen IDs/input/expected vẫn bất biến.

## T1. Backend cấp scope từ hồ sơ gốc và trả identity nhất quán

**Files:** Modify `src/invoice_referee/settlement/models.py`, `store.py`, `persistence/queries.py`; test `tests/settlement/test_b3_api.py`, `test_b7_linked_api.py`, `test_b7_adjustment.py`. Không sửa phép tính/rulebook engine.

**Interfaces:**
- Add read-only `dossier_ref: str | None = None` vào `CaseView`/`CaseSummary` để old serialized artifacts vẫn đọc được; mọi response GET/create/list hiện hành phải trả string nonblank.
- Add `queries.dossier_reference(conn: sqlite3.Connection, case: sqlite3.Row) -> str`: đọc persisted submission và origin_link; return parent ID cho linked, otherwise own ID. Parent phải tồn tại và đúng employee/work; link lỗi trả `LINKED_B7_INVALID`, không lấy child làm root để che lỗi. Không gọi Store từ records.
- Preserve `Store.create_b3_case(build_submission, command, request_payload, origin='USER') -> CaseView`; bên trong cấp `case_id` một lần rồi `build_submission(case_id)`. Lookup replay/fingerprint trước UUID.

- [x] **T1.1 RED — gốc, scope và replay**. Thêm vào test B3 API dùng fixture `b3_client`/`NATIVE_FORM` hiện có:

```python
def test_new_b3_uses_own_id_as_dossier_scope(b3_client):
    body = {"actor_id": "NV-DEMO-01", "intake": NATIVE_FORM}
    headers = {"Idempotency-Key": "dossier-new"}
    first = b3_client.post("/api/b3-cases", json=body, headers=headers)
    assert first.status_code == 201, first.text
    case = first.json()
    assert case["dossier_ref"] == case["id"]
    assert case["submission"]["work_ref"] == case["id"]
    assert case["submission"]["employee_ref"] == "NV-DEMO-01"
    again = b3_client.post("/api/b3-cases", json=body, headers=headers)
    assert again.status_code == 200, again.text
    assert again.json()["id"] == case["id"]
    assert again.json()["dossier_ref"] == case["dossier_ref"]
    assert len(b3_client.get("/api/cases").json()) == 1
```

Run: `rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b3_api.py -q`. RED phải do field/scope sai, không do fixture/import hỏng.

- [x] **T1.2 GREEN — identity projection và create**. Cấp case_id trước build_submission trong cùng transaction; thêm projection vào `_case_view` và `list_cases`. Không dùng `work_ref` để tính root. Không sửa persisted JSON khi GET. Update assertion `startswith('WORK-')` trong `test_b3_api.py` thành bằng case.id cho create mới, nhưng giữ tests cố ý dùng WORK cũ để kiểm tương thích.

```python
# Sau lookup/check_replay, trong transaction tạo B3:
case_id = f"C-{uuid.uuid4().hex[:12]}"
submission = build_submission(case_id)
# _case_view/list_cases dùng queries.dossier_reference; import theo alias
# queries hiện có ở Store, không tạo records callback về Store.
```

- [x] **T1.3 Regression linked/legacy**. Mở hai B3 cùng nhân viên/nơi/ngày nhưng keys khác: roots khác; mở B7 từ mỗi parent: child IDs khác, child.dossier_ref bằng đúng parent.id. Copy JSON hồ sơ cũ với WORK scope vào DB test: GET/list root đúng và scope/decision/source bytes không đổi. Adjustment giữ root cũ. Replay same key không nhân bản; same key changed body vẫn 409. Existing scoped grant của hồ sơ cũ vẫn áp đúng scope; grant của hồ sơ A không cover B mới. Run `test_b3_api.py`, `test_b7_linked_api.py`, `test_b7_adjustment.py`, `test_b3_workflow_api.py`, `test_b7_policy_authority.py` qua pytest fake.

## T2. B7 tự chi không yêu cầu người dùng nhập mã

**Files:** Modify `models.py`, `service.py`, `store.py`, `src/invoice_referee/api/settlement.py`; Create `tests/settlement/test_b7_standalone_api.py`. Dùng B7 generic pipeline đã có, không viết lifecycle thứ hai.

**Interfaces:**
- `B7StandaloneIntake(BaseModel)`: extra forbid, frozen; `purpose: str`, `scope: str`, strip/nonblank bằng validator. Không employee/work/job/clock/parent/amount/authority.
- `Service.submit_standalone_b7(actor_id: str, intake: B7StandaloneIntake, command: Command) -> CaseView`: lookup activated b3_context.people như submit_b3, chỉ EMPLOYEE; Command actor phải khớp actor_id. Clock lấy activated b7_context.demo_clock nếu có, otherwise UTC now; không dùng B3 demo clock cho mốc quyết toán. Same key replay giữ clock/id đã cấp.
- `Store.create_standalone_b7(build_submission: Callable[[str], Submission], command: Command, request_payload: dict[str, Any], origin: str = 'USER') -> CaseView`: lookup operation riêng trước cấp ID, scope = own case_id. Body fingerprint chỉ actor/intake, không timestamp/UUID server mới.
- Add `POST /api/b7-cases`, body `{actor_id, intake: {purpose, scope}}`, required Idempotency-Key; fixed EMPLOYEE; 201 create / 200 replay. `Submission(job='B7', employee_ref=actor_id, work_ref=case_id, form={'purpose': intake.purpose, 'scope': intake.scope}, money_as_of=clock, knowledge_cutoff=clock)`; không origin_link và không suy A=0.

- [x] **T2.1 RED — API create không mã và chống injection**. File test mới import `b3_client` fixture từ `tests.settlement.test_b7_linked_api` để dùng temp DB/fake/config thực; không đọc .env. Test tối thiểu:

```python
def test_standalone_b7_derives_identity_without_advance(b3_client):
    response = b3_client.post("/api/b7-cases", json={
        "actor_id": "NV-DEMO-01",
        "intake": {"purpose": "Công tác Hà Nội", "scope": "Chi phí chuyến đi"},
    }, headers={"Idempotency-Key": "standalone-personal"})
    assert response.status_code == 201, response.text
    case = response.json()
    assert case["job"] == "B7"
    assert case["dossier_ref"] == case["id"]
    assert case["submission"]["work_ref"] == case["id"]
    assert case["submission"]["employee_ref"] == "NV-DEMO-01"
    assert case["linked_b7"] is None
    assert case["money_summary"]["received_vnd"] is None
    assert "origin_link" not in case["submission"]["form"]
```

Thêm tests same-key replay/conflict, empty purpose/scope, accountant/unknown persona rejected, injected employee/work/grants/clock/parent forbidden. After upload+run với history thiếu: A vẫn unknown, không vì nhãn “tự chi” mà thành zero.

- [x] **T2.2 GREEN — dùng boundaries đang có**. Route chuyển body sang typed intake, `_command` fixed EMPLOYEE, gọi Service. Store dùng cùng pattern atomic create/replay/audit/version của create_b3_case; nếu tách private insertion helper, chỉ hai managed-create callers, không factory registry/framework. Giữ `/api/cases` + frozen evaluator semantics nguyên vẹn.

- [x] **T2.3 Check**. Không đổi gold/schema frozen để xanh. Chạy:

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/settlement/test_b7_standalone_api.py tests/settlement/test_intake.py tests/settlement/test_evaluation.py tests/settlement/test_evaluation_v2.py tests/settlement/test_b7_linked_api.py -q
```

## T3. Một bộ chọn người dùng demo, không ô nhập định danh

**Files:** Modify `frontend/src/settlement/App.tsx`, `api.ts`, `types.ts`, `uiCopy.ts`; tests `App.test.tsx`, `uiCopy.test.ts`. Không sửa DocumentViewer/styles đang có writer khác trừ khi cần style rất nhỏ cho bộ chọn.

**Interfaces:**
- `api.createStandaloneB7(actorId: string, intake: {purpose: string; scope: string}, key?: string): Promise<CaseView>` gửi `/api/b7-cases`; giữ request idempotency helper hiện có và key ổn định cho retry.
- Types thêm `dossier_ref?: string | null` ở CaseView/CaseSummary cho old fixtures; server responses mới luôn có. Không dùng fallback work_ref cho nhãn.
- Dùng một selected actor state; role derive từ `people.find(p => p.actor_ref === selectedActorRef)`. Xóa b3PersonaRef/role/employeeRef song song nếu chỉ phục vụ chọn danh tính. Các props actorId/role ở Actions tiếp tục được derive, không đổi signature mọi component.

- [x] **T3.1 RED — UI và payload**. Thêm vào App.test.tsx dùng setup fixture hiện có:

```tsx
test('chọn người dùng demo bằng tên, không nhập mã hoặc phòng ban', async () => {
  setup();
  const picker = await screen.findByRole('combobox', {name: 'Người dùng demo'});
  expect(picker).toHaveTextContent('Nguyễn An — Nhân viên');
  expect(picker).toHaveTextContent('Trần Bình — Kế toán');
  expect(picker).not.toHaveTextContent('NV-DEMO-01');
  expect(picker).not.toHaveTextContent('Kinh doanh');
  expect(screen.queryByLabelText('Mã người thao tác')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Vai trò demo')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Nhân viên nộp (persona demo)')).not.toBeInTheDocument();
});
```

Thêm fixture nhân viên thứ hai + tests submit WEB/IMPORT gắn đúng actor; chuyển sang kế toán rồi review cùng hồ sơ vẫn giữ employee đầu tiên và ghi actor kế toán; approver tương tự; UI create disabled khi context lỗi. Update test cũ khẳng định `Nguyễn An — Kinh doanh` vì expectation đã đổi; không xóa behavior guard.

- [x] **T3.2 GREEN — thay picker và gửi lệnh**. Label/options thực tế:

```tsx
<>
  <label htmlFor="demo-person">Người dùng demo</label>
  <select id="demo-person" value={selectedActorRef} onChange={handlePersonChange}>
    {people.map((person) => (
      <option key={person.actor_ref} value={person.actor_ref}>
        {person.name} — {roleLabel(person.role)}
      </option>
    ))}
  </select>
</>
```

`roleLabel(role: DemoRole): string` đã có trong uiCopy; thống nhất APPROVER display thành `Người phê duyệt` (enum vẫn APPROVER), cập nhật uiCopy test liên quan. Duplicate display names thêm suffix ổn định. Chuyển persona khi form có nội dung: confirm native `window.confirm('Chuyển người dùng sẽ bỏ bản nháp chưa lưu. Bạn có muốn tiếp tục?')`; Cancel giữ nguyên actor/draft/files, Accept xóa draft và queue chưa lưu, không xóa persisted sources. Nếu upload/mutation đang chạy, khóa picker tới khi hoàn tất để không đổi actor giữa chuỗi import. Late response của actor cũ không được submit/revise dưới actor mới.

- [x] **T3.3 B7 thường ngày**. Bỏ employee/work inputs và điều kiện `workRef.trim()`. “Tạo quyết toán trực tiếp” gọi createStandaloneB7 với purpose/scope; clock được backend cấp. Linked chọn hồ sơ gốc và gọi endpoint hiện có. Legacy controls/frozen-case creator chỉ trong khu kiểm thử, không làm phương án thường ngày. Dùng link/ID thật khi thao tác, không đổi identity của hồ sơ đang mở khi chuyển persona.

Run: `rtk proxy npm --prefix frontend run test -- --run src/settlement/App.test.tsx src/settlement/uiCopy.test.ts`.

## T4. Một mã hồ sơ chung trên inbox, workspace và các giai đoạn

**Files:** Modify `App.tsx`, `B7Intake.tsx`, `Report.tsx`, `uiCopy.ts`, `Actions.tsx` nếu cần truyền display name; tests `App.test.tsx`, `B7Intake.test.tsx`, `Report.test.tsx`. Technical details có thể giữ raw refs; không rewrite backend error codes.

**Interfaces:** `uiCopy.dossierReference(view: CaseView): string | null` lấy server field; compatibility với old loaded view dùng `linked_b7.origin.origin_case_id` hoặc B7 form origin đã typed, B3/standalone own ID. Nếu known linked nhưng thiếu root thì return null và `Chưa xác định hồ sơ gốc`, không lấy child ID để giả root. Summary dùng `dossier_ref`; old summary thiếu field chỉ hiển thị ID bản ghi với nhãn riêng, chờ backend mới.

- [x] **T4.1 RED — same dossier, different stage**. Render parent/B7 khác IDs cùng dossier_ref: header/inbox mã hồ sơ chung; nút mở parent gọi getCase(parent_id), upload/run gọi child.id. Hai chuyến cùng người/ngày vẫn có hai roots riêng. Adjustment không biến thành chuyến mới. Normal UI không hiện WORK/NV/ACC/department; technical details vẫn mở được raw IDs. Không làm mất chứng từ/source locators.

- [x] **T4.2 GREEN — copy và navigation**. Header dùng `Mã hồ sơ: {dossierReference(view)}` cùng tên người và giai đoạn. B7Intake bỏ `Công việc WORK-...`, hiển thị `Quyết toán thuộc hồ sơ ...` + `Xem đề nghị tạm ứng`. Inbox/search dùng root và tên/giai đoạn; không collapse bản ghi thành một stage tổng tự tính. Link adjustment tới quyết toán trước vẫn giữ. Source refs/amount/date/readability/owner không thay đổi vì identity display.

- [x] **T4.3 Documents không là khóa**. Test hai imports có cùng text `Số: DN-01` nhưng khác hồ sơ/keys không tự nối hoặc dedup; giấy không có Số vẫn được upload/preview. Test này dùng fake reader/source temp, không cần OCR LIVE. Nhân viên confirm draft vẫn cần; tên trên giấy khác profile phải giữ kiểm source/profile conflict hiện có, không vì account đã biết mà bỏ đối chiếu.

Run: `rtk proxy npm --prefix frontend run test -- --run src/settlement/App.test.tsx src/settlement/B7Intake.test.tsx src/settlement/Report.test.tsx`.

## T5. Nghiệm thu UI, bảo toàn dữ liệu và cập nhật docs

**Files:** Modify đúng phần liên quan `docs/settlement/PRODUCT.md` P2a/P3, `docs/settlement/SYSTEM.md` S6/S10, `docs/testing/B3_APPROVAL_WALKTHROUGH.md`, `docs/testing/B6_B7_LINKED_WALKTHROUGH.md`; `README.md` nếu command thay đổi. Ghi kết quả tại plan này, không tạo thêm report MD trùng. Không sửa brief/frozen corpus/private runtime DB.

- [x] **T5.1 Required checks** sau focused checks:

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake .venv/bin/python -m pytest tests/ -q
rtk proxy .venv/bin/python -m pip check
rtk proxy npm --prefix frontend run test -- --run
rtk proxy npm --prefix frontend run build
rtk git diff --check
```

Chỉ report actual counts/exit/mode. Phân biệt lỗi do task và lỗi từ dirty frontend trước task. Check frozen corpus bytes không đổi bằng Git diff/hash của manifests; không đóng task bằng sửa expected.

- [x] **T5.2 UI acceptance** trên DB/artifacts test riêng, fake/context đã cấu hình; không gọi LIVE hoặc dùng DB hiện tại. Browser bị policy chặn thì không bypass, giữ `USER_UI_UNEXECUTED` và giao checklist cho người dùng:

| Thao tác | Bằng chứng cần lưu |
| --- | --- |
| Chọn Nguyễn An, tạo hai đề nghị Hà Nội | Không nhập mã/phòng ban; hai mã hồ sơ riêng; người nộp đúng |
| Chuyển nhân viên khác khi có draft | Cancel giữ draft/actor; Accept bỏ draft chưa lưu; không gửi nhầm người |
| Kế toán rà soát, người duyệt quyết định | Tên người đề nghị giữ nguyên; audit đúng người thao tác, guards vẫn áp dụng |
| Mở quyết toán từ đề nghị đầu | Cùng mã hồ sơ, khác giai đoạn; không lấy ứng của đề nghị thứ hai |
| Chuyển hồ sơ, reload, mở chứng từ | Root không đổi, originals/versions không mất, request dùng đúng child ID |
| Tạo quyết toán tự chi trực tiếp | Không nhập employee/work; không tự tạo B3/ứng0; thiếu history vẫn cần làm rõ |
| Mở hồ sơ cũ có WORK scope | UI mã hồ sơ rõ; source/decision/history nguyên vẹn, scope quyền không bị nới |
| Hai giấy cùng Số hoặc thiếu Số | Không tự merge/khóa nộp chỉ vì Số; original giữ nguyên |

- [x] **T5.3 Update current docs**: mô tả root dossier ID và backend compatibility scope; picker mô phỏng, không authentication; B3/B7 separate records cùng root; managed standalone route mới; imported number không key. Chỉ đánh IMPLEMENTED sau wired path, VERIFIED theo mode của execution, UI nếu chưa thao tác ghi chưa nghiệm thu. Không claim quality baseline từ identity tests.

## Prompt giao coding agent

```text
Đọc AGENTS.md và docs/superpowers/plans/2026-10-12-dossier-identity-and-demo-personas.md.
Triển khai T1–T5, test regression đỏ trước sửa. Đọc current diff vì App/B3Intake/styles/
DocumentViewer đang có thay đổi của writer khác; giữ nguyên phần không thuộc nhiệm vụ.
Mục tiêu: một người dùng demo theo profile, không nhập mã; mã hồ sơ gốc chung cho
tạm ứng/quyết toán; hồ sơ mới không sinh WORK ID thứ hai. Giữ scopes/historical IDs
và frozen datasets cũ, không merge DB rows hoặc bỏ financial guards. B7 tự chi vẫn có
đường tạo không mã, không biến thành tạm ứng0. Không thêm login/framework/SQL migration/
counter số giấy, không gọi LIVE/Git/publish. Báo tests thực chạy, diff, checklist UI và
mọi phần USER_UI_UNEXECUTED; checkbox/source không chứng minh UI hay quality AI.
```
