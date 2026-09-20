"""InvoiceReferee — judge-ready Streamlit demo UI.

The UI only calls the production ``review()`` service and the Verify harness. It
never re-implements decision logic. Sample cases and pasted/uploaded JSON both go
through the same path.

Run:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ``streamlit run app/streamlit_app.py`` puts ``app/`` (the script's own
# directory) on ``sys.path[0]``, not the project root. The top-level ``verify``
# and ``app`` packages then fail to import. Ensure the project root is importable
# regardless of how the app is launched or the current working directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from invoice_referee.domain import models as m
from invoice_referee.transaction.builder import build_transaction
from invoice_referee.services.reviewer import review
from invoice_referee.audit.store import AuditStore
from invoice_referee.agent.config import client_from_env
from verify import harness

from app import presentation as p

st.set_page_config(page_title="InvoiceReferee", page_icon="🧾", layout="wide")

_DECISION_STYLE = {
    "AUTO_PROCESS": ("✅", "green"),
    "REQUEST_INFO": ("❓", "orange"),
    "ESCALATE": ("⚠️", "red"),
}
_CHECK_ICON = {
    "PASS": "✅",
    "FAIL": "❌",
    "UNKNOWN": "❓",
    "NOT_APPLICABLE": "➖",
}


def _run_review(evidence: dict) -> None:
    """Run a review and store result + a fresh human-control audit store in session."""
    # Uses the configured LLM provider when a key is set, else deterministic fallback.
    client = client_from_env()
    result = review(evidence, client=client, model=getattr(client, "model", None))
    st.session_state["result"] = result
    st.session_state["human_audit"] = AuditStore(transaction_id=result.transaction.transaction_id)


def _render_evidence(tx: m.Transaction) -> None:
    st.subheader("Evidence")
    cols = st.columns(5)
    for col, (label, present) in zip(cols, p.evidence_summary(tx).items()):
        col.metric(label, "✓" if present else "—")

    if tx.po:
        st.caption(
            f"PO {tx.po.po_id} · vendor {tx.po.vendor_id} · approved {p.format_vnd(tx.po.approved_total)}"
        )
    if tx.invoice:
        st.caption(
            f"Invoice {tx.invoice.invoice_id} ({tx.invoice.invoice_number}/{tx.invoice.invoice_series}) "
            f"· {tx.invoice.invoice_type.value} · total {p.format_vnd(tx.invoice.total_amount)}"
            + ("  ⚠️ flagged" if tx.invoice.flagged else "")
        )


def _render_checks(checks: list[m.CheckResult]) -> None:
    st.subheader("Checks")
    rows = []
    for c in checks:
        rows.append(
            {
                "Check": c.check_id.replace("CHECK_", ""),
                "Rule": c.policy_rule_id or "—",
                "Status": f"{_CHECK_ICON.get(c.status.value, '')} {c.status.value}",
                "Expected": str(c.expected) if c.expected is not None else "—",
                "Actual": str(c.actual) if c.actual is not None else "—",
                "Reason": c.reason or "",
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_decision(result: m.ReviewResult) -> None:
    d = result.decision
    icon, color = _DECISION_STYLE.get(d.action.value, ("", "gray"))
    st.subheader("Decision")
    st.markdown(f"### {icon} :{color}[{d.action.value}]")
    st.write(f"**Reason:** {d.reason}")
    if d.uncertainty:
        st.write(f"**Uncertainty:** {d.uncertainty.type.value}")
    if d.question:
        st.info(f"**Question:** {d.question}")
    if d.target:
        st.write(f"**Escalation target:** {d.target}")
    if d.policy_rule_ids:
        st.caption("Policy rules: " + ", ".join(d.policy_rule_ids))

    a = result.agent_assessment
    if a is not None:
        if a.fallback_used:
            st.caption(
                f"🛟 Assessment source: **deterministic fallback** "
                f"(LLM unavailable/invalid) · prompt {a.prompt_version or '—'}"
            )
        else:
            st.caption(
                f"🤖 Assessment source: **LLM** ({a.model or 'configured provider'}) "
                f"· prompt {a.prompt_version or '—'}"
            )
        with st.expander("LLM assessment / explanation"):
            st.write(a.explanation)


def _render_audit(result: m.ReviewResult) -> None:
    st.subheader("Audit History")
    events = list(result.audit_events)
    human = st.session_state.get("human_audit")
    if human is not None:
        events = events + list(human.events)
    rows = [
        {
            "Time": e.timestamp,
            "Event": e.event_type,
            "Rule": e.rule_id or "—",
            "Result": e.result or "—",
            "Reason": e.reason or "",
        }
        for e in events
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.download_button(
        "Export audit JSON",
        data=json.dumps(rows, ensure_ascii=False, indent=2),
        file_name=f"audit_{result.transaction.transaction_id or 'tx'}.json",
        mime="application/json",
    )


def _render_human_controls(result: m.ReviewResult) -> None:
    tx = result.transaction
    human: AuditStore = st.session_state["human_audit"]
    st.subheader("Human controls")
    st.write(f"Workflow status: **{tx.workflow_status.value}**")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Stop** (changes workflow status only)")
        stop_reason = st.text_input("Stop reason", key="stop_reason")
        if st.button("Stop transaction", disabled=tx.workflow_status is m.WorkflowStatus.STOPPED):
            if not stop_reason.strip():
                st.warning("A reason is required to Stop.")
            else:
                human.record_stop(tx, actor="judge@demo", reason=stop_reason.strip())
                st.success("Transaction stopped. Agent decision preserved in audit.")
                st.rerun()

    with c2:
        st.markdown("**Override** (records a new effective decision, keeps original)")
        new_action = st.selectbox("Override decision", p.decision_action_labels(), key="ovr_action")
        ovr_reason = st.text_input("Override reason", key="ovr_reason")
        if st.button("Override decision"):
            if not ovr_reason.strip():
                st.warning("A reason is required to Override.")
            else:
                human.record_override(
                    tx, actor="judge@demo",
                    overridden_action=m.DecisionAction(new_action), reason=ovr_reason.strip(),
                )
                st.success(f"Override recorded. Original {tx.decision.action.value} kept in history.")
                st.rerun()


def _render_verify() -> None:
    st.subheader("Verify harness")
    st.caption("Runs the documented cases through the same production review() path.")
    c1, c2, c3 = st.columns(3)
    suite = None
    if c1.button("▶ Run Full Verify"):
        suite = "all"
    if c2.button("Core Verify"):
        suite = "core"
    if c3.button("Escalation Verify"):
        suite = "escalation"
    if suite:
        results = harness.run_suite(suite)
        rows = [
            {
                "Suite": r.suite or "-",
                "Case": r.case_id,
                "Expected": r.expected,
                "Actual": r.actual,
                "Result": "PASS" if r.passed else "FAIL",
                "Uncertainty": r.uncertainty_type or "—",
                "Target": r.target or "—",
                "LLM": "fallback" if r.fallback_used else "llm",
                "Question": r.question or "",
                "Timestamp": r.timestamp,
            }
            for r in results
        ]
        passed = sum(1 for r in results if r.passed)
        llm_rows = sum(1 for r in results if not r.fallback_used)
        st.dataframe(rows, use_container_width=True, hide_index=True)
        (st.success if passed == len(results) else st.error)(
            f"{passed}/{len(results)} cases passed — suite '{suite}'."
        )
        st.caption(f"Assessment source: {llm_rows}/{len(results)} via LLM, "
                   f"{len(results) - llm_rows} deterministic fallback.")


def main() -> None:
    st.title("🧾 InvoiceReferee")
    st.markdown(
        "**Bắt đầu ở đây:** chọn một sample case bên trái rồi bấm **Review**, "
        "hoặc dán/upload một transaction JSON mới. Xem quyết định, lý do, câu hỏi và audit; "
        "hoặc bấm **Run Full Verify**. Không cần đăng nhập, không cần cài đặt."
    )

    with st.sidebar:
        st.header("Input")
        mode = st.radio("Nguồn dữ liệu", ["Sample case", "Paste JSON", "Upload JSON"])
        evidence = None
        error = None

        if mode == "Sample case":
            case_id = st.selectbox("Sample", p.list_sample_cases())
            if st.button("Review", type="primary"):
                evidence = p.load_sample(case_id)
        elif mode == "Paste JSON":
            text = st.text_area("Transaction JSON", height=260, placeholder='{ "transaction_id": "...", ... }')
            if st.button("Review", type="primary"):
                try:
                    evidence = p.parse_json_input(text)
                except ValueError as exc:
                    error = str(exc)
        else:
            uploaded = st.file_uploader("Upload .json", type=["json"])
            if st.button("Review", type="primary") and uploaded is not None:
                try:
                    evidence = p.parse_json_input(uploaded.read().decode("utf-8"))
                except ValueError as exc:
                    error = str(exc)

        if error:
            st.error(error)  # technical input error, kept separate from business uncertainty
        if evidence is not None:
            _run_review(evidence)

    result = st.session_state.get("result")
    if result is None:
        st.info("Chưa có transaction nào được review. Chọn input ở thanh bên trái.")
        _render_verify()
        return

    _render_decision(result)
    _render_evidence(result.transaction)
    _render_checks(result.checks)
    _render_human_controls(result)
    _render_audit(result)
    st.divider()
    _render_verify()


main()
