// Processing details: the run trace / technical debug surface for one snapshot.
// Read-only — no fetch and no provider side effects. The default screen shows a
// single visible simulation label; raw run id/status/stage live in here.
import type { Report, RunView } from './types';

interface ProcessingDetailsProps {
  run: RunView | null;
  report: Report | null;
}

export function ProcessingDetails({ run, report }: ProcessingDetailsProps) {
  if (!run) return null;
  return (
    <details className="tech-context-summary sr-only" data-testid="processing-details">
      <summary>Thông tin xử lý</summary>
      <ul className="reasons">
        <li>Run: <code>{run.id}</code></li>
        <li>Trạng thái run: <code>{run.status}</code>
          {run.completion ? ` (${run.completion})` : ''}</li>
        {run.stage && <li>Giai đoạn: <code>{run.stage}</code></li>}
        <li>Chế độ nguồn: <code>{run.mode}</code></li>
        {report && <li>Report: <code>{report.run_id}</code> · <code>{report.completion}</code></li>}
      </ul>
    </details>
  );
}
