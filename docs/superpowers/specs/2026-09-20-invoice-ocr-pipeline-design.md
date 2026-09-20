# InvoiceReferee Supplier-Invoice OCR Pipeline Design

**Date:** 2026-09-20  
**Status:** Draft for user review  
**Challenge:** OrganizationAI — Challenge A, Escalation Referee  
**Target:** Sprint 1

## 1. Decision summary

InvoiceReferee will add one end-to-end document-ingestion path for **Supplier Invoice only**:

```text
Supplier Invoice PDF/PNG/JPG
→ validated document
→ page images + preserved PDF text layer
→ local PaddleOCR/PP-StructureV3
→ OCR text/layout/tables with provenance
→ invoice field candidates
→ deterministic extraction validation
→ human confirmation/correction
→ reviewed canonical invoice evidence
→ existing Transaction/Checks/Policy/LLM/Guard pipeline
```

PO, Goods Receipt, Payment History, prior invoices, and approvals remain structured JSON in Sprint 1.

The OCR subsystem extracts candidate facts. It never issues `AUTO_PROCESS`, `REQUEST_INFO`, or `ESCALATE`. Final actions remain owned by Policy v0 and the deterministic Decision Guard.

## 2. Problem being solved

The current production path starts from a structured Python dictionary matching the canonical evidence schema. Real supplier invoices can instead arrive as:

- a text-based PDF;
- a scanned PDF;
- a PNG/JPEG image;
- a low-quality or rotated capture.

The missing subsystem is not only character recognition. It must preserve document provenance, reconstruct invoice fields and line items, expose uncertainty, let a human correct extraction, and produce canonical evidence without converting missing or invalid fields into confident values.

## 3. Goals

Sprint 1 must demonstrate:

1. Upload of one Supplier Invoice as PDF, PNG, JPG, or JPEG.
2. A unified page-image OCR path for PDFs and images.
3. Preservation of embedded PDF text as secondary evidence when present.
4. Local OCR and document-structure extraction with PaddleOCR/PP-StructureV3.
5. Field-level values, confidence, page number, and bounding box.
6. Extraction of invoice header fields and line items into the existing canonical schema.
7. Fail-closed handling of missing, invalid, ambiguous, or conflicting fields.
8. Human confirmation/correction before extracted fields become reviewed evidence.
9. A single audit history covering upload, OCR, corrections, business checks, final decision, Stop, and Override.
10. The same existing `review()` service for JSON fixtures and OCR-originated evidence.

## 4. Non-goals

Sprint 1 does not include:

- OCR for PO, Goods Receipt, payment records, or approvals;
- handwritten invoices;
- multiple invoices inside one uploaded file;
- signature, stamp, QR authenticity, or forgery verification;
- tax-law or e-invoice legal validation;
- automatic vendor onboarding;
- model training or fine-tuning;
- broad fraud detection;
- RAG, vector databases, or multi-agent orchestration;
- asynchronous queues or distributed workers;
- permanent document storage;
- automatic payment or accounting entries.

## 5. Supported document contract

### 5.1 Accepted files

| Property | Sprint 1 contract |
| --- | --- |
| Document type | One Supplier Invoice per file |
| MIME types | `application/pdf`, `image/png`, `image/jpeg` |
| Extensions | `.pdf`, `.png`, `.jpg`, `.jpeg` |
| Maximum file size | 10 MiB |
| Maximum pages | 5 |
| Printed languages | Vietnamese and English |
| Handwriting | Unsupported |
| Password-protected PDF | Rejected as technical input error |
| Corrupt/unrenderable file | Rejected as technical input error |

The validator must inspect magic bytes/content type rather than trusting the filename extension alone.

### 5.2 Required invoice fields

Critical header fields:

- `invoice_id` generated internally from the document hash/session when absent;
- `invoice_number`;
- `invoice_series`;
- `invoice_type`;
- `vendor_id` resolved from structured PO/vendor-master evidence rather than guessed by OCR;
- `vendor_tax_code`;
- `po_id`;
- `invoice_date`;
- `currency`;
- `total_amount`.

Critical line-item fields:

- `item_id` or a human-confirmed mapping to the PO item;
- `description`;
- `invoiced_quantity`;
- `unit_price`;
- `line_total`.

Unknown critical fields remain `None` with warnings. They must never default to `""` or `0` merely to satisfy the downstream dataclass.

`vendor_id` and `item_id` require identity resolution rather than character recognition:

- OCR extracts vendor name/tax code and invoice item descriptions or supplier SKUs.
- Structured PO/vendor-master evidence supplies internal vendor and item IDs.
- A deterministic resolver maps tax code/SKU when an exact mapping exists.
- Ambiguous mapping requires human selection from the PO candidates.
- Sprint 1 extends the structured PO evidence with `vendor_tax_code` and optional supplier-SKU mappings; it does not infer internal IDs from names alone.

## 6. Architectural boundaries

```text
app/
  upload and human confirmation only

services/extractor.py
  extraction orchestration only

ingestion/
  file validation, rendering, preprocessing, OCR adapter,
  field extraction, normalization, extraction validation

domain/models.py
  shared immutable data contracts

services/reviewer.py
  existing business-review orchestration

checks/ + policy/ + decision/
  unchanged ownership of business facts and final action

audit/
  one unified event timeline
```

No OCR or field-mapping logic may be embedded in Streamlit. No business decision logic may be embedded in the OCR subsystem.

## 7. Proposed modules

```text
src/invoice_referee/ingestion/
├── file_validation.py       # MIME, size, page count, encrypted/corrupt checks
├── document_router.py       # PDF vs image route
├── pdf_renderer.py          # render pages; preserve native text spans
├── image_preprocessing.py   # orientation, color normalization, deskew
├── ocr.py                   # OCREngine protocol + PaddleOCR adapter
├── invoice_fields.py        # OCRDocument -> FieldCandidate[]
├── identity_resolution.py   # tax code/SKU -> internal vendor/item IDs
├── extraction_validation.py # field/schema/arithmetic/cross-source validation
└── pipeline.py              # extract_invoice() orchestration

src/invoice_referee/services/
└── extractor.py             # application-facing extraction service

app/
├── streamlit_app.py         # upload -> verify fields -> review
└── extraction_presentation.py
```

These modules are the accepted ownership boundaries. Shared helpers may be private within the owning module; extraction, identity resolution, validation, and orchestration must not be merged into the Streamlit layer.

## 8. Data contracts

### 8.1 UploadedDocument

```python
@dataclass
class UploadedDocument:
    document_id: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    content: bytes
```

`document_id` is stable within the review session. Raw content is not copied into audit events.

### 8.2 DocumentPage

```python
@dataclass
class DocumentPage:
    document_id: str
    page_number: int
    image_bytes: bytes
    width: int
    height: int
    dpi: int
    native_text: str | None
```

PDF pages are rendered at 300 DPI. The original document remains unchanged. Native PDF text is retained for cross-checking but does not bypass OCR.

### 8.3 BoundingBox and OCRBlock

```python
@dataclass(frozen=True)
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float

@dataclass
class OCRBlock:
    block_id: str
    page_number: int
    text: str
    confidence: float
    bounding_box: BoundingBox
    block_type: str  # TEXT | KEY_VALUE | TABLE_CELL
    row_index: int | None = None
    column_index: int | None = None
```

Coordinates are normalized to page dimensions so UI rendering is independent of pixel resolution.

### 8.4 OCRDocument

```python
@dataclass
class OCRDocument:
    document_id: str
    pages: list[DocumentPage]
    blocks: list[OCRBlock]
    full_text: str
    engine: str
    engine_version: str
    processing_ms: int
    warnings: list[str]
```

### 8.5 FieldCandidate

```python
class FieldStatus(str, Enum):
    EXTRACTED = "EXTRACTED"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    CORRECTED = "CORRECTED"
    MISSING = "MISSING"
    INVALID = "INVALID"
    CONFLICTING = "CONFLICTING"

@dataclass
class FieldCandidate:
    field_name: str
    raw_text: str | None
    normalized_value: object | None
    confidence: float | None
    status: FieldStatus
    page_number: int | None
    bounding_box: BoundingBox | None
    evidence_block_ids: list[str]
    extraction_method: str
    warnings: list[str]
```

`extraction_method` is one of `NATIVE_PDF_TEXT`, `OCR_RULE`, `OCR_TABLE`, `LLM_ASSISTED`, or `HUMAN`.

### 8.6 InvoiceExtractionResult

```python
class ExtractionStatus(str, Enum):
    PROCESSING = "PROCESSING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REVIEWED = "REVIEWED"
    FAILED = "FAILED"

@dataclass
class InvoiceExtractionResult:
    document_id: str
    status: ExtractionStatus
    fields: dict[str, FieldCandidate]
    line_items: list[dict[str, FieldCandidate]]
    warnings: list[str]
    audit_events: list[AuditEvent]
```

`REVIEWED` means a human has accepted, corrected, or explicitly marked unknown every critical field. It does not mean every field has a non-null value.

## 9. Processing flow

### 9.1 File validation

The pipeline rejects before OCR when:

- MIME/magic bytes do not match the allow-list;
- the file exceeds 10 MiB;
- the PDF exceeds five pages;
- the PDF is encrypted;
- the file cannot be decoded or rendered;
- an image dimension/decompression limit is exceeded.

These are technical input errors, not `REQUEST_INFO` decisions.

### 9.2 PDF and image routing

PDF:

1. Read page count and encryption state.
2. Extract native text spans when available.
3. Render every page to a 300-DPI image.
4. Preserve native text with page references for later comparison.

PNG/JPEG:

1. Decode safely.
2. Normalize color mode.
3. Create a one-page `DocumentPage`.

### 9.3 Image preprocessing

The Sprint 1 baseline performs:

- EXIF orientation normalization for image uploads;
- PaddleOCR orientation detection and correction;
- RGB/grayscale normalization required by the selected OCR model;
- deskew when the estimated skew is between 0.5 and 10 degrees;
- no-op deskew outside that range, with a warning for larger angles;
- no denoise, document-unwarping, or adaptive image enhancement in the baseline.

Denoise, unwarping, and contrast enhancement are excluded from the accepted baseline because they can destroy small invoice characters. They require a documented evaluation-set improvement before being added.

The original page image remains available. Preprocessing must not overwrite the only copy used for evidence display.

### 9.4 OCR and structure extraction

`PaddleOCREngine` implements:

```python
class OCREngine(Protocol):
    def analyze(self, pages: list[DocumentPage]) -> OCRDocument: ...
```

Baseline engine:

- PaddleOCR local inference;
- PP-StructureV3 document parsing;
- CPU-compatible configuration;
- table recognition enabled;
- orientation correction enabled;
- document unwarping and denoise disabled in the Sprint 1 baseline;
- model weights downloaded during build/setup and cached before judge execution.

The current macOS/Python 3.12 environment is supported by current PaddlePaddle CPU packages, but macOS local execution is CPU-only. Target deployment compatibility and latency must be proven before implementation is called complete.

### 9.5 Field extraction

Extraction is deterministic-first:

1. Detect labels/anchors such as invoice number, invoice series, tax code, PO number, date, and total.
2. Use spatial relationships to bind a label to its value.
3. Reconstruct line items from OCR table cells.
4. Normalize dates, IDs, quantities, and integer VND without substituting missing values.
5. Compare OCR-derived text with native PDF text when both exist.
6. Resolve internal vendor/item IDs only through exact structured mappings or explicit human selection.

LLM extraction assistance is disabled by default in the Sprint 1 baseline. When explicitly enabled for the demo, it is used only for unresolved semantic mapping:

- input is OCR blocks, layout references, allowed field names, and schema;
- output is candidate field-to-block mappings;
- every value must cite existing OCR block IDs;
- LLM-derived candidates always require human confirmation in Sprint 1;
- an unavailable/invalid LLM leaves fields unresolved instead of inventing a fallback value.

### 9.6 Extraction validation

Validators run before human review:

- required-field presence;
- date parse validity;
- money/quantity integer validity;
- non-negative values;
- line quantity × unit price consistency when applicable;
- sum of line totals versus invoice total;
- duplicate candidate use of conflicting OCR spans;
- OCR/native-PDF disagreement;
- field provenance exists for every non-human value.

The extraction validator reports facts and warnings. It does not apply PO policy or produce Agent actions.

## 10. Confidence and confirmation policy

Prototype thresholds are configuration, not universal truth:

- critical field confidence `< 0.90` → `NEEDS_CONFIRMATION`;
- non-critical field confidence `< 0.80` → `NEEDS_CONFIRMATION`;
- missing confidence → `NEEDS_CONFIRMATION`;
- OCR/native-text disagreement → `CONFLICTING`;
- failed normalization → `INVALID`;
- LLM-assisted mapping → `NEEDS_CONFIRMATION` regardless of model confidence;
- human correction → `CORRECTED` with actor and original candidate preserved.

Thresholds must be evaluated on the Sprint 1 extraction set. They are not accuracy claims and must be labeled synthetic/configured.

## 11. Human confirmation experience

The UI presents:

```text
Left: original invoice page
Right: extracted header fields and line-item table
```

Selecting a field highlights its source bounding box. Each field shows:

- extracted value;
- normalized value;
- confidence;
- page/source;
- warnings;
- Confirm, Correct, or Mark Unknown.

The user cannot start business review until every critical field is explicitly resolved as:

- confirmed;
- corrected;
- or unknown.

`Mark Unknown` preserves `None` plus a parse warning. The resulting invoice is flagged so the existing business pipeline must not confidently auto-process it.

## 12. Canonical evidence handoff

After human review:

```text
InvoiceExtractionResult(REVIEWED)
→ reviewed_invoice_to_evidence()
→ existing raw evidence dictionary
→ build_transaction()
→ run_checks()
→ build_policy_context()
→ assess()
→ guard()
```

The handoff adds extraction metadata without changing the meaning of existing business fields:

```json
{
  "invoice": {
    "invoice_number": "0000123",
    "total_amount": 30000000,
    "flagged": false,
    "source_type": "OCR"
  },
  "extraction_metadata": {
    "document_id": "DOC-...",
    "engine": "paddleocr",
    "engine_version": "...",
    "warnings": [],
    "field_provenance": {}
  }
}
```

Before this handoff is implemented, current normalization must be changed so absent critical values do not become `""` or `0`.

## 13. LLM boundaries

The system has two distinct LLM tasks with separate contracts:

### Task A — extraction assistance

- disabled by default in the baseline and enabled only through explicit configuration;
- map OCR blocks to allow-listed invoice fields;
- cite exact OCR block IDs;
- never create or modify a value;
- all output requires human confirmation.

### Task B — review communication

- remains the existing normal review-assessment stage; a deterministic fallback is used when no provider is configured;
- receive reviewed transaction facts, deterministic checks, and policy context;
- select one real unresolved check;
- explain it and produce a directly answerable question;
- never change checks, policy, authority, or final action.

The tasks use separate prompts, schemas, validation, and audit events. Invoice text is untrusted data and must never be concatenated as executable instructions without clear separation.

## 14. State model

```text
UPLOADED
→ VALIDATED
→ OCR_PROCESSING
→ NEEDS_EXTRACTION_REVIEW
→ EXTRACTION_REVIEWED
→ BUSINESS_REVIEWED
   ├─ READY_FOR_PAYMENT_REVIEW
   ├─ AWAITING_INFORMATION
   └─ ESCALATED

Any active state
→ STOPPED
```

Technical extraction states are not Agent decisions. The only user-facing Agent decisions remain:

- `AUTO_PROCESS`;
- `REQUEST_INFO`;
- `ESCALATE`.

## 15. Unified audit

One audit timeline uses a single event-ID sequence. Minimum new event types:

- `DOCUMENT_UPLOADED`;
- `DOCUMENT_VALIDATED`;
- `PAGE_RENDERED`;
- `OCR_COMPLETED`;
- `FIELD_EXTRACTED`;
- `FIELD_FLAGGED`;
- `FIELD_CONFIRMED`;
- `FIELD_CORRECTED`;
- `EXTRACTION_REVIEWED`.

Each field event records:

- actor;
- timestamp;
- document/page/block references;
- original candidate;
- corrected/confirmed value where applicable;
- engine/model version;
- reason/warnings.

The UI export must preserve full event objects, including IDs, actors, input refs, rule IDs, and details. Automated review and human-control events must not use separate stores with colliding IDs.

## 16. Error handling

| Failure | Behavior |
| --- | --- |
| Unsupported/corrupt/encrypted file | Technical input error; no Agent decision |
| OCR engine unavailable | Extraction failure with retry option; no guessed fields |
| Page unreadable | Preserve page warning; fields remain unknown |
| Low-confidence critical field | Human confirmation required |
| Native PDF text conflicts with OCR | Show both values; human resolves |
| LLM extraction mapper unavailable | Deterministic candidates remain; unresolved fields stay unknown |
| Business evidence missing after review | Existing Guard maps to `REQUEST_INFO` |
| Out-of-scope transaction | Existing Guard maps to `ESCALATE` |

## 17. Security and privacy

- Accept only allow-listed MIME/magic-byte combinations.
- Sanitize filenames; never use user filenames as executable paths.
- Apply PDF page, image dimension, and decompression limits.
- Store temporary files outside the repository and remove them after the session/request.
- Do not persist raw invoice bytes by default.
- Do not include raw invoice content in logs or exception messages.
- Treat OCR text as untrusted content.
- Never allow OCR/LLM output to invoke tools, mutate policy, or trigger payment.
- Do not expose API keys in UI, audit, or exports.
- Document data retention and consent before using real invoices.

## 18. Testing strategy

### 18.1 Unit tests

- MIME/magic-byte validation;
- size/page/encryption/corruption rejection;
- PDF rendering and native-text preservation;
- image normalization;
- PaddleOCR response mapping using recorded synthetic responses;
- bounding-box normalization;
- field normalization without zero/empty defaults;
- arithmetic and cross-source extraction warnings;
- confidence/status mapping;
- reviewed-evidence conversion;
- audit event provenance.

### 18.2 Extraction evaluation set

Create 15 synthetic invoice documents with ground-truth annotations:

- 5 text PDFs;
- 5 scanned PDFs;
- 5 PNG/JPEG images;
- at least 5 distinct layouts;
- at least one rotated page;
- at least one low-contrast page;
- at least one multi-page invoice;
- at least one unreadable critical field;
- at least one OCR/native-text conflict;
- at least one line-item table with multiple rows.

Ground truth is stored separately from production inputs. Production extraction code must not read expected values or document IDs.

### 18.3 Metrics

- document acceptance/rejection accuracy;
- normalized exact match per critical field;
- critical-field recall;
- line-item row/cell accuracy;
- false auto-confirm rate;
- human correction rate;
- percentage of values with valid provenance;
- extraction latency by document type/page count;
- LLM-assisted candidate acceptance rate;
- downstream action accuracy after OCR-originated evidence.

The most important safety metric is **false auto-confirm rate**. The target for the Sprint 1 evaluation set is zero: an incorrect critical field must not silently become reviewed evidence.

### 18.4 Integration tests

```text
PDF/image fixture
→ OCR response
→ human confirmation simulation
→ canonical evidence
→ production review()
→ expected decision and audit
```

Required end-to-end scenarios:

1. clear routine invoice → `AUTO_PROCESS` after confirmation;
2. unreadable amount → flagged/unknown → `REQUEST_INFO`;
3. OCR reads the wrong PO ID and human corrects it → correction preserved;
4. quantity mismatch after extraction → `REQUEST_INFO`;
5. beyond-authority amount → `ESCALATE`;
6. wrong invoice/PO linkage → fail closed;
7. OCR engine failure → technical error, not business decision.

All existing 191 tests and Core/Escalation/All Verify suites must remain green.

## 19. Verify and judge experience

The homepage offers two independent judge paths:

1. **Structured Verify:** existing one-click deterministic suites.
2. **Document Upload:** upload one provided PDF/image, inspect extracted fields, confirm flagged fields, then run the same production review.

The OCR demo must show:

- original page;
- extracted value and source highlight;
- confidence/warning;
- one human correction or unknown field;
- final business decision;
- unified audit from upload through decision.

OCR extraction tests should not inflate the existing 4-case Core or 5-case Escalation requirements. They are separate evidence that the document boundary works.

## 20. Deployment

- Baseline runtime: Python 3.12.
- Local development on macOS uses PaddlePaddle CPU inference; macOS GPU inference is not assumed.
- Public deployment must use a host/container that can install and retain PaddlePaddle/PaddleOCR model weights.
- Model weights are installed or warmed before judge interaction; no first-click model download.
- OCR remains synchronous for up to five pages.
- The target deployment is accepted only after a three-page scanned PDF completes within 20 seconds at p95 over 20 warm runs.
- If the selected host cannot meet memory or latency requirements, deployment moves to a larger single-process host; Sprint 1 does not introduce a queue or distributed OCR service.

`OCREngine` remains an adapter so a cloud or lighter local engine can replace PaddleOCR later without changing field validation, human confirmation, or business review.

## 21. Acceptance criteria

The design is implemented when all of the following are true:

1. PDF/PNG/JPEG Supplier Invoice upload works through the public UI.
2. Every PDF page is rendered and OCR processed; native PDF text is retained when present.
3. Every extracted non-human field has page/block provenance.
4. Missing or invalid critical fields remain unknown rather than becoming empty strings or zero.
5. Low-confidence, conflicting, invalid, and LLM-assisted fields require human confirmation.
6. Human corrections preserve the original candidate and actor/reason/time.
7. Reviewed evidence enters the existing production `review()` path.
8. OCR never emits a final Agent action.
9. A wrong PO/receipt/invoice relationship cannot `AUTO_PROCESS`.
10. Extraction and business events share one collision-free audit history.
11. The 15-document extraction set reports field-level metrics and zero false auto-confirms.
12. Existing tests and Verify suites remain green.
13. The deployed warm OCR path meets the documented three-page latency target.
14. The UI and documentation clearly disclose unsupported inputs, synthetic thresholds, local model use, and human-confirmation behavior.

## 22. External technical references

- [PaddleOCR — PP-StructureV3 local usage](https://www.paddleocr.ai/v3.6.0/en/version3.x/pipeline_usage/PP-StructureV3.html)
- [PaddleOCR — Installation](https://www.paddleocr.ai/main/en/version3.x/installation.html)
- [PaddlePaddle — macOS pip installation](https://www.paddlepaddle.org.cn/documentation/docs/en/install/pip/macos-pip_en.html)
- [PyMuPDF documentation](https://pymupdf.readthedocs.io/)
- [OWASP — Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
- [OWASP — Improper Output Handling](https://genai.owasp.org/llmrisk/llm052025-improper-output-handling/)
