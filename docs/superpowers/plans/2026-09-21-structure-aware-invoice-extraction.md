# Structure-Aware Invoice Field Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace brittle one-block `label:value` invoice mapping with a structure-aware, candidate-based extraction cascade that handles table summaries, repeated seller/buyer labels, split label/value blocks, fuzzy labels, explicit conflicts, and grounded semantic fallback.

**Architecture:** Keep OCR providers behind the existing `OCRDocument` boundary, derive deterministic sections/table-row roles/spatial relationships, let focused extractors produce candidates, resolve agreements and conflicts explicitly, and call semantic mapping only for unresolved fields. Deterministic normalization, provenance, and mandatory human confirmation remain authoritative.

**Tech Stack:** Python 3.12 standard library (`unicodedata`, `difflib`, `re`), existing dataclasses, Mistral/Paddle OCR adapters, Streamlit, pytest.

**Spec:** `docs/superpowers/specs/2026-09-21-structure-aware-invoice-extraction-design.md`

## Global Constraints

- Change only OCR block-to-field extraction and its presentation/evaluation surfaces.
- Do not replace or bypass the provider-neutral `OCRDocument` boundary.
- Do not change Policy v0, the three Agent actions, authority rules, deterministic business checks, or the Decision Guard.
- Use deterministic structure/rule extraction before semantic fallback.
- Use fuzzy matching only for labels, never for values, invoice IDs, tax codes, PO IDs, money, dates, or quantities.
- LLM/provider-annotation extraction remains disabled by default.
- Every semantic candidate must cite existing OCR blocks and verbatim raw text.
- Every critical field still requires Confirm, Correct, or Mark Unknown before `review()`.
- Never combine provider confidence, mapping score, and validation status into one score.
- Preserve conflicting alternatives; never silently choose by confidence.
- No new third-party fuzzy-matching dependency; use Python stdlib.
- Existing JSON review and OCR provider paths must remain backward compatible.
- Preserve unrelated worktree changes.
- Do not stage or commit unless the user explicitly authorizes that Git action. Each task ends with a review checkpoint and suggested commit message only.

## File map

```text
src/invoice_referee/domain/models.py
  Extend OCRBlock, FieldCandidate, InvoiceExtractionResult; add structure enums/contracts.

src/invoice_referee/ingestion/document_structure.py
  New deterministic section, table-row, and neighbor analysis.

src/invoice_referee/ingestion/candidate_resolver.py
  New candidate agreement, priority, provenance merge, and conflict handling.

src/invoice_referee/ingestion/invoice_fields.py
  Refactor into focused deterministic candidate extractors and orchestration.

src/invoice_referee/ingestion/ocr.py
  Preserve explicit table index/row/column metadata from providers.

src/invoice_referee/ingestion/llm_mapper.py
  Return grounded raw-text candidates; never normalized model values.

src/invoice_referee/ingestion/extraction_validation.py
  Validate separated confidence/mapping metadata and arithmetic/semantic warnings.

src/invoice_referee/audit/store.py
  Record selected method, scores, provenance, alternatives, and conflicts.

app/extraction_presentation.py + app/streamlit_app.py
  Show candidate source/conflicts and confirm line-item fields.

verify/structure_harness.py + tests/fixtures_structure/
  New heterogeneous recorded-block evaluation, separate from business Verify.
```

## Dependency graph

```text
Task 1 contracts/provider metadata
  ├─ Task 2 structure analyzer
  └─ Task 3 candidate resolver

Task 2 + Task 3
  ├─ Task 4 section/key-value/spatial extractors
  └─ Task 5 table item/summary extractors

Tasks 4 + 5
  └─ Task 6 extraction orchestration/validation
       ├─ Task 7 grounded semantic fallback
       └─ Task 8 audit/UI confirmation

Tasks 1–8
  └─ Task 9 heterogeneous evaluation
       └─ Task 10 end-to-end verification/docs
```

---

### Task 1: Add structure and candidate metadata contracts

**Files:**
- Modify: `src/invoice_referee/domain/models.py:485-570`
- Modify: `src/invoice_referee/ingestion/ocr.py`
- Modify: `tests/test_models.py`
- Modify: `tests/test_ocr_adapter.py`
- Modify: `tests/test_mistral_ocr.py`

**Interfaces:**
- Consumes: provider OCR blocks.
- Produces: explicit `table_index`, structure contracts, separated candidate scores, and candidate-set storage.

- [ ] **Step 1: Write failing contract tests**

```python
def test_ocr_block_preserves_table_identity():
    block = m.OCRBlock(
        block_id="P1-T2-R9-C5",
        page_number=1,
        text="9.000.000",
        confidence=0.99,
        bounding_box=m.BoundingBox(0.1, 0.1, 0.9, 0.2),
        block_type="TABLE_CELL",
        table_index=2,
        row_index=9,
        column_index=5,
    )
    assert (block.table_index, block.row_index, block.column_index) == (2, 9, 5)


def test_field_candidate_separates_provider_and_mapping_scores():
    candidate = _candidate(
        provider_confidence=0.99,
        mapping_score=0.91,
        section_role=m.SectionRole.SUMMARY.value,
    )
    assert candidate.provider_confidence == 0.99
    assert candidate.mapping_score == 0.91
    assert candidate.confidence == 0.99  # compatibility alias during migration


def test_extraction_result_candidate_sets_are_instance_local():
    first = m.InvoiceExtractionResult("DOC-A", m.ExtractionStatus.NEEDS_REVIEW)
    second = m.InvoiceExtractionResult("DOC-B", m.ExtractionStatus.NEEDS_REVIEW)
    first.field_candidates["total_amount"] = [_candidate()]
    assert second.field_candidates == {}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_models.py tests/test_ocr_adapter.py tests/test_mistral_ocr.py -k 'table_identity or separates_provider or candidate_sets' -v
```

Expected: missing attributes/types.

- [ ] **Step 3: Add structure enums and contracts**

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


@dataclass
class DocumentStructure:
    section_by_block_id: dict[str, SectionRole] = field(default_factory=dict)
    row_role_by_key: dict[tuple[int, int, int], TableRowRole] = field(default_factory=dict)
    blocks_by_table_row: dict[tuple[int, int, int], list["OCRBlock"]] = field(default_factory=dict)
    right_neighbor_by_block_id: dict[str, list[str]] = field(default_factory=dict)
    below_neighbor_by_block_id: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Extend OCRBlock and FieldCandidate compatibly**

```python
@dataclass
class OCRBlock:
    block_id: str
    page_number: int
    text: str
    confidence: float
    bounding_box: BoundingBox
    block_type: str
    row_index: Optional[int] = None
    column_index: Optional[int] = None
    table_index: Optional[int] = None


@dataclass
class FieldCandidate:
    # retain existing fields unchanged
    provider_confidence: Optional[float] = None
    mapping_score: Optional[float] = None
    section_role: Optional[str] = None

    def __post_init__(self) -> None:
        if self.provider_confidence is None:
            self.provider_confidence = self.confidence
        if self.confidence is None:
            self.confidence = self.provider_confidence
        for name, value in (
            ("provider_confidence", self.provider_confidence),
            ("mapping_score", self.mapping_score),
        ):
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
```

Append `table_index` after the existing optional fields so legacy positional construction of `row_index` and `column_index` retains its meaning. New code uses keyword arguments.

Add to `InvoiceExtractionResult`:

```python
field_candidates: dict[str, list[FieldCandidate]] = field(default_factory=dict)
line_item_candidate_sets: list[dict[str, list[FieldCandidate]]] = field(default_factory=list)
```

- [ ] **Step 5: Preserve table index in provider adapters**

Update Paddle and Mistral block mapping so every table cell gets `table_index`. Parse Mistral IDs with one strict helper:

```python
_TABLE_ID = re.compile(r"T(?P<table>\d+)(?:H|R)(?P<row>\d+)(?:C(?P<col>\d+))?$")


def parse_table_position(block_id: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
    match = _TABLE_ID.search(block_id)
    if not match:
        return None, None, None
    return (
        int(match.group("table")),
        int(match.group("row")),
        int(match.group("col")) if match.group("col") is not None else None,
    )
```

Provider-native row/column metadata wins over parsed IDs. Parsing is the compatibility path for current recorded Mistral fixtures.

- [ ] **Step 6: Run focused and provider regressions**

Run:

```bash
.venv/bin/pytest tests/test_models.py tests/test_ocr_adapter.py tests/test_mistral_ocr.py -v
```

- [ ] **Step 7: Review checkpoint**

Inspect graph callers of `OCRBlock` and `FieldCandidate`; verify all existing constructors remain valid. Suggested commit message if authorized: `feat: add structure-aware OCR contracts`.

---

### Task 2: Build deterministic document-structure analysis

**Files:**
- Create: `src/invoice_referee/ingestion/document_structure.py`
- Create: `tests/test_document_structure.py`

**Interfaces:**
- Consumes: `analyze_document_structure(document: OCRDocument) -> DocumentStructure`.
- Produces: sections, grouped table rows, row roles, and spatial neighbors.

- [ ] **Step 1: Add normalization and table-row fixture helpers**

```python
def normalize_label(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t\r\n:：()")


def table_cell(text, *, table=0, row=0, col=0, block_id=None):
    return m.OCRBlock(
        block_id=block_id or f"P1-T{table}-R{row}-C{col}",
        page_number=1,
        text=text,
        confidence=0.99,
        bounding_box=m.BoundingBox(0.1, 0.1, 0.9, 0.2),
        block_type="TABLE_CELL",
        table_index=table,
        row_index=row,
        column_index=col,
    )
```

- [ ] **Step 2: Write failing row-role tests from `a.jpg`**

```python
def test_classifies_a_jpg_table_rows():
    document = _a_jpg_structure_document()
    structure = analyze_document_structure(document)
    assert structure.row_role_by_key[(1, 0, 0)] is m.TableRowRole.COLUMN_HEADER
    assert structure.row_role_by_key[(1, 0, 1)] is m.TableRowRole.ORDINAL_HEADER
    assert structure.row_role_by_key[(1, 0, 2)] is m.TableRowRole.DATA
    assert structure.row_role_by_key[(1, 0, 3)] is m.TableRowRole.DATA
    for row in range(4, 9):
        assert structure.row_role_by_key[(1, 0, row)] is m.TableRowRole.EMPTY
    assert structure.row_role_by_key[(1, 0, 9)] is m.TableRowRole.GRAND_TOTAL
```

- [ ] **Step 3: Write seller/buyer/signature section tests**

```python
def test_duplicate_tax_labels_receive_different_sections():
    document = _document_with_seller_buyer_and_signature()
    structure = analyze_document_structure(document)
    assert structure.section_by_block_id["SELLER-TAX"] is m.SectionRole.SELLER
    assert structure.section_by_block_id["BUYER-TAX"] is m.SectionRole.BUYER
    assert structure.section_by_block_id["SIGN-DATE"] is m.SectionRole.SIGNATURE
```

- [ ] **Step 4: Write spatial-neighbor tests**

```python
def test_spatial_index_orders_same_section_right_then_below():
    document = _split_label_value_document()
    structure = analyze_document_structure(document)
    assert structure.right_neighbor_by_block_id["LABEL"] == ["RIGHT-NEAR", "RIGHT-FAR"]
    assert structure.below_neighbor_by_block_id["LABEL"] == ["BELOW"]
    assert "OTHER-SECTION" not in structure.right_neighbor_by_block_id["LABEL"]
```

- [ ] **Step 5: Run tests and verify failure**

Run `.venv/bin/pytest tests/test_document_structure.py -v`.

- [ ] **Step 6: Implement table grouping and classification order**

```python
def _group_table_rows(document: m.OCRDocument) -> dict[tuple[int, int, int], list[m.OCRBlock]]:
    rows: dict[tuple[int, int, int], list[m.OCRBlock]] = defaultdict(list)
    for block in document.blocks:
        if block.block_type != "TABLE_CELL":
            continue
        if block.table_index is None or block.row_index is None:
            continue
        rows[(block.page_number, block.table_index, block.row_index)].append(block)
    for cells in rows.values():
        cells.sort(key=lambda b: b.column_index if b.column_index is not None else 10_000)
    return dict(rows)
```

Implement `classify_table_row(cells)` in exact order: empty → column header → ordinal header → specific summary aliases → data → ambiguous. Use longest matching summary alias, with tax/subtotal aliases evaluated before generic total aliases.

- [ ] **Step 7: Implement section and neighbor analysis**

Identify item-table extent first. Classify seller/buyer anchors only before the item table; classify signature anchors after the item table; classify lookup/legal notices as footer. Build right/below neighbors only between blocks on the same page and in the same section.

Use constants:

```python
MIN_VERTICAL_OVERLAP = 0.50
MIN_HORIZONTAL_OVERLAP = 0.30
MAX_RIGHT_GAP = 0.20
MAX_BELOW_GAP = 0.12
```

These are prototype configuration and must be evaluated, not presented as universal geometry rules.

- [ ] **Step 8: Run structure tests**

Run `.venv/bin/pytest tests/test_document_structure.py -v`.

- [ ] **Step 9: Review checkpoint**

Confirm empty and ambiguous rows never receive `DATA`. Suggested commit message if authorized: `feat: analyze invoice document structure`.

---

### Task 3: Add candidate collection and explicit conflict resolution

**Files:**
- Create: `src/invoice_referee/ingestion/candidate_resolver.py`
- Create: `tests/test_candidate_resolver.py`

**Interfaces:**
- Consumes: `resolve_field_candidates(field_name, candidates) -> FieldResolution`.
- Produces: selected candidate, alternatives, and explicit conflict state.

- [ ] **Step 1: Define resolution contract in the resolver module**

```python
@dataclass
class FieldResolution:
    field_name: str
    selected: Optional[m.FieldCandidate]
    alternatives: list[m.FieldCandidate] = field(default_factory=list)
    conflicting: bool = False
```

Priority map:

```python
METHOD_PRIORITY = {
    "HUMAN": 0,
    "EXACT_KEY_VALUE": 10,
    "SECTION_AWARE": 10,
    "TABLE_SUMMARY": 10,
    "TABLE_ITEM": 10,
    "EXACT_SPATIAL": 20,
    "PROVIDER_ANNOTATION": 30,
    "FUZZY_SPATIAL": 40,
    "LLM_ASSISTED": 50,
}
```

- [ ] **Step 2: Write agreement/provenance merge tests**

```python
def test_equal_values_merge_provenance_without_conflict():
    exact = candidate(9_000_000, "TABLE_SUMMARY", ["LABEL", "VALUE"])
    annotation = candidate(9_000_000, "PROVIDER_ANNOTATION", ["VALUE"])
    resolution = resolve_field_candidates("total_amount", [annotation, exact])
    assert resolution.conflicting is False
    assert resolution.selected.extraction_method == "TABLE_SUMMARY"
    assert resolution.selected.evidence_block_ids == ["LABEL", "VALUE"]
    assert resolution.alternatives == [annotation]
```

- [ ] **Step 3: Write conflict tests**

```python
def test_different_values_are_conflicting_even_if_confidence_differs():
    high_conf_wrong = candidate(7_000_000, "PROVIDER_ANNOTATION", ["B1"], confidence=0.999)
    lower_conf_exact = candidate(9_000_000, "TABLE_SUMMARY", ["B2", "B3"], confidence=0.91)
    resolution = resolve_field_candidates("total_amount", [high_conf_wrong, lower_conf_exact])
    assert resolution.conflicting is True
    assert resolution.selected.normalized_value == 9_000_000
    assert resolution.selected.status is m.FieldStatus.CONFLICTING
```

- [ ] **Step 4: Implement deterministic resolution**

Sort candidates by method priority, then stable input order. Select the first valid candidate. Merge missing evidence IDs from agreeing candidates without changing selected method/scores. If any valid candidate has a different normalized value, set selected status to `CONFLICTING`, add a warning naming alternative methods, and preserve every alternative.

- [ ] **Step 5: Run resolver tests**

Run `.venv/bin/pytest tests/test_candidate_resolver.py -v`.

- [ ] **Step 6: Review checkpoint**

Verify provider confidence is never part of semantic conflict resolution. Suggested commit message if authorized: `feat: resolve extraction candidates explicitly`.

---

### Task 4: Implement section-aware header and spatial extraction

**Files:**
- Modify: `src/invoice_referee/ingestion/invoice_fields.py:20-108`
- Create: `tests/test_structure_aware_headers.py`
- Modify: `tests/test_invoice_fields.py`

**Interfaces:**
- Consumes: `extract_header_candidates(document, structure) -> dict[str, list[FieldCandidate]]`.
- Produces: exact key-value, section-aware, exact-spatial, and fuzzy-spatial candidates.

- [ ] **Step 1: Write seller/buyer tax-code tests**

```python
def test_seller_tax_code_uses_section_not_first_unscoped_match():
    document, structure = seller_buyer_document(buyer_first=True)
    candidates = extract_header_candidates(document, structure)
    assert candidates["vendor_tax_code"][0].normalized_value == "0110329220"
    assert candidates["vendor_tax_code"][0].section_role == "SELLER"
```

- [ ] **Step 2: Write header-date priority tests**

```python
def test_header_date_outranks_signature_date():
    document, structure = document_with_dates(
        header="Ngày (day) 10 tháng 07 năm 2023",
        signature="Ngày: 11/07/2023",
    )
    candidates = extract_header_candidates(document, structure)
    resolution = resolve_field_candidates("invoice_date", candidates["invoice_date"])
    assert resolution.selected.normalized_value == "2023-07-10"
    assert resolution.selected.section_role == "HEADER"
```

- [ ] **Step 3: Write split-block spatial tests**

```python
def test_exact_label_binds_value_in_right_neighbor():
    document, structure = split_total_document(label="Amount due", value="9.000.000")
    candidates = extract_header_candidates(document, structure)
    total = candidates["total_amount"][0]
    assert total.normalized_value == 9_000_000
    assert total.extraction_method == "EXACT_SPATIAL"
    assert total.evidence_block_ids == ["LABEL", "VALUE"]
```

- [ ] **Step 4: Write conservative fuzzy tests**

```python
def test_fuzzy_label_handles_small_ocr_error_but_never_tax_as_total():
    fuzzy = fuzzy_label_match("tỗng cộmg thanh toan", field_name="total_amount")
    assert fuzzy.score >= FUZZY_LABEL_THRESHOLD
    assert fuzzy_label_match("tổng tiền thuế", field_name="total_amount") is None
```

- [ ] **Step 5: Run tests and verify current failures**

Run:

```bash
.venv/bin/pytest tests/test_structure_aware_headers.py tests/test_invoice_fields.py -v
```

- [ ] **Step 6: Refactor aliases into exact concepts**

Expose one normalization dispatcher shared by deterministic and semantic extractors:

```python
MONEY_FIELDS = {"subtotal_amount", "tax_amount", "discount_amount", "shipping_amount", "total_amount"}
DATE_FIELDS = {"invoice_date", "signature_date"}


def normalize_candidate_value(field_name: str, raw_text: str):
    if field_name in MONEY_FIELDS:
        return norm.normalize_money(raw_text)
    if field_name in DATE_FIELDS:
        return norm.normalize_date(raw_text)
    if field_name == "invoiced_quantity":
        cleaned = re.sub(r"[^\d-]", "", raw_text)
        return int(cleaned) if cleaned and cleaned.lstrip("-").isdigit() else None
    return norm.normalize_id(raw_text)
```

Keep aliases data-only and longest-first. Separate summary concepts from header aliases:

```python
HEADER_ALIASES = {
    "invoice_number": ("số hóa đơn", "invoice number", "invoice no", "số"),
    "invoice_series": ("mẫu số - ký hiệu", "ký hiệu", "serial no", "series"),
    "vendor_tax_code": ("mã số thuế", "tax code", "tax id", "mst"),
    "po_id": ("purchase order", "po number", "po no", "số po", "đơn hàng"),
    "invoice_date": ("ngày hóa đơn", "invoice date", "ngày"),
    "total_amount": ("tổng cộng thanh toán", "total payment", "grand total", "amount due"),
}
```

Use `SequenceMatcher(None, normalized_label, alias).ratio()` for fuzzy label score. Start with `FUZZY_LABEL_THRESHOLD = 0.90`; mark every fuzzy candidate `NEEDS_CONFIRMATION`.

- [ ] **Step 7: Implement exact/section/spatial/fuzzy candidate generation**

Exact one-block candidates use `EXACT_KEY_VALUE`; seller/buyer/date role candidates use `SECTION_AWARE`; split-block candidates use `EXACT_SPATIAL`; unresolved labels above the threshold use `FUZZY_SPATIAL`. Every candidate records provider confidence, mapping score, section role, and cited blocks.

- [ ] **Step 8: Run header extraction regressions**

Run:

```bash
.venv/bin/pytest tests/test_structure_aware_headers.py tests/test_invoice_fields.py tests/test_mistral_ocr.py -v
```

- [ ] **Step 9: Review checkpoint**

Confirm fuzzy code never receives raw value strings for comparison. Suggested commit message if authorized: `feat: add section-aware invoice header extraction`.

---

### Task 5: Implement table item and summary extraction

**Files:**
- Modify: `src/invoice_referee/ingestion/invoice_fields.py:110-173`
- Create: `tests/test_structure_aware_tables.py`
- Create: `tests/fixtures_structure/a_jpg_blocks.json`

**Interfaces:**
- Consumes: `extract_table_candidates(document, structure) -> TableExtraction`.
- Produces: candidate sets for real line items and summary fields; excludes non-data rows.

Define the internal return type in `invoice_fields.py`:

```python
@dataclass
class TableExtraction:
    field_candidates: dict[str, list[m.FieldCandidate]] = field(default_factory=dict)
    selected_line_items: list[dict[str, m.FieldCandidate]] = field(default_factory=list)
    line_item_candidate_sets: list[dict[str, list[m.FieldCandidate]]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

- [ ] **Step 1: Add a minimal recorded-block fixture from `a.jpg`**

Store only blocks required to reproduce mapping behavior:

- row 0 column labels;
- row 1 ordinal labels;
- rows 2–3 real data;
- one representative empty row plus an empty-row count fixture;
- row 9 total label/value;
- seller/buyer tax blocks;
- header/signature dates.

Do not store raw image bytes or API credentials.

- [ ] **Step 2: Write the `a.jpg` regression**

```python
def test_a_jpg_yields_two_items_and_table_total(a_jpg_ocr_document):
    result = extract_invoice_fields(a_jpg_ocr_document)
    assert len(result.line_items) == 2
    assert result.line_items[0]["description"].normalized_value == "Khóa học thực hành kế toán tổng hợp"
    assert result.line_items[1]["description"].normalized_value == "Dịch vụ kế toán thuế quý 3/2023"
    assert result.fields["total_amount"].normalized_value == 9_000_000
    assert result.fields["total_amount"].extraction_method == "TABLE_SUMMARY"
    assert result.fields["total_amount"].evidence_block_ids == [
        "P1-M0-P1-T0R9C0",
        "P1-M0-P1-T0R9C5",
    ]
```

- [ ] **Step 3: Add non-data-row exclusion tests**

```python
def test_ordinal_empty_summary_and_ambiguous_rows_never_become_items(a_jpg_ocr_document):
    result = extract_invoice_fields(a_jpg_ocr_document)
    descriptions = [line["description"].normalized_value for line in result.line_items]
    assert "2" not in descriptions
    assert None not in descriptions
    assert "Tổng cộng tiền thanh toán (Total payment):" not in descriptions
```

- [ ] **Step 4: Add competing-summary tests**

```python
def test_specific_summary_labels_map_to_distinct_fields():
    document = summary_table_document(
        subtotal="8.000.000",
        tax="800.000",
        shipping="200.000",
        discount="0",
        grand_total="9.000.000",
    )
    result = extract_invoice_fields(document)
    assert result.fields["subtotal_amount"].normalized_value == 8_000_000
    assert result.fields["tax_amount"].normalized_value == 800_000
    assert result.fields["shipping_amount"].normalized_value == 200_000
    assert result.fields["total_amount"].normalized_value == 9_000_000
```

- [ ] **Step 5: Run tests and verify current failure**

Run `.venv/bin/pytest tests/test_structure_aware_tables.py -v`.

- [ ] **Step 6: Implement TableItemExtractor**

Use column concepts from `COLUMN_HEADER`; process only rows classified `DATA`; skip empty cells; create one candidate set per line-item field. Do not synthesize `item_id`; identity resolution remains separate.

- [ ] **Step 7: Implement TableSummaryExtractor**

For each summary row, select the most specific canonical summary field and the rightmost valid money cell. Cite label and value blocks, use minimum cited provider confidence, and assign `mapping_score=1.0` for exact aliases.

- [ ] **Step 8: Run table and arithmetic regressions**

Run:

```bash
.venv/bin/pytest tests/test_structure_aware_tables.py tests/test_invoice_fields.py tests/test_extraction_validation.py -v
```

- [ ] **Step 9: Review checkpoint**

Confirm no row role except `DATA` can create a line item. Suggested commit message if authorized: `feat: extract invoice table items and summaries structurally`.

---

### Task 6: Integrate structure analysis, candidate resolution, and validation

**Files:**
- Modify: `src/invoice_referee/ingestion/invoice_fields.py`
- Modify: `src/invoice_referee/ingestion/extraction_validation.py`
- Modify: `tests/test_invoice_fields.py`
- Modify: `tests/test_extraction_validation.py`

**Interfaces:**
- Consumes: `extract_invoice_fields(document: OCRDocument) -> InvoiceExtractionResult` unchanged.
- Produces: selected fields/line items plus complete candidate sets and conflicts.

- [ ] **Step 1: Write candidate-set integration tests**

```python
def test_extract_invoice_fields_preserves_selected_and_alternatives(conflicting_total_document):
    result = extract_invoice_fields(conflicting_total_document)
    assert result.fields["total_amount"].status is m.FieldStatus.CONFLICTING
    assert len(result.field_candidates["total_amount"]) == 2
    assert {c.normalized_value for c in result.field_candidates["total_amount"]} == {
        7_000_000,
        9_000_000,
    }
```

- [ ] **Step 2: Write separated-confidence validation tests**

```python
def test_fuzzy_mapping_requires_confirmation_even_with_high_ocr_confidence(candidate_factory):
    candidate = candidate_factory(
        extraction_method="FUZZY_SPATIAL",
        provider_confidence=0.999,
        mapping_score=0.92,
    )
    result = extraction_result(total_amount=candidate)
    validate_extraction(result)
    assert candidate.status is m.FieldStatus.NEEDS_CONFIRMATION
```

- [ ] **Step 3: Refactor extraction orchestration**

Implement candidate-set merge without overwriting:

```python
def merge_candidate_sets(
    *sources: dict[str, list[m.FieldCandidate]],
) -> dict[str, list[m.FieldCandidate]]:
    merged: dict[str, list[m.FieldCandidate]] = defaultdict(list)
    for source in sources:
        for field_name, candidates in source.items():
            merged[field_name].extend(candidates)
    return dict(merged)
```

```python
def extract_invoice_fields(document: m.OCRDocument) -> m.InvoiceExtractionResult:
    structure = analyze_document_structure(document)
    header_sets = extract_header_candidates(document, structure)
    table = extract_table_candidates(document, structure)

    field_sets = merge_candidate_sets(header_sets, table.field_candidates)
    resolutions = {
        name: resolve_field_candidates(name, candidates)
        for name, candidates in field_sets.items()
    }

    return m.InvoiceExtractionResult(
        document_id=document.document_id,
        status=m.ExtractionStatus.NEEDS_REVIEW,
        fields={name: r.selected for name, r in resolutions.items() if r.selected is not None},
        line_items=table.selected_line_items,
        field_candidates=field_sets,
        line_item_candidate_sets=table.line_item_candidate_sets,
        warnings=list(structure.warnings),
    )
```

- [ ] **Step 4: Update extraction validation**

Treat `FUZZY_SPATIAL`, `PROVIDER_ANNOTATION`, and `LLM_ASSISTED` as always `NEEDS_CONFIRMATION`. Preserve pre-existing `CONFLICTING`. Use `provider_confidence` for OCR-threshold checks; never substitute mapping score.

- [ ] **Step 5: Add cross-field semantic warnings**

Add warnings for seller/buyer tax-code equality and signature-only invoice date. Extend arithmetic validation to subtotal/tax/shipping/discount only when all required components are present; never infer missing components as zero except an explicitly extracted zero.

- [ ] **Step 6: Run focused extraction suites**

Run:

```bash
.venv/bin/pytest tests/test_document_structure.py tests/test_candidate_resolver.py tests/test_structure_aware_headers.py tests/test_structure_aware_tables.py tests/test_invoice_fields.py tests/test_extraction_validation.py -v
```

- [ ] **Step 7: Review checkpoint**

Trace all callers of `extract_invoice_fields` and confirm its public signature remains unchanged. Suggested commit message if authorized: `refactor: integrate structure-aware field candidates`.

---

### Task 7: Ground semantic fallback in raw OCR evidence

**Files:**
- Modify: `src/invoice_referee/ingestion/llm_mapper.py:25-129`
- Modify: `src/invoice_referee/services/extractor.py:31-73`
- Modify: `tests/test_llm_mapper.py`
- Modify: `tests/test_extractor_service.py`

**Interfaces:**
- Consumes: `map_unresolved_fields(document, unresolved_names, client) -> list[FieldCandidate]` unchanged.
- Produces: raw-text semantic candidates added to candidate sets, not direct field overwrites.

- [ ] **Step 1: Change tests from normalized `value` to grounded `raw_text`**

```python
def test_semantic_mapper_normalizes_only_after_grounding(ocr_document):
    client = FakeClient(json.dumps({
        "mappings": [{
            "field_name": "total_amount",
            "raw_text": "9.000.000",
            "block_ids": ["BLK-TOTAL"],
        }]
    }))
    candidate = map_unresolved_fields(ocr_document, ["total_amount"], client)[0]
    assert candidate.raw_text == "9.000.000"
    assert candidate.normalized_value == 9_000_000
    assert candidate.extraction_method == "LLM_ASSISTED"
    assert candidate.status is m.FieldStatus.NEEDS_CONFIRMATION
```

- [ ] **Step 2: Add grounding rejection tests**

Reject nonexistent block IDs, unrequested fields, raw text absent from cited blocks, and normalized values supplied without verbatim raw text.

- [ ] **Step 3: Update prompt schema**

```python
SYSTEM_INSTRUCTION = (
    "Map untrusted OCR blocks to allowed invoice fields. Return raw text copied "
    "verbatim from cited block_ids. Never normalize, compute, infer, or invent. "
    'Return {"mappings":[{"field_name":str,"raw_text":str,"block_ids":[str]}]}.'
)
```

- [ ] **Step 4: Deterministically normalize by field type**

Reuse the same normalization dispatcher as deterministic candidates. Set `provider_confidence` to the minimum confidence of cited OCR blocks, `mapping_score=None`, and `section_role` from the cited label block when unambiguous.

- [ ] **Step 5: Merge semantic candidates through CandidateResolver**

Change `merge_llm_candidates` to append into `result.field_candidates`, rerun resolution for affected fields, and preserve deterministic alternatives. It must not overwrite `result.fields[name]` directly.

- [ ] **Step 6: Keep the feature flag off by default**

Verify `extract_invoice(..., enable_llm_mapping=False)` makes no semantic call. When enabled, request only unresolved allow-listed fields after deterministic resolution.

- [ ] **Step 7: Run semantic/service tests**

Run:

```bash
.venv/bin/pytest tests/test_llm_mapper.py tests/test_extractor_service.py -v
```

- [ ] **Step 8: Review checkpoint**

Confirm the semantic mapper cannot output policy, action, authority, or normalized money. Suggested commit message if authorized: `fix: ground semantic OCR mappings in raw blocks`.

---

### Task 8: Expose alternatives, conflicts, and line-item confirmation in UI/audit

**Files:**
- Modify: `app/extraction_presentation.py`
- Modify: `app/streamlit_app.py:138-188`
- Modify: `src/invoice_referee/audit/store.py:97-132`
- Modify: `tests/test_extraction_presentation.py`
- Modify: `tests/test_app_smoke.py`
- Modify: `tests/test_audit.py`

**Interfaces:**
- Consumes: selected candidates plus candidate sets.
- Produces: complete header/line-item review controls and auditable alternatives/conflicts.

- [ ] **Step 1: Add presentation row tests**

```python
def test_field_rows_show_method_scores_section_and_conflict(conflicting_result):
    row = ep.field_rows(conflicting_result)[0]
    assert row["Method"] == "TABLE_SUMMARY"
    assert row["OCR confidence"] == pytest.approx(0.99)
    assert row["Mapping score"] == pytest.approx(1.0)
    assert row["Section"] == "SUMMARY"
    assert row["Alternatives"] == 1
    assert row["Status"] == "CONFLICTING"
```

- [ ] **Step 2: Add line-item review control tests**

```python
def test_build_field_reviews_includes_every_line_item_cell(reviewed_form_result):
    reviews = ep.build_field_reviews(reviewed_form_result.form_values, reviewed_form_result.result)
    assert "line_items[0].invoiced_quantity" in reviews
    assert "line_items[0].unit_price" in reviews
    assert "line_items[0].line_total" in reviews
```

- [ ] **Step 3: Extend pure presentation helpers**

Show selected method, provider confidence, mapping score, section, evidence IDs, warning text, and alternative count. Add an alternatives expander data structure containing method, raw/normalized value, and provenance.

- [ ] **Step 4: Render controls for header and line-item candidates**

Refactor `_render_extraction_review()` to use pure helper-generated review keys for both:

```text
header_field
line_items[0].field
line_items[1].field
```

Do not call business review unless `apply_field_reviews()` returns `ExtractionStatus.REVIEWED`.

- [ ] **Step 5: Extend audit field details**

Extend the helper signature compatibly:

```python
def record_field_event(
    self,
    event_type: str,
    candidate: m.FieldCandidate,
    *,
    actor: str = "InvoiceReferee",
    reason: Optional[str] = None,
    alternatives: Optional[list[m.FieldCandidate]] = None,
) -> m.AuditEvent:
    alternatives = list(alternatives or [])
```

Record:

```python
details={
    "field_name": candidate.field_name,
    "normalized_value": candidate.normalized_value,
    "selected_method": candidate.extraction_method,
    "provider_confidence": candidate.provider_confidence,
    "mapping_score": candidate.mapping_score,
    "section_role": candidate.section_role,
    "evidence_block_ids": list(candidate.evidence_block_ids),
    "alternative_count": len(alternatives),
    "conflict": candidate.status is m.FieldStatus.CONFLICTING,
}
```

- [ ] **Step 6: Add AppTest regression**

Use an injected recorded engine and assert a line-item field appears as a review control. Submit without reviewing one critical line field and assert business `review()` is not called.

- [ ] **Step 7: Run UI/audit suites**

Run:

```bash
.venv/bin/pytest tests/test_extraction_presentation.py tests/test_app_smoke.py tests/test_audit.py tests/test_reviewed_evidence.py -v
```

- [ ] **Step 8: Review checkpoint**

Confirm the UI no longer proceeds while extraction status is `NEEDS_REVIEW`. Suggested commit message if authorized: `feat: review extraction conflicts and line items`.

---

### Task 9: Create a heterogeneous structure-generalization harness

**Files:**
- Create: `tests/fixtures_structure/generate.py`
- Create: `tests/fixtures_structure/manifest.json`
- Create: `tests/fixtures_structure/recorded/` (20 generated OCRDocument JSON fixtures)
- Create: `verify/structure_harness.py`
- Create: `tests/test_structure_harness.py`

**Interfaces:**
- Consumes: recorded provider-neutral OCR blocks and independent ground truth.
- Produces: structure/mapping/provenance/conflict/generalization metrics.

- [ ] **Step 1: Define manifest schema**

```json
{
  "ST01": {
    "family": "TABLE_FOOTER_TOTAL",
    "recorded": "recorded/ST01.json",
    "expected": {
      "row_roles": {"1:0:9": "GRAND_TOTAL"},
      "fields": {"total_amount": 9000000},
      "line_item_count": 2,
      "selected_evidence": {
        "total_amount": ["R9C0", "R9C5"]
      }
    }
  }
}
```

Expected values remain outside production modules.

- [ ] **Step 2: Generate two fixtures for each layout family**

Generate 20 provider-neutral recorded block fixtures covering:

1. table-footer total;
2. total outside table;
3. subtotal/tax/discount/final total;
4. label above value;
5. multiple tables;
6. multi-page invoice;
7. seller/buyer duplicate labels;
8. different header/signature dates;
9. English alternative labels;
10. OCR-corrupted label text.

Include one fixture derived from the minimal `a.jpg` block set. Generate deterministic block IDs, coordinates, confidence, table indices, rows, and columns.

- [ ] **Step 3: Write metric tests**

```python
def test_harness_reports_zero_false_auto_confirms(results):
    summary = summarize(results)
    assert summary.false_auto_confirm_count == 0


def test_harness_requires_provenance_for_selected_fields(results):
    assert all(result.provenance_ok for result in results)


def test_every_layout_family_has_two_cases(manifest):
    counts = Counter(case["family"] for case in manifest.values())
    assert set(counts.values()) == {2}
```

- [ ] **Step 4: Implement harness results**

Per case report:

```text
CASE | FAMILY | ROW ROLES | ITEMS | FIELDS | BINDING | PROVENANCE | CONFLICTS | PASS
```

Summary reports section accuracy, row-role precision/recall, line-item precision/recall, field recall, field precision, binding accuracy, normalized exact match, provenance coverage, conflict accuracy, semantic fallback rate, human-review rate, and false auto-confirms.

Add an optional live diagnostic CLI that never changes expected labels:

```python
parser.add_argument("--live-file", type=Path)
parser.add_argument("--expected-case", default="ST01")
```

When `--live-file` is present, validate/render the file, call `engine_from_env()`, run structure-aware extraction, and compare it with the selected manifest case. Print engine/model version and latency. Do not persist raw document bytes or provider responses.

- [ ] **Step 5: Run generator and harness**

Run:

```bash
.venv/bin/python tests/fixtures_structure/generate.py
.venv/bin/pytest tests/test_structure_harness.py -v
.venv/bin/python -m verify.structure_harness
```

- [ ] **Step 6: Review checkpoint**

Confirm recorded fixtures are provider-neutral and production code never imports the manifest. Suggested commit message if authorized: `test: add structure-generalization evaluation`.

---

### Task 10: Run full regression and update canonical documentation

**Files:**
- Create: `tests/test_a_jpg_structure_regression.py`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/DATA_MODEL.md`
- Modify: `docs/DECISION_FLOW.md`
- Modify: `docs/EVALUATION_PLAN.md`
- Modify: `docs/BUILD_LOG.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: complete structure-aware extraction implementation.
- Produces: fresh verification evidence and documented limitations.

- [ ] **Step 1: Add the final `a.jpg` recorded-block regression**

```python
def test_a_jpg_structure_regression(a_jpg_ocr_document):
    result = validate_extraction(extract_invoice_fields(a_jpg_ocr_document))
    assert len(result.line_items) == 2
    assert result.fields["total_amount"].normalized_value == 9_000_000
    assert result.fields["vendor_tax_code"].normalized_value == "0110329220"
    assert result.fields["invoice_date"].normalized_value == "2023-07-11"
    assert result.fields["total_amount"].evidence_block_ids == [
        "P1-M0-P1-T0R9C0",
        "P1-M0-P1-T0R9C5",
    ]
    assert not any(line["description"].normalized_value in (None, "2") for line in result.line_items)
```

- [ ] **Step 2: Run all focused extraction suites**

Run:

```bash
.venv/bin/pytest tests/test_models.py tests/test_ocr_adapter.py tests/test_mistral_ocr.py tests/test_document_structure.py tests/test_candidate_resolver.py tests/test_structure_aware_headers.py tests/test_structure_aware_tables.py tests/test_invoice_fields.py tests/test_extraction_validation.py tests/test_llm_mapper.py tests/test_extractor_service.py tests/test_extraction_presentation.py tests/test_reviewed_evidence.py tests/test_audit.py tests/test_app_smoke.py tests/test_structure_harness.py tests/test_a_jpg_structure_regression.py -v
```

- [ ] **Step 3: Run the full product regression**

Run:

```bash
.venv/bin/pytest -v
.venv/bin/python -m verify.harness --suite core
.venv/bin/python -m verify.harness --suite escalation
.venv/bin/python -m verify.harness --suite all
.venv/bin/python -m verify.ocr_harness
.venv/bin/python -m verify.structure_harness
```

Expected: all commands exit zero; business expected labels remain unchanged.

- [ ] **Step 4: Run one live OCR diagnostic on `a.jpg` when locally available**

Run:

```bash
.venv/bin/python -m verify.structure_harness --live-file a.jpg --expected-case ST01
```

The command runs the configured OCR provider, saves no raw document bytes, and compares block-to-candidate behavior with the recorded regression. If `a.jpg` is absent, report the live diagnostic as not run rather than fabricating evidence.

- [ ] **Step 5: Update documentation with measured evidence only**

Document:

- structure-analysis boundary;
- extractor/candidate priority;
- separate provider confidence and mapping score;
- conflict and semantic-grounding behavior;
- mandatory human confirmation;
- current heterogeneous evaluation metrics;
- existing recorded-set limitations;
- actual test counts and commands;
- unsupported layouts and known failure modes.

- [ ] **Step 6: Final review checkpoint**

Run `rtk git status --short`, inspect every changed path, and preserve unrelated files. Suggested commit message if the user authorizes a commit: `feat: add structure-aware invoice extraction`.

---

## Execution checkpoints

- After Task 1: provider metadata and candidate scores are explicit without breaking current constructors.
- After Task 2: sections, row roles, and spatial neighbors are deterministic and independently tested.
- After Task 3: candidates can agree/conflict without silent overwrites.
- After Task 5: `a.jpg` block structure yields exactly two items and the correct table total.
- After Task 7: semantic fallback is grounded in raw text and remains feature-flagged.
- After Task 8: every critical header and line-item field can be reviewed in UI.
- After Task 9: generalization is measured across 10 layout families instead of one template.
- After Task 10: all extraction and business verification evidence is fresh.
