"""Transaction Builder — link normalized evidence into one Transaction.

The builder does not invent missing documents and does not decide business
outcomes. It classifies transaction type conservatively so the Policy Engine can
apply tri-state scope (UNKNOWN / OUTSIDE_POLICY / IN_SCOPE):

- an explicit ``transaction_type`` that maps to a supported type wins;
- an explicit but unsupported type is preserved in ``declared_transaction_type``
  (transaction_type stays ``None``) so policy can mark it OUTSIDE_POLICY;
- with no declaration, a PO reference implies PO_GOODS_PURCHASE; otherwise the
  type stays unknown so policy routes to REQUEST_INFO.
"""

from __future__ import annotations

from typing import Any, Optional

from invoice_referee.domain import models as m
from invoice_referee.ingestion import normalization as norm


def _classify_type(
    raw: dict[str, Any], invoice: Optional[m.SupplierInvoice], po: Optional[m.PurchaseOrder]
) -> tuple[Optional[m.TransactionType], Optional[str]]:
    declared = norm.normalize_id(raw.get("transaction_type"))
    if declared is not None:
        try:
            return m.TransactionType(declared.upper()), None
        except ValueError:
            # Known but unsupported type — keep it for OUTSIDE_POLICY classification.
            return None, declared

    has_po_reference = po is not None or (invoice is not None and invoice.po_id)
    if has_po_reference:
        return m.TransactionType.PO_GOODS_PURCHASE, None
    return None, None


def _evidence_issues(
    po: Optional[m.PurchaseOrder],
    receipts: list[m.GoodsReceipt],
    invoice: Optional[m.SupplierInvoice],
) -> list[m.EvidenceIssue]:
    """Structural linkage/status problems that must block AUTO_PROCESS.

    These are fail-closed facts (wrong PO linkage, a PO that is not APPROVED, a
    Goods Receipt that is not RECEIVED). A missing status stays a problem: it is
    never assumed to be the routine value. Absent documents are handled by the
    Policy Engine's required-document presence rules, not here.
    """
    issues: list[m.EvidenceIssue] = []

    if po is not None and po.status != "APPROVED":
        issues.append(
            m.EvidenceIssue(
                issue_id="PO_STATUS",
                policy_rule_id="P14",
                reason="Purchase Order is not in APPROVED status",
                evidence_refs=[po.po_id] if po.po_id else [],
            )
        )

    if po is not None and invoice is not None and po.po_id and invoice.po_id != po.po_id:
        issues.append(
            m.EvidenceIssue(
                issue_id="INVOICE_PO_LINK",
                policy_rule_id="P14",
                reason="Invoice references a different PO than the linked Purchase Order",
                evidence_refs=[x for x in (po.po_id, invoice.invoice_id) if x],
            )
        )

    for receipt in receipts:
        if po is not None and po.po_id and receipt.po_id != po.po_id:
            issues.append(
                m.EvidenceIssue(
                    issue_id="RECEIPT_PO_LINK",
                    policy_rule_id="P14",
                    reason="Goods Receipt references a different PO than the linked Purchase Order",
                    evidence_refs=[x for x in (receipt.receipt_id, po.po_id) if x],
                )
            )
        if receipt.status != "RECEIVED":
            issues.append(
                m.EvidenceIssue(
                    issue_id="RECEIPT_STATUS",
                    policy_rule_id="P14",
                    reason="Goods Receipt is not in RECEIVED status",
                    evidence_refs=[receipt.receipt_id] if receipt.receipt_id else [],
                )
            )

    return issues


def build_transaction(evidence: dict[str, Any]) -> m.Transaction:
    """Build a :class:`Transaction` from a raw evidence dict.

    Expected keys (all optional except an identifier): ``transaction_id``,
    ``transaction_type``, ``purchase_order``, ``goods_receipts``, ``invoice``,
    ``prior_invoices``, ``payment_history``, ``approvals``.
    """
    po_raw = evidence.get("purchase_order") or evidence.get("po")
    po = norm.to_purchase_order(po_raw) if po_raw else None

    goods_receipts = [norm.to_goods_receipt(gr) for gr in evidence.get("goods_receipts", []) if gr]

    invoice_raw = evidence.get("invoice")
    invoice = norm.to_supplier_invoice(invoice_raw) if invoice_raw else None

    prior_invoices = [
        norm.to_supplier_invoice(pi) for pi in evidence.get("prior_invoices", []) if pi
    ]
    payment_history = [
        norm.to_payment_record(p) for p in evidence.get("payment_history", []) if p
    ]
    approvals = [norm.to_approval_record(a) for a in evidence.get("approvals", []) if a]

    transaction_type, declared_type = _classify_type(evidence, invoice, po)

    return m.Transaction(
        transaction_id=norm.normalize_id(evidence.get("transaction_id")) or "",
        transaction_type=transaction_type,
        declared_transaction_type=declared_type,
        po=po,
        goods_receipts=goods_receipts,
        invoice=invoice,
        prior_invoices=prior_invoices,
        payment_history=payment_history,
        approvals=approvals,
        evidence_issues=_evidence_issues(po, goods_receipts, invoice),
        created_at=evidence.get("created_at"),
        updated_at=evidence.get("updated_at"),
    )
