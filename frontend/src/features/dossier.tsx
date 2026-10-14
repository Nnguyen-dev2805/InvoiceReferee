import type { CaseView } from "../types";

const STATE_LABELS: Record<string, string> = {
  DRAFT: "Bản nháp",
  PROCESSING: "Đang xử lý",
  EVIDENCE_READY: "Đã đọc chứng từ",
  WAITING: "Chờ người xử lý",
  TECHNICAL_ERROR: "Lỗi xử lý",
  READY_TO_EXECUTE: "Sẵn sàng thực hiện",
  SETTLED: "Đã cân bằng",
  STOPPED: "Đã dừng",
};

// A payment basis is labelled by what actually established it: a Q32 employee
// declaration is NOT a bank-verified fact (ADR0007), so the label must not
// imply bank verification.
const BASIS_LABELS: Record<string, string> = {
  INDEPENDENT_PAYMENT: "Chứng từ thanh toán độc lập",
  FINANCIAL_CONFIRMATION: "Xác nhận tài chính",
  EMPLOYEE_DECLARATION_Q32: "Lời xác nhận của nhân viên",
  UNSPECIFIED_LEGACY: "Chưa xác định căn cứ",
};

const ISSUE_LABELS: Record<string, string> = {
  FACT: "Dữ kiện",
  POLICY: "Chính sách",
  AUTHORITY: "Quyền",
};

const MONEY_LABELS: Record<string, string> = {
  T: "Tổng chi công việc",
  E: "Chi phí đủ điều kiện",
  C: "Công ty trả trực tiếp",
  A: "Ứng thực nhận",
  P: "Đã hoàn",
  R: "Đã thu hồi",
  unpaid: "Chưa thanh toán",
  S: "Chênh lệch (S)",
};

const UNKNOWN_LABEL = "Chưa xác minh";

export function formatMoney(value: number | null): string {
  if (value === null) return UNKNOWN_LABEL;
  return new Intl.NumberFormat("vi-VN").format(value) + " ₫";
}

/** One money figure: a known amount, or an explicit "chưa xác minh" state. */
export function MoneyLine({
  label,
  fact,
}: {
  label: string;
  fact: { value: number | null; state: string };
}) {
  const known = fact.state === "KNOWN" && fact.value !== null;
  return (
    <li data-testid={`money-${label}`}>
      {label}: <strong>{known ? formatMoney(fact.value) : UNKNOWN_LABEL}</strong>
    </li>
  );
}

export function Dossier({ caseView }: { caseView: CaseView | null }) {
  return (
    <section aria-labelledby="dossier-title">
      <h2 id="dossier-title">Hồ sơ</h2>
      {caseView === null ? (
        <p className="muted">
          Chưa có hồ sơ nào được mở. Hãy chọn hoạt động và tạo hồ sơ.
        </p>
      ) : (
        <>
          <p className="summary">{caseView.summary}</p>
          <p>
            Trạng thái:{" "}
            <strong>{STATE_LABELS[caseView.state] ?? caseView.state}</strong>{" "}
            <span className="muted">(phiên bản {caseView.version})</span>
          </p>

          <h3>Chứng từ ({caseView.sources.length})</h3>
          {caseView.sources.length === 0 ? (
            <p className="muted">Chưa có chứng từ nào.</p>
          ) : (
            <ul>
              {caseView.sources.map((source) => (
                <li key={source.id}>
                  {source.media} · {source.digest.slice(0, 12)}…
                </li>
              ))}
            </ul>
          )}

          <h3>Số tiền</h3>
          <ul className="money">
            {Object.entries(caseView.actual_money)
              .filter(([key]) => key in MONEY_LABELS)
              .map(([key, fact]) => (
                <MoneyLine key={key} label={MONEY_LABELS[key]} fact={fact} />
              ))}
          </ul>

          {caseView.payment_basis.length > 0 && (
            <>
              <h3>Căn cứ chi trả</h3>
              <ul className="payment-basis" data-testid="payment-basis">
                {caseView.payment_basis.map((basis) => (
                  <li key={basis.expense_id} data-testid={`basis-${basis.expense_id}`}>
                    {BASIS_LABELS[basis.kind] ?? basis.kind}
                    {basis.actor ? ` · ${basis.actor}` : ""}
                  </li>
                ))}
              </ul>
            </>
          )}

          <h3>Việc cần xử lý ({caseView.issues.length})</h3>
          {caseView.issues.length === 0 ? (
            <p className="muted">Chưa có việc cần xử lý ở bước này.</p>
          ) : (
            <ul className="issues">
              {caseView.issues.map((issue) => (
                <li key={issue.id}>
                  <p>
                    <strong>[{ISSUE_LABELS[issue.kind] ?? issue.kind}]</strong>{" "}
                    {issue.question}
                  </p>
                  <p className="muted">
                    Người xử lý: {issue.owner} · Căn cứ: {issue.basis}
                  </p>
                </li>
              ))}
            </ul>
          )}

          <h3>Lịch sử</h3>
          <ul className="audit">
            {caseView.audit.map((line, index) => (
              <li key={`${index}-${line}`}>{line}</li>
            ))}
          </ul>

          <details>
            <summary>Chi tiết kỹ thuật</summary>
            <pre>
              {JSON.stringify(
                {
                  id: caseView.id,
                  state: caseView.state,
                  version: caseView.version,
                  actual_money: caseView.actual_money,
                },
                null,
                2,
              )}
            </pre>
          </details>
        </>
      )}
    </section>
  );
}
