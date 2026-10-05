import { useState } from 'react';
import type { AuditEvent, CaseRecord, PaymentRequest, RunRecord, SourceRef, StopReply } from './types';
import {
  ACTION_LABEL,
  ISSUE_CLASS_LABEL,
  RUN_STATUS_LABEL,
  formatVnd,
  runInFlight,
  stageLabel,
} from './format';
import { AlertIcon, CheckCircleIcon, MoneyIcon, QuestionIcon, StopIcon } from './icons';

interface CaseDetailProps {
  run: RunRecord;
  onStop: () => Promise<StopReply>;
  caseRecord?: CaseRecord;
  paymentRequest?: PaymentRequest | null;
  history?: AuditEvent[];
}

type StopState = 'idle' | 'pending' | 'stopped' | 'completed';

export function CaseDetail({
  run,
  onStop,
  caseRecord,
  paymentRequest,
  history,
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

      <PipelineStepper
        stage={run.stage}
        isFlight={runInFlight(run.status)}
        isDone={run.status === 'SUCCEEDED'}
      />

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
                <SourceRefs refs={issue.refs} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {decision && decision.checks.length > 0 && (
        <details className="checks">
          <summary>Kiểm tra đã chạy ({decision.checks.length})</summary>
          <ul>
            {decision.checks.map((check) => (
              <li key={check.rule_id} className={`check check-${check.status.toLowerCase()}`}>
                <span className="check-rule">{check.rule_id}</span>
                <span className="check-status">{check.status}</span>
                <span className="check-reason">{check.reason}</span>
                <SourceRefs refs={check.refs} />
              </li>
            ))}
          </ul>
        </details>
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

      {history && history.length > 0 && <AuditTimeline events={history} />}

      {decision && (
        <details className="diagnostics">
          <summary>Chi tiết kỹ thuật (JSON)</summary>
          <pre>{JSON.stringify(run.result, null, 2)}</pre>
        </details>
      )}
    </section>
  );
}

// --- Pipeline Stepper ---------------------------------------------------------

const PIPELINE_STEPS = ['Tiếp nhận', 'Đọc OCR', 'Đối chiếu', 'Quy định', 'Quyết định'];

function getPipelineStepIndex(stage: string | null | undefined, isDone: boolean): number {
  if (isDone) return 4;
  if (!stage) return 0;
  if (stage === 'created' || stage === 'intake') return 0;
  if (stage.startsWith('ocr')) return 1;
  if (stage.startsWith('analyze') || stage.startsWith('apply') || stage === 'cross_source') return 2;
  if (stage === 'policy' || stage.includes('evaluate')) return 3;
  if (stage === 'finalized') return 4;
  return 2;
}

function PipelineStepper({
  stage,
  isFlight,
  isDone,
}: {
  stage: string | null | undefined;
  isFlight: boolean;
  isDone: boolean;
}) {
  const currentStep = getPipelineStepIndex(stage, isDone);
  return (
    <div className="stepper" role="region" aria-label="Tiến trình xử lý hồ sơ">
      <div className="stepper-track">
        {PIPELINE_STEPS.map((label, idx) => {
          const isCompleted = isDone || idx < currentStep;
          const isActive = !isDone && idx === currentStep;
          return (
            <div
              key={label}
              className={`stepper-step ${isCompleted ? 'step-completed' : ''} ${isActive ? 'step-active' : ''}`}
            >
              <div className="step-circle" aria-hidden="true">
                {isCompleted ? '✓' : idx + 1}
              </div>
              <span className="step-label">{label}</span>
            </div>
          );
        })}
      </div>
      {isFlight && stageLabel(stage) && (
        <p className="stage-line" role="status">
          Bước hiện tại: <strong>{stageLabel(stage)}</strong>
        </p>
      )}
    </div>
  );
}

// --- Source references (provenance of a fact/issue/check) ----------------------

const EVENT_KIND_LABEL: Record<string, string> = {
  CASE_CREATED: 'Tạo hồ sơ',
  RUN_STARTED: 'Bắt đầu xử lý',
  STAGE: 'Bước xử lý',
  RUN_FINALIZED: 'Kết thúc xử lý',
  POLICY_CHANGE: 'Thay đổi policy',
  HUMAN_ACTION: 'Hành động con người',
  STOP_REQUESTED: 'Yêu cầu dừng',
};

function SourceRefs({ refs }: { refs: SourceRef[] }) {
  if (!refs || refs.length === 0) return null;
  return (
    <ul className="source-refs">
      {refs.map((ref, index) => (
        <li key={`${ref.evidence_id}-${ref.locator}-${index}`}>
          <code>{ref.locator}</code> · <span>{ref.raw_value}</span>
          <span className="muted"> (chứng từ {ref.evidence_id.slice(0, 8)}…, trang {ref.page_index + 1})</span>
        </li>
      ))}
    </ul>
  );
}

function AuditTimeline({ events }: { events: AuditEvent[] }) {
  // Newest first for a readable audit trail.
  const ordered = [...events].sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1));
  return (
    <details className="audit" open>
      <summary>Nhật ký kiểm toán ({events.length})</summary>
      <div className="timeline-container">
        <ol className="timeline">
          {ordered.map((event) => (
            <li key={event.id} className="timeline-item">
              <span className="timeline-node" aria-hidden="true" />
              <div className="timeline-content">
                <div className="timeline-header">
                  <span className="audit-kind">{EVENT_KIND_LABEL[event.kind] ?? event.kind}</span>
                  <time dateTime={event.timestamp}>
                    {new Date(event.timestamp).toLocaleString('vi-VN')}
                  </time>
                </div>
                {event.stage && (
                  <p className="muted timeline-meta">{stageLabel(event.stage) ?? event.stage}</p>
                )}
                {event.reason && (
                  <p className="audit-reason timeline-meta">{event.reason}</p>
                )}
              </div>
            </li>
          ))}
        </ol>
      </div>
    </details>
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
