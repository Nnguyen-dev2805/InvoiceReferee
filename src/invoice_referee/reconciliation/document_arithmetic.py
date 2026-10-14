"""Pure per-document arithmetic gate (core validation; TC06/TC11).

A readable number is not a consistent number. The document's own arithmetic can
fail while every field is read correctly:

- TC06: the settlement form prints ứng 4.000.000 − chi 3.240.000 = 760.000, but
  the refund line says 700.000 (off by 60.000);
- TC11: the invoice prints 5.000.000 + thuế 400.000 = 5.400.000, but the printed
  total says 5.500.000 (off by 100.000).

Neither is an OCR failure, and neither is fixed by trusting a computed figure:
the printed source numbers are preserved. This module checks the relationships
the document TYPE and its established fields determine, and returns typed
findings. It is PURE: no I/O, no model call, no policy engine — the admission
layer turns each finding into a blocking FACT and the Reconciler/commit gate
consumes it, so no affirmative financial effect is issued while a contradiction
is open.

A material component that is UNREADABLE (e.g. a tax that could not be read) makes
the check impossible: it is a finding, never a silent zero. A component that is
NOT_PRESENT is genuinely not applicable (a receipt with no VAT fields is never
forced to reconcile).
"""

from __future__ import annotations

from dataclasses import dataclass

from invoice_referee.domain.common import EvidenceRef, parse_vnd
from invoice_referee.domain.documents import DocumentAnalysis, FieldCandidate

# Invoice-like documents carry the subtotal + tax (+ service charge − discount) =
# total relationship. A ticket/receipt is not forced to carry VAT fields.
_INVOICE_TYPES = frozenset({"E_INVOICE"})
# A money component whose value the total depends on. UNREADABLE/AMBIGUOUS here
# means the total cannot be verified.
_MATERIAL_INVOICE_COMPONENTS = ("tax", "discount", "service_charge")


@dataclass(frozen=True)
class ArithmeticFinding:
    """One document-internal arithmetic contradiction (typed, sourced)."""

    code: str
    field_or_rule: str
    basis: str
    question: str
    refs: tuple[EvidenceRef, ...] = ()


def _field(document: DocumentAnalysis, name: str) -> FieldCandidate | None:
    for candidate in document.fields:
        if candidate.field == name:
            return candidate
    return None


def _found(document: DocumentAnalysis, name: str) -> int | None:
    candidate = _field(document, name)
    if candidate is None or candidate.state != "FOUND":
        return None
    return parse_vnd(candidate.value)


def _state(document: DocumentAnalysis, name: str) -> str:
    candidate = _field(document, name)
    return candidate.state if candidate is not None else "NOT_PRESENT"


def _refs(document: DocumentAnalysis, *names: str) -> tuple[EvidenceRef, ...]:
    out: list[EvidenceRef] = []
    for name in names:
        candidate = _field(document, name)
        if candidate is not None and candidate.state == "FOUND":
            out.extend(candidate.refs)
    return tuple(out)


def _vnd(amount: int) -> str:
    """A plain integer VND for a question/basis (no locale separator)."""
    return str(int(amount))


def check_document_arithmetic(document: DocumentAnalysis) -> tuple[ArithmeticFinding, ...]:
    """The document-internal arithmetic findings for one analysis (pure)."""
    findings: list[ArithmeticFinding] = []
    if document.document_type == "SETTLEMENT_FORM":
        findings.extend(_check_settlement_form(document))
    if document.document_type in _INVOICE_TYPES:
        findings.extend(_check_invoice(document))
    return tuple(findings)


def _check_settlement_form(document: DocumentAnalysis) -> list[ArithmeticFinding]:
    """The paper's own declared relationship: advance − total = refund (or reimburse)."""
    advance = _found(document, "declared_advance")
    total = _found(document, "printed_total")
    if advance is None or total is None:
        # Without both an advance and a cost the paper's internal relation is not
        # established; the missing-evidence/advance FACT path already covers it.
        return []
    findings: list[ArithmeticFinding] = []
    # Only one direction applies: when the advance exceeds the cost the paper
    # returns money (refund); when the cost exceeds the advance the company pays
    # extra (reimbursement). The inapplicable side is a verified zero, not a
    # negative — so F02 (advance 5m < cost 5.4m, refund 0, reimburse 400k) is not
    # a false contradiction.
    expected_refund = max(advance - total, 0)
    refund = _found(document, "printed_return")
    if refund is not None and refund != expected_refund:
        diff = abs(refund - expected_refund)
        findings.append(ArithmeticFinding(
            code="settlement-return",
            field_or_rule="expense:arithmetic:return",
            basis=(
                f"Giấy ghi ứng {_vnd(advance)} − chi {_vnd(total)} = {_vnd(expected_refund)} "
                f"nhưng số hoàn lại in trên giấy là {_vnd(refund)} (lệch {_vnd(diff)})."
            ),
            question=(
                f"Xác nhận/sửa số tiền hoàn lại trên giấy quyết toán: phép tính cho "
                f"{_vnd(expected_refund)} nhưng giấy ghi {_vnd(refund)} (lệch {_vnd(diff)})."
            ),
            refs=_refs(document, "declared_advance", "printed_total", "printed_return"),
        ))
    reimburse = _found(document, "printed_reimbursement")
    expected_reimburse = max(total - advance, 0)
    if reimburse is not None and reimburse != expected_reimburse:
        diff = abs(reimburse - expected_reimburse)
        findings.append(ArithmeticFinding(
            code="settlement-reimburse",
            field_or_rule="expense:arithmetic:reimburse",
            basis=(
                f"Giấy ghi chi {_vnd(total)} − ứng {_vnd(advance)} = {_vnd(expected_reimburse)} "
                f"nhưng số đề nghị chi thêm là {_vnd(reimburse)} (lệch {_vnd(diff)})."
            ),
            question=(
                f"Xác nhận/sửa số tiền đề nghị chi thêm: phép tính cho "
                f"{_vnd(expected_reimburse)} nhưng giấy ghi {_vnd(reimburse)} (lệch {_vnd(diff)})."
            ),
            refs=_refs(document, "declared_advance", "printed_total", "printed_reimbursement"),
        ))
    return findings


def _check_invoice(document: DocumentAnalysis) -> list[ArithmeticFinding]:
    """The invoice's subtotal + tax (+ service − discount) = total relationship."""
    subtotal = _found(document, "subtotal")
    total = _found(document, "total_amount")
    if subtotal is None or total is None:
        return []
    # A material component that was read as unreadable/ambiguous cannot be treated
    # as zero: the total is unverifiable, so the document is not silently eligible.
    unread = [
        name for name in _MATERIAL_INVOICE_COMPONENTS
        if _state(document, name) in ("UNREADABLE", "AMBIGUOUS")
    ]
    if unread:
        return [ArithmeticFinding(
            code="invoice-components-unread",
            field_or_rule="expense:arithmetic:components",
            basis=(
                "Không đọc được thành phần bắt buộc để kiểm tổng hóa đơn ("
                + ", ".join(unread) + "); không mặc định bằng 0."
            ),
            question=(
                "Bổ sung/đọc lại " + ", ".join(unread)
                + " để đối chiếu tổng hóa đơn (không coi phần chưa đọc là 0)."
            ),
            refs=_refs(document, "subtotal", "total_amount"),
        )]
    expected = subtotal
    for name in _MATERIAL_INVOICE_COMPONENTS:
        value = _found(document, name)
        if value is None:
            continue  # NOT_PRESENT / not applicable: not forced to reconcile
        expected += -value if name == "discount" else value
    if expected != total:
        diff = abs(total - expected)
        findings: list[ArithmeticFinding] = [ArithmeticFinding(
            code="invoice-total",
            field_or_rule="expense:arithmetic:total",
            basis=(
                f"Tiền hàng {_vnd(subtotal)} cộng thuế/phí ra {_vnd(expected)} nhưng tổng "
                f"hóa đơn in {_vnd(total)} (lệch {_vnd(diff)})."
            ),
            question=(
                f"Đối chiếu/cung cấp hóa đơn hợp lệ: tiền hàng + thuế/phí = {_vnd(expected)} "
                f"nhưng tổng in {_vnd(total)} (lệch {_vnd(diff)})."
            ),
            refs=_refs(document, "subtotal", "tax", "service_charge", "discount", "total_amount"),
        )]
        return findings
    return []
