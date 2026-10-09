# InvoiceReferee — Evaluation hiện hành

Ngày 09/10/2026. **Protocol đã được đồng ý; chưa có baseline chất lượng mới, gold độc lập, holdout hoặc professional trial.** Đọc cùng [Product](PRODUCT.md), [Rulebook](RULEBOOK.md), [System](SYSTEM.md) và [plan](../superpowers/plans/2026-10-09-settlement-mvp.md). [Đề cuộc thi gốc](../Challenge_Brief_OrganizationAI_VN.docx.md) quyết định requirements.

## E1. Đơn vị chấm và hoàn thành

B7 là job chính; B3 chấm riêng. Một run là một job với input, nguồn, policy, config, mốc tiền và revision rõ. Các run trước/sau bổ sung hoặc receipt thuộc lifecycle liên kết. Hồ sơ thiếu/mâu thuẫn vẫn vào mẫu số; không lọc chỉ hồ sơ đủ nguồn trước khi đo.

Gold routine: đủ căn cứ để lưu report/checks đúng trong scope, không cần người chọn giao dịch, sửa fact, ghép trước hoặc giải quyết fact/policy/quyền giữa chừng. Loại một phần chi cá nhân chắc chắn theo rule vẫn có thể routine; không chỉ chọn happy cases. Gold needs-resolution có material issues cần giải quyết, có thể nhiều issue/case. Technical/capability/Stop là trục riêng.

First-pass completion tính từ submit tới kết quả đúng được lưu, không có can thiệp fact. Re-check sau phản hồi là assisted, không đổi nhãn ban đầu thành routine. Upload/import là input nhưng công sức tìm/export/chuẩn bị/handmatching phải đo. Checkpoint kế toán và người duyệt thường quy không là FP, vẫn tính effort. Job complete khác phê duyệt, thực nhận và đóng; net đúng nhưng action/state sai vẫn fail.

## E2. Gold và dữ liệu

Mỗi packet cần family/job/mốc; manifest tách input, expected và followup; originals/coverage; policy snapshot/quyền; critical facts có value hoặc unknown và refs; quan hệ expense–payment/parts/same-event; checks/issues/owner và phản hồi đủ; components/net hoặc unknown; permitted/forbidden actions và closure conditions.

Oracle đọc nguồn/policy độc lập production output/engine. Cần lượt đối chiếu nguồn và số học khác trước freeze. Bất đồng giữ reason/unknown; không sửa expected theo output để xanh. Policy đổi phải version và giải thích gold đổi vì rule nào. Attestation khác bank proof. Chấm câu hỏi theo ý nghĩa/owner/refs, không exact phrase hoặc IDs tự sinh.

[Corpus development](../discovery/eval_development/CORPUS_INDEX.md) có 20 packet conditions: 15 B7 + 5 B3, một template family, 9 routine/11 needs theo expected nháp, single-author và nhiều counterfactuals. Hash đúng không xác thực truth hoặc chứng minh 20 test pass. Initial closure chỉ Q04 vì có decision/actual receipt/scope đủ. Chưa gold adjudication độc lập, OCR/matching chất lượng thực, control traces hoặc trial người thật.

Corpus và examples giữ nguyên bytes/paths, gồm inputs, policy bundles, expected, followup, JSON/CSV/PNG. `policy_files[*].snapshot_path` và hash là phiên bản của case; `source_path` là origin lịch sử có thể tra trong [archive manifest](../archive/MANIFEST.json). Không dùng Rulebook hôm nay thay frozen policy, sửa input/gold để thuận output hoặc nạp expected vào prompt. Dataset Markdown là dữ liệu đánh giá, không policy toàn app.

Giới hạn: author hints trong narrative, coverage giả lập được cung cấp, Q07 đã có bank–finance mapping, nguồn text sạch hơn raw OCR/matching, expected money fields khác nhau, một PNG bị che tổng. Khi tạo quality dataset, đưa ghi chú tác giả khỏi prompt bằng version mới; không sửa âm thầm bộ cũ. Q08 là unknown case, không thay case nguồn rõ nhưng reader đọc sai.

## E3. Trục chấm và mẫu số

| Trục | Chấm cụ thể | Không đủ để coi đúng |
| --- | --- | --- |
| Extraction | Critical known fields đúng value/type/meaning/ref/locator; unknown đúng riêng; missing/abstain trên nguồn rõ là lỗi | JSON valid, cả document READABLE hoặc quote model tự viết |
| Linking | Required links/parts đúng; extra wrong links; namespaces và source support | Net đúng tình cờ, amount/date khớp hoặc người đã ghép trước |
| Rule/money | Applicability/checks/components, exact integer amount/chiều hoặc null đúng; đủ material dependencies | Chỉ S đúng hoặc production engine làm oracle |
| Escalation | Đủ material issues; đúng FACT/POLICY/AUTHORITY/owner; technical riêng | Một NEEDS_HUMAN che issue bị bỏ sót hoặc wrong reason |
| Question/continue | Khoản/ref/đã biết/vướng/request đúng owner; phản hồi đủ giúp tiếp tục, sai không resolve | Văn phong hay hoặc khớp câu mẫu |
| Control/workflow | State/action/history thật: Stop/stale/trùng/partial/incidents/closure | UI báo dừng/đóng nhưng hậu quả lưu sai |
| Operation/value | Calls/retries/timing/usage provenance; prep→review→decision→reconcile, onboarding và wait | Replay latency là live hoặc LLM nhanh hơn là kế toán tiết kiệm |

Mẫu số critical facts/links cố định trước thấy output, kể cả gold fact bị output bỏ sót. Alternative source đủ căn cứ có thể pass mà không trích mọi field trên mọi bill. Extra wrong link đổi tiền làm case fail. Expected null phải assert actual null; không skip hoặc lấy first-non-null làm payable. Unknown không cho guessed amount kèm disclaimer pass.

`N_need` là tất cả gold-needs cases, `N_routine` là tất cả gold-routine cases trong set đã cố định. FN: needs case tự complete không chuyển tiếp. FP: routine bị đòi giải quyết issue không có thật. Wrong reason/owner chấm detection riêng nhưng fail reason/question. `U_need`/`U_routine`: không có output chấm được vì technical/timeout/capability, không gán business uncertainty giả.

Báo FN/N_need, FP/N_routine cùng U/N và khoảng bảo thủ: `[FN/N_need,(FN+U_need)/N_need]`, `[FP/N_routine,(FP+U_routine)/N_routine]`. Mẫu số 0 là N/A, không 100%. First-pass routine completion = số job routine đúng được lưu tự động / N_routine; failure/không output là chưa hoàn thành. Issue recall riêng chống một issue che lỗi bỏ sót khác. FN=0 không tốt nếu toàn N lỗi kỹ thuật.

Lưu mọi lần thử/repair/retry/failure, không chọn chỉ lần thành công. Usage/cost vắng là unavailable, không 0. Reuse giữ origin/config; không báo nó là lần đọc live mới. Nếu không đủ trace xác định nguyên nhân, ghi inconclusive thay vì quy hết lỗi cho OCR/model.

## E4. Catalogue và controls

| IDs | Nội dung |
| --- | --- |
| Q01–Q04 | Chi thêm, tự chi có nguồn zero, hoàn ứng thừa và already-fulfilled zero |
| Q05–Q07 | Split payer, phần cá nhân, invoice/event aliases so với giao dịch khác cùng amount/date; chấm links ngoài net |
| Q08–Q12 | Số bắt buộc không đọc được, cash payer thiếu, coverage gap, actual advance unknown, payer contradiction |
| Q13–Q15 | Budget exception, authority sai scope, chưa prior B/post-incurred acceptance |
| A01–A05 | Native proposal, external decision reuse, estimate conflict, history gap, authority scope |

Q13 conditional 4 không approved 4 trước decision; Q14 calculated 3 không authorized 3; Q08 known subtotal 2−A2 không whole S0. Branches theo manifests/version; không IDs/file names làm production branching. Clones/M1/M2 cùng family không independent cases để suy tác động.

| ID | Assertion phải có bằng chứng thực thi |
| --- | --- |
| C01 | Rerun/copy fulfilled không new request/money/entitlement; giữ history/refs |
| C02 | Approved3, actual2, pending1 giữ remaining1; không close/chi trùng hoặc rewrite approved2 |
| C03 | Sai payee/overpay giữ raw incident; không correct fulfillment/clip/auto recovery hoặc suy absence0 |
| C04 | Stop ack rồi late output không current/handoff/action/close; local Stop không bank cancel |
| C05 | Material input/policy/authority change re-check validity; giữ old decision; đúng fulfillment giảm remaining không ritual approval |
| C06 | Sai owner/scope/unsupported answer/typed unreadable amount không resolve; source đủ và re-check mới hết issue |
| C07 | Event/decision sau money cutoff không vào old run; đổi scope/revision liên kết và giữ initial |

Controls này là spec, chưa có traces đã chạy cho lõi mới. SYS-01..17 trong System nối plan tới integration/UI và hậu quả persisted; không cần distributed framework.

## E5. Splits, Verify và freeze

Development 20 dùng thiết kế/tune, chưa holdout. Calibration/holdout mới về family/source/layout/business context; không chia clones qua các sets hoặc đổi amount cùng template gọi độc lập. Holdout không chọn prompt/model/threshold. Sau dùng lỗi holdout để sửa, set đó thành feedback/development; cần fresh holdout cho claim độc lập.

Freeze dataset/input/source/policy/gold/model/config trước run. B1 có thể baseline yếu nhưng log trung thực, không readiness đã đạt. B2 so cùng scope/policy/common comparison set và set độc lập mới thích hợp; không nhớ expected hoặc nới business rules để tăng score.

Verify Escalation 5 đề xuất 3 B7 routine (+3, surplus−0,7, fulfilled0) và 2 needs (actual advance unknown, budget exception có quyền). Full suite vẫn cần authority Q14/Q15 và inputs mới. Core 4 là suite riêng theo đề. Runner sequential qua cùng app; hiển thị expected/actual/verdict/timestamp/mode/versions. CLI được mô tả nhưng chưa chạy không verified.

## E6. Gates và phép so sánh AI

| Gate | Evidence |
| --- | --- |
| Đo baseline | Packets/gold/source-policy được rà soát/version, actual runs/logs toàn set cùng app; failures báo đủ |
| Report đúng trên declared suite | Không critical money/source/null/policy/state violation; đủ gold checks và technical outcomes; không đảm bảo mọi input |
| Mở action B | Ngoài A cần persisted proof quyền/version/Stop/stale/idempotency/audit/history; vẫn không bank execution |
| Value/Sprint2 | Ít nhất 3 professional users thật, before/after, feedback cải tiến, independent miss/unnecessary metrics |

Đo rules với facts chuẩn → fake/replay pipeline → live originals → UI → trial nghiệp vụ. POLICY_REPLAY, PIPELINE_FAKE_OR_REPLAY, LIVE_END_TO_END và trial chứng minh các phần khác nhau. Fake không reader quality; UI đúng không full-corpus quality; unit xanh không chứng minh composition UI.

M0 bring-up sau authorization phù hợp: nguồn synthetic nhỏ kiểm account/model/output/ref, vision/reasoning thực quan sát và usage. M1 giữ OCR outputs/prompts/keys/candidates/budget so Small-none/Medium-none. M2 giữ originals/gold/keys/policy so OCR→selected model với vision trực tiếp. M3 calibration signals; M4 freeze/holdout; M5 UI 5 phiên/controls/effort. Không benchmark 130 models vì catalog có 130; tăng reasoning/model chỉ khi có failure cụ thể và controlled comparison.

Strata cần native/mixed/scan PDF, chữ số nhỏ, xoay/mờ/cắt góc, total/subtotal, personal/split, multipage, hidden-text mismatch và genuinely unknown. Chọn đường chính bằng downstream quality/abstention/links/failures/latency/cost, không chỉ OCR char accuracy hoặc bảng xếp hạng vendor. Fallback chỉ nhóm lỗi có evidence cải thiện; không lấy reader trả số để pass, disagreements giữ issue. Hai readers không independent truth.

Adaptation Sprint2 dùng feedback/calibration để đổi quality/linkage/escalation threshold version, không budget/quyền/receipt/source/unknown hard gates. Signals có nguồn; score vắng không chế confidence từ văn phong. Đo activation/rollback/version và fresh holdout; chưa có signal đủ không giả đã hoàn thành adaptation.

## E7. Trial, operation và submission

So manual/assisted cùng scope/checkpoints, đảo thứ tự hoặc cases tương đương để giảm hiệu ứng nhớ. Đo active effort và wait riêng: tìm/export/upload/import/handmatch, đọc/check/sửa/bổ sung, review/decision, receipt/closure; giữ onboarding và khó khăn mới. Prep trước Run không 0 vì đã làm ngoài app.

Pilot cùng operator không professional trial. Ít nhất 3 người thật theo đề, permission và synthetic/redacted data phù hợp; feedback/cải tiến có nguồn. Báo N nhỏ, từng case/person, errors/corrections; không suy mọi doanh nghiệp hoặc hứa tiết kiệm 80%. Research/agent/synthetic feedback không thay người làm nghiệp vụ.

Live URL public không signup, clean-clone runbook, Core 4/Escalation 5/new input/audit/Stop/Override, public repo/history, đúng 5 slides/video ≤3 phút/build log và rehearsal là gates riêng theo đề. User muốn live URL cuối; không tự publish/Git/outbound hoặc tạo feedback giả. Hạn 15/10 khóa,17/10 demo; quality không suy từ spec hoặc agent completion.
