import { useState } from 'react';
import type { CaseRecord, PaymentRequest, RunRecord, StopReply } from './types';
import {
  ACTION_LABEL,
  ISSUE_CLASS_LABEL,
  RUN_STATUS_LABEL,
  formatVnd,
  runInFlight,
} from './format';
import { AlertIcon, CheckCircleIcon, MoneyIcon, QuestionIcon, StopIcon } from './icons';

interface CaseDetailProps {
  run: RunRecord;
  onStop: () => Promise<StopReply>;
  caseRecord?: CaseRecord;
  paymentRequest?: PaymentRequest | null;
  policyActive?: boolean;
  onActivatePolicy?: (reason: string) => Promise<void>;
}

type StopState = 'idle' | 'pending' | 'stopped' | 'completed';

export function CaseDetail({
  run,
  onStop,
  caseRecord,
  paymentRequest,
  policyActive = true,
  onActivatePolicy,
}: CaseDetailProps) {
  const [stopState, setStopState] = useState<StopState>('idle');
  const [stopError, setStopError] = useState<string | null>(null);
  const decision = run.result?.decision;
  const canStop = runInFlight(run.status) && stopState === 'idle';

  async function handleStop() {
    setStopState('pending');
    setStopError(null);
    try {
      const reply = await onStop();
      if (reply.status === 'ALREADY_COMPLETED') {
        setStopState('completed');
      } else {
        setStopState('stopped');
      }
    } catch (error) {
      setStopState('idle');
      setStopError(error instanceof Error ? error.message : 'Dừng thất bại.');
    }
  }

  return (
    <section className="panel" aria-labelledby="detail-heading">
      <header className="panel-head">
        <h2 id="detail-heading">Hồ sơ {run.case_id}</h2>
        <span className={`status status-${run.status.toLowerCase()}`}>
          {RUN_STATUS_LABEL[run.status]}
        </span>
      </header>

      {!policyActive && onActivatePolicy && (
        <PolicyNotice onActivatePolicy={onActivatePolicy} />
      )}

      {run.status === 'FAILED' && (
        <div className="notice notice-error" role="alert">
          <AlertIcon />
          <div>
            <strong>Lỗi kỹ thuật khi xử lý.</strong>
            <p>{decision?.technical_code ?? 'Không có mã lỗi.'} — đây không phải kết luận nghiệp vụ.</p>
          </div>
        </div>
      )}

      {decision && <DecisionSummary decision={decision} />}

      {decision && decision.issues.length > 0 && (
        <div className="issues">
          <h3>Câu hỏi / vấn đề cần xử lý</h3>
          <ul>
            {decision.issues.map((issue) => (
              <li key={issue.id} className="issue">
                <span className="issue-class">{ISSUE_CLASS_LABEL[issue.issue_class]}</span>
                <p>{issue.question}</p>
                <span className="issue-owner">Người xử lý: {issue.owner_mode}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {caseRecord && caseRecord.evidence.length > 0 && (
        <div className="evidence">
          <h3>Chứng từ</h3>
          <ul>
            {caseRecord.evidence.map((item) => (
              <li key={item.id}>
                {item.original_name} · {item.role} · {Math.ceil(item.size / 1024)} KB
              </li>
            ))}
          </ul>
        </div>
      )}

      {decision?.action === 'CREATE_PAYMENT_REQUEST' && (
        <div className="payment" aria-live="polite">
          <MoneyIcon />
          <div>
            <strong>Đã tạo đề nghị chi trả</strong>
            <p>
              Số tiền: {formatVnd(paymentRequest?.amount_vnd ?? decision.accepted_amount_vnd)}.
              Đây là đề nghị chi trả, chưa phải xác nhận đã chuyển tiền.
            </p>
            {paymentRequest && paymentRequest.status !== 'CREATED' && (
              <p className="muted">Trạng thái đề nghị: {paymentRequest.status}.</p>
            )}
          </div>
        </div>
      )}

      <div className="detail-actions">
        {canStop && (
          <button type="button" className="btn btn-danger" onClick={handleStop}>
            <StopIcon /> Dừng xử lý
          </button>
        )}
        {stopState === 'pending' && (
          <span className="muted" role="status">
            Đang dừng… chờ máy chủ xác nhận.
          </span>
        )}
        {stopState === 'stopped' && (
          <span role="status">Đã dừng xử lý.</span>
        )}
        {stopState === 'completed' && (
          <span role="status">Không thể dừng: hồ sơ đã hoàn tất trước đó.</span>
        )}
      </div>
      {stopError && (
        <p className="field-error" role="alert">
          {stopError}
        </p>
      )}

      {decision && (
        <details className="diagnostics">
          <summary>Chi tiết kỹ thuật (JSON)</summary>
          <pre>{JSON.stringify(run.result, null, 2)}</pre>
        </details>
      )}
    </section>
  );
}

function DecisionSummary({ decision }: { decision: NonNullable<RunRecord['result']>['decision'] }) {
  const isCreate = decision.action === 'CREATE_PAYMENT_REQUEST';
  const isHuman = decision.action === 'REQUEST_INFO' || decision.action === 'ESCALATE';
  return (
    <div className={`decision decision-${decision.action.toLowerCase()}`}>
      <div className="decision-head">
        {isCreate && <CheckCircleIcon />}
        {isHuman && <QuestionIcon />}
        {decision.action === 'REJECT' && <AlertIcon />}
        <strong>{ACTION_LABEL[decision.action]}</strong>
      </div>
      {isCreate && (
        <p>
          Số tiền chấp nhận: <strong>{formatVnd(decision.accepted_amount_vnd)}</strong>
          {decision.completion_basis === 'HUMAN_AUTHORIZED' && ' (sau phê duyệt của con người)'}
        </p>
      )}
      {decision.reasons.length > 0 && (
        <ul className="reasons">
          {decision.reasons.map((reason, index) => (
            <li key={index}>{reason}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PolicyNotice({ onActivatePolicy }: { onActivatePolicy: (reason: string) => Promise<void> }) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!reason.trim()) {
      setError('Cần lý do để kích hoạt policy demo.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onActivatePolicy(reason);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Kích hoạt thất bại.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="notice notice-warn">
      <AlertIcon />
      <div>
        <strong>Policy demo chưa được kích hoạt.</strong>
        <p>Hệ thống sẽ không tự xử lý cho tới khi policy được kích hoạt tường minh.</p>
        <div className="field">
          <label htmlFor="policy-reason">Lý do kích hoạt</label>
          <input
            id="policy-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
          {error && <p className="field-error" role="alert">{error}</p>}
        </div>
        <button type="button" className="btn" onClick={submit} disabled={busy}>
          {busy ? 'Đang kích hoạt…' : 'Kích hoạt policy demo'}
        </button>
      </div>
    </div>
  );
}
