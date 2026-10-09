"""W03 reader contracts: budget, mock transports, validation, direct parsing.

All provider calls go through ``httpx.MockTransport``; no test touches the
network, prints env values, or needs real API keys.
"""
from __future__ import annotations

import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import RunBudget, SourceRecord
from invoice_referee.settlement.reader import StructuredLedgerReader
from tests.settlement import builders as b

FIXTURES = Path(__file__).with_name("fixtures")


# --- Budget (plan W03) -------------------------------------------------------

def test_budget_exhaustion_is_not_an_unreadable_source():
    budget = RunBudget(deadline=time.monotonic() + 30, max_calls=1)
    budget.reserve_call()
    with pytest.raises(DomainError) as error:
        budget.reserve_call()
    assert error.value.code == "BUDGET_EXHAUSTED"
    assert budget.calls == 1


def test_budget_deadline_exhaustion_is_technical():
    budget = RunBudget(deadline=time.monotonic() - 1, max_calls=10)
    with pytest.raises(DomainError) as error:
        budget.reserve_call()
    assert error.value.code == "BUDGET_EXHAUSTED"
    assert budget.calls == 0


# --- Transport helpers -------------------------------------------------------

def ocr_transport(pages_payload, usage=None):
    body = {"pages": pages_payload}
    if usage is not None:
        body["usage"] = usage

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


def failing_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("provider không được gọi trong test này")

    return httpx.MockTransport(handler)


def timeout_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    return httpx.MockTransport(handler)


def scripted_transport(responses, capture):
    def handler(request: httpx.Request) -> httpx.Response:
        capture.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json=responses[len(capture) - 1])

    return httpx.MockTransport(handler)


def xkiro_body(fields=None, relations=None, finish_reason="stop", usage=None,
               response_model="gateway/mistralai/mistral-small-2603"):
    if fields is None and relations is None:
        fields = []
    content = json.dumps({"fields": fields} if fields is not None
                         else {"relations": relations}, ensure_ascii=False)
    body = {"choices": [{"message": {"content": content},
                        "finish_reason": finish_reason}],
            "model": response_model}
    if usage is not None:
        body["usage"] = usage
    return body


def make_reader(tmp_path, ocr_transport=None, xkiro_transport=None):
    from invoice_referee.settlement.reader import (
        MistralOCRClient,
        SettlementReader,
        XkiroClient,
    )

    return SettlementReader(
        artifact_root=tmp_path,
        ocr=MistralOCRClient(api_key="test-ocr-key",
                              transport=ocr_transport or failing_transport()),
        xkiro=XkiroClient(api_key="test-xkiro-key",
                          transport=xkiro_transport or failing_transport()),
    )


def write_source(tmp_path, name: str, content: bytes, media_type: str,
                 source_id="S-img1") -> SourceRecord:
    path = tmp_path / source_id
    path.write_bytes(content)
    return SourceRecord(
        id=source_id, case_id="C-TEST", filename=name, media_type=media_type,
        sha256="h-" + source_id, size_bytes=len(content), status="ACCEPTED",
        uploader_actor_id="NV-01", received_at=datetime.now(timezone.utc),
        provenance={}, original_path=Path(source_id),
    )


def budget() -> RunBudget:
    return RunBudget(deadline=time.monotonic() + 30, max_calls=32)


def png_bytes() -> bytes:
    return (FIXTURES / "tiny.png").read_bytes()


# --- Mistral OCR: page index mapping ----------------------------------------

def test_mistral_page0_maps_to_ui_page1(tmp_path):
    ocr_pages = [{"index": 0, "markdown": "Tổng thanh toán: 5.000.000 VND"}]
    extract = xkiro_body(fields=[{
        "key": "expense.EXP-1.amount", "raw_text": "5.000.000",
        "read_state": "READ", "value": 5000000,
        "evidence": {"page": 1, "quote": "Tổng thanh toán: 5.000.000"},
    }])
    reader = make_reader(tmp_path, ocr_transport(ocr_pages),
                         scripted_transport([extract], []))
    source = write_source(tmp_path, "hoa-don.png", png_bytes(), "image/png")
    observations = reader.read(source, ["expense."], budget())
    assert observations[0].page == 1
    assert observations[0].value == 5_000_000
    assert observations[0].source_id == source.id


def test_ocr_duplicate_page_index_is_invalid(tmp_path):
    ocr_pages = [{"index": 0, "markdown": "a"}, {"index": 0, "markdown": "b"}]
    extract = xkiro_body(fields=[])
    reader = make_reader(tmp_path, ocr_transport(ocr_pages),
                         scripted_transport([extract], []))
    source = write_source(tmp_path, "hoa-don.png", png_bytes(), "image/png")
    with pytest.raises(DomainError) as error:
        reader.read(source, [], budget())
    assert error.value.code == "PROVIDER_OUTPUT_INVALID"


# --- xkiro request contract --------------------------------------------------

def test_xkiro_request_has_full_model_none_effort_json_mode(tmp_path):
    ocr_pages = [{"index": 0, "markdown": "text"}]
    captured: list[dict] = []
    extract = xkiro_body(fields=[])
    reader = make_reader(tmp_path, ocr_transport(ocr_pages),
                         scripted_transport([extract], captured))
    source = write_source(tmp_path, "hoa-don.png", png_bytes(), "image/png")
    reader.read(source, [], budget())
    request = captured[0]
    assert request["model"] == "mistralai/mistral-small-2603"
    assert request["reasoning_effort"] == "none"
    assert request["response_format"] == {"type": "json_object"}
    assert requested_temperature_is_zero(request)
    trace = reader.trace_entries()
    extract_entry = next(e for e in trace if e.stage == "extract")
    assert extract_entry.requested_model == "mistralai/mistral-small-2603"
    assert extract_entry.response_model != extract_entry.requested_model


def requested_temperature_is_zero(request: dict) -> bool:
    return request["temperature"] == 0


def test_usage_missing_is_none_not_zero(tmp_path):
    ocr_pages = [{"index": 0, "markdown": "text"}]
    extract = xkiro_body(fields=[], usage=None)
    reader = make_reader(tmp_path, ocr_transport(ocr_pages, usage=None),
                         scripted_transport([extract], []))
    source = write_source(tmp_path, "hoa-don.png", png_bytes(), "image/png")
    reader.read(source, [], budget())
    assert reader.trace_entries()
    for entry in reader.trace_entries():
        assert entry.usage is None


# --- Invalid / truncated / unknown ------------------------------------------

def test_invalid_json_retries_once_then_succeeds(tmp_path):
    ocr_pages = [{"index": 0, "markdown": "text"}]
    bad = {"choices": [{"message": {"content": "not json {{"},
                        "finish_reason": "stop"}], "model": "m"}
    good = xkiro_body(fields=[])
    reader = make_reader(tmp_path, ocr_transport(ocr_pages),
                         scripted_transport([bad, good], []))
    source = write_source(tmp_path, "hoa-don.png", png_bytes(), "image/png")
    observations = reader.read(source, [], budget())
    assert observations == []
    assert reader.attempts_for(source.id) == 2  # lần đầu + đúng 1 retry


def test_invalid_json_twice_is_technical_failure(tmp_path):
    ocr_pages = [{"index": 0, "markdown": "text"}]
    bad = {"choices": [{"message": {"content": "still not json"},
                        "finish_reason": "stop"}], "model": "m"}
    reader = make_reader(tmp_path, ocr_transport(ocr_pages),
                         scripted_transport([bad, bad], []))
    source = write_source(tmp_path, "hoa-don.png", png_bytes(), "image/png")
    with pytest.raises(DomainError) as error:
        reader.read(source, [], budget())
    assert error.value.code == "PROVIDER_OUTPUT_INVALID"
    assert reader.attempts_for(source.id) == 2


def test_truncated_output_is_technical_not_not_found(tmp_path):
    ocr_pages = [{"index": 0, "markdown": "text"}]
    truncated = xkiro_body(fields=[], finish_reason="length")
    reader = make_reader(tmp_path, ocr_transport(ocr_pages),
                         scripted_transport([truncated], []))
    source = write_source(tmp_path, "hoa-don.png", png_bytes(), "image/png")
    with pytest.raises(DomainError) as error:
        reader.read(source, [], budget())
    assert error.value.code == "PROVIDER_OUTPUT_TRUNCATED"


def test_read_timeout_is_technical(tmp_path):
    from invoice_referee.settlement.reader import (
        MistralOCRClient,
        SettlementReader,
        XkiroClient,
    )

    reader = SettlementReader(
        artifact_root=tmp_path,
        ocr=MistralOCRClient(api_key="k", transport=timeout_transport()),
        xkiro=XkiroClient(api_key="k", transport=timeout_transport()),
    )
    source = write_source(tmp_path, "hoa-don.png", png_bytes(), "image/png")
    with pytest.raises(DomainError) as error:
        reader.read(source, [], budget())
    assert error.value.code == "PROVIDER_FAILED"


def test_money_string_value_stays_unclear_not_guessed(tmp_path):
    ocr_pages = [{"index": 0, "markdown": "Tổng: 3.000.000"}]
    field = {"key": "expense.EXP-1.amount", "raw_text": "3.000.000",
             "read_state": "READ", "value": "3.000.000",
             "evidence": {"page": 1, "quote": "Tổng: 3.000.000"}}
    reader = make_reader(tmp_path, ocr_transport(ocr_pages),
                         scripted_transport([xkiro_body(fields=[field])], []))
    source = write_source(tmp_path, "hoa-don.png", png_bytes(), "image/png")
    observations = reader.read(source, ["expense."], budget())
    assert observations[0].read_state == "UNCLEAR"
    assert observations[0].value is None
    assert observations[0].raw == "3.000.000"


def test_requested_key_missing_from_output_is_not_not_found(tmp_path):
    ocr_pages = [{"index": 0, "markdown": "text"}]
    reader = make_reader(tmp_path, ocr_transport(ocr_pages),
                         scripted_transport([xkiro_body(fields=[])], []))
    source = write_source(tmp_path, "hoa-don.png", png_bytes(), "image/png")
    observations = reader.read(source, ["expense.EXP-1.amount"], budget())
    missing = [o for o in observations if o.key == "expense.EXP-1.amount"]
    assert missing and missing[0].read_state == "UNCLEAR"
    assert missing[0].value is None


# --- Direct parsing without providers ----------------------------------------

def test_csv_ledger_parses_directly_without_provider_calls(tmp_path):
    csv_text = (
        "source_record_ref,event_kind,payer_ref,payee_ref,gross_amount_vnd,"
        "currency,event_at,reported_status\n"
        "TX-01,DISBURSEMENT,ORG-01,NV-01,2000000,VND,2026-10-06T09:00:00+07:00,"
        "completed\n"
    )
    source = write_source(tmp_path, "lich-su.csv", csv_text.encode("utf-8"),
                          "text/csv", source_id="S-csv1")
    reader = make_reader(tmp_path)
    observations = reader.read(source, ["payment."], budget())
    amounts = [o for o in observations if o.key == "payment.TX-01.amount"]
    assert amounts and amounts[0].value == 2_000_000
    payers = [o for o in observations if o.key == "payment.TX-01.payer"]
    assert payers and payers[0].value == "COMPANY"
    statuses = [o for o in observations if o.key == "payment.TX-01.status"]
    assert statuses and statuses[0].value == "RECEIVED"
    assert reader.trace_entries() == []  # không gọi provider nào


def test_ledger_text_parses_directly_without_provider_calls(tmp_path):
    ledger = "fact F1 expense.EXP-1.amount 5000000\n"
    source = write_source(tmp_path, "hoa-don.txt", ledger.encode("utf-8"),
                          "text/plain", source_id="S-txt1")
    reader = make_reader(tmp_path)
    observations = reader.read(source, ["expense."], budget())
    assert observations[0].value == 5_000_000
    assert reader.trace_entries() == []


# --- Matching -----------------------------------------------------------------

def test_match_returns_proposed_relations_and_filters_unknown_refs(tmp_path):
    run_input, facts, _ = b.run_input(facts=(
        b.expense_facts("EXP-1", 5_000_000, source_id="S1")
        + b.payment_facts("PAY-1", 5_000_000, "EMPLOYEE", source_id="S2")))
    relation_payload = {"relations": [
        {"id": "RM-1", "kind": "EXPENSE_PAYMENT", "from": "EXP-1", "to": "PAY-1",
         "portion_vnd": None, "supporting": ["S1", "S2"], "status": "PROPOSED",
         "reason": "số và bên khớp"},
        {"id": "RM-2", "kind": "EXPENSE_PAYMENT", "from": "EXP-1", "to": "PAY-404",
         "portion_vnd": None, "supporting": ["S1"], "status": "PROPOSED",
         "reason": "ref không tồn tại"},
    ]}

    def match_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{"message": {
                "content": json.dumps(relation_payload, ensure_ascii=False)},
                "finish_reason": "stop"}],
            "model": "m"})

    from invoice_referee.settlement.reader import (
        MistralOCRClient,
        SettlementReader,
        XkiroClient,
    )

    reader = SettlementReader(
        artifact_root=tmp_path,
        ocr=MistralOCRClient(api_key="k", transport=failing_transport()),
        xkiro=XkiroClient(api_key="k", transport=httpx.MockTransport(match_handler)),
    )
    proposed = reader.match(run_input, facts, budget())
    assert [r.relation_id for r in proposed] == ["RM-1"]
    assert proposed[0].status == "PROPOSED"
    filtered = [e for e in reader.trace_entries()
                if e.error_code == "UNKNOWN_REF_FILTERED"]
    assert filtered and "PAY-404" in (filtered[0].detail or "")


# --- Resource envelope ---------------------------------------------------------

def test_oversize_pixels_image_rejected_before_ocr(tmp_path):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("L", (5000, 5000), color=128).save(buf, format="PNG")
    source = write_source(tmp_path, "kho.png", buf.getvalue(), "image/png")
    reader = make_reader(tmp_path)
    with pytest.raises(DomainError) as error:
        reader.read(source, [], budget())
    assert error.value.code == "REPRESENTATION_LIMIT"


def test_fake_reader_also_parses_csv_directly(tmp_path):
    csv_text = (
        "source_record_ref,event_kind,payer_ref,payee_ref,gross_amount_vnd,"
        "currency,event_at,reported_status\n"
        "TX-02,RETURN,NV-01,ORG-01,700000,VND,2026-10-07T09:00:00+07:00,"
        "received\n"
    )
    source = write_source(tmp_path, "hoan-ung.csv", csv_text.encode("utf-8"),
                          "text/csv", source_id="S-csv2")
    reader = StructuredLedgerReader(tmp_path)
    observations = reader.read(source, ["payment."], budget())
    payers = [o for o in observations if o.key == "payment.TX-02.payer"]
    assert payers and payers[0].value == "EMPLOYEE"
    assert reader.trace_entries() == []
