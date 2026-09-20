"""Check Engine — run the 8 deterministic checks.

The engine returns facts only (``list[CheckResult]``); it never returns a
Decision. PO-specific checks are gated by transaction type: for unknown or
outside-policy types they return ``NOT_APPLICABLE`` instead of fabricating
missing-evidence failures.
"""

from __future__ import annotations

from invoice_referee.domain import models as m
from invoice_referee.checks import _support as s
from invoice_referee.checks.vendor import check_vendor, CHECK_ID as VENDOR
from invoice_referee.checks.item import check_item, CHECK_ID as ITEM
from invoice_referee.checks.quantity import check_quantity, CHECK_ID as QUANTITY
from invoice_referee.checks.price import check_price, CHECK_ID as PRICE
from invoice_referee.checks.amount import check_amount, CHECK_ID as AMOUNT
from invoice_referee.checks.duplicate import check_duplicate, CHECK_ID as DUPLICATE
from invoice_referee.checks.payment import check_payment, CHECK_ID as PAYMENT
from invoice_referee.checks.po_limit import check_po_limit, CHECK_ID as PO_LIMIT

# Order mirrors docs/DECISION_FLOW.md step 5.
_CHECKS = [
    check_vendor,
    check_item,
    check_quantity,
    check_price,
    check_amount,
    check_duplicate,
    check_payment,
    check_po_limit,
]

_CHECK_IDS = [VENDOR, ITEM, QUANTITY, PRICE, AMOUNT, DUPLICATE, PAYMENT, PO_LIMIT]


def run_checks(tx: m.Transaction) -> list[m.CheckResult]:
    # Gate: PO-goods-purchase checks only apply to that workflow. Unknown or
    # outside-policy types get NOT_APPLICABLE, not fake failures.
    if tx.transaction_type is not m.TransactionType.PO_GOODS_PURCHASE:
        return [
            m.CheckResult(
                check_id=cid,
                status=m.CheckStatus.NOT_APPLICABLE,
                reason="Check does not apply to a non PO-goods-purchase transaction type",
                evidence_refs=s.evidence_refs(tx),
            )
            for cid in _CHECK_IDS
        ]

    return [check(tx) for check in _CHECKS]
