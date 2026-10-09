// Questions panel (W04): each unresolved report issue becomes a question with
// owner and refs; answering records the response — only a re-check resolves.
import { useState } from 'react';
import type { QuestionView } from './types';

const OWNER_LABELS: Record<QuestionView['owner'], string> = {
  EMPLOYEE: 'Nhân viên',
  ACCOUNTANT: 'Kế toán',
  APPROVER: 'Người duyệt',
};

const STATUS_LABELS: Record<QuestionView['status'], string> = {
  OPEN: 'Đang chờ trả lời',
  ANSWERED: 'Đã trả lời — chờ re-check',
  RESOLVED: 'Đã xử lý',
  SUPERSEDED: 'Không còn áp dụng',
};

interface AnswerDraft {
  content: string;
  sourceIds: string[];
}

export function QuestionsPanel({
  questions,
  caseVersion,
  sourceIds,
  role,
  onResponded,
}: {
  questions: QuestionView[];
  caseVersion: number;
  sourceIds: string[];
  role: string;
  onResponded: (questionId: string, draft: AnswerDraft) => Promise<void>;
}) {
  const [drafts, setDrafts] = useState<Record<string, AnswerDraft>>({});

  const draftFor = (questionId: string): AnswerDraft =>
    drafts[questionId] ?? { content: '', sourceIds: [] };

  const setDraft = (questionId: string, update: Partial<AnswerDraft>) =>
    setDrafts((current) => ({
      ...current,
      [questionId]: { ...draftFor(questionId), ...update },
    }));

  if (questions.length === 0) {
    return (
      <div className="panel" data-testid="questions-panel">
        <h2>Câu hỏi</h2>
        <p className="muted">Chưa có câu hỏi nào cho hồ sơ này.</p>
      </div>
    );
  }

  return (
    <div className="panel" data-testid="questions-panel">
      <h2>Câu hỏi ({questions.length})</h2>
      <p className="muted">
        Trả lời đúng owner với nguồn tham chiếu; lời khai không tự thành fact —
        chỉ re-check sau khi có nguồn mới kết luận được.
      </p>
      {questions.map((question) => {
        const draft = draftFor(question.id);
        const ownerMatch = role === question.owner;
        return (
          <div key={question.id} className="field">
            <h3>{STATUS_LABELS[question.status]} — {OWNER_LABELS[question.owner]}</h3>
            <p>{question.message}</p>
            {question.refs.length > 0 && (
              <p className="muted">
                Refs:{' '}
                {question.refs.map((ref) => (
                  <code key={ref}>{ref}</code>
                ))}
              </p>
            )}
            {question.status === 'OPEN' && (
              <>
                <label htmlFor={`answer-${question.id}`}>Trả lời</label>
                <input
                  id={`answer-${question.id}`}
                  value={draft.content}
                  placeholder="Nội dung trả lời cho owner"
                  onChange={(e) => setDraft(question.id, { content: e.target.value })}
                />
                <label>Nguồn tham chiếu (chọn nguồn đã upload)</label>
                {sourceIds.length === 0 && (
                  <p className="muted">Chưa có nguồn nào trong hồ sơ để tham chiếu.</p>
                )}
                {sourceIds.map((sourceId) => (
                  <label key={sourceId} className="helper">
                    <input
                      type="checkbox"
                      checked={draft.sourceIds.includes(sourceId)}
                      onChange={(e) =>
                        setDraft(question.id, {
                          sourceIds: e.target.checked
                            ? [...draft.sourceIds, sourceId]
                            : draft.sourceIds.filter((s) => s !== sourceId),
                        })
                      }
                    />{' '}
                    {sourceId}
                  </label>
                ))}
                {!ownerMatch && (
                  <p className="notice-warn" role="alert">
                    Vai hiện tại ({role}) không phải owner của câu hỏi — phản hồi
                    sẽ được ghi lại nhưng không resolve.
                  </p>
                )}
                <button
                  className="btn"
                  disabled={!draft.content.trim()}
                  onClick={() =>
                    void onResponded(question.id, draft)
                  }
                >
                  Gửi trả lời (version {caseVersion})
                </button>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
