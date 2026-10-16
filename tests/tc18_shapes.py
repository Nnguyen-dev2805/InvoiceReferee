"""TC18-shaped deterministic fixtures (paper + invoice + acceptance + transfer)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from invoice_referee.domain.case import CaseScope, ReadSet
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.reconciliation.admission import admit_evidence

SHA = "a" * 64
AS_OF = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)


def _ref(source: str, quote: str) -> EvidenceRef:
    return EvidenceRef(source_id=source, source_sha256=SHA, page=1, exact_quote=quote)  # type: ignore[arg-type]


def _found(name: str, value: object, source: str, quote: str) -> FieldCandidate:
    return FieldCandidate(
        field=name, state="FOUND", value=value, refs=(_ref(source, quote),)
    )


def _paper(
    *,
    labor_note: str | None = "Biên bản nghiệm thu và chuyển khoản",
    labor_reason: str | None = None,
) -> DocumentAnalysis:
    parts = (
        _found(
            "description",
            "Mua linh kiện máy in",
            "s-paper",
            "Mua linh kiện máy in 2700000",
        ),
        _found("amount", "2700000", "s-paper", "Mua linh kiện máy in 2700000"),
        _found("invoice_refs", ("00001801",), "s-paper", "00001801"),
        _found("note", "Đính kèm hóa đơn", "s-paper", "Đính kèm hóa đơn"),
    )
    labor = [
        _found(
            "description", "Nhân công sửa chữa", "s-paper", "Nhân công sửa chữa 1500000"
        ),
        _found("amount", "1500000", "s-paper", "Nhân công sửa chữa 1500000"),
        _found(
            "invoice_refs", ("BBNT-181026-02", "FT262918104578"), "s-paper", "BBNT refs"
        ),
    ]
    if labor_note is not None:
        labor.append(_found("note", labor_note, "s-paper", labor_note))
    if labor_reason is not None:
        labor.append(
            _found("no_evidence_reason", labor_reason, "s-paper", labor_reason)
        )
    return DocumentAnalysis(
        source_id="s-paper",
        document_id="s-paper:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",),
        page_range=(1, 1),
        fields=(
            _found("declared_name", "NGUYỄN MINH AN", "s-paper", "NGUYỄN MINH AN"),
            _found("purpose", "Sửa chữa máy in", "s-paper", "Sửa chữa máy in"),
            _found("printed_total", "4200000", "s-paper", "Tổng 4200000"),
            _found("declared_advance", "5000000", "s-paper", "Ứng 5000000"),
        ),
        line_items=(
            DocumentLine(id="r1", fields=parts),
            DocumentLine(id="r2", fields=tuple(labor)),
        ),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
    )


def _invoice() -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="s-inv",
        document_id="s-inv:1-1:E_INVOICE",
        document_type="E_INVOICE",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",),
        page_range=(1, 1),
        fields=(
            _found("document_number", "00001801", "s-inv", "Số 00001801"),
            _found("issuer_name", "Phúc An", "s-inv", "Phúc An"),
            _found("total_amount", "2700000", "s-inv", "Tổng 2700000"),
            _found("buyer_person_name", "NGUYỄN MINH AN", "s-inv", "NGUYỄN MINH AN"),
            _found("document_date", "2026-10-08", "s-inv", "08/10/2026"),
        ),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
    )


def _acceptance(*, issuer: str = "Trung tâm Kỹ thuật Phúc An") -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="s-acc",
        document_id="s-acc:1-1:ACCEPTANCE_RECORD",
        document_type="ACCEPTANCE_RECORD",
        roles=("SUPPORTING_DOCUMENT",),
        page_range=(1, 1),
        fields=(
            _found("document_number", "BBNT-181026-02", "s-acc", "Số BBNT-181026-02"),
            _found("issuer_name", issuer, "s-acc", issuer),
            _found("total_amount", "1500000", "s-acc", "Trị giá 1500000"),
            _found("document_date", "2026-10-09", "s-acc", "09/10/2026"),
        ),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
    )


def _transfer(
    *,
    payee: str = "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
    status: str = "Thành công",
) -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="s-trf",
        document_id="s-trf:1-1:PAYMENT_PROOF",
        document_type="PAYMENT_PROOF",
        roles=("PAYMENT_EVIDENCE",),
        page_range=(1, 1),
        fields=(
            _found("document_number", "FT262918104578", "s-trf", "Mã FT262918104578"),
            _found(
                "payer_name", "NGUYỄN MINH AN", "s-trf", "Người chuyển NGUYỄN MINH AN"
            ),
            _found("payee_name", payee, "s-trf", payee),
            _found("total_amount", "1500000", "s-trf", "Số tiền 1500000"),
            _found("transaction_status", status, "s-trf", status),
        ),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
    )


def _org() -> OrganizationContext:
    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    return OrganizationContext.model_validate_json(
        json.dumps(
            {
                "organization_id": "tenant:t",
                "profile": "WORK_EXPENSE",
                "activity": {
                    "activity_id": "activity:1",
                    "name": "a",
                    "occurred_at": "2026-10-06T09:00:00+07:00",
                    "purpose": "p",
                    "profile": "WORK_EXPENSE",
                    "authorization": {"id": "auth:1"},
                },
                "people": (
                    {"id": "employee:a", "name": "NGUYỄN MINH AN"},
                    {"id": "employee:accountant", "name": "Kế toán"},
                ),
                "budgets": (),
                "grants": (
                    {
                        "id": "g:r",
                        "version": "v1",
                        "actor": "system:referee",
                        "actions": ["RECOGNIZE_COST"],
                        "scope": "activity:1",
                        "max_amount": 8_000_000,
                        "effective_from": interval[0],
                        "effective_to": interval[1],
                    },
                    {
                        "id": "g:i",
                        "version": "v1",
                        "actor": "system:referee",
                        "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"],
                        "scope": "activity:1",
                        "max_amount": 4_000_000,
                        "effective_from": interval[0],
                        "effective_to": interval[1],
                    },
                ),
                "ledger": (
                    {
                        "id": "adv:1",
                        "external_key": "bank:ADV-1",
                        "kind": "ADVANCE_RECEIVED",
                        "scope": "activity:1",
                        "payer": "company:demo",
                        "payee": "employee:a",
                        "amount": 5_000_000,
                        "event_at": "2026-10-05T09:00:00+07:00",
                        "recorded_at": "2026-10-05T10:00:00+07:00",
                        "verification_state": "CONFIRMED",
                        "allocation_state": "ALLOCATED",
                    },
                ),
                "coverage": {
                    "activity": "activity:1",
                    "start": "2026-09-01T00:00:00+07:00",
                    "as_of": "2026-10-10T18:00:00+07:00",
                    "fund_ids": ["company:bank"],
                    "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"],
                    "opening_by_fund": {"company:bank": 0},
                    "ledger_version": "l:v1",
                    "witness_keys": ["cov:1"],
                },
            }
        )
    )


def _admit(paper, docs):
    report = ReadResult(
        provider_mode="LIVE", data_origin="LIVE_READ", documents=(paper, *docs)
    )
    return admit_evidence(
        report,
        scope=CaseScope(
            tenant="tenant:t",
            employee="employee:a",
            activity="activity:1",
            profile="WORK_EXPENSE",
        ),
        organization=_org(),
        confirmations=(),
        ledger=(),
        coverage=None,
        read_set=ReadSet(
            input_revision=1,
            control_epoch=0,
            context_version=1,
            ledger_version=1,
            usage_version=0,
        ),
        as_of=AS_OF,
    )


