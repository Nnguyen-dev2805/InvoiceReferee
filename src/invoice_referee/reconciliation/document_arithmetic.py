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
import re
import unicodedata

from invoice_referee.domain.common import EvidenceRef, parse_vnd
from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate

# Invoice-like documents carry the subtotal + tax (+ service charge − discount) =
# total relationship. A ticket/receipt is not forced to carry VAT fields.
_INVOICE_TYPES = frozenset({"E_INVOICE"})
# A money component whose value the total depends on. UNREADABLE/AMBIGUOUS here
# means the total cannot be verified.
_MATERIAL_INVOICE_COMPONENTS = ("tax", "discount", "service_charge")
_SUMMARY_LINE_PREFIXES = (
    "tong cong", "tong chi phi", "tong so tien", "tong thanh toan", "tong tien",
    "cong tien", "cong chi phi", "subtotal", "sub total", "grand total", "total",
)


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


def _line_field(line: DocumentLine, name: str) -> FieldCandidate | None:
    return next((candidate for candidate in line.fields if candidate.field == name), None)


def _candidate_refs(candidate: FieldCandidate | None) -> list[EvidenceRef]:
    if candidate is None:
        return []
    refs = list(candidate.refs)
    for alternative in candidate.alternatives:
        refs.extend(alternative.refs)
    return refs


def _unique_refs(refs: list[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    seen: set[tuple[str, str, int, str]] = set()
    out: list[EvidenceRef] = []
    for ref in refs:
        key = (str(ref.source_id), ref.source_sha256, ref.page, ref.exact_quote)
        if key not in seen:
            seen.add(key)
            out.append(ref)
    return tuple(out)


def _row_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def is_settlement_summary_row(description: str) -> bool:
    label = _row_label(description)
    return any(label == prefix or label.startswith(prefix + " ") for prefix in _SUMMARY_LINE_PREFIXES)


def _vnd(amount: int) -> str:
    """A plain integer VND for a question/basis (no locale separator)."""
    return str(int(amount))


def _pretty_vnd(amount: int) -> str:
    return f"{int(amount):,}".replace(",", ".")


def check_document_arithmetic(document: DocumentAnalysis) -> tuple[ArithmeticFinding, ...]:
    """The document-internal arithmetic findings for one analysis (pure)."""
    findings: list[ArithmeticFinding] = []
    if document.document_type == "SETTLEMENT_FORM":
        findings.extend(_check_settlement_form(document))
        findings.extend(_check_settlement_line_total(document))
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


def _check_settlement_line_total(document: DocumentAnalysis) -> list[ArithmeticFinding]:
    """Compare source-backed cost rows with the paper total; never sum partial rows."""
    if not document.line_items:
        return []

    total_field = _field(document, "printed_total")
    total = _found(document, "printed_total")
    refs = _candidate_refs(total_field)
    cost_rows: list[tuple[str, int]] = []
    unresolved: list[str] = []

    for index, line in enumerate(document.line_items, start=1):
        description_field = _line_field(line, "description")
        amount_field = _line_field(line, "amount")
        refs.extend(line.refs)
        refs.extend(_candidate_refs(description_field))
        refs.extend(_candidate_refs(amount_field))

        if description_field is None or description_field.state != "FOUND":
            state = description_field.state if description_field is not None else "NOT_PRESENT"
            unresolved.append(f"dòng {index} (nội dung {state})")
            continue
        if not isinstance(description_field.value, str):
            unresolved.append(f"dòng {index} (nội dung không phải văn bản)")
            continue
        description = description_field.value.strip()
        if not description:
            unresolved.append(f"dòng {index} (thiếu nội dung)")
            continue
        if is_settlement_summary_row(description):
            continue

        if amount_field is None or amount_field.state != "FOUND":
            state = amount_field.state if amount_field is not None else "NOT_PRESENT"
            unresolved.append(f"'{description}' (số tiền {state})")
            continue
        amount = parse_vnd(amount_field.value)
        if amount is None:
            unresolved.append(f"'{description}' (không đọc được số tiền VND)")
            continue
        cost_rows.append((description, amount))

    row_refs = _unique_refs(refs)
    total_state = total_field.state if total_field is not None else "NOT_PRESENT"
    if total is None and total_state in ("NOT_PRESENT", "NOT_APPLICABLE") and not unresolved:
        # The paper makes no aggregate-total assertion to reconcile. Its sourced
        # cost rows can still be assessed against original expense documents.
        return []
    if unresolved or not cost_rows or total is None:
        reasons = unresolved[:]
        if not cost_rows and not reasons:
            reasons.append("không nhận diện được dòng chi phí nào ngoài dòng tổng/phụ")
        if total is None and total_state not in ("NOT_PRESENT", "NOT_APPLICABLE"):
            reasons.append(f"tổng trên giấy {total_state}")
        details = "; ".join(reasons)
        return [ArithmeticFinding(
            code="settlement-line-items-unresolved",
            field_or_rule="expense:arithmetic:line_total",
            basis=(
                "Không thể đối chiếu tổng dòng chi phí vì thiếu hoặc chưa đọc rõ "
                f"{details}; không được bỏ dòng hay coi là 0."
            ),
            question=(
                "Vui lòng làm rõ nội dung/số tiền của các dòng chưa đọc rõ và tổng trên giấy, "
                "hoặc cung cấp giấy quyết toán đã sửa."
            ),
            refs=row_refs or document.refs,
        )]

    row_total = sum(amount for _, amount in cost_rows)
    if row_total == total:
        return []

    difference = abs(row_total - total)
    row_basis = " + ".join(f"{description} {_pretty_vnd(amount)} đ" for description, amount in cost_rows)
    return [ArithmeticFinding(
        code="settlement-line-total",
        field_or_rule="expense:arithmetic:line_total",
        basis=(
            f"Tổng dòng chi phí ({row_basis}) là {_pretty_vnd(row_total)} đ, nhưng "
            f"tổng in trên giấy là {_pretty_vnd(total)} đ (lệch {_pretty_vnd(difference)} đ)."
        ),
        question=(
            f"Hai khoản chi cộng thành {_pretty_vnd(row_total)} đ, nhưng tổng trên giấy là "
            f"{_pretty_vnd(total)} đ. Vui lòng làm rõ khoản thiếu hoặc cung cấp giấy quyết toán đã sửa."
        ),
        refs=row_refs or document.refs,
    )]


def _invoice_refs(document: DocumentAnalysis) -> tuple[EvidenceRef, ...]:
    return _unique_refs([
        ref for field in document.fields
        if field.field in ("subtotal", "tax", "discount", "service_charge", "total_amount")
        for ref in _candidate_refs(field)
    ])


def _check_invoice(document: DocumentAnalysis) -> list[ArithmeticFinding]:
    """Check printed components; never infer tax/allocation from the total."""
    subtotal = _found(document, "subtotal")
    total = _found(document, "total_amount")
    if subtotal is None or total is None:
        return []
    components = [f for f in document.fields if f.field in _MATERIAL_INVOICE_COMPONENTS]
    unread = sorted({f.field for f in components if f.state in ("UNREADABLE", "AMBIGUOUS")
                     or (f.state == "FOUND" and parse_vnd(f.value) is None)})
    if unread:
        return [ArithmeticFinding(
            code="invoice-components-unread",
            field_or_rule="expense:arithmetic:components",
            basis="Không đọc được thành phần bắt buộc để kiểm tổng hóa đơn ("
                  + ", ".join(unread) + "); không mặc định bằng 0.",
            question="Bổ sung/đọc lại " + ", ".join(unread)
                     + " để đối chiếu tổng hóa đơn (không coi phần chưa đọc là 0).",
            refs=_invoice_refs(document),
        )]
    taxes = [f for f in components if f.field == "tax" and f.state == "FOUND"]
    # A repeated quote/location is not a second economic tax component. A printed
    # total plus its breakdown is also not an additive set. Keep both in source;
    # ask for clarification rather than choosing the set that fits printed total.
    seen: set[tuple] = set()
    overlapping = False
    for tax in taxes:
        locations = {
            (ref.source_id, ref.source_sha256, ref.page,
             ("bbox", ref.bbox) if ref.bbox is not None else
             ("record", ref.record_key) if ref.record_key is not None else
             ("quote", " ".join(ref.exact_quote.split())))
            for ref in tax.refs
        }
        overlapping |= bool(seen.intersection(locations))
        seen.update(locations)
    has_total_label = any(
        re.search(r"(?:tong(?: cong)? (?:tien )?thue|total (?:vat|tax)|(?:vat|tax) total)", _row_label(ref.exact_quote))
        for tax in taxes for ref in tax.refs
    )
    if overlapping or (len(taxes) > 1 and has_total_label):
        return [ArithmeticFinding(
            code="invoice-tax-sources-overlap",
            field_or_rule="expense:arithmetic:components",
            basis="Các giá trị thuế có nguồn trùng hoặc gồm cả tổng thuế và thành phần; chưa xác định bộ khoản thuế độc lập để cộng.",
            question="Đối chiếu tổng tiền thuế in trên hóa đơn hoặc cung cấp từng khoản tiền thuế có căn cứ phân biệt; không cộng lại cùng nguồn.",
            refs=_invoice_refs(document),
        )]
    expected = subtotal + sum(parse_vnd(t.value) for t in taxes)
    for name in ("service_charge", "discount"):
        value = _found(document, name)
        if value is not None:
            expected += -abs(value) if name == "discount" else value
    if expected != total:
        diff = abs(total - expected)
        return [ArithmeticFinding(
            code="invoice-total",
            field_or_rule="expense:arithmetic:total",
            basis=f"Tiền hàng {_vnd(subtotal)} cộng thuế/phí ra {_vnd(expected)} nhưng tổng hóa đơn in {_vnd(total)} (lệch {_vnd(diff)}).",
            question=f"Đối chiếu/cung cấp hóa đơn hợp lệ: tiền hàng + thuế/phí = {_vnd(expected)} nhưng tổng in {_vnd(total)} (lệch {_vnd(diff)}).",
            refs=_invoice_refs(document),
        )]
    return []
