"""Compatibility shim for the old settlement_records module path.

The lifecycle functions now live under ``settlement.persistence`` (queries,
decision_records, money_records, action_records). This module re-exports them so
existing ``_st.<fn>`` callers in ``store.py`` keep working. New code should
import from the specific persistence module.
"""
from __future__ import annotations

from invoice_referee.settlement.persistence import (
    action_records as _action,
    decision_records as _decision,
    money_records as _money,
    queries as _queries,
)

# reads/selectors/context
workflow_view = _queries.workflow_view
settlement_proof_source_ids = _queries.settlement_proof_source_ids
money_events = _queries.money_events
current_decision = _queries.current_decision
fulfillment = _queries.fulfillment
current_revalidation = _queries.current_revalidation
decision_cost_signature = _queries.decision_cost_signature
open_question_count = _queries.open_question_count
latest_handoff = _queries.latest_handoff
closure = _queries.closure
receipt_signature = _queries.receipt_signature
grant_for = _queries.grant_for
grant_for_action = _queries.grant_for_action
require_handoff_basis = _queries.require_handoff_basis
require_accountant_route = _queries.require_accountant_route
augment_packet_with_money = _queries.augment_packet_with_money
build_money_context = _queries.build_money_context
# writes
record_presentation = _decision.record_presentation
record_decision = _decision.record_decision
record_money = _money.record_money
revalidate = _money.revalidate
handoff = _action.handoff
close = _action.close
prepare_adjustment = _action.prepare_adjustment
