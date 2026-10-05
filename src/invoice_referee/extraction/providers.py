"""Provider boundary: OCR transport, per-document analysis, cross-source (T05).

Ledger §3.2 interface:

- ``Providers.ocr(evidence) -> RawOcr``      — Mistral OCR, one evidence per call.
- ``Providers.analyze(request) -> DocumentFacts`` — one Kimi AnalyzeDocument call.
- ``Providers.cross_source(bundle) -> MappingProposal`` — one Kimi ProposeCrossSource call.
- ``Providers.identities`` records the identity of every invocation/repair.
- ``registry_from_ocr(evidence, raw) -> SourceRegistry`` — build the citable
  source registry from the OCR response (pages/blocks/words/scores).

``FakeProviders`` mirrors the same signatures with ``.calls`` and is subclassable
to emit slow/malformed responses. ``LiveProviders`` implements the verified
Mistral + Kimi APIs with a thin ``httpx`` transport (the only runtime dependency
they need); tests inject a fake client to prove the exact request shape without
network.

Repair budget (System §4): ONE shared JSON/contract repair per invocation; the
cross-source coverage proposal may consume ONE additional repair invocation. The
loop never repeats until the model says "valid" — a second malformed/invalid
response is a technical ``INVALID_ANALYSIS``.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import signal
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from invoice_referee.domain.models import (
    AnalysisRequest,
    DocumentFacts,
    DomainError,
    Evidence,
    EvidenceBundle,
    MappingProposal,
    RawOcr,
    SourceBlock,
    SourceRegistry,
    SourceWord,
    StageIdentity,
)
from invoice_referee.extraction.validation import (
    REPAIR_BUDGET,
    check_ref,
    shared_repair_allowed,
    validate_document,
)

# --- Verified provider identities (docs/evidence/provider-contract.md) ---------
# Defaults verified 2026-10-05; overridable via environment (see LiveProviders).

MISTRAL_OCR_MODEL = 'mistral-ocr-latest'
MISTRAL_BASE_URL = 'https://api.mistral.ai/v1'
KIMI_MODEL = 'kimi-k2.6'
KIMI_BASE_URL = 'https://api.moonshot.ai/v1'

ANALYZE_PROMPT_VERSION = 'analyze-v1'
ANALYZE_SCHEMA_VERSION = 'document-facts-v1'
CROSS_PROMPT_VERSION = 'cross-source-v1'
CROSS_SCHEMA_VERSION = 'mapping-proposal-v1'

PROMPT_DIR = Path(__file__).resolve().parent / 'prompts'
DEFAULT_TIMEOUT_SECONDS = 60.0


def _env_default(name: str, default: str) -> str:
    """Read a pinned provider value from the environment, else the verified default."""
    value = os.environ.get(name)
    return value if value else default


# --- Public payload builders (serialized per-document request, no prose) -------

def analysis_payload(request: AnalysisRequest) -> dict[str, Any]:
    """Payload for AnalyzeDocument: ONE evidence's registry + role + hints only.

    Never carries employee prose, expected labels, case IDs or other documents.
    ``threshold_version`` is included so a B2 threshold change alters the hashed
    analyze request (ledger §3.1: threshold/registry/role/hints are part of the
    hashed request).
    """
    return {
        'evidence_id': request.evidence.id,
        'role': request.evidence.role,
        'source_registry': request.registry.model_dump(mode='json'),
        'required_fields': request.required_fields,
        'threshold_version': request.threshold_version,
        'schema_version': ANALYZE_SCHEMA_VERSION,
    }


def cross_source_payload(bundle: EvidenceBundle) -> dict[str, Any]:
    """Payload for ProposeCrossSource: usable facts + refs only, no prose."""
    return {
        'documents': [doc.model_dump(mode='json') for doc in bundle.documents],
        'schema_version': CROSS_SCHEMA_VERSION,
    }


# --- Providers interface -------------------------------------------------------

class Providers(ABC):
    """Boundary the pipeline depends on. Adapters return facts/proposals only."""

    identities: list[StageIdentity]

    @abstractmethod
    def ocr(self, evidence: Evidence) -> RawOcr: ...

    @abstractmethod
    def analyze(self, request: AnalysisRequest) -> DocumentFacts: ...

    @abstractmethod
    def cross_source(self, bundle: EvidenceBundle) -> MappingProposal: ...


# --- OCR response -> source registry -------------------------------------------

def registry_from_ocr(evidence: Evidence, raw: RawOcr) -> SourceRegistry:
    """Build a citable registry from a Mistral OCR response.

    One block per page; words come from ``word_confidence_scores`` (native
    per-word signal, nested under ``page.confidence_scores`` when
    ``confidence_scores_granularity="word"``) and each word is assigned to the
    line it starts on using the documented ``start_index``. Locators are
    line-level (``{block_id}-l{n}``) so a model can cite a numeric span by its
    line. When the API returns no word scores the words are tokenized without a
    score and stay ``score=None`` — a missing score is kept MISSING (→
    UNCERTAIN), never fabricated.

    ``uncovered_item_regions`` is populated from OCR structure: an OCR ``table``
    block (or an extracted ``tables`` entry) is an item region OCR found. Any
    such region whose id is not claimed by the document facts stays listed as
    uncovered, so a later ``TOTAL_ONLY``/covered-region claim over it is rejected.
    (OCR knows *where* item regions are, not the item IDs; the analyzer's
    ``covered_item_regions`` is reconciled against these region ids.)
    """
    pages = raw.payload.get('pages') if isinstance(raw.payload, dict) else None
    if not isinstance(pages, list):
        raise DomainError('PROVIDER_FAILED', 'OCR response thiếu danh sách pages.')

    blocks: list[SourceBlock] = []
    item_regions: list[str] = []
    seen_indices: set[int] = set()
    for page in pages:
        if not isinstance(page, dict):
            raise DomainError('PROVIDER_FAILED', 'OCR page không phải object.')
        index = _page_index(page, len(blocks))
        if index in seen_indices:
            raise DomainError('PROVIDER_FAILED', f'OCR page index trùng: {index}.')
        seen_indices.add(index)
        markdown = page.get('markdown') or ''
        block_id = f'b-{index + 1}'
        words: list[SourceWord] = []
        locators: dict[str, list[str]] = {}

        scores = _word_scores(page)
        if scores:
            for i, entry in enumerate(scores):
                word_id = f'w-{index}-{i}'
                text = str(entry.get('text', ''))
                words.append(SourceWord(id=word_id, text=text, score=_score_string(entry.get('confidence'))))
                line = _line_for_offset(markdown, entry.get('start_index'))
                locators.setdefault(f'{block_id}-l{line}', []).append(word_id)
        else:
            for line_no, line in enumerate(markdown.splitlines()):
                for wi, token in enumerate(line.split()):
                    word_id = f'w-{index}-{line_no}-{wi}'
                    words.append(SourceWord(id=word_id, text=token, score=None))
                    locators.setdefault(f'{block_id}-l{line_no}', []).append(word_id)

        blocks.append(
            SourceBlock(
                evidence_id=evidence.id,
                page_index=index,
                block_id=block_id,
                text=markdown,
                words=words,
                locators=locators,
            )
        )
        item_regions.extend(_page_item_regions(page, block_id))
    try:
        return SourceRegistry(
            evidence_id=evidence.id, blocks=blocks, uncovered_item_regions=item_regions
        )
    except ValidationError as exc:
        raise DomainError('PROVIDER_FAILED', f'OCR structure không hợp lệ: {exc.error_count()} lỗi.') from exc


def _page_index(page: dict[str, Any], fallback: int) -> int:
    """Parse a page index, turning a non-int value into a technical failure."""
    value = page.get('index', fallback)
    if isinstance(value, bool) or not isinstance(value, int):
        raise DomainError('PROVIDER_FAILED', f'OCR page index không hợp lệ: {value!r}')
    return value


def _page_item_regions(page: dict[str, Any], block_id: str) -> list[str]:
    """Item regions OCR exposes: table blocks and extracted tables.

    Mistral OCR surfaces tables as ``blocks`` with ``type == 'table'`` (and/or an
    extracted ``tables`` list). Each becomes an item region id; the analyzer must
    claim it in ``covered_item_regions`` or it stays uncovered.
    """
    regions: list[str] = []
    blocks = page.get('blocks')
    if isinstance(blocks, list):
        for i, block in enumerate(blocks):
            if isinstance(block, dict) and block.get('type') == 'table':
                table_id = block.get('table_id')
                regions.append(str(table_id) if table_id else f'{block_id}-t{i}')
    tables = page.get('tables')
    if isinstance(tables, list):
        for i, table in enumerate(tables):
            if isinstance(table, dict) and table.get('id'):
                regions.append(str(table['id']))
            else:
                regions.append(f'{block_id}-t{i}')
    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for region in regions:
        if region not in seen:
            seen.add(region)
            unique.append(region)
    return unique


def _word_scores(page: dict[str, Any]) -> list[Any]:
    """Extract per-word confidence entries from a page (nested or flat shape).

    Verified Mistral schema nests them at ``page.confidence_scores.
    word_confidence_scores``; a flat ``page.word_confidence_scores`` is also
    tolerated so a schema variant does not silently drop the native signal.
    """
    nested = page.get('confidence_scores')
    if isinstance(nested, dict) and isinstance(nested.get('word_confidence_scores'), list):
        return nested['word_confidence_scores']
    flat = page.get('word_confidence_scores')
    return flat if isinstance(flat, list) else []


def _score_string(value: Any) -> str | None:
    if value is None:
        return None
    try:
        from decimal import Decimal, InvalidOperation

        return format(Decimal(str(value)).normalize(), 'f')
    except (InvalidOperation, ValueError):
        raise DomainError('PROVIDER_FAILED', f'OCR confidence không hợp lệ: {value!r}')


def _line_for_offset(markdown: str, start_index: Any) -> int:
    if not isinstance(start_index, int) or start_index < 0:
        return 0
    return markdown.count('\n', 0, min(start_index, len(markdown)))


# --- Fake providers ------------------------------------------------------------

class FakeProviders(Providers):
    """Deterministic fake with the real signatures and a ``.calls`` trace.

    Subclass and override ``ocr``/``analyze``/``cross_source`` to emit slow or
    malformed responses (e.g. raise ``DomainError('PROVIDER_FAILED')``).
    """

    def __init__(
        self,
        documents: dict[str, DocumentFacts] | None = None,
        registries: dict[str, SourceRegistry] | None = None,
        *,
        mapping: MappingProposal | None = None,
    ) -> None:
        self.documents = dict(documents or {})
        self.registries = dict(registries or {})
        self._mapping = mapping
        self.calls: list[str] = []
        self.identities: list[StageIdentity] = []
        self.usages: list[dict[str, int | None]] = []
        # The fake returns its injected records directly (no model, no repair), so
        # these stay empty/zero. Present so T06/T08 can read them uniformly across
        # FakeProviders and LiveProviders.
        self.repair_calls = 0
        self.repair_reasons: list[str] = []

    def ocr(self, evidence: Evidence) -> RawOcr:
        self.calls.append(f'ocr:{evidence.id}')
        self.identities.append(
            _identity('ocr', f'fake:{evidence.id}', 'none', 'fake-ocr', 'ocr-v1', 'fake')
        )
        return RawOcr(
            provider='fake',
            model_id='fake-ocr',
            payload={'pages': [], 'evidence_id': evidence.id},
            received_at=datetime.now(timezone.utc),
        )

    def analyze(self, request: AnalysisRequest) -> DocumentFacts:
        self.calls.append(f'analyze:{request.evidence.id}')
        self.identities.append(
            _identity('analyze', f'fake:{request.evidence.id}', ANALYZE_PROMPT_VERSION,
                      'fake-kimi', ANALYZE_SCHEMA_VERSION, 'fake')
        )
        try:
            doc = self.documents[request.evidence.id]
        except KeyError as exc:
            raise DomainError(
                'PROVIDER_FAILED', f'Fake không có document cho {request.evidence.id!r}.'
            ) from exc
        return validate_document(doc, request)

    def cross_source(self, bundle: EvidenceBundle) -> MappingProposal:
        self.calls.append('cross_source')
        self.identities.append(
            _identity('cross_source', 'fake:bundle', CROSS_PROMPT_VERSION,
                      'fake-kimi', CROSS_SCHEMA_VERSION, 'fake')
        )
        return self._mapping if self._mapping is not None else MappingProposal()


def _identity(stage: str, request_hash: str, prompt_version: str, model_id: str,
              schema_version: str, provider: str) -> StageIdentity:
    return StageIdentity(
        stage=stage,
        request_hash=request_hash,
        prompt_version=prompt_version,
        model_id=model_id,
        schema_version=schema_version,
        provider=provider,
    )


# --- Live providers (verified APIs; thin httpx transport) ----------------------

class LiveProviders(Providers):
    """Mistral OCR + Kimi/Moonshot adapters over a thin ``httpx`` transport.

    Both clients are injectable so a fake client can prove the exact request
    shape without network. Timeouts are finite (60s/call) and the httpx client
    performs no retries, so the repair budget is not multiplied. A transport
    failure becomes ``PROVIDER_FAILED`` (technical), never a business verdict.

    A single ``httpx.Client`` is used for both APIs (httpx is already a project
    dependency); this avoids pulling the heavy ``mistralai`` SDK (httpx2 +
    jsonpath-python + dateutil) for one endpoint. Both APIs are plain JSON POSTs.
    """

    def __init__(
        self,
        *,
        mistral_api_key: str | None = None,
        kimi_api_key: str | None = None,
        mistral_model: str | None = None,
        kimi_model: str | None = None,
        mistral_base_url: str | None = None,
        kimi_base_url: str | None = None,
        ocr_client: Any | None = None,
        chat_client: Any | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        prompt_dir: Path = PROMPT_DIR,
    ) -> None:
        self._mistral_api_key = mistral_api_key
        self._kimi_api_key = kimi_api_key
        # Model/base-url values come from the environment (pinned defaults), so
        # the values advertised in .env.example are actually read. The composition
        # root may also pass them explicitly (T06).
        self.mistral_model = mistral_model or _env_default('MISTRAL_OCR_MODEL', MISTRAL_OCR_MODEL)
        self.kimi_model = kimi_model or _env_default('KIMI_MODEL', KIMI_MODEL)
        self._mistral_base_url = mistral_base_url or _env_default('MISTRAL_BASE_URL', MISTRAL_BASE_URL)
        self._kimi_base_url = kimi_base_url or _env_default('KIMI_BASE_URL', KIMI_BASE_URL)
        self._ocr_client = ocr_client
        self._chat_client = chat_client
        self._timeout = timeout_seconds
        self._prompt_dir = Path(prompt_dir)
        self.identities: list[StageIdentity] = []
        # Token usage per Kimi invocation; a missing count is None, never 0.
        self.usages: list[dict[str, int | None]] = []
        # Repair accounting (System §4 "Ghi repair reason và budget"): the number
        # of repair invocations actually issued and why, for T06/T08 to persist
        # into PipelineResult.repair_calls.
        self.repair_calls = 0
        self.repair_reasons: list[str] = []

    # --- OCR ---

    def ocr(self, evidence: Evidence) -> RawOcr:
        client = self._ocr_client or self._require_ocr_client()
        document = _document_chunk(evidence)
        self._record_identity(
            'ocr', {'document': _redact_document(document)}, 'none',
            'ocr-v1', self.mistral_model, 'mistral',
        )
        payload = self._ocr_request(client, document)
        return RawOcr(
            provider='mistral',
            model_id=self.mistral_model,
            payload=payload,
            received_at=datetime.now(timezone.utc),
        )

    def _ocr_request(self, client: Any, document: dict[str, Any]) -> dict[str, Any]:
        body = {
            'model': self.mistral_model,
            'document': document,
            'include_blocks': True,
            'confidence_scores_granularity': 'word',
        }
        try:
            with _finite_timeout(self._timeout):
                response = client.post('/ocr', json=body)
                response.raise_for_status()
                return response.json()
        except DomainError:
            raise
        except Exception as exc:  # noqa: BLE001 — any transport failure is technical
            raise DomainError('PROVIDER_FAILED', f'OCR transport lỗi: {type(exc).__name__}')

    def _require_ocr_client(self) -> Any:
        if not self._mistral_api_key:
            raise DomainError('CONFIG_NOT_ACTIVE', 'MISTRAL_API_KEY chưa được cấu hình.')
        return _http_client(self._mistral_api_key, self._mistral_base_url, self._timeout)

    # --- AnalyzeDocument ---

    def analyze(self, request: AnalysisRequest) -> DocumentFacts:
        client = self._chat_client or self._require_chat_client()
        prompt = self._read_prompt('analyze-v1.txt')
        payload = analysis_payload(request)
        return self._with_repair(
            client=client,
            stage='analyze',
            prompt=prompt,
            payload=payload,
            schema_version=ANALYZE_SCHEMA_VERSION,
            parse=lambda text: _parse_document(text, request),
        )

    # --- ProposeCrossSource ---

    def cross_source(self, bundle: EvidenceBundle) -> MappingProposal:
        client = self._chat_client or self._require_chat_client()
        prompt = self._read_prompt('cross-source-v1.txt')
        payload = cross_source_payload(bundle)
        return self._with_repair(
            client=client,
            stage='cross_source',
            prompt=prompt,
            payload=payload,
            schema_version=CROSS_SCHEMA_VERSION,
            parse=lambda text: _parse_mapping(text, bundle),
            extra_budget=1,
        )

    # --- Shared repair loop ---

    def _with_repair(
        self,
        *,
        client: Any,
        stage: str,
        prompt: str,
        payload: dict[str, Any],
        schema_version: str,
        parse: Callable[[str], Any],
        extra_budget: int = 0,
    ) -> Any:
        budget = REPAIR_BUDGET + extra_budget
        repair_count = 0
        current_prompt = prompt
        base_prompt_version = (
            ANALYZE_PROMPT_VERSION if stage == 'analyze' else CROSS_PROMPT_VERSION
        )
        while True:
            self._record_identity(stage, {'prompt': current_prompt, 'payload': payload},
                                  base_prompt_version, schema_version,
                                  self.kimi_model, 'kimi')
            content, _usage = self._chat(client, current_prompt, payload)
            try:
                return parse(content)
            except (DomainError, ValidationError, ValueError) as exc:
                # DomainError carries ``message``; ValidationError/ValueError do not.
                reason = getattr(exc, 'message', None) or str(exc)
                allowed = (
                    shared_repair_allowed(repair_count)
                    if extra_budget == 0
                    else repair_count < budget
                )
                if not allowed:
                    raise DomainError(
                        'INVALID_ANALYSIS', f'{stage} không hợp lệ sau repair: {reason}'
                    )
                repair_count += 1
                self.repair_calls += 1
                self.repair_reasons.append(f'{stage}: {reason}')
                current_prompt = self._repair_prompt(reason)

    def _chat(self, client: Any, prompt: str, payload: dict[str, Any]) -> tuple[str, Any]:
        messages = [
            {'role': 'system', 'content': prompt},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False, sort_keys=True)},
        ]
        body = {
            'model': self.kimi_model,
            'messages': messages,
            'response_format': {'type': 'json_object'},
            'temperature': 0,
        }
        try:
            with _finite_timeout(self._timeout):
                response = client.post('/chat/completions', json=body)
                response.raise_for_status()
                data = response.json()
        except DomainError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DomainError('PROVIDER_FAILED', f'Kimi transport lỗi: {type(exc).__name__}')
        try:
            content = data['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as exc:
            raise DomainError('INVALID_ANALYSIS', 'Kimi response thiếu choices/message.') from exc
        if not isinstance(content, str):
            raise DomainError('INVALID_ANALYSIS', 'Kimi trả về nội dung không phải chuỗi.')
        usage = _usage_dict(data.get('usage'))
        self.usages.append(usage)
        return content, usage

    def _require_chat_client(self) -> Any:
        if not self._kimi_api_key:
            raise DomainError('CONFIG_NOT_ACTIVE', 'KIMI_API_KEY chưa được cấu hình.')
        return _http_client(self._kimi_api_key, self._kimi_base_url, self._timeout)

    # --- Prompt / identity helpers ---

    def _read_prompt(self, name: str) -> str:
        return (self._prompt_dir / name).read_text(encoding='utf-8')

    def _repair_prompt(self, reason: str) -> str:
        template = self._read_prompt('repair-v1.txt')
        return template.replace('{{reason}}', reason)

    def _record_identity(self, stage: str, request_parts: dict[str, Any],
                         prompt_version: str, schema_version: str, model_id: str,
                         provider: str) -> None:
        self.identities.append(
            _identity(
                stage=stage,
                request_hash=_hash_payload({'parts': request_parts, 'model': model_id}),
                prompt_version=prompt_version,
                model_id=model_id,
                schema_version=schema_version,
                provider=provider,
            )
        )


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _redact_document(document: dict[str, Any]) -> dict[str, Any]:
    """Identity payload for OCR: never hash/store the raw base64 document body."""
    return {'type': document.get('type'), 'document_url': '<redacted>'}


# --- Parsing helpers (used by LiveProviders and mirrored by fakes) -------------

def _parse_document(text: str, request: AnalysisRequest) -> DocumentFacts:
    data = json.loads(text)
    doc = DocumentFacts.model_validate(data)
    return validate_document(doc, request)


def _parse_mapping(text: str, bundle: EvidenceBundle) -> MappingProposal:
    data = json.loads(text)
    proposal = MappingProposal.model_validate(data)
    _validate_mapping(proposal, bundle)
    return proposal


def _validate_mapping(proposal: MappingProposal, bundle: EvidenceBundle) -> None:
    primary_ids: set[str] = set()
    receipt_ids: set[str] = set()
    for doc in bundle.documents:
        for item in doc.items:
            if doc.kind == 'GOODS_RECEIPT':
                receipt_ids.add(item.id)
            else:
                primary_ids.add(item.id)
    for left, right in proposal.pairs:
        if left not in primary_ids:
            raise DomainError('INVALID_ANALYSIS', f'mapping pair left {left!r} không thuộc primary')
        if right not in receipt_ids:
            raise DomainError('INVALID_ANALYSIS', f'mapping pair right {right!r} không thuộc receipt')
    for ref in proposal.refs:
        registry = bundle.registries.get(ref.evidence_id)
        if registry is None:
            raise DomainError(
                'INVALID_ANALYSIS', f'mapping ref evidence {ref.evidence_id!r} không có registry'
            )
        check_ref(ref, registry)


# --- Thin client / transport helpers -------------------------------------------

def _http_client(api_key: str, base_url: str, timeout_seconds: float) -> Any:
    """Thin httpx client: finite timeout, no retries (budget is not multiplied)."""
    import httpx

    return httpx.Client(
        base_url=base_url,
        headers={'Authorization': f'Bearer {api_key}'},
        timeout=timeout_seconds,
        transport=httpx.HTTPTransport(retries=0),
    )


def _document_chunk(evidence: Evidence) -> dict[str, Any]:
    try:
        data = Path(evidence.stored_path).read_bytes()
    except OSError as exc:
        raise DomainError('PROVIDER_FAILED', f'Không đọc được evidence {evidence.id!r}.') from exc
    encoded = base64.b64encode(data).decode('ascii')
    return {'type': 'document_url', 'document_url': f'data:{evidence.mime};base64,{encoded}'}


def _usage_dict(usage: Any) -> dict[str, int | None]:
    """Token counts from the API; a missing count is ``None``, never a fake 0."""
    if usage is None:
        return {'prompt_tokens': None, 'completion_tokens': None, 'total_tokens': None}
    get = usage.get if isinstance(usage, dict) else lambda name: getattr(usage, name, None)
    return {
        'prompt_tokens': get('prompt_tokens'),
        'completion_tokens': get('completion_tokens'),
        'total_tokens': get('total_tokens'),
    }


@contextmanager
def _finite_timeout(seconds: float):
    """Bound a synchronous provider call on the main thread (finite 60s/call).

    A background thread cannot receive SIGALRM, so the loop does not rely on it
    there; the HTTP client's own timeout still applies.
    """
    if not hasattr(signal, 'SIGALRM') or threading.current_thread() is not threading.main_thread():
        yield
        return

    def _raise(_signum, _frame):
        raise TimeoutError('provider call timed out')

    previous = signal.signal(signal.SIGALRM, _raise)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


__all__ = [
    'ANALYZE_PROMPT_VERSION',
    'ANALYZE_SCHEMA_VERSION',
    'CROSS_PROMPT_VERSION',
    'CROSS_SCHEMA_VERSION',
    'DEFAULT_TIMEOUT_SECONDS',
    'FakeProviders',
    'KIMI_BASE_URL',
    'KIMI_MODEL',
    'LiveProviders',
    'MISTRAL_BASE_URL',
    'MISTRAL_OCR_MODEL',
    'PROMPT_DIR',
    'Providers',
    'analysis_payload',
    'cross_source_payload',
    'registry_from_ocr',
]
