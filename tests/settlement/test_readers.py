"""W03 reader contracts: budget, mock transports, validation, direct parsing.

All provider calls go through ``httpx.MockTransport``; no test touches the
network, prints env values, or needs real API keys.
"""
from __future__ import annotations

import base64
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.b3 import B3_V1_KEYS
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


def scanned_pdf_bytes(pages=1):
    from PIL import Image

    image = Image.open(io.BytesIO(png_bytes())).convert("RGB")
    output = io.BytesIO()
    image.save(output, format="PDF", save_all=True,
               append_images=[image] * (pages - 1))
    return output.getvalue()


def test_scanned_pdf_sends_rendered_png_with_image_mime(tmp_path):
    def image_api(request):
        document = json.loads(request.content)["document"]
        url = document["image_url"]
        if not url.startswith("data:image/png;base64,"):
            return httpx.Response(422, json={"detail": "Expected PNG image"})
        assert base64.b64decode(url.split(",", 1)[1]).startswith(b"\x89PNG\r\n\x1a\n")
        return httpx.Response(200, json={"pages": [{"index": 0,
                            "markdown": "Tổng: 1.000.000 VND"}]})

    fields = [{"key": "expense.EXP-1.amount", "value": 1000000,
               "read_state": "READ", "raw_text": "1.000.000",
               "evidence": {"page": 1, "quote": "Tổng: 1.000.000 VND"}}]
    reader = make_reader(tmp_path, httpx.MockTransport(image_api),
                         scripted_transport([xkiro_body(fields=fields)], []))
    source = write_source(tmp_path, "scan.pdf", scanned_pdf_bytes(), "application/pdf")
    observations = reader.read(source, ["expense."], budget())
    assert observations[0].value == 1000000
    assert observations[0].source_id == source.id


def test_two_scan_pages_keep_original_page_and_consume_two_page_slots(tmp_path, monkeypatch):
    from invoice_referee.settlement import reader as reader_module

    monkeypatch.setattr(reader_module, "MAX_PDF_IMAGE_PAGES_PER_RUN", 2)
    fields = [{"key": "expense.EXP-1.amount", "value": 1000000,
               "read_state": "READ", "raw_text": "1.000.000",
               "evidence": {"page": 1, "quote": "Tổng: 1.000.000 VND"}}]
    reader = make_reader(tmp_path,
                         ocr_transport([{"index": 0, "markdown": "Tổng: 1.000.000 VND"}]),
                         scripted_transport([xkiro_body(fields=fields)] * 2, []))
    source = write_source(tmp_path, "two-pages.pdf", scanned_pdf_bytes(2), "application/pdf")
    observations = reader.read(source, [], budget())
    assert [o.page for o in observations] == [1, 2]
    assert [o.locator for o in observations] == ["page 1", "page 2"]
    assert len({o.fact_id for o in observations}) == 2


def test_failed_ocr_is_retained_in_call_trace(tmp_path):
    reader = make_reader(tmp_path, timeout_transport())
    source = write_source(tmp_path, "scan.png", png_bytes(), "image/png")
    with pytest.raises(DomainError) as error:
        reader.read(source, [], budget())
    assert error.value.code == "PROVIDER_FAILED"
    trace = reader.trace_entries()
    assert len(trace) == 1
    assert trace[0].stage == "ocr"
    assert trace[0].ok is False
    assert trace[0].error_code == "PROVIDER_FAILED"
    assert trace[0].source_id == source.id


@pytest.mark.parametrize("different_source", [False, True])
def test_model_local_fact_ids_do_not_collide_across_extractions(tmp_path, different_source):
    from invoice_referee.settlement.rules import evaluate

    reader = make_reader(tmp_path)
    first = write_source(tmp_path, "one.png", png_bytes(), "image/png", "S1")
    second = (write_source(tmp_path, "two.png", png_bytes(), "image/png", "S2")
              if different_source else first)
    facts = []
    for source, page, amount in [(first, 1, 2000000),
                                  (second, 1 if different_source else 2, 4000000)]:
        content = json.dumps({"fields": [{
            "fact_id": "f1", "key": "history.advance.received", "value": amount,
            "read_state": "READ", "raw_text": str(amount),
            "evidence": {"page": 1, "quote": str(amount)},
        }]})
        facts.extend(reader._parse_extract(content, source, page, []))
    run_input, _, _ = b.run_input(job="B3")
    report = evaluate(run_input, facts, [])
    assert len({o.fact_id for o in facts}) == 2
    assert report.components.a.value is None  # differing values are still a conflict
    issue = next(i for i in report.issues if i.issue_id == "I-CONTRADICTION")
    assert all(o.fact_id in issue.refs for o in facts)


def test_duplicate_model_fact_id_in_one_output_still_rejected(tmp_path):
    reader = make_reader(tmp_path)
    source = write_source(tmp_path, "one.png", png_bytes(), "image/png")
    field = {"fact_id": "f1", "key": "history.advance.received", "value": 2000000,
             "read_state": "READ", "raw_text": "2000000", "evidence": {"page": 1}}
    with pytest.raises(DomainError) as error:
        reader._parse_extract(json.dumps({"fields": [field, field]}), source, 1, [])
    assert error.value.code == "PROVIDER_OUTPUT_INVALID"


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


def test_usage_nested_token_details_are_traced_not_rejected(tmp_path):
    """Real APIs nest ``*_tokens_details`` objects inside ``usage``.

    A raw provider ``usage`` carrying nested detail objects must not crash the
    run: the trace records the nested counts instead of a Pydantic failure that
    would mark the whole run FAILED.
    """
    ocr_pages = [{"index": 0, "markdown": "Tổng: 5.000.000"}]
    nested_usage = {
        "prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30,
        "prompt_tokens_details": {"cached_tokens": 512},
        "completion_tokens_details": {"reasoning_tokens": 4},
    }
    extract = xkiro_body(fields=[], usage=nested_usage)
    reader = make_reader(tmp_path, ocr_transport(ocr_pages, usage=nested_usage),
                         scripted_transport([extract], []))
    source = write_source(tmp_path, "hoa-don.png", png_bytes(), "image/png")
    reader.read(source, [], budget())
    usages = [entry.usage for entry in reader.trace_entries() if entry.usage]
    assert len(usages) == 2  # OCR + extract both traced, none rejected
    for usage in usages:
        assert usage["total_tokens"] == 30
        assert usage["prompt_tokens_details"] == {"cached_tokens": 512}


def test_usage_non_numeric_values_are_dropped_not_fatal(tmp_path):
    """A stray non-numeric usage value is dropped, never fatal to the run."""
    ocr_pages = [{"index": 0, "markdown": "text"}]
    extract = xkiro_body(fields=[], usage={
        "total_tokens": 7, "weird": "not-a-number",
        "prompt_tokens_details": {"cached_tokens": 3},
    })
    reader = make_reader(tmp_path, ocr_transport(ocr_pages, usage={"total_tokens": 7}),
                         scripted_transport([extract], []))
    source = write_source(tmp_path, "hoa-don.png", png_bytes(), "image/png")
    reader.read(source, [], budget())
    for entry in reader.trace_entries():
        if entry.usage:
            assert entry.usage["total_tokens"] == 7
            assert "weird" not in entry.usage


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


# --- B3 v1 key grammar và prompt --------------------------------------------

def test_b3_keys_select_b3_extract_prompt(tmp_path, monkeypatch):
    import invoice_referee.settlement.reader as reader_module

    captured: list[str] = []
    original_load = reader_module.load_prompt

    def spy_load_prompt(name):
        captured.append(name)
        return original_load(name)

    monkeypatch.setattr(reader_module, "load_prompt", spy_load_prompt)
    reader = make_reader(tmp_path, ocr_transport([{"index": 0,
                                                   "markdown": "text"}]),
                         scripted_transport([xkiro_body(fields=[])], []))
    source = write_source(tmp_path, "de-nghi.png", png_bytes(), "image/png")
    reader.read(source, ["document.role", "advance."], budget())
    assert captured == ["settlement-b3-extract.txt"]


def test_b7_keys_keep_shared_extract_prompt(tmp_path, monkeypatch):
    import invoice_referee.settlement.reader as reader_module

    captured: list[str] = []
    original_load = reader_module.load_prompt

    def spy_load_prompt(name):
        captured.append(name)
        return original_load(name)

    monkeypatch.setattr(reader_module, "load_prompt", spy_load_prompt)
    reader = make_reader(tmp_path, ocr_transport([{"index": 0,
                                                   "markdown": "text"}]),
                         scripted_transport([xkiro_body(fields=[])], []))
    source = write_source(tmp_path, "hoa-don.png", png_bytes(), "image/png")
    reader.read(source, ["expense."], budget())
    assert captured == ["settlement-extract.txt"]


def test_fake_reader_filters_b3_grammar_keys(tmp_path):
    ledger = (
        "fact X1 document.role FORECAST\n"
        "fact X2 forecast.total 8000000\n"
        "fact X3 payment.TX-9.amount 100\n"
    )
    source = write_source(tmp_path, "du-toan.txt", ledger.encode(),
                          "text/plain", source_id="S-b3ledger")
    reader = StructuredLedgerReader(tmp_path)
    observations = reader.read(
        source, ["document.role", "person.", "trip.", "advance.", "forecast."],
        budget())
    keys = {o.key for o in observations}
    assert keys == {"document.role", "forecast.total"}


# --- B3 v1 extraction contract: concrete trip fields, not prefixes ------------

def _b3_extract_payload(captured: list[dict]) -> dict:
    """The user payload sent to the model, decoded from the chat request."""
    request = captured[0]
    return json.loads(request["messages"][1]["content"])


def test_b3_keys_are_concrete_scalar_fields_not_prefixes():
    # trip./person./advance. prefix thô không phải field dữ liệu: model không
    # thể trả "trip." — nó phải thấy trip.destination/trip.purpose cụ thể.
    assert "trip.destination" in B3_V1_KEYS
    assert "trip.purpose" in B3_V1_KEYS
    assert "trip.start" in B3_V1_KEYS
    assert "trip.end" in B3_V1_KEYS
    assert "person.employee_ref" in B3_V1_KEYS
    assert "person.name" in B3_V1_KEYS
    assert "trip." not in B3_V1_KEYS
    assert "person." not in B3_V1_KEYS
    assert "advance." not in B3_V1_KEYS


def test_b3_extract_request_asks_for_destination_and_purpose(tmp_path):
    ocr_pages = [{"index": 0, "markdown": "Lý do tạm ứng: công tác Hà Nội"}]
    captured: list[dict] = []
    reader = make_reader(tmp_path, ocr_transport(ocr_pages),
                         scripted_transport([xkiro_body(fields=[])], captured))
    source = write_source(tmp_path, "de-nghi.png", png_bytes(), "image/png")
    reader.read(source, B3_V1_KEYS, budget())
    keys = _b3_extract_payload(captured)["keys"]
    assert "trip.destination" in keys
    assert "trip.purpose" in keys
    assert "trip." not in keys


def test_b3_merged_prose_text_reaches_extraction(tmp_path):
    prose = ("Lý do tạm ứng: khảo sát yêu cầu và thống nhất phạm vi triển khai "
             "dự án tại Đà Nẵng từ 2026-10-12 đến 2026-10-13.")
    ocr_pages = [{"index": 0, "markdown": prose}]
    captured: list[dict] = []
    reader = make_reader(tmp_path, ocr_transport(ocr_pages),
                         scripted_transport([xkiro_body(fields=[])], captured))
    source = write_source(tmp_path, "de-nghi.png", png_bytes(), "image/png")
    reader.read(source, B3_V1_KEYS, budget())
    payload = _b3_extract_payload(captured)
    assert "Đà Nẵng" in payload["text"]
    assert "khảo sát yêu cầu" in payload["text"]


def test_omitted_b3_trip_field_is_unclear_not_prefix_or_not_found(tmp_path):
    ocr_pages = [{"index": 0, "markdown": "text"}]
    # Model returns trip.destination but omits trip.purpose entirely.
    extract = xkiro_body(fields=[{
        "key": "trip.destination", "raw_text": "Đà Nẵng",
        "read_state": "READ", "value": "Đà Nẵng",
        "evidence": {"page": 1, "quote": "Đà Nẵng"}}])
    reader = make_reader(tmp_path, ocr_transport(ocr_pages),
                         scripted_transport([extract], []))
    source = write_source(tmp_path, "de-nghi.png", png_bytes(), "image/png")
    observations = reader.read(source, B3_V1_KEYS, budget())
    by_key = {o.key: o for o in observations}
    # No fabricated prefix pseudo-field.
    assert "trip." not in by_key
    assert "person." not in by_key
    assert "forecast." not in by_key
    # Omitted concrete field → UNCLEAR, never NOT_FOUND.
    assert by_key["trip.purpose"].read_state == "UNCLEAR"
    assert by_key["trip.purpose"].value is None
    # Extracted concrete field kept as READ.
    assert by_key["trip.destination"].read_state == "READ"
    assert by_key["trip.destination"].value == "Đà Nẵng"


def test_explicit_not_found_is_kept_distinct_from_unclear(tmp_path):
    ocr_pages = [{"index": 0, "markdown": "text"}]
    extract = xkiro_body(fields=[{
        "key": "trip.destination", "raw_text": None,
        "read_state": "NOT_FOUND", "value": None,
        "evidence": {"page": 1, "quote": ""}}])
    reader = make_reader(tmp_path, ocr_transport(ocr_pages),
                         scripted_transport([extract], []))
    source = write_source(tmp_path, "de-nghi.png", png_bytes(), "image/png")
    observations = reader.read(source, B3_V1_KEYS, budget())
    by_key = {o.key: o for o in observations}
    assert by_key["trip.destination"].read_state == "NOT_FOUND"


def test_ambiguous_destination_stays_unclear(tmp_path):
    ocr_pages = [{"index": 0, "markdown": "text"}]
    extract = xkiro_body(fields=[{
        "key": "trip.destination", "raw_text": "Hà Nội / Đà Nẵng",
        "read_state": "UNCLEAR", "value": None,
        "evidence": {"page": 1, "quote": "Hà Nội / Đà Nẵng"}}])
    reader = make_reader(tmp_path, ocr_transport(ocr_pages),
                         scripted_transport([extract], []))
    source = write_source(tmp_path, "de-nghi.png", png_bytes(), "image/png")
    observations = reader.read(source, B3_V1_KEYS, budget())
    destination = next(o for o in observations if o.key == "trip.destination")
    assert destination.read_state == "UNCLEAR"
    assert destination.value is None


def test_b3_extract_prompt_guides_merged_prose_trip_fields():
    from invoice_referee.settlement.reader import load_prompt

    prompt = load_prompt("settlement-b3-extract.txt")
    # Must name the concrete scalar keys the backend needs.
    assert "trip.destination" in prompt
    assert "trip.purpose" in prompt
    assert "trip.start" in prompt
    assert "trip.end" in prompt
    # Must tell the model to read from merged prose, not a dedicated label.
    assert "Lý do tạm ứng" in prompt or "Nội dung công tác" in prompt
    # Must forbid inferring the place from company address / a cost row.
    assert "địa chỉ công ty" in prompt
    # Keep the "no guessing / null when unclear" contract.
    assert "không đoán" in prompt
