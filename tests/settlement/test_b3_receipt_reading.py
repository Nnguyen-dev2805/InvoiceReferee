"""B5 receipt reading (b3-intake-v1): upload → read → draft, no money event.

These exercise the real reader path with httpx.MockTransport (no network, no
LIVE, no keys) over the packet-literal context. A read is a SEPARATE step: it
must never create a money event or move the stage; only the existing
``record_b3_advance`` guard does that.
"""
from __future__ import annotations

import json
import time
from datetime import timedelta

import httpx
import pytest

from invoice_referee.settlement.models import Upload
from invoice_referee.settlement.reader import (
    MistralOCRClient,
    SettlementReader,
    XkiroClient,
)
from tests.settlement.test_b3_funding import approved_b3, upload_receipt  # noqa: F401
from tests.settlement.test_b3_workflow import (  # noqa: F401
    command, ready_b3, presented_b3,
)


def _xkiro_body(fields):
    content = json.dumps({"fields": fields}, ensure_ascii=False)
    return {"choices": [{"message": {"content": content},
                         "finish_reason": "stop"}],
            "model": "gateway/test"}


def _reader_with(fields, artifact_root):
    """A real SettlementReader whose xkiro returns the given receipt fields."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_xkiro_body(fields))

    return SettlementReader(
        artifact_root=artifact_root,
        ocr=MistralOCRClient(api_key="k",
                             transport=httpx.MockTransport(handler)),
        xkiro=XkiroClient(api_key="k",
                          transport=httpx.MockTransport(handler)),
    )


def _receipt_field(key, value, *, read_state="READ", quote=None, page=1):
    return {"fact_id": key.replace(".", "-"), "key": key,
            "raw_text": quote if quote is not None else str(value),
            "read_state": read_state, "value": value,
            "evidence": {"page": page, "quote": quote or str(value)}}


def _install_reader(svc, fields):
    reader = _reader_with(fields, svc.store.artifact_root)
    svc.reader = reader
    return reader


BANK_FIELDS = [
    _receipt_field("receipt.amount", 2_000_000, quote="Số tiền: 2.000.000 đ"),
    _receipt_field("receipt.currency", "VND"),
    _receipt_field("receipt.payer_name", "Công ty InvoiceReferee",
                   quote="Bên chuyển: Công ty InvoiceReferee"),
    _receipt_field("receipt.receiver_name", "Nguyễn An",
                   quote="Bên nhận: Nguyễn An"),
    _receipt_field("receipt.event_ref", "TX-L01-ADV-001"),
    _receipt_field("receipt.narrative", "Tạm ứng công tác Hà Nội"),
    _receipt_field("receipt.outcome_text",
                   "Đã ghi có cho người hưởng; giao dịch hoàn tất."),
    _receipt_field("receipt.proof_scope", "RECEIVER_CONFIRMED"),
    _receipt_field("receipt.event_at", "2026-10-10T10:00:00+07:00"),
]


def _upload_proof(svc, case, key="proof"):
    return svc.add_b3_advance_proof(case.id,
        Upload(filename="bank-receipt.txt", content=b"BIEN NHAN ..."),
        command(key, "ACC-DEMO-01", "ACCOUNTANT", svc.get_case(case.id).case_version))


def test_read_produces_draft_without_money_event(approved_b3):
    svc, case, decision = approved_b3
    proof = _upload_proof(svc, case)
    _install_reader(svc, BANK_FIELDS)
    before = svc.get_case(case.id)
    read = svc.read_b3_advance_receipt(
        case.id, proof.id, "BANK_TRANSFER",
        command("read", "ACC-DEMO-01", "ACCOUNTANT", before.case_version))
    assert read.status == "READ"
    assert read.proposal.amount_vnd == 2_000_000
    assert read.proposal.payee_ref == "NV-DEMO-01"
    assert read.proposal.classification_hint == "CONFIRMED_RECEIPT"
    # No money event, no stage change, no input revision change.
    after = svc.get_case(case.id)
    assert after.b3_workflow.funding.recorded_received_vnd is None
    assert after.stage == before.stage
    assert after.input_revision == before.input_revision
    assert after.b3_workflow.advance_events == []


def test_facts_keep_source_locator_and_quote(approved_b3):
    svc, case, decision = approved_b3
    proof = _upload_proof(svc, case)
    _install_reader(svc, BANK_FIELDS)
    read = svc.read_b3_advance_receipt(
        case.id, proof.id, "BANK_TRANSFER",
        command("read", "ACC-DEMO-01", "ACCOUNTANT", svc.get_case(case.id).case_version))
    amount = next(f for f in read.facts if f.key == "receipt.amount")
    assert amount.value == 2_000_000
    assert amount.locator  # a real locator, not a fabricated field name
    assert amount.page == 1
    assert amount.quote and "2.000.000" in amount.quote


def test_bank_order_only_never_hints_received(approved_b3):
    svc, case, decision = approved_b3
    proof = _upload_proof(svc, case)
    fields = [f for f in BANK_FIELDS if f["key"] != "receipt.proof_scope"]
    fields.append(_receipt_field("receipt.proof_scope", "ORDER_ONLY",
                                 quote="Lập lệnh thành công, chờ duyệt"))
    _install_reader(svc, fields)
    read = svc.read_b3_advance_receipt(
        case.id, proof.id, "BANK_TRANSFER",
        command("read", "ACC-DEMO-01", "ACCOUNTANT", svc.get_case(case.id).case_version))
    assert read.proposal.classification_hint == "UNCONFIRMED"
    assert any(w.code == "BANK_SCOPE_NOT_RECEIVER" for w in read.warnings)


def test_sender_debit_only_never_hints_received(approved_b3):
    svc, case, decision = approved_b3
    proof = _upload_proof(svc, case)
    fields = [f for f in BANK_FIELDS if f["key"] != "receipt.proof_scope"]
    fields.append(_receipt_field("receipt.proof_scope", "SENDER_DEBIT"))
    _install_reader(svc, fields)
    read = svc.read_b3_advance_receipt(
        case.id, proof.id, "BANK_TRANSFER",
        command("read", "ACC-DEMO-01", "ACCOUNTANT", svc.get_case(case.id).case_version))
    assert read.proposal.classification_hint == "UNCONFIRMED"


def test_cash_acknowledged_hints_received(approved_b3):
    svc, case, decision = approved_b3
    proof = _upload_proof(svc, case, key="cashproof")
    fields = [
        _receipt_field("receipt.amount", 2_000_000),
        _receipt_field("receipt.currency", "VND"),
        _receipt_field("receipt.receiver_name", "Nguyễn An"),
        _receipt_field("receipt.voucher_number", "PC-L01-001"),
        _receipt_field("receipt.handed_by_name", "Trần Bình"),
        _receipt_field("receipt.acknowledgement", "ACKNOWLEDGED"),
        _receipt_field("receipt.event_ref", "PC-L01-001"),
    ]
    _install_reader(svc, fields)
    read = svc.read_b3_advance_receipt(
        case.id, proof.id, "CASH",
        command("read", "ACC-DEMO-01", "ACCOUNTANT", svc.get_case(case.id).case_version))
    assert read.proposal.classification_hint == "CONFIRMED_RECEIPT"
    assert read.proposal.acknowledgement == "ACKNOWLEDGED"


def test_cash_unsigned_never_hints_received(approved_b3):
    svc, case, decision = approved_b3
    proof = _upload_proof(svc, case, key="cashunsigned")
    fields = [
        _receipt_field("receipt.amount", 2_000_000),
        _receipt_field("receipt.receiver_name", "Nguyễn An"),
        _receipt_field("receipt.voucher_number", "PC-L01-002"),
        _receipt_field("receipt.acknowledgement", "UNCONFIRMED"),
    ]
    _install_reader(svc, fields)
    read = svc.read_b3_advance_receipt(
        case.id, proof.id, "CASH",
        command("read", "ACC-DEMO-01", "ACCOUNTANT", svc.get_case(case.id).case_version))
    assert read.proposal.classification_hint == "UNCONFIRMED"
    assert any(w.code == "CASH_NOT_HANDED" for w in read.warnings)


def test_similar_name_is_not_matched(approved_b3):
    svc, case, decision = approved_b3
    proof = _upload_proof(svc, case, key="wrongname")
    fields = [f for f in BANK_FIELDS if f["key"] != "receipt.receiver_name"]
    fields.append(_receipt_field("receipt.receiver_name", "Nguyễn Anh"))
    _install_reader(svc, fields)
    read = svc.read_b3_advance_receipt(
        case.id, proof.id, "BANK_TRANSFER",
        command("read", "ACC-DEMO-01", "ACCOUNTANT", svc.get_case(case.id).case_version))
    assert read.proposal.payee_ref == "OTHER"
    assert read.proposal.receiver_name == "Nguyễn Anh"  # raw kept
    assert any(w.code == "RECEIVER_NOT_MATCHED" for w in read.warnings)


def test_missing_amount_stays_none_not_approved(approved_b3):
    svc, case, decision = approved_b3
    proof = _upload_proof(svc, case, key="noamount")
    fields = [f for f in BANK_FIELDS if f["key"] != "receipt.amount"]
    _install_reader(svc, fields)
    read = svc.read_b3_advance_receipt(
        case.id, proof.id, "BANK_TRANSFER",
        command("read", "ACC-DEMO-01", "ACCOUNTANT", svc.get_case(case.id).case_version))
    assert read.proposal.amount_vnd is None  # never the approved 2tr


def test_provider_error_becomes_failed_draft(approved_b3):
    svc, case, decision = approved_b3
    proof = _upload_proof(svc, case, key="proverr")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    reader = SettlementReader(
        artifact_root=svc.store.artifact_root,
        ocr=MistralOCRClient(api_key="k", transport=httpx.MockTransport(handler)),
        xkiro=XkiroClient(api_key="k", transport=httpx.MockTransport(handler)))
    svc.reader = reader
    read = svc.read_b3_advance_receipt(
        case.id, proof.id, "BANK_TRANSFER",
        command("read", "ACC-DEMO-01", "ACCOUNTANT", svc.get_case(case.id).case_version))
    assert read.status == "FAILED"
    assert read.error
    assert read.proposal.amount_vnd is None
    # Still no money event.
    assert svc.get_case(case.id).b3_workflow.funding.recorded_received_vnd is None


def test_read_requires_approved_and_accountant(approved_b3):
    from invoice_referee.shared.errors import DomainError
    svc, case, decision = approved_b3
    proof = _upload_proof(svc, case, key="guard")
    _install_reader(svc, BANK_FIELDS)
    with pytest.raises(DomainError) as exc:
        svc.read_b3_advance_receipt(
            case.id, proof.id, "BANK_TRANSFER",
            command("bad", "NV-DEMO-01", "ACCOUNTANT",
                    svc.get_case(case.id).case_version))
    assert exc.value.code == "BEYOND_AUTHORITY"


def test_read_rejects_foreign_source(approved_b3):
    from invoice_referee.shared.errors import DomainError
    svc, case, decision = approved_b3
    _install_reader(svc, BANK_FIELDS)
    with pytest.raises(DomainError) as exc:
        svc.read_b3_advance_receipt(
            case.id, "S-KHONG-THUOC", "BANK_TRANSFER",
            command("foreign", "ACC-DEMO-01", "ACCOUNTANT",
                    svc.get_case(case.id).case_version))
    assert exc.value.code == "BASIS_MISMATCH"


def test_read_then_confirm_records_event(approved_b3):
    """The read drafts; the accountant's confirm is what records the event."""
    svc, case, decision = approved_b3
    proof = _upload_proof(svc, case)
    _install_reader(svc, BANK_FIELDS)
    read = svc.read_b3_advance_receipt(
        case.id, proof.id, "BANK_TRANSFER",
        command("read", "ACC-DEMO-01", "ACCOUNTANT", svc.get_case(case.id).case_version))
    assert read.status == "READ"
    # Confirm using the draft's proposal through the existing guard.
    from tests.settlement.test_b3_funding import receipt_payload
    payload = receipt_payload(proof.id, decision, event_ref="TX-L01-ADV-001")
    svc.record_b3_advance(case.id, payload,
        command("confirm", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(case.id).case_version))
    view = svc.get_case(case.id)
    assert view.b3_workflow.funding.recorded_received_vnd == 2_000_000
    assert view.stage == "AWAITING_WORK_SETTLEMENT"


def test_late_read_does_not_overwrite_newer_draft(approved_b3):
    """A re-read is a NEW draft row; the older draft is not mutated."""
    svc, case, decision = approved_b3
    proof = _upload_proof(svc, case)
    _install_reader(svc, BANK_FIELDS)
    first = svc.read_b3_advance_receipt(
        case.id, proof.id, "BANK_TRANSFER",
        command("read1", "ACC-DEMO-01", "ACCOUNTANT", svc.get_case(case.id).case_version))
    fields2 = [f for f in BANK_FIELDS if f["key"] != "receipt.amount"]
    fields2.append(_receipt_field("receipt.amount", 1_000_000))
    _install_reader(svc, fields2)
    second = svc.read_b3_advance_receipt(
        case.id, proof.id, "BANK_TRANSFER",
        command("read2", "ACC-DEMO-01", "ACCOUNTANT", svc.get_case(case.id).case_version))
    assert second.id != first.id
    reads = svc.store.receipt_reads(case.id)
    assert len(reads) == 2
    assert reads[0].proposal.amount_vnd == 2_000_000
    assert reads[1].proposal.amount_vnd == 1_000_000
