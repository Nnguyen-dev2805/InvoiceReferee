"""B3 verbal assignment intake entry point (b3-intake-v1, Task 1).

Data contracts live in ``settlement.contracts.b3_contracts`` (pure data, no
``settlement.models`` import) and the evaluator lives in
``settlement.b3_evaluation``. This module re-exports both so callers can keep
importing ``from invoice_referee.settlement.b3_intake import ...``, and keeps the
company-context loader here.

Invariants (Rulebook R1/R2/R5/R6/R8, Product P2a):

- Money is strict integer VND; ``None`` is unknown, never a hidden ``0``.
- An IMPORT draft may be partially empty; a confirmed submission must be
  complete with a positive request and at least one estimate row.
- The company context is backend fixture data (explicit version/activation);
  an employee upload never supplies or overrides it.
- A fixed demo clock is only accepted for an activated synthetic fixture.
"""
from __future__ import annotations

from typing import Any

from invoice_referee.settlement.contracts.b3_contracts import (
    B3_INTAKE_SCHEMA,
    _KIND_STATUSES,
    B3CompanyContext,
    B3Coverage,
    B3DecisionState,
    B3EstimateRow,
    B3Grant,
    B3HistoryKind,
    B3HistoryRecord,
    B3HistoryStatus,
    B3Intake,
    B3Person,
    B3Proposal,
    B3Readiness,
    B3ReceiptSource,
    B3Route,
    DEMO_RECEIPT_SOURCES,
)
from invoice_referee.settlement.b3_evaluation import (
    B3_ROW_KEY_TEMPLATES,
    B3_SCALAR_KEYS,
    B3_V1_KEYS,
    evaluate_b3_proposal,
)


def load_b3_context(path) -> B3CompanyContext:
    """Load an explicitly configured context file; malformed is a startup error.

    An absent/unset path is the caller's "not configured" case; a configured
    file that fails validation must never fall back to implicit authority.
    """
    import json
    from pathlib import Path

    from invoice_referee.shared.errors import DomainError

    file = Path(path)
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except OSError as error:
        raise DomainError(
            "CONFIG_NOT_ACTIVE",
            f"Không đọc được SETTLEMENT_B3_CONTEXT_PATH ({file}): {error}",
        ) from error
    except json.JSONDecodeError as error:
        raise DomainError(
            "CONFIG_NOT_ACTIVE",
            f"File context B3 không phải JSON hợp lệ ({file}): {error}",
        ) from error
    try:
        return B3CompanyContext.model_validate(data)
    except Exception as error:  # pydantic ValidationError
        raise DomainError(
            "CONFIG_NOT_ACTIVE",
            f"File context B3 không hợp lệ ({file}): {error}",
        ) from error


def is_b3_v1(form: dict[str, Any] | None) -> bool:
    """True khi form theo hợp đồng b3-intake-v1 (case B3 mới); legacy không đổi."""
    return isinstance(form, dict) and form.get("schema_version") == B3_INTAKE_SCHEMA
