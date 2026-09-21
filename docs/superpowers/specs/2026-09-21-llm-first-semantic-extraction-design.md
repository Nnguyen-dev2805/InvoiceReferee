# LLM-First Semantic Extraction Design

**Status:** implemented (2026-09-21). Supersedes the whole of
`2026-09-21-structure-aware-invoice-extraction-design.md`: its label/layout mapper
and its `DocumentStructure` / `SectionRole` / `TableRowRole` / candidate-resolver
contracts were **removed**, not reused. Only `FieldCandidate` and the validation
cascade survive, because they carry no label knowledge.

## 1. Decision summary

Production extraction becomes **OCR → LLM semantic mapping → grounding verifier →
deterministic normalization/validation**. The rule/fuzzy label mapper was **deleted
outright** — there is no fallback extractor. The LLM is an *extractor*: it may only
cite OCR blocks, and every value it returns is re-derived by code.

Nothing downstream changes: 8 deterministic checks, Policy v0, Decision Guard,
and the three Agent actions are untouched.

## 2. Root cause this removes

The deterministic extractor must *guess which label means what*. Every new layout
adds an alias, a column concept, or a fuzzy threshold. `a.jpg` alone needed ten
layout families of fixtures. Two costs are structural, not incidental:

- Vietnamese receipts print `ĐG` / `TT` / `SL`, which are ambiguous abbreviations
  with no general rule; `Tổng cộng` vs `Tổng thanh toán` vs `Cộng tiền hàng` are
  distinguished only by a hand-maintained alias table.
- A receipt and an invoice share label vocabulary but not meaning. `Số:` is an
  invoice number on an invoice and a receipt number on a receipt; the alias table
  cannot express that, because the disambiguating fact is *document type*.

Document type is a semantic judgement. That is exactly what the LLM supplies and
the rule table cannot.

## 3. Architecture

```text
Image/PDF
→ Mistral OCR 4.1                      (unchanged; ocr.py)
→ OCRDocument: blocks + bbox + confidence
→ LLM semantic extraction              (new: ingestion/semantic_extraction.py)
→ grounding verifier                   (new: ingestion/grounding.py, pure)
→ deterministic normalization          (existing: normalization.py)
→ deterministic validation             (existing: extraction_validation.py)
→ human confirmation                   (existing: pipeline.py)
→ canonical evidence
   ├─ SUPPLIER_INVOICE → review()      (existing PO/GR/payment path)
   └─ receipt types    → human review only, never review()
```

Module boundaries:

| Module | Responsibility | New? |
| --- | --- | --- |
| `domain/models.py` | `DocumentType`, `MerchantReceipt`, receipt line-item profile, `InvoiceExtractionResult.document_type` | extended |
| `ingestion/semantic_extraction.py` | prompt, strict-JSON parse, allow-list profiles, semantic → `FieldCandidate` | new |
| `ingestion/grounding.py` | citation verifier: block exists, raw text verbatim, field allow-listed, no forbidden keys | new |
| `ingestion/pipeline.py` | human confirmation; `reviewed_extraction_to_evidence` routes by type and refuses a receipt | extended |
| `services/extractor.py` | the only extractor call site; fails closed with no client | extended |
| `ingestion/field_normalization.py` | raw grounded text -> typed value, by field name | new (moved out of `invoice_fields`) |

## 4. Domain contract changes

```python
class DocumentType(str, Enum):
    SUPPLIER_INVOICE = "SUPPLIER_INVOICE"
    RESTAURANT_RECEIPT = "RESTAURANT_RECEIPT"
    TEMPORARY_BILL = "TEMPORARY_BILL"
    POS_RECEIPT = "POS_RECEIPT"
    UNKNOWN = "UNKNOWN"
```

`InvoiceExtractionResult.document_type: DocumentType = DocumentType.UNKNOWN` —
appended with a default so every existing construction keeps working.

Field profiles (allow-lists; a field outside the profile for the detected type is
**rejected**, not coerced):

```text
SUPPLIER_INVOICE
  vendor_tax_code buyer_tax_code invoice_series invoice_number
  invoice_date subtotal_amount tax_amount total_amount po_id

RESTAURANT_RECEIPT / TEMPORARY_BILL / POS_RECEIPT
  merchant_name receipt_number receipt_datetime table_number cashier_name
  subtotal_amount tax_amount total_amount
```

`MerchantReceipt` carries receipt evidence out of extraction. It is a *separate*
contract from `SupplierInvoice` precisely so a receipt cannot be mistaken for one:
the legacy `reviewed_invoice_to_evidence` only ever builds an `invoice` key, so a
receipt routed through it would be silently mislabelled. The type-aware
`reviewed_extraction_to_evidence` therefore routes explicitly and raises
`UnsupportedDocumentTypeError` for a receipt (unless `allow_receipt=True`) or for
`UNKNOWN`.

`po_id` is on the invoice profile even though the spec's field list omitted it: it
is a critical field printed on real invoices, and leaving it out meant every
LLM-extracted invoice was silently incomplete. A test now asserts
`CRITICAL_FIELDS - profile == {"vendor_id"}`.

## 5. Grounding rules (all fail closed)

A semantic mapping is accepted only if **all** hold; otherwise it is dropped and
recorded in `SemanticExtraction.rejected` with a reason — never silently lost.

1. `block_id` exists in the `OCRDocument`.
2. `raw_text` occurs verbatim in the text of the cited blocks, bounded by a
   non-alphanumeric character (or a currency marker such as `đ`). The boundary
   matters: plain substring containment would let `"3"` "ground" against
   `"Số hóa đơn: 0000123"`. This single rule also enforces "no normalized values,
   no arithmetic, no OCR correction": a model returning `9000000` for a block
   reading `9.000.000` fails rule 2.
3. `field_name` is in the allow-list for the detected document type.
4. The response contains no forbidden key (`vendor_id`, `item_id`, `po_id`,
   `policy_rule_ids`, `action`, `proposed_action`, `decision`, `approved_total`).
   A forbidden key rejects the **whole** response — a model that emits policy
   output is not a model whose other output should be trusted.
5. `document_type` itself cites an existing block.

`document_type == UNKNOWN` ⇒ no invoice/receipt fields are accepted; the result
keeps raw OCR evidence and goes to human review.

## 6. What is auto-accepted vs. human-reviewed

`LLM_ASSISTED` candidates are `NEEDS_CONFIRMATION` by construction, and
`extraction_validation` has always forced that regardless of confidence. Invariant
19 ("a human must confirm every critical field") is therefore preserved: **no
field is auto-accepted on the LLM path.** Auto-accept remains reachable only for
exact deterministic methods, which the LLM-first path does not use. Fail-closed
conditions (ungrounded, unparseable, conflicting, `UNKNOWN` type) add a *second*
gate on top of that, not a relaxation of it.

## 7. Rule-based mappers that leave the production LLM path

`extract_invoice` calls **only** `semantic_extraction.extract_semantics`. The
following modules were **deleted from `src/`** and no longer exist anywhere on the
production path:

- `HEADER_ALIASES` / `LINE_COLUMNS` label matching (`Tổng cộng` → `total_amount`,
  `ĐG` → `unit_price`, `TT` → `line_total`)
- `fuzzy_label_match` and `FUZZY_LABEL_THRESHOLD`
- `_section_aware_candidates` / `_exact_spatial_candidates` position heuristics
- `document_structure._COLUMN_CONCEPTS` / `_SUMMARY_ALIASES` column mapping
- `llm_mapper.map_unresolved_fields` (the legacy unresolved-field fallback)
- `document_structure.analyze_document_structure` and the whole `DocumentStructure`
  / `SectionRole` / `TableRowRole` contract
- `candidate_resolver.resolve_field_candidates` and `METHOD_PRIORITY`

They were removed rather than kept as a baseline: a baseline that can no longer be
called from production cannot be compared against in production, and keeping the
alias tables in the tree invited their reuse. The normalization functions they
contained were the one part still needed, and moved to `field_normalization.py`.

## 8. Evidence: the real fixtures

`a.jpg` — a Vietnamese supplier invoice (2 line items, total 9.000.000, one tax
block read as the seller's). Recorded at `tests/fixtures_structure/a_jpg_blocks.json`.

`b.jpg` — **the task spec's `b.jpg` is `data/image/sen_non_bo.jpg`** (`SEN NAM BỘ`),
recovered from git blob `f2e0be798564e670d0f304af6f4a511734a9296f` (commit
`703e03b`). Live Mistral OCR 4.1 reproduces the spec's values exactly:
`PHIẾU TẠM TĨNH` (`P1-BLK0003`), `Số: 2627003876` (`P1-BLK0004`),
`Tổng thanh toán 4.035.570đ` (`P1-BLK0013`), and a real table
`Tên món | SL | ĐG | TT` as `TABLE_CELL` blocks. Recorded at
`tests/fixtures_structure/b_jpg_blocks.json` (60 blocks, 40 table cells).

Its arithmetic is exact and therefore usable by deterministic verification:
`12.000+30.000+45.000+2.016.000+420.750+775.000+105.000+195.000+100.000 =
3.698.750` matches the printed `Tiền hàng 3.698.750đ`, and
`3.698.750 + 336.820 = 4.035.570` matches `Tổng thanh toán`.

Note the OCR reads `TĨNH` for `TÍNH` — a real provider error, left in the fixture
as recorded. It is why the type classifier must tolerate OCR-corrupted labels
rather than matching one exact spelling.

Recording is reproducible via `python -m tests.fixtures_structure.record_live_blocks`;
the image bytes and raw provider response are never stored.

## 9. Non-goals

- No change to `checks/`, `policy/`, `decision/guard.py`, `agent/service.py`.
- Receipts do not enter `review()`; no PO-based check ever sees a receipt.
- No fuzzy matching of values, no confidence-based guessing, no LLM-supplied
  normalization.
- No new policy rule, no fourth action, no change to the authority threshold.
