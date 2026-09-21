# Structure-Aware Invoice Field Extraction Design

**Date:** 2026-09-21  
**Status:** Draft for user review  
**Scope:** Supplier-Invoice OCR field mapping only  
**Parent design:** `docs/superpowers/specs/2026-09-20-invoice-ocr-pipeline-design.md`

## 1. Decision summary

Replace the current single-pass `label:value` rule mapper with a provider-neutral, structure-aware candidate pipeline:

```text
OCRDocument
→ DocumentStructure analysis
→ deterministic field extractors
→ candidate collection and conflict detection
→ semantic fallback for unresolved fields only
→ deterministic normalization and cross-field validation
→ human confirmation
→ reviewed canonical invoice evidence
```

This design changes only how OCR blocks become `FieldCandidate` objects. It does not change:

- file validation, rendering, or OCR provider boundaries;
- the requirement that every critical field be confirmed, corrected, or marked unknown;
- transaction linking and deterministic business checks;
- Policy v0, Agent actions, authority rules, or the Decision Guard.

## 2. Problem statement

The current extractor assumes a header field appears as `label: value` inside one OCR block:

```text
OCRBlock.text
→ split on ':'
→ alias substring match
→ FieldCandidate
```

This works for blocks such as:

```text
Số (Invoice No.): 00002438
```

It fails when document meaning is represented by structure rather than one string:

```text
Table row 9, column 0: Tổng cộng tiền thanh toán (Total payment):
Table row 9, column 5: 9.000.000
```

The OCR provider has already recovered the label, value, table row, column, block IDs, confidence, and document ordering. The current mapper discards that structure and misclassifies the total as a line-item value.

## 3. Evidence from `a.jpg`

The configured runtime was executed on `a.jpg` using `mistral-ocr-latest`:

```text
processing time: 6538 ms
pages: 1
blocks: 82
```

Verified OCR evidence:

| Meaning | Block | Type | Text | Confidence |
| --- | --- | --- | --- | --- |
| Total label | `P1-M0-P1-T0R9C0` | `TABLE_CELL` | `Tổng cộng tiền thanh toán (Total payment):` | 0.9926 |
| Total value | `P1-M0-P1-T0R9C5` | `TABLE_CELL` | `9.000.000` | 0.9926 |
| Seller tax code | `P1-BLK0008` | `KEY_VALUE` | `MST (Tax Code): 0110329220` | 0.9999 |
| Buyer tax code | `P1-BLK0012` | `KEY_VALUE` | `MST (Tax Code): 0 1 1 0 3 2 9 5 7 3` | 0.9947 |
| Header date | `P1-BLK0005` | `TEXT` | `Ngày (day) 11 tháng (month) 07 năm (year) 2023` | 0.9999 |
| Signature date | `P1-BLK0020` | `KEY_VALUE` | `Ngày: 11/07/2023` | 0.9999 |

Observed mapping defects:

1. `total_amount` was not created.
2. `9.000.000` became `line_items[8].line_total`.
3. The ordinal header row `1 | 2 | 3 | 4 | 5 | 6 = 4 x 5` became a fake line item.
4. Six empty rows became empty line items.
5. The signature date was selected as `invoice_date`; it only happened to equal the header date.
6. Seller tax code was selected because it appeared before buyer tax code, not because the mapper understood seller/buyer roles.

Failure classification:

```text
OCR_TEXT                    PASS
BLOCK_DETECTION             PASS
TABLE_ROW/COLUMN DETECTION  PASS
LABEL_COVERAGE              PASS
HEADER VALUE BINDING        FAIL
TABLE ROW CLASSIFICATION    FAIL
SECTION DISAMBIGUATION      WEAK
NORMALIZATION               PASS
```

## 4. Goals

1. Preserve and use OCR structural information instead of flattening it prematurely.
2. Correctly classify table headers, ordinal rows, data rows, empty rows, and summary rows.
3. Extract totals when label and value are in separate blocks or cells.
4. Distinguish seller, buyer, signature, and footer contexts.
5. Prevent subtotal, tax, discount, and shipping amounts from being mislabeled as final total.
6. Support exact labels first and conservative fuzzy matching only for unresolved labels.
7. Use semantic extraction only after deterministic extractors fail.
8. Require every semantic candidate to cite existing OCR blocks and raw text.
9. Preserve conflicting candidates instead of silently selecting one.
10. Keep all critical fields under the existing human-confirmation invariant.

## 5. Non-goals

- replacing Mistral OCR or PaddleOCR;
- training or fine-tuning a document model;
- vendor-specific template classes;
- fuzzy matching of monetary values or IDs;
- allowing an LLM to normalize money, calculate totals, or create uncited values;
- changing the canonical invoice schema beyond candidate metadata;
- automatically trusting high-confidence fields without human review;
- changing the business-review decision flow.

## 6. High-level architecture

```text
OCR Provider Adapter
        ↓
OCRDocument
        ↓
DocumentStructureAnalyzer
  ├─ sections
  ├─ table row roles
  └─ spatial relationships
        ↓
Deterministic Candidate Extractors
  ├─ ExactKeyValueExtractor
  ├─ SectionAwareExtractor
  ├─ TableItemExtractor
  ├─ TableSummaryExtractor
  ├─ SpatialKeyValueExtractor
  └─ FuzzyLabelExtractor
        ↓
CandidateResolver
  ├─ agreements
  ├─ priority
  └─ conflicts
        ↓ unresolved fields only
SemanticFieldMapper
  ├─ provider annotation adapter, optional
  └─ grounded LLM mapper, feature-flagged
        ↓
CandidateResolver
        ↓
Deterministic Normalization/Validation
        ↓
Human Confirmation
```

## 7. Minimal module boundaries

```text
src/invoice_referee/ingestion/
├── document_structure.py    # sections, row roles, spatial index
├── invoice_fields.py        # deterministic candidate extractors
├── candidate_resolver.py    # candidate priority/agreement/conflict
├── llm_mapper.py            # grounded semantic fallback
├── extraction_validation.py # normalization/cross-field warnings
└── pipeline.py              # human review and canonical handoff
```

No new framework, database, queue, or model-training subsystem is introduced.

## 8. Structure contracts

### 8.1 SectionRole

```python
class SectionRole(str, Enum):
    HEADER = "HEADER"
    SELLER = "SELLER"
    BUYER = "BUYER"
    ITEM_TABLE = "ITEM_TABLE"
    SUMMARY = "SUMMARY"
    SIGNATURE = "SIGNATURE"
    FOOTER = "FOOTER"
    UNKNOWN = "UNKNOWN"
```

### 8.2 TableRowRole

```python
class TableRowRole(str, Enum):
    COLUMN_HEADER = "COLUMN_HEADER"
    ORDINAL_HEADER = "ORDINAL_HEADER"
    DATA = "DATA"
    EMPTY = "EMPTY"
    SUBTOTAL = "SUBTOTAL"
    TAX = "TAX"
    DISCOUNT = "DISCOUNT"
    SHIPPING = "SHIPPING"
    GRAND_TOTAL = "GRAND_TOTAL"
    AMBIGUOUS = "AMBIGUOUS"
```

### 8.3 DocumentStructure

```python
@dataclass
class DocumentStructure:
    section_by_block_id: dict[str, SectionRole] = field(default_factory=dict)
    row_role_by_key: dict[tuple[int, int, int], TableRowRole] = field(default_factory=dict)
    blocks_by_table_row: dict[tuple[int, int, int], list[OCRBlock]] = field(default_factory=dict)
    right_neighbor_by_block_id: dict[str, list[str]] = field(default_factory=dict)
    below_neighbor_by_block_id: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
```

The table-row key is `(page_number, table_index, row_index)`. Provider adapters must encode a stable table index in table-cell block IDs or metadata. Existing Mistral IDs such as `P1-M0-P1-T0R9C5` already contain `T0`, `R9`, and `C5`.

## 9. Document structure analysis

### 9.1 Section classification

Section classification uses deterministic anchors and reading order:

- seller anchors: `seller`, `đơn vị bán`, `người bán`;
- buyer anchors: `buyer`, `người mua`, `đơn vị mua`;
- item table begins at a row containing at least two known column labels;
- summary rows are classified inside or immediately after an item table;
- signature anchors: `signed`, `ký điện tử`, `người bán hàng`, `người mua hàng`;
- footer anchors: lookup URLs, provider/legal notices, page footer blocks.

An anchor starts a section until the next stronger anchor in reading order. Table cells are assigned `ITEM_TABLE` or `SUMMARY` from row classification rather than vertical position alone.

### 9.2 Spatial index

For non-table blocks, define candidate neighbors using normalized bounding boxes:

- same page only;
- right neighbor: vertical overlap at least 50%, positive horizontal gap, nearest first;
- below neighbor: horizontal overlap at least 30%, positive vertical gap, nearest first;
- maximum gap is configurable and evaluated on the development set;
- blocks from a different section are excluded.

For table cells, row/column indices take precedence over approximate bounding boxes. Current Mistral table cells share a table-level bbox, so cell-level geometry cannot be assumed.

## 10. Table row classification

Normalize every cell with Unicode NFKC, lowercase, whitespace collapse, and punctuation trimming before classification. Preserve original text for provenance.

Classification order is deterministic:

### EMPTY

All cells are blank after normalization.

### COLUMN_HEADER

At least two different cells match known column concepts:

```text
description, unit, quantity, unit price, line total
```

### ORDINAL_HEADER

At least three cells form a column-number sequence or formula labels such as:

```text
1 | 2 | 3 | 4 | 5 | 6 = 4 x 5
```

### GRAND_TOTAL / SUBTOTAL / TAX / DISCOUNT / SHIPPING

At least one label cell matches a summary concept and at least one other cell contains a valid money value. Longest and most specific alias wins:

```text
"tổng tiền thuế"      → TAX
"cộng tiền hàng"      → SUBTOTAL
"chiết khấu"          → DISCOUNT
"phí vận chuyển"      → SHIPPING
"tổng cộng thanh toán"→ GRAND_TOTAL
"amount due"          → GRAND_TOTAL
```

Generic aliases such as `tổng tiền` do not override a longer tax/subtotal alias.

### DATA

A non-empty description plus:

- a valid quantity; and
- at least one valid unit price or line total.

### AMBIGUOUS

Any non-empty row not satisfying the preceding rules. Ambiguous rows do not become line items automatically.

## 11. Deterministic candidate extractors

All extractors return candidates. They never mutate the final field map directly.

### 11.1 ExactKeyValueExtractor

Handles one-block `label: value` pairs. It uses exact normalized aliases and longest-alias matching.

### 11.2 SectionAwareExtractor

Uses section context to disambiguate repeated labels:

```text
SELLER + tax code → vendor_tax_code
BUYER  + tax code → buyer_tax_code
HEADER + date     → invoice_date
SIGNATURE + date  → signature_date, not invoice_date
```

Buyer-only fields may remain extraction metadata when they are not part of the current canonical business schema.

### 11.3 TableItemExtractor

Processes only rows classified `DATA`. It never converts header, ordinal, empty, summary, or ambiguous rows into line items.

### 11.4 TableSummaryExtractor

For each summary row:

1. identify the canonical summary field from the most specific label;
2. select the rightmost valid money cell not used as a label;
3. cite both label and value block IDs;
4. use the minimum provider confidence of cited blocks;
5. set mapping score to `1.0` for exact aliases.

For `a.jpg`, it must emit:

```json
{
  "field_name": "total_amount",
  "raw_text": "9.000.000",
  "normalized_value": 9000000,
  "extraction_method": "TABLE_SUMMARY",
  "provider_confidence": 0.9926006933812204,
  "mapping_score": 1.0,
  "evidence_block_ids": [
    "P1-M0-P1-T0R9C0",
    "P1-M0-P1-T0R9C5"
  ]
}
```

### 11.5 SpatialKeyValueExtractor

For an exact label without an in-block value:

1. inspect valid right neighbors in distance order;
2. inspect valid below neighbors if no right value exists;
3. require the candidate to normalize to the expected field type;
4. cite label and value blocks;
5. reject candidates crossing section boundaries.

### 11.6 FuzzyLabelExtractor

Runs only when no exact deterministic candidate exists for the field.

- compare normalized label text, never values;
- require a conservative configurable threshold;
- use the same spatial binding rules as exact labels;
- keep `mapping_score` separate from provider confidence;
- mark output `NEEDS_CONFIRMATION` regardless of score;
- do not fuzzy-match invoice numbers, tax codes, PO IDs, or money values.

## 12. Candidate model

Extend `FieldCandidate` with:

```python
provider_confidence: Optional[float] = None
mapping_score: Optional[float] = None
section_role: Optional[str] = None
```

Existing `confidence` remains temporarily readable for backward compatibility and is deprecated in favor of `provider_confidence`. No combined confidence score is created.

Extraction methods are allow-listed:

```text
NATIVE_PDF_TEXT
EXACT_KEY_VALUE
SECTION_AWARE
TABLE_ITEM
TABLE_SUMMARY
EXACT_SPATIAL
FUZZY_SPATIAL
PROVIDER_ANNOTATION
LLM_ASSISTED
HUMAN
```

## 13. Candidate collection and resolution

Candidate store:

```python
dict[str, list[FieldCandidate]]
```

Resolution priority:

```text
HUMAN
> EXACT_KEY_VALUE / SECTION_AWARE / TABLE_SUMMARY / TABLE_ITEM
> EXACT_SPATIAL
> PROVIDER_ANNOTATION with evidence alignment
> FUZZY_SPATIAL
> grounded LLM
> MISSING
```

Rules:

1. Candidates with the same normalized value agree and may merge provenance.
2. Candidates with different normalized values produce `CONFLICTING`.
3. Provider confidence cannot resolve a semantic disagreement.
4. A lower-priority candidate cannot overwrite a higher-priority candidate.
5. A semantic candidate without aligned evidence blocks is rejected.
6. The selected candidate and all rejected/conflicting alternatives remain available for audit and evaluation.

## 14. Semantic fallback

Semantic mapping runs only for allow-listed unresolved fields after deterministic resolution.

### 14.1 Grounded LLM mapper

The mapper returns:

```json
{
  "field_name": "total_amount",
  "raw_text": "9.000.000",
  "block_ids": ["B41", "B42"]
}
```

It does not return normalized money, dates, quantities, IDs, confidence, policy, or business actions.

Validation requires:

- field name is unresolved and allow-listed;
- all cited block IDs exist;
- raw text appears in cited OCR blocks after whitespace normalization;
- deterministic normalization succeeds for the field type;
- output status is always `NEEDS_CONFIRMATION`.

LLM-assisted extraction remains disabled by default, preserving the accepted parent OCR invariant.

### 14.2 Mistral document annotation

Mistral OCR supports `document_annotation_format` with JSON Schema. It may be implemented behind the same semantic mapper interface. [Mistral Annotations](https://docs.mistral.ai/studio/document-processing/annotations)

Provider annotations are candidates, not final facts. Each annotated raw value must align back to one or more OCR blocks; otherwise it is rejected. Provider-specific annotation response shapes stop at the adapter.

## 15. Deterministic normalization and validation

Normalization remains authoritative for:

- integer VND money;
- ISO dates;
- non-negative integer quantities;
- IDs and tax codes;
- enum values.

Cross-field checks produce warnings/conflicts but never silently change values:

```text
quantity × unit_price = line_total
sum(line_total) = subtotal or total when no adjustments exist
subtotal + tax + shipping - discount = total_amount
seller tax code != buyer tax code
invoice date should not be sourced only from SIGNATURE when a HEADER date exists
```

When components required for an equation are absent, the equation is not assumed to pass.

## 16. Human confirmation

The existing Sprint 1 invariant remains unchanged: every critical header and line-item field must be confirmed, corrected, or marked unknown before business review.

The confirmation UI shows:

- selected candidate;
- extraction method;
- provider confidence;
- mapping score;
- section and evidence block IDs;
- conflicting alternatives;
- warnings;
- source highlight when geometry is available.

Human correction outranks all machine candidates and preserves the original candidate, actor, reason, and timestamp.

## 17. Audit events

Reuse the unified extraction audit and add candidate-resolution details to existing field events:

```json
{
  "field_name": "total_amount",
  "selected_method": "TABLE_SUMMARY",
  "selected_value": 9000000,
  "provider_confidence": 0.9926,
  "mapping_score": 1.0,
  "section_role": "SUMMARY",
  "evidence_block_ids": ["R9C0", "R9C5"],
  "alternative_count": 1,
  "conflict": false
}
```

Raw document bytes and secrets remain excluded.

## 18. Error handling

| Condition | Result |
| --- | --- |
| OCR text missing | `MISSING`; no invented value |
| Table row ambiguous | Exclude from line items; warning |
| Exact candidates disagree | `CONFLICTING`; human review |
| Fuzzy candidate below threshold | Discard |
| Semantic candidate lacks evidence | Reject |
| Normalization fails | `INVALID` |
| Arithmetic mismatch | Warning/conflict; preserve values |
| Provider annotation unavailable | Continue deterministic path |
| LLM unavailable | Continue without semantic candidate |

No extraction error becomes an Agent decision until reviewed evidence reaches the existing business pipeline.

## 19. Evaluation design

### 19.1 Existing set limitation

The current 15-document recorded set is not a generalization test:

- OCR01–OCR14 each contain six simple key-value blocks, eight table cells, and one line item;
- OCR15 contains the same header pattern and two line items;
- recorded mode reports 0 ms inference and does not measure live OCR quality;
- layout diversity is insufficient to select among mapping architectures.

### 19.2 Structure-generalization set

Create a separate bounded set with at least two documents for each layout family:

1. total in item-table footer;
2. total outside table;
3. subtotal + tax + discount + final total;
4. label above value;
5. multiple tables;
6. multi-page invoice;
7. seller/buyer duplicate labels;
8. signature date different from invoice date;
9. English-only alternative labels;
10. OCR-corrupted label text.

Use synthetic or consented/anonymized invoices. Keep development examples separate from final holdout examples.

### 19.3 Metrics

- section-classification accuracy;
- table-row-role precision/recall;
- line-item row precision/recall;
- critical-field extraction recall;
- field mapping precision;
- value-binding accuracy;
- normalized exact match;
- provenance coverage;
- conflict detection accuracy;
- semantic fallback invocation rate;
- human correction rate;
- false auto-confirm count.

Safety gates:

- false auto-confirm count must be zero on the evaluation set;
- every selected non-human field must have provenance;
- ambiguous and conflicting rows must not become routine line items;
- no expected labels or case IDs may enter production extraction logic.

## 20. Required regression cases

### `a.jpg`

Expected:

- exactly two line items;
- no ordinal or empty line items;
- `total_amount = 9_000_000` from row 9 label/value cells;
- seller tax code `0110329220`, not buyer tax code;
- invoice date sourced from the header date block when available;
- arithmetic `7_000_000 + 2_000_000 = 9_000_000` passes;
- all selected values retain evidence block IDs.

### Competing totals

Given subtotal, tax, discount, shipping, and final total, each must map to its own canonical field; `total_amount` must not come from subtotal or tax.

### Different section dates

When invoice header date and signature date differ, `invoice_date` must come from `HEADER`; signature date remains separate metadata.

### Fuzzy collision

`Tổng tiền thuế` must not map to final `total_amount` merely because it contains `tổng tiền`.

### Semantic fallback grounding

An LLM/provider candidate with a nonexistent block ID or uncited raw text must be rejected.

## 21. Acceptance criteria

1. `a.jpg` produces exactly the two real line items and the correct total candidate.
2. Ordinal headers, empty rows, summary rows, and ambiguous rows do not become line items.
3. Seller/buyer duplicate labels are mapped using section context rather than first occurrence alone.
4. Header dates outrank signature dates for `invoice_date`.
5. Exact table-summary extraction cites both label and value blocks.
6. Fuzzy matching applies only to labels and never auto-confirms a critical field.
7. Semantic fallback runs only for unresolved allow-listed fields and requires block grounding.
8. Conflicting candidate values remain explicit and require human review.
9. Provider confidence, mapping score, and validation status remain separate.
10. Every selected non-human candidate has provenance.
11. The heterogeneous layout evaluation reports all defined metrics and zero false auto-confirms.
12. Existing OCR/document, JSON review, Core Verify, Escalation Verify, and Full Verify tests remain green.

## 22. External references

- [Mistral OCR 4.1](https://docs.mistral.ai/models/ocr-4-1)
- [Mistral OCR API](https://docs.mistral.ai/api/endpoint/ocr)
- [Mistral Structured Annotations](https://docs.mistral.ai/studio/document-processing/annotations)

