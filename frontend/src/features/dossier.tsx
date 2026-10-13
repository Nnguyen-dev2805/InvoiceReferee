import type { CaseView } from "../types";

const STATE_LABELS: Record<string, string> = {
  DRAFT: "Bản nháp",
  PROCESSING: "Đang xử lý",
  WAITING: "Chờ người xử lý",
  TECHNICAL_ERROR: "Lỗi xử lý",
  READY_TO_EXECUTE: "Sẵn sàng thực hiện",
  SETTLED: "Đã cân bằng",
  STOPPED: "Đã dừng",
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
