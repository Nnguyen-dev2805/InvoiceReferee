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
# and ``app`` packages then fail to import, and the ``invoice_referee`` package
# lives under ``src/`` (only importable via an editable install locally). On a
# clean host such as Streamlit Community Cloud there is no editable install, so
# make both the project root and ``src/`` importable regardless of how the app
# is launched or what the current working directory is.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _p in (_PROJECT_ROOT, _PROJECT_ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Streamlit Community Cloud injects deployment secrets via ``st.secrets`` rather
# than a ``.env`` file (``.env`` is intentionally gitignored). Bridge any LLM_*
# secret into the process environment so ``client_from_env()`` picks it up with
# no code branching between local and deployed runs.
try:  # pragma: no cover - exercised only on the deployed host
    import os as _os

    import streamlit as _st_secrets_probe

    for _k, _v in dict(_st_secrets_probe.secrets).items():
        if _k.startswith("LLM_") and _k not in _os.environ:
            _os.environ[_k] = str(_v)
except Exception:
    # No secrets file locally (or none set): fall back to real env / .env / fallback.
    pass

import streamlit as st

from invoice_referee.domain import models as m
from invoice_referee.transaction.builder import build_transaction
from invoice_referee.services.reviewer import review
from invoice_referee.audit.store import AuditStore
from invoice_referee.agent.config import client_from_env
from invoice_referee.ingestion import normalization as norm
from verify import harness

from app import presentation as p
from app import extraction_presentation as ep

_MIME_BY_SUFFIX = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}

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


def _run_review(evidence: dict, audit: AuditStore | None = None) -> None:
    """Run a review and store result + a fresh human-control audit store in session."""
    # Uses the configured LLM provider when a key is set, else deterministic fallback.
    client = client_from_env()
    result = review(evidence, client=client, model=getattr(client, "model", None), audit=audit)
    st.session_state["result"] = result
    st.session_state["human_audit"] = AuditStore(transaction_id=result.transaction.transaction_id)


def _extract_document(uploaded, po_json: str, actor: str) -> None:
    """Validate + OCR-extract an uploaded invoice into session state."""
    from invoice_referee.services.extractor import extract_invoice, ExtractionError
    from invoice_referee.ingestion.file_validation import DocumentInputError
    from invoice_referee.ingestion.ocr_config import engine_from_env

    suffix = uploaded.name.rsplit(".", 1)[-1].lower()
    mime = _MIME_BY_SUFFIX.get(suffix)
    if mime is None:
        st.error("Unsupported file type. Upload a PDF, PNG, or JPEG invoice.")
        return

    try:
        base_evidence = p.parse_json_input(po_json)
    except ValueError as exc:
        st.error(f"Structured PO/GR/payment JSON is invalid: {exc}")
        return

    po_raw = base_evidence.get("purchase_order") or base_evidence.get("po") or {}
    po = norm.to_purchase_order(po_raw)
    transaction_id = norm.normalize_id(base_evidence.get("transaction_id")) or "TX-OCR"

    try:
        engine = engine_from_env()  # PaddleOCR local by default; Mistral if configured
        result, audit = extract_invoice(
            transaction_id=transaction_id,
            filename=uploaded.name,
            claimed_mime=mime,
            content=uploaded.read(),
            po=po,
            engine=engine,
            actor=actor,
        )
    except DocumentInputError as exc:
        st.error(f"Document input error: {exc}")  # technical, not a business decision
        return
    except ValueError as exc:  # e.g. OCR engine misconfiguration
        st.error(f"OCR engine configuration error: {exc}")
        return
    except ExtractionError as exc:
        st.error(f"Extraction failed: {exc}")
        return

    st.session_state["extraction_result"] = result
    st.session_state["extraction_audit"] = audit
    st.session_state["extraction_base_evidence"] = base_evidence
    st.session_state.pop("result", None)


def _render_extraction_review() -> None:
    """Confirm/correct/mark-unknown extracted fields, then run business review."""
    from invoice_referee.ingestion.pipeline import (
        apply_field_reviews,
        reviewed_invoice_to_evidence,
        FieldReview,
    )

    result: m.InvoiceExtractionResult = st.session_state["extraction_result"]
    st.subheader("Extracted fields — confirm before review")
    st.caption(
        "Every critical field must be Confirmed, Corrected, or Marked unknown. "
        "OCR extracts candidate facts only; the decision still comes from the "
        "deterministic policy pipeline."
    )
    st.dataframe(ep.field_rows(result), use_container_width=True, hide_index=True)
    if result.line_items:
        st.dataframe(ep.line_item_rows(result), use_container_width=True, hide_index=True)

    with st.form("field_reviews"):
        form_values: dict[str, dict] = {}
        for name, candidate in result.fields.items():
            c1, c2 = st.columns([1, 2])
            action = c1.selectbox(
                name,
                ["CONFIRM", "CORRECT", "MARK_UNKNOWN"],
                key=f"act_{name}",
            )
            value = c2.text_input(
                f"{name} value (for Correct)",
                value="" if candidate.normalized_value is None else str(candidate.normalized_value),
                key=f"val_{name}",
            )
            reason = c2.text_input(f"{name} reason", key=f"rsn_{name}")
            form_values[name] = {"action": action, "value": value, "reason": reason}
        submitted = st.form_submit_button("Confirm extraction & Review", type="primary")

    if submitted:
        reviews = ep.build_field_reviews(form_values, result)
        try:
            reviewed = apply_field_reviews(result, reviews, actor="judge@demo")
        except ValueError as exc:
            st.error(str(exc))  # e.g. missing reason for Correct/Mark unknown
            return
        audit: AuditStore = st.session_state["extraction_audit"]
        audit.record_extraction_reviewed(reviewed, actor="judge@demo")
        evidence = reviewed_invoice_to_evidence(reviewed, st.session_state["extraction_base_evidence"])
        _run_review(evidence, audit=audit)
        st.session_state.pop("extraction_result", None)
        st.rerun()


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
        mode = st.radio(
            "Nguồn dữ liệu",
            ["Sample case", "Paste JSON", "Upload JSON", "Invoice Document"],
        )
        evidence = None
        error = None

        if mode == "Invoice Document":
            st.caption(
                "Upload one Supplier Invoice (PDF/PNG/JPEG). PO, Goods Receipt and "
                "payment history stay structured JSON below."
            )
            uploaded_doc = st.file_uploader(
                "Invoice file", type=["pdf", "png", "jpg", "jpeg"], key="doc_upload"
            )
            po_json = st.text_area(
                "Structured PO / GR / payment JSON",
                height=200,
                key="doc_base_json",
                placeholder='{ "transaction_id": "...", "purchase_order": { ... }, "goods_receipts": [ ... ] }',
            )
            if st.button("Process invoice", type="primary"):
                if uploaded_doc is None:
                    st.warning("Upload an invoice file first.")
                else:
                    _extract_document(uploaded_doc, po_json or "{}", actor="judge@demo")

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

    # An in-progress OCR extraction takes over the main panel until confirmed.
    if st.session_state.get("extraction_result") is not None:
        _render_extraction_review()
        st.divider()
        _render_verify()
        return

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
