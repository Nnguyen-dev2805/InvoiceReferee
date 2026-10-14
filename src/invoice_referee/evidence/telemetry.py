"""Operation/step tracing over the real workflow (contracts §9; LangSmith wiring).

One `operation()` is one real unit of work the user triggered — a draft read, a
submit/processing job, an answer/decision re-assessment, an actual-money record,
a Stop/Resume. Each operation opens a ROOT span; the work it performs emits child
`step()` spans with their OWN ids and the root as parent, so a processing trace
is a tree (not a flat list of runs that reuse one id).

Design rules (14/10/2026 wiring):

- **No network inside a SQLite mutation transaction.** Spans are buffered locally
  while the operation runs and flushed to the sink only when the operation exits
  (the caller places the operation around the transaction, so the flush is
  outside it).
- **Real timings.** Start/end are wall-clock instants captured at entry/exit; a
  span with no end is left open rather than faked to latency 0.
- **Never blocks or changes business.** A sink failure is recorded in
  `export_errors` and never raises; the local buffer always survives.
- **Honest skip.** A step that did not run (cache hit, no candidates) is recorded
  with an explicit `skipped` reason, never as a successful provider call.
- **Redaction.** Inputs/outputs are filtered by the sink before export.

The recorder is pure orchestration: it never calls OCR/LLM, never reads gold and
never writes business state.
"""

from __future__ import annotations

import contextvars
import hashlib
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Iterator

from invoice_referee.evidence.trace import (
    LangSmithTrace,
    TraceSpan,
    sanitize_trace_error,
    stage_payload,
)

# The operation currently in scope, so nested helpers (admission, reconcile) can
# attach steps without threading the object through every signature. Set by
# `operation()`; async-safe because each task/request gets its own context.
_current_operation: contextvars.ContextVar["Operation | None"] = contextvars.ContextVar(
    "invoice_referee_current_operation", default=None
)
_current_step: contextvars.ContextVar["Step | None"] = contextvars.ContextVar(
    "invoice_referee_current_step", default=None
)


@dataclass(frozen=True)
class LlmTraceContext:
    stage: str
    prompt_version: str
    schema_version: str
    attempt_kind: str = "provider_call"


_current_llm_context: contextvars.ContextVar[LlmTraceContext | None] = contextvars.ContextVar(
    "invoice_referee_llm_trace_context", default=None
)


def current_operation() -> "Operation | None":
    """The operation in scope for the current call, or None."""
    return _current_operation.get()


def code_revision() -> str:
    """The code revision for trace metadata (env → git → package version).

    Never fabricated: an unresolvable revision is reported as the package version
    with an explicit UNKNOWN marker rather than a guessed hash.
    """
    import os
    import subprocess

    env = os.environ.get("INVOICE_REFEREE_CODE_REVISION")
    if env:
        return env.strip()[:64]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    from invoice_referee import __version__

    return f"UNKNOWN:{__version__}"


def _new_run_id(name: str) -> str:
    return f"{name}:{uuid.uuid4().hex}"


@dataclass
class Operation:
    """One user-triggered operation: a root span plus its child steps."""

    run_id: str
    name: str
    parent_run_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    inputs: dict[str, object] = field(default_factory=dict)
    outputs: dict[str, object] = field(default_factory=dict)
    error: str | None = None
    output_state: str | None = None
    llm_call_counts: dict[str, int] = field(default_factory=dict)
    spans: list[TraceSpan] = field(default_factory=list)
    # The recorder that owns this operation, so a nested helper reached via the
    # contextvar can attach steps without the owner being passed explicitly.
    recorder: "TraceRecorder | None" = None


@dataclass
class Step:
    """One child step of an operation; the caller fills outputs/error."""

    run_id: str
    name: str
    inputs: dict[str, object] = field(default_factory=dict)
    outputs: dict[str, object] = field(default_factory=dict)
    error: str | None = None
    skipped: str | None = None
    output_state: str | None = None


class TraceRecorder:
    """Builds root/child spans for real operations and flushes them to a sink.

    `sink` is a `LangSmithTrace` (which is itself a no-op local sink when tracing
    is disabled). The recorder is safe to use whether or not tracing is enabled:
    spans are always buffered locally; the network export only happens on flush.
    """

    def __init__(self, sink: LangSmithTrace | None = None) -> None:
        self.sink = sink or LangSmithTrace(api_key=None)
        self.enabled = bool(getattr(self.sink, "enabled", False))
        # Every operation that has been flushed, in order (local evidence).
        self.operations: list[Operation] = []

    @property
    def export_errors(self) -> list[str]:
        return getattr(self.sink, "export_errors", [])

    def operation(
        self,
        name: str,
        *,
        run_id: str | None = None,
        parent_run_id: str | None = None,
        metadata: dict[str, object] | None = None,
        tags: tuple[str, ...] = (),
    ) -> "Iterator[Operation]":
        """Open a root span for one real operation; flush on exit."""
        return _OperationContext(self, name, run_id, parent_run_id, metadata, tags)

    def step(
        self,
        name: str,
        *,
        operation: Operation,
        run_id: str | None = None,
        metadata: dict[str, object] | None = None,
        inputs: dict[str, object] | None = None,
    ) -> "Iterator[Step]":
        """Open a child span under `operation`; buffered until the op flushes."""
        return _StepContext(self, name, operation, run_id, metadata, inputs)

    def record_span(self, operation: Operation, span: TraceSpan) -> None:
        """Buffer one already-built span under an operation (no network)."""
        operation.spans.append(span)

    def flush(self, operation: Operation) -> None:
        """Send an operation's spans to the sink, root first.

        Called OUTSIDE any SQLite transaction (the caller wraps the operation
        around the transaction). A sink error is captured, never raised.
        """
        for span in operation.spans:
            # The sink reads span.metadata/inputs/outputs directly; no extra
            # payload is needed. `record` never raises (errors -> export_errors).
            self.sink.record(span)
        flush_sink = getattr(self.sink, "flush", None)
        if callable(flush_sink):
            try:
                flush_sink(timeout=5.0)
            except Exception as error:
                self.export_errors.append(
                    sanitize_trace_error(f"{type(error).__name__}: {error}")
                )
        if operation not in self.operations:
            self.operations.append(operation)

    def trace_ref(self, operation: Operation) -> str:
        """The logical trace reference persisted with the report/job/view."""
        return operation.run_id


class _OperationContext:
    def __init__(
        self,
        recorder: TraceRecorder,
        name: str,
        run_id: str | None,
        parent_run_id: str | None,
        metadata: dict[str, object] | None,
        tags: tuple[str, ...],
    ) -> None:
        self.recorder = recorder
        self.name = name
        self.run_id = run_id or _new_run_id(name)
        self.parent_run_id = parent_run_id
        self.metadata = dict(metadata or {})
        self.tags = tags

    def __enter__(self) -> Operation:
        self.started_at = datetime.now(UTC)
        self.op = Operation(
            run_id=self.run_id,
            name=self.name,
            parent_run_id=self.parent_run_id,
            metadata=self.metadata,
            tags=self.tags,
            recorder=self.recorder,
        )
        self._token = _current_operation.set(self.op)
        return self.op

    def __exit__(self, exc_type, exc, tb) -> bool:
        _current_operation.reset(self._token)
        ended_at = datetime.now(UTC)
        if exc is not None and self.op.error is None:
            self.op.error = sanitize_trace_error(
                f"{exc_type.__name__ if exc_type else 'Error'}: {exc}"
            )
        output_state = self.op.output_state or (
            "COLLECTED" if self.op.outputs else "NOT_COLLECTED"
        )
        root = TraceSpan(
            name=self.name,
            run_id=self.op.run_id,
            parent_run_id=self.op.parent_run_id,
            run_type="chain",
            started_at=self.started_at,
            ended_at=ended_at,
            inputs=self.op.inputs,
            outputs=self.op.outputs,
            output_state=output_state,
            error=self.op.error,
            metadata=self.op.metadata,
            tags=self.op.tags,
        )
        # Root first so LangSmith sees the parent before its children.
        self.op.spans.insert(0, root)
        self.recorder.flush(self.op)
        return False  # never swallow a business exception


class _StepContext:
    def __init__(
        self,
        recorder: TraceRecorder,
        name: str,
        operation: Operation,
        run_id: str | None,
        metadata: dict[str, object] | None,
        inputs: dict[str, object] | None,
    ) -> None:
        self.recorder = recorder
        self.name = name
        self.operation = operation
        self.run_id = run_id or _new_run_id(name)
        self.metadata = dict(metadata or {})
        self.inputs = dict(inputs or {})

    def __enter__(self) -> Step:
        self.started_at = datetime.now(UTC)
        self.step = Step(run_id=self.run_id, name=self.name, inputs=self.inputs)
        self._step_token = _current_step.set(self.step)
        return self.step

    def __exit__(self, exc_type, exc, tb) -> bool:
        _current_step.reset(self._step_token)
        ended_at = datetime.now(UTC)
        if exc is not None and self.step.error is None:
            self.step.error = sanitize_trace_error(
                f"{exc_type.__name__ if exc_type else 'Error'}: {exc}"
            )
        outputs = dict(self.step.outputs)
        if self.step.skipped is not None:
            outputs.setdefault("skipped", self.step.skipped)
        output_state = self.step.output_state or (
            "COLLECTED" if outputs else "NOT_COLLECTED"
        )
        span = TraceSpan(
            name=self.name,
            run_id=self.step.run_id,
            parent_run_id=self.operation.run_id,
            run_type="chain",
            started_at=self.started_at,
            ended_at=ended_at,
            inputs=self.step.inputs,
            outputs=outputs,
            output_state=output_state,
            error=self.step.error,
            metadata=self.metadata,
        )
        self.recorder.record_span(self.operation, span)
        return False


@contextmanager
def null_operation(name: str = "noop") -> Iterator[Operation]:
    """A no-op operation for tests/STUB paths that do not trace."""
    yield Operation(run_id=f"{name}:noop", name=name)


@contextmanager
def step(name: str, *, metadata: dict[str, object] | None = None, inputs: dict[str, object] | None = None) -> Iterator[Step]:
    """Attach a child step to the current operation, if any (else a no-op).

    Lets a nested helper (e.g. `read_root`) emit a step without threading the
    recorder/operation through its signature. With no operation in scope it is a
    harmless no-op, so the same code path works under tests and the STUB flow.
    """
    op = current_operation()
    if op is None or op.recorder is None:
        yield Step(run_id=f"{name}:noop", name=name)
        return
    with op.recorder.step(name, operation=op, metadata=metadata, inputs=inputs) as s:
        yield s


@contextmanager
def llm_trace_context(
    *,
    stage: str,
    prompt_version: str,
    schema_version: str,
    attempt_kind: str = "provider_call",
) -> Iterator[None]:
    """Attach stable prompt/schema labels to real provider calls in this scope."""
    token = _current_llm_context.set(
        LlmTraceContext(
            stage=stage,
            prompt_version=prompt_version,
            schema_version=schema_version,
            attempt_kind=attempt_kind,
        )
    )
    try:
        yield
    finally:
        _current_llm_context.reset(token)


def record_llm_call(
    *,
    started_at: datetime,
    ended_at: datetime,
    system: str,
    user: str,
    requested_model: str,
    returned_model: str | None,
    parsed_response: dict[str, object] | None,
    usage: dict[str, object],
    error: str | None,
) -> None:
    """Buffer one `run_type=llm` child for an actual provider request."""
    operation = current_operation()
    if operation is None or operation.recorder is None:
        return

    context = _current_llm_context.get()
    current_step = _current_step.get()
    stage_name = (
        context.stage
        if context is not None
        else current_step.name if current_step is not None else "structured_output"
    )
    stage_instance = current_step.name if current_step is not None else stage_name
    attempt_scope = current_step.run_id if current_step is not None else stage_name
    attempt_key = f"{attempt_scope}:{stage_name}"
    attempt_index = operation.llm_call_counts.get(attempt_key, 0) + 1
    operation.llm_call_counts[attempt_key] = attempt_index
    prompt_version = context.prompt_version if context is not None else "unversioned"
    schema_version = context.schema_version if context is not None else "json-object-v1"
    attempt_kind = context.attempt_kind if context is not None else "provider_call"

    parsed_json_summary: dict[str, object] = {}
    parsed_json_sha256: str | None = None
    if parsed_response is not None:
        import json

        canonical_response = json.dumps(
            parsed_response, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        parsed_json_sha256 = hashlib.sha256(canonical_response.encode("utf-8")).hexdigest()
        known_lists = ("documents", "fields", "line_items", "assessments", "promotions")
        parsed_json_summary = {
            "top_level_keys": sorted(str(key) for key in parsed_response.keys()),
            "list_counts": {
                key: len(parsed_response[key])
                for key in known_lists
                if isinstance(parsed_response.get(key), list)
            },
        }

    inputs = stage_payload(
        "llm",
        {
            "requested_model": requested_model,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "attempt_index": attempt_index,
            "attempt_kind": attempt_kind,
            "stage_instance": stage_instance,
            "system_chars": len(system),
            "user_chars": len(user),
            "system_sha256": hashlib.sha256(system.encode("utf-8")).hexdigest(),
            "user_sha256": hashlib.sha256(user.encode("utf-8")).hexdigest(),
        },
    )
    outputs = stage_payload(
        "llm",
        {
            "status": "FAILED" if error is not None else "SUCCEEDED",
            "response_format": "json_object",
            "parsed_json_summary": parsed_json_summary,
            "parsed_json_sha256": parsed_json_sha256,
            "requested_model": requested_model,
            "returned_model": returned_model,
            "usage": usage,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "attempt_index": attempt_index,
            "attempt_kind": attempt_kind,
            "stage_instance": stage_instance,
            "system_chars": len(system),
            "user_chars": len(user),
            "system_sha256": inputs["system_sha256"],
            "user_sha256": inputs["user_sha256"],
        },
    )
    operation.recorder.record_span(
        operation,
        TraceSpan(
            name=f"llm:{stage_name}",
            run_id=_new_run_id(f"llm:{stage_name}"),
            parent_run_id=operation.run_id,
            run_type="llm",
            model=returned_model or requested_model,
            started_at=started_at,
            ended_at=ended_at,
            inputs=inputs,
            outputs=outputs,
            output_state="COLLECTED",
            error=sanitize_trace_error(error) if error is not None else None,
            metadata={
                "provider": "xkiro",
                "stage": stage_name,
                "requested_model": requested_model,
                "returned_model": returned_model,
                "usage": usage,
                "prompt_version": prompt_version,
                "schema_version": schema_version,
                "attempt_index": attempt_index,
                "attempt_kind": attempt_kind,
                "stage_instance": stage_instance,
            },
            tags=("llm", stage_name),
        ),
    )
