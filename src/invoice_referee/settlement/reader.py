"""Settlement readers (W03): provider-backed reading behind a small protocol.

Split of responsibility (System §S1/S2/S4):

- The reader only produces observations/relations with refs, raw text, locators
  and usage. It never computes reports or approvals.
- Direct parsing (structured ledger text, CSV ledger contract, native PDF
  text) happens without any provider call; provider calls are reserved in the
  run budget and traced with requested/returned model ids and usage (usage
  missing stays ``None``, never a fabricated 0).
- Output is validated: invalid JSON retries exactly once per extraction unit;
  truncated output, timeouts and transport failures are technical failures —
  they never become NOT_FOUND or a fabricated value. Money values that arrive
  as strings stay UNCLEAR with the raw text; no guessed conversion.
- PDFium runs behind one process-wide lock (not thread-safe); page and pixel
  envelopes are checked before any resource is spent.

Provider endpoints/config v0 (System §S5): Mistral OCR ``/ocr``; xkiro is an
OpenAI-compatible gateway at ``https://api.xkiro.com/v1`` with a full vendor
model id and ``reasoning_effort: none``; the response ``model`` is recorded
separately from the requested model (gateway routing is not upstream proof).
"""
from __future__ import annotations

import base64
import csv
import io
import json
import threading
import time
from pathlib import Path
from typing import Any, Protocol

import httpx

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import (
    CallTrace,
    Observation,
    Relation,
    RunBudget,
    RunInput,
    SourceRecord,
)

PROMPTS_DIR = Path(__file__).parents[1] / "extraction" / "prompts"

MISTRAL_OCR_BASE_URL = "https://api.mistral.ai/v1"
MISTRAL_OCR_MODEL = "mistral-ocr-latest"
XKIRO_BASE_URL = "https://api.xkiro.com/v1"
XKIRO_MODEL = "mistralai/mistral-small-2603"

OCR_TIMEOUT_SECONDS = 60.0
XKIRO_TIMEOUT_SECONDS = 80.0
EXTRACT_MAX_OUTPUT_TOKENS = 3072
MATCH_MAX_OUTPUT_TOKENS = 2048

MAX_PIXELS_PER_REPRESENTATION = 24_000_000
MAX_PDF_PAGES_PER_FILE = 20
MAX_PDF_IMAGE_PAGES_PER_RUN = 40
MAX_ATTEMPTS_PER_UNIT = 2

# pypdfium2 is not thread-safe: one process-wide executor (System §S5).
_PDFIUM_LOCK = threading.Lock()


def is_per_source_error(code: str) -> bool:
    """Technical, per-source failures: keep partial output, continue the run."""
    return code in {
        "PROVIDER_FAILED", "PROVIDER_OUTPUT_INVALID", "PROVIDER_OUTPUT_TRUNCATED",
        "SOURCE_UNREADABLE", "REPRESENTATION_LIMIT", "SOURCE_PAGE_LIMIT",
        "RUN_PAGE_LIMIT", "LEDGER_LINE_INVALID", "CSV_CONTRACT_INVALID",
    }


class Reader(Protocol):
    """Reads facts from one source and proposes links between them."""

    mode: str

    def read(self, source: SourceRecord, keys: list[str],
             budget: RunBudget) -> list[Observation]: ...

    def match(self, run_input: RunInput, candidates: list[Observation],
              budget: RunBudget) -> list[Relation]: ...

    def reset_trace(self) -> None: ...

    def trace_entries(self) -> list[CallTrace]: ...


# --- Structured ledger v1 (direct parse, no provider) ------------------------

LEDGER_DIRECTIVES = ("fact ", "unclear ", "rel ")


def looks_like_ledger(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped.startswith(LEDGER_DIRECTIVES)
    return False


def parse_ledger_line(line: str, source_id: str,
                      line_number: int) -> Observation | None:
    parts = line.split()
    locator = f"line {line_number}"
    if parts[0] == "fact" and len(parts) >= 4:
        fact_id, key, raw_value = parts[1], parts[2], " ".join(parts[3:])
        value: int | str
        try:
            value = int(raw_value)
        except ValueError:
            value = raw_value
        return Observation(
            fact_id=fact_id, key=key, raw=raw_value, read_state="READ",
            value=value, source_id=source_id, row=line_number, locator=locator,
            basis=f"structured ledger {source_id} {locator}",
        )
    if parts[0] == "unclear" and len(parts) >= 4:
        fact_id, key = parts[1], parts[2]
        raw_text = " ".join(parts[3:])
        return Observation(
            fact_id=fact_id, key=key, raw=raw_text, read_state="UNCLEAR",
            value=None, source_id=source_id, row=line_number, locator=locator,
            basis=f"structured ledger {source_id} {locator}: không đọc được",
            usability="UNUSABLE",
        )
    if parts[0] == "rel" and len(parts) >= 5:
        relation_id, kind, from_id, to_id = parts[1], parts[2], parts[3], parts[4]
        portion: int | None = None
        if "portion" in parts:
            index = parts.index("portion")
            if index + 1 < len(parts):
                portion = int(parts[index + 1])
        return Observation(
            fact_id=relation_id, key="relation", raw=line, read_state="READ",
            value={"kind": kind, "from": from_id, "to": to_id,
                   "portion_vnd": portion},
            source_id=source_id, row=line_number, locator=locator,
            basis=f"structured ledger {source_id} {locator}",
        )
    raise DomainError(
        "LEDGER_LINE_INVALID",
        f"Dòng ledger không hợp lệ tại {source_id} {locator}: {line}",
    )


class StructuredLedgerReader:
    """Fake/offline reader for the documented synthetic ledger format."""

    mode = "FAKE_OR_REPLAY"

    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = Path(artifact_root)
        self._trace: list[CallTrace] = []

    def reset_trace(self) -> None:
        self._trace = []

    def trace_entries(self) -> list[CallTrace]:
        return list(self._trace)

    def read(self, source: SourceRecord, keys: list[str],
             budget: RunBudget) -> list[Observation]:
        budget.reserve_call()  # một lần đọc nguồn = một call trong budget
        text = self._load_text(source)
        if source.media_type == "text/csv":
            return [o for o in parse_csv_ledger(text, source.id)
                    if _wanted(o.key, keys)]
        return self.parse_text(text, source.id, keys)

    def _load_text(self, source: SourceRecord) -> str:
        path = self.artifact_root / source.original_path
        try:
            return path.read_text(encoding="utf-8-sig")
        except OSError as error:
            raise DomainError(
                "SOURCE_UNREADABLE",
                f"Không đọc được nguồn {source.id}: {error}",
            ) from error

    @staticmethod
    def parse_text(text: str, source_id: str,
                   keys: list[str]) -> list[Observation]:
        observations: list[Observation] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            observation = parse_ledger_line(stripped, source_id, line_number)
            if observation is not None and _wanted(observation.key, keys):
                observations.append(observation)
        return observations

    def match(self, run_input: RunInput, candidates: list[Observation],
              budget: RunBudget) -> list[Relation]:
        relations: list[Relation] = []
        for observation in candidates:
            if observation.key != "relation" or observation.read_state != "READ":
                continue
            if not isinstance(observation.value, dict):
                continue
            payload = observation.value
            relations.append(Relation(
                relation_id=observation.fact_id,
                kind=payload["kind"],  # type: ignore[arg-type]
                from_id=payload["from"], to_id=payload["to"],
                portion_vnd=payload.get("portion_vnd"),
                supporting_refs=[observation.source_id],
                status="ESTABLISHED",
                reason=f"structured ledger ghép trực tiếp ({observation.locator})",
            ))
        return relations


def _key_matches(key: str, requested: str) -> bool:
    """One requested key matches one returned key.

    Three shapes (System §S2 key grammar):
    - concrete scalar (``trip.destination``): exact match only.
    - prefix family (``expense.`` / ``payment.`` / ``forecast.`` in B7): a
      trailing-dot namespace matches any key under it.
    - row template (``forecast.row.<row_id>.description``): ``<row_id>`` is a
      document-local placeholder, so any non-empty row id matches.
    """
    if "<row_id>" in requested:
        prefix, suffix = requested.split("<row_id>", 1)
        return (key.startswith(prefix) and key.endswith(suffix)
                and len(key) > len(prefix) + len(suffix))
    if requested.endswith("."):
        return key.startswith(requested)
    return key == requested


def _wanted(key: str, keys: list[str]) -> bool:
    if not keys:
        return True
    return any(_key_matches(key, requested) for requested in keys)


# --- CSV ledger contract (direct parse, System §S8) ---------------------------

CSV_COLUMNS = ["source_record_ref", "event_kind", "payer_ref", "payee_ref",
               "gross_amount_vnd", "currency", "event_at", "reported_status"]

# v0 side mapping theo event_kind: công ty giải ngân ra phía nhân viên;
# nhân viên nộp lại về phía công ty. Ref gốc giữ trong raw, không đoán thêm.
_EMPLOYEE_INBOUND_KINDS = {"DISBURSEMENT", "REIMBURSEMENT"}


def parse_csv_ledger(text: str, source_id: str) -> list[Observation]:
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    if any(name not in fieldnames for name in CSV_COLUMNS):
        raise DomainError(
            "CSV_CONTRACT_INVALID",
            f"CSV {source_id} thiếu các cột hợp đồng {CSV_COLUMNS}.",
        )
    observations: list[Observation] = []
    for row_number, row in enumerate(reader, start=2):
        ref = (row.get("source_record_ref") or "").strip()
        if not ref:
            continue  # dòng trống không tạo absence giả
        event_kind = (row.get("event_kind") or "").strip().upper()
        inbound = event_kind in _EMPLOYEE_INBOUND_KINDS
        payer = "COMPANY" if inbound else "EMPLOYEE"
        payee = "EMPLOYEE" if inbound else "COMPANY"
        reported = (row.get("reported_status") or "").strip().lower()
        status = "RECEIVED" if reported in {"received", "completed", "done"} \
            else "PENDING"
        raw_amount = (row.get("gross_amount_vnd") or "").strip()
        try:
            amount = int(raw_amount)
        except ValueError:
            amount = None
        common = {"source_id": source_id, "row": row_number,
                  "locator": f"row {row_number}",
                  "basis": f"CSV ledger {source_id} row {row_number}"}
        observations.extend([
            Observation(fact_id=f"{ref}-amount", key=f"payment.{ref}.amount",
                        raw=raw_amount,
                        read_state="READ" if amount is not None else "UNCLEAR",
                        value=amount, **common),
            Observation(fact_id=f"{ref}-payer", key=f"payment.{ref}.payer",
                        raw=f"event_kind={event_kind}", read_state="READ",
                        value=payer, **common),
            Observation(fact_id=f"{ref}-payee", key=f"payment.{ref}.payee",
                        raw=f"event_kind={event_kind}", read_state="READ",
                        value=payee, **common),
            Observation(fact_id=f"{ref}-status", key=f"payment.{ref}.status",
                        raw=f"reported_status={reported}", read_state="READ",
                        value=status, **common),
        ])
    return observations


# --- Provider clients ---------------------------------------------------------

class MistralOCRClient:
    """Thin transport for the Mistral OCR endpoint (no SDK)."""

    def __init__(self, api_key: str, base_url: str = MISTRAL_OCR_BASE_URL,
                 model: str = MISTRAL_OCR_MODEL,
                 timeout: float = OCR_TIMEOUT_SECONDS,
                 transport: httpx.BaseTransport | None = None) -> None:
        if not api_key:
            raise DomainError("CONFIG_NOT_ACTIVE",
                              "MISTRAL_API_KEY chưa được cấu hình.")
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url,
                            headers={"Authorization": f"Bearer {self.api_key}"},
                            transport=self._transport)

    def ocr_document(self, document: dict[str, Any],
                     timeout: float) -> dict[str, Any]:
        body = {"model": self.model, "document": document, "include_blocks": True}
        with self._client() as client:
            try:
                response = client.post("/ocr", json=body, timeout=timeout)
                response.raise_for_status()
                return response.json()
            except DomainError:
                raise
            except Exception as error:  # noqa: BLE001 — any transport failure
                raise DomainError(
                    "PROVIDER_FAILED",
                    f"OCR call thất bại kỹ thuật: {type(error).__name__}: {error}",
                ) from error


class XkiroClient:
    """OpenAI-compatible JSON chat client (full vendor model id, effort none)."""

    def __init__(self, api_key: str, base_url: str = XKIRO_BASE_URL,
                 model: str = XKIRO_MODEL, timeout: float = XKIRO_TIMEOUT_SECONDS,
                 transport: httpx.BaseTransport | None = None) -> None:
        if not api_key:
            raise DomainError("CONFIG_NOT_ACTIVE", "XKIRO_API_KEY chưa được cấu hình.")
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url,
                            headers={"Authorization": f"Bearer {self.api_key}"},
                            transport=self._transport)

    def chat_json(self, system_prompt: str, user_payload: dict[str, Any],
                  max_tokens: int, timeout: float) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(
                    user_payload, ensure_ascii=False, sort_keys=True)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": max_tokens,
            "reasoning_effort": "none",
        }
        with self._client() as client:
            try:
                response = client.post("/chat/completions", json=body,
                                        timeout=timeout)
                response.raise_for_status()
                data = response.json()
            except DomainError:
                raise
            except Exception as error:  # noqa: BLE001
                raise DomainError(
                    "PROVIDER_FAILED",
                    f"xkiro call thất bại kỹ thuật: {type(error).__name__}: {error}",
                ) from error
        try:
            content = data["choices"][0]["message"]["content"]
            finish_reason = data["choices"][0].get("finish_reason")
        except (KeyError, IndexError, TypeError) as error:
            raise DomainError(
                "PROVIDER_OUTPUT_INVALID",
                f"xkiro response thiếu choices/content: {error}",
            ) from error
        usage = data.get("usage")
        return {
            "content": content,
            "finish_reason": finish_reason,
            "requested_model": self.model,
            "response_model": data.get("model") if isinstance(
                data.get("model"), str) else None,
            "usage": usage if isinstance(usage, dict) else None,
        }


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def _is_money_key(key: str) -> bool:
    from invoice_referee.settlement.rules import MONEY_KEY_SUFFIXES

    return any(key.endswith(suffix) or key == suffix
               for suffix in MONEY_KEY_SUFFIXES)


def _remaining_timeout(budget: RunBudget, default: float) -> float:
    return max(0.0, min(default, budget.deadline - time.monotonic()))


# --- Live settlement reader ---------------------------------------------------

class SettlementReader:
    """Provider-backed reader: route by content, budget-bounded, traced."""

    mode = "LIVE"

    def __init__(self, artifact_root: Path, ocr: MistralOCRClient,
                 xkiro: XkiroClient,
                 max_attempts: int = MAX_ATTEMPTS_PER_UNIT) -> None:
        self.artifact_root = Path(artifact_root)
        self.ocr = ocr
        self.xkiro = xkiro
        self.max_attempts = max_attempts
        self._trace: list[CallTrace] = []
        self._attempts: dict[str, int] = {}
        self._run_pages = 0
        self._call_seq = 0

    # --- trace bookkeeping ----------------------------------------------------

    def reset_trace(self) -> None:
        self._trace = []
        self._attempts = {}
        self._run_pages = 0
        self._call_seq = 0

    def trace_entries(self) -> list[CallTrace]:
        return list(self._trace)

    def attempts_for(self, source_id: str) -> int:
        return self._attempts.get(source_id, 0)

    def _count_attempt(self, key: str) -> None:
        self._attempts[key] = self._attempts.get(key, 0) + 1

    def _record(self, stage: str, source_id: str | None, ok: bool, *,
                requested_model: str | None = None,
                response_model: str | None = None,
                usage: dict[str, int | None] | None = None,
                error_code: str | None = None, detail: str | None = None,
                duration_ms: int = 0) -> None:
        self._call_seq += 1
        self._trace.append(CallTrace(
            call_id=f"T-{self._call_seq}", stage=stage, source_id=source_id,
            requested_model=requested_model, response_model=response_model,
            usage=usage, ok=ok, error_code=error_code, detail=detail,
            duration_ms=duration_ms,
        ))

    # --- reading ---------------------------------------------------------------

    def read(self, source: SourceRecord, keys: list[str],
             budget: RunBudget) -> list[Observation]:
        content = self._load_bytes(source)
        media_type = source.media_type
        if media_type == "text/csv":
            text = content.decode("utf-8-sig")
            return [o for o in parse_csv_ledger(text, source.id)
                    if _wanted(o.key, keys)]
        if media_type in {"text/plain", "text/markdown"}:
            text = content.decode("utf-8-sig")
            if looks_like_ledger(text):
                return [o for o in StructuredLedgerReader.parse_text(
                    text, source.id, keys)]
            return self._extract_from_text(source, text, None, keys, budget)
        if media_type in {"image/jpeg", "image/png"}:
            self._check_pixels(content, source)
            return self._read_image(source, content, keys, budget)
        if media_type == "application/pdf":
            return self._read_pdf(source, content, keys, budget)
        raise DomainError(
            "SOURCE_UNREADABLE",
            f"Không có đường đọc cho nguồn {source.id} ({media_type}).",
        )

    def _load_bytes(self, source: SourceRecord) -> bytes:
        path = self.artifact_root / source.original_path
        try:
            return path.read_bytes()
        except OSError as error:
            raise DomainError(
                "SOURCE_UNREADABLE",
                f"Không đọc được nguồn {source.id}: {error}",
            ) from error

    @staticmethod
    def _check_pixels(content: bytes, source: SourceRecord) -> None:
        from PIL import Image

        with Image.open(io.BytesIO(content)) as image:
            pixels = image.width * image.height
        if pixels > MAX_PIXELS_PER_REPRESENTATION:
            raise DomainError(
                "REPRESENTATION_LIMIT",
                f"Ảnh {source.id} vượt giới hạn {MAX_PIXELS_PER_REPRESENTATION} "
                f"pixels/representation; không downsample làm mất field.",
            )

    def _read_image(self, source: SourceRecord, content: bytes,
                    keys: list[str], budget: RunBudget, *,
                    source_page: int | None = None) -> list[Observation]:
        budget.reserve_call()
        # PDF pages are rendered as PNG; the retained source is still a PDF.
        image_media_type = "image/png" if source_page is not None else source.media_type
        document = {
            "type": "image_url",
            "image_url": f"data:{image_media_type};base64,"
                         f"{base64.b64encode(content).decode('ascii')}",
        }
        started = time.monotonic()
        try:
            payload = self.ocr.ocr_document(
                document, _remaining_timeout(budget, self.ocr.timeout))
            pages = self._validated_pages(payload)
            if source_page is not None and len(pages) != 1:
                raise DomainError("PROVIDER_OUTPUT_INVALID",
                                  "OCR một trang PDF phải trả đúng một trang ảnh.")
        except DomainError as error:
            self._record("ocr", source.id, False, requested_model=self.ocr.model,
                         error_code=error.code, detail=error.message,
                         duration_ms=int((time.monotonic() - started) * 1000))
            raise
        self._record("ocr", source.id, True, requested_model=self.ocr.model,
                     response_model=payload.get("model") if isinstance(
                         payload.get("model"), str) else None,
                     usage=payload.get("usage") if isinstance(
                         payload.get("usage"), dict) else None,
                     duration_ms=int((time.monotonic() - started) * 1000))
        if source_page is None:
            self._count_run_pages(len(pages), source)
        observations: list[Observation] = []
        # trang chưa đọc là technical/capability, không NOT_FOUND (System §S2)
        for page in pages:
            observations.extend(self._extract_from_text(
                source, page["markdown"],
                source_page if source_page is not None else page["index"] + 1,
                keys, budget))
        return observations

    def _read_pdf(self, source: SourceRecord, content: bytes,
                  keys: list[str], budget: RunBudget) -> list[Observation]:
        import pypdfium2 as pdfium

        with _PDFIUM_LOCK:
            try:
                pdf = pdfium.PdfDocument(content)
            except Exception as error:  # noqa: BLE001
                raise DomainError(
                    "SOURCE_UNREADABLE",
                    f"PDF {source.id} không mở được: {error}",
                ) from error
            page_count = len(pdf)
            if page_count > MAX_PDF_PAGES_PER_FILE:
                raise DomainError(
                    "SOURCE_PAGE_LIMIT",
                    f"PDF {source.id} có {page_count} trang, vượt giới hạn "
                    f"{MAX_PDF_PAGES_PER_FILE}; không truncate rồi báo đủ.",
                )
            self._count_run_pages(page_count, source)
            pages_text: list[tuple[int, str]] = []
            pages_image: list[tuple[int, bytes]] = []
            for index in range(page_count):
                page = pdf[index]
                text = self._pdf_page_text(page)
                if len(text.strip()) >= 20:
                    pages_text.append((index + 1, text))
                else:
                    pages_image.append((index + 1, self._render_page(page)))
            pdf.close()
        observations: list[Observation] = []
        for page_number, text in pages_text:
            observations.extend(self._extract_from_text(
                source, text, page_number, keys, budget))
        for page_number, image_bytes in pages_image:
            observations.extend(self._read_image(source, image_bytes, keys, budget,
                                                source_page=page_number))
        return observations

    @staticmethod
    def _pdf_page_text(page: Any) -> str:
        text_page = page.get_textpage()
        try:
            return text_page.get_text_range()
        finally:
            text_page.close()

    @staticmethod
    def _render_page(page: Any,
                     max_pixels: int = MAX_PIXELS_PER_REPRESENTATION) -> bytes:
        from PIL import Image

        width, height = page.get_size()
        scale = min(2.0, (max_pixels / (width * height)) ** 0.5) \
            if width * height else 1.0
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil()
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def _count_run_pages(self, pages: int, source: SourceRecord) -> None:
        self._run_pages += pages
        if self._run_pages > MAX_PDF_IMAGE_PAGES_PER_RUN:
            raise DomainError(
                "RUN_PAGE_LIMIT",
                f"Run vượt giới hạn {MAX_PDF_IMAGE_PAGES_PER_RUN} trang "
                f"PDF/ảnh (tại nguồn {source.id}).",
            )

    @staticmethod
    def _validated_pages(payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            raise DomainError("PROVIDER_OUTPUT_INVALID",
                              "OCR response không phải object.")
        pages = payload.get("pages")
        if not isinstance(pages, list) or not pages:
            raise DomainError("PROVIDER_OUTPUT_INVALID",
                              "OCR response thiếu danh sách pages.")
        seen: set[int] = set()
        for page in pages:
            if not isinstance(page, dict):
                raise DomainError("PROVIDER_OUTPUT_INVALID",
                                  "OCR page không phải object.")
            index = page.get("index")
            if isinstance(index, bool) or not isinstance(index, int):
                raise DomainError("PROVIDER_OUTPUT_INVALID",
                                  f"OCR page index không hợp lệ: {index!r}")
            if index in seen:
                raise DomainError("PROVIDER_OUTPUT_INVALID",
                                  f"OCR page index trùng: {index}.")
            seen.add(index)
            if not isinstance(page.get("markdown"), str):
                raise DomainError("PROVIDER_OUTPUT_INVALID",
                                  "OCR page thiếu markdown.")
        return pages

    # --- extraction (xkiro) -----------------------------------------------------

    def _extract_from_text(self, source: SourceRecord, text: str,
                           page: int | None, keys: list[str],
                           budget: RunBudget) -> list[Observation]:
        # B3 v1 dùng grammar riêng (document.role/forecast.row.*...); B7/B3
        # legacy giữ prompt extraction chung.
        prompt = load_prompt(
            "settlement-b3-extract.txt" if "document.role" in keys
            else "settlement-extract.txt")
        payload = {
            "source_id": source.id,
            "filename": source.filename,
            "page": page,
            "keys": keys,
            "text": text[:20000],
        }
        last_error: DomainError | None = None
        for attempt in range(self.max_attempts):
            self._count_attempt(source.id)
            budget.reserve_call()
            started = time.monotonic()
            try:
                result = self.xkiro.chat_json(
                    prompt, payload, EXTRACT_MAX_OUTPUT_TOKENS,
                    _remaining_timeout(budget, self.xkiro.timeout))
            except DomainError as error:
                self._record("extract", source.id, False,
                             requested_model=self.xkiro.model,
                             error_code=error.code, detail=error.message,
                             duration_ms=int((time.monotonic() - started) * 1000))
                if error.code != "PROVIDER_OUTPUT_INVALID" or \
                        attempt == self.max_attempts - 1:
                    raise
                last_error = error
                continue
            if result["finish_reason"] not in {None, "stop"}:
                self._record("extract", source.id, False,
                             requested_model=self.xkiro.model,
                             response_model=result["response_model"],
                             usage=result["usage"],
                             error_code="PROVIDER_OUTPUT_TRUNCATED",
                             detail=f"finish_reason={result['finish_reason']}",
                             duration_ms=int((time.monotonic() - started) * 1000))
                raise DomainError(
                    "PROVIDER_OUTPUT_TRUNCATED",
                    "Output bị cắt (finish_reason != stop); không dùng JSON cắt.",
                )
            try:
                observations = self._parse_extract(result["content"], source,
                                                   page, keys)
            except DomainError as error:
                self._record("extract", source.id, False,
                             requested_model=self.xkiro.model,
                             response_model=result["response_model"],
                             usage=result["usage"],
                             error_code=error.code, detail=error.message,
                             duration_ms=int((time.monotonic() - started) * 1000))
                if error.code != "PROVIDER_OUTPUT_INVALID" or \
                        attempt == self.max_attempts - 1:
                    raise
                last_error = error
                continue
            self._record("extract", source.id, True,
                         requested_model=result["requested_model"],
                         response_model=result["response_model"],
                         usage=result["usage"],
                         duration_ms=int((time.monotonic() - started) * 1000))
            return observations
        raise last_error or DomainError("PROVIDER_OUTPUT_INVALID",
                                        "extract không thành công.")

    def _parse_extract(self, content: str, source: SourceRecord,
                       page: int | None, keys: list[str]) -> list[Observation]:
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError) as error:
            raise DomainError("PROVIDER_OUTPUT_INVALID",
                              f"Extract output không phải JSON: {error}") from error
        if not isinstance(parsed, dict) or not isinstance(parsed.get("fields"),
                                                          list):
            raise DomainError("PROVIDER_OUTPUT_INVALID",
                              "Extract output thiếu danh sách fields.")
        location_id = f"{source.id}-p{page}" if page is not None else source.id
        observations: list[Observation] = []
        seen_fact_ids: set[str] = set()
        for entry in parsed["fields"]:
            if not isinstance(entry, dict):
                raise DomainError("PROVIDER_OUTPUT_INVALID",
                                  "Field không phải object.")
            local_id = entry.get("fact_id")
            if local_id:
                if not isinstance(local_id, str):
                    raise DomainError("PROVIDER_OUTPUT_INVALID",
                                      "Fact ID của model phải là chuỗi.")
                if local_id in seen_fact_ids:
                    raise DomainError("PROVIDER_OUTPUT_INVALID",
                                      f"Fact ID trùng trong output: {local_id}.")
                seen_fact_ids.add(local_id)
            # Model IDs belong to one response, not the whole dossier.
            fact_id = f"{location_id}-field-{len(observations) + 1}"
            key = entry.get("key")
            if not isinstance(key, str) or not key:
                raise DomainError("PROVIDER_OUTPUT_INVALID",
                                  "Field thiếu key.")
            read_state = entry.get("read_state")
            if read_state not in {"READ", "NOT_FOUND", "UNCLEAR"}:
                raise DomainError("PROVIDER_OUTPUT_INVALID",
                                  f"read_state không hợp lệ: {read_state!r}")
            value = entry.get("value")
            raw = entry.get("raw_text")
            if read_state == "READ" and _is_money_key(key) and \
                    (isinstance(value, bool) or not isinstance(value, int)):
                read_state = "UNCLEAR"  # không đoán chuyển separator/tỷ giá
                value = None
            evidence = entry.get("evidence") if isinstance(
                entry.get("evidence"), dict) else {}
            quote = evidence.get("quote") if isinstance(
                evidence.get("quote"), str) else None
            evidence_page = evidence.get("page")
            final_page = page if page is not None else (
                evidence_page if isinstance(evidence_page, int) else None)
            locator = f"page {final_page}" if final_page is not None else "n/a"
            basis = (f"{source.filename} {locator}"
                     + (f", trích: {quote}" if quote else ""))
            observations.append(Observation(
                fact_id=fact_id, key=key,
                raw=raw if isinstance(raw, str) else None,
                read_state=read_state, value=value, source_id=source.id,
                page=final_page, locator=locator, basis=basis,
                usability="USABLE" if read_state == "READ" else "UNCERTAIN",
            ))
        # A requested concrete field omitted from output is UNCLEAR — never
        # NOT_FOUND (System §S2): "chưa trả đủ dữ liệu" ≠ "đã tìm không thấy".
        # Prefix families (``expense.``) and row templates
        # (``forecast.row.<row_id>.x``) are grammars, not single fields, so they
        # are never fabricated as pseudo-observations.
        requested = [k for k in keys if "." in k and "<row_id>" not in k
                     and not k.endswith(".")]
        returned = {o.key for o in observations}
        for key in requested:
            if key not in returned:
                observations.append(Observation(
                    fact_id=f"{location_id}-missing-{key}", key=key,
                    raw=None, read_state="UNCLEAR", value=None,
                    source_id=source.id, page=page,
                    locator=f"page {page}" if page is not None else "n/a",
                    basis="không có trong output; không suy NOT_FOUND",
                    usability="UNCERTAIN",
                ))
        return observations

    # --- matching (xkiro) --------------------------------------------------------

    def match(self, run_input: RunInput, candidates: list[Observation],
              budget: RunBudget) -> list[Relation]:
        facts = [o for o in candidates
                 if o.read_state == "READ" and o.key != "relation"]
        if not facts:
            return []
        prompt = load_prompt("settlement-match.txt")
        payload = {
            "work_ref": run_input.submission.work_ref,
            "employee_ref": run_input.submission.employee_ref,
            "candidates": [
                {"fact_id": o.fact_id, "key": o.key, "value": o.value,
                 "source_id": o.source_id}
                for o in facts  # toàn bộ candidates, không fixed top-k
            ],
        }
        self._count_attempt("match")
        budget.reserve_call()
        started = time.monotonic()
        try:
            result = self.xkiro.chat_json(prompt, payload, MATCH_MAX_OUTPUT_TOKENS,
                                          _remaining_timeout(budget,
                                                             self.xkiro.timeout))
        except DomainError as error:
            self._record("match", None, False, requested_model=self.xkiro.model,
                         error_code=error.code, detail=error.message,
                         duration_ms=int((time.monotonic() - started) * 1000))
            raise
        if result["finish_reason"] not in {None, "stop"}:
            raise DomainError(
                "PROVIDER_OUTPUT_TRUNCATED",
                "Match output bị cắt; không dùng JSON cắt.",
            )
        self._record("match", None, True,
                     requested_model=result["requested_model"],
                     response_model=result["response_model"],
                     usage=result["usage"],
                     duration_ms=int((time.monotonic() - started) * 1000))
        try:
            parsed = json.loads(result["content"])
        except (json.JSONDecodeError, TypeError) as error:
            raise DomainError("PROVIDER_OUTPUT_INVALID",
                              f"Match output không phải JSON: {error}") from error
        if not isinstance(parsed, dict) or not isinstance(parsed.get("relations"),
                                                          list):
            raise DomainError("PROVIDER_OUTPUT_INVALID",
                              "Match output thiếu danh sách relations.")
        known_ids = self._entity_ids(facts)
        relations: list[Relation] = []
        seen_ids: set[str] = set()
        for entry in parsed["relations"]:
            if not isinstance(entry, dict):
                raise DomainError("PROVIDER_OUTPUT_INVALID",
                                  "Relation không phải object.")
            relation_id = entry.get("id") or f"RM-{len(relations) + 1}"
            if relation_id in seen_ids:
                raise DomainError("PROVIDER_OUTPUT_INVALID",
                                  f"Relation ID trùng: {relation_id}.")
            seen_ids.add(relation_id)
            kind = entry.get("kind")
            from_id, to_id = entry.get("from"), entry.get("to")
            if kind not in {"EXPENSE_PAYMENT", "SAME_EVENT"}:
                self._record("match", None, False, error_code="UNKNOWN_KIND_FILTERED",
                             detail=f"relation {relation_id} kind={kind!r}")
                continue
            if from_id not in known_ids or to_id not in known_ids:
                # phát hiện và ghi trace, không drop âm thầm (SYS-02)
                self._record("match", None, False,
                             error_code="UNKNOWN_REF_FILTERED",
                             detail=f"relation {relation_id}: {from_id} → {to_id}")
                continue
            portion = entry.get("portion_vnd")
            if portion is not None and (isinstance(portion, bool)
                                        or not isinstance(portion, int)):
                portion = None
            relations.append(Relation(
                relation_id=relation_id, kind=kind, from_id=from_id,
                to_id=to_id, portion_vnd=portion,
                supporting_refs=[entry.get("supporting")] if isinstance(
                    entry.get("supporting"), str) else [],
                status="PROPOSED",
                reason=entry.get("reason") if isinstance(
                    entry.get("reason"), str) else "",
            ))
        return relations

    @staticmethod
    def _entity_ids(facts: list[Observation]) -> set[str]:
        ids: set[str] = set()
        for observation in facts:
            parts = observation.key.split(".")
            if len(parts) >= 3 and parts[0] in {"expense", "payment"}:
                ids.add(parts[1])
        return ids
