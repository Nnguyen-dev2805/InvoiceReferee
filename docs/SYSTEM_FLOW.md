# InvoiceReferee — System Flow

Sơ đồ kiến trúc và luồng dữ liệu của toàn hệ thống (Sprint 1), khớp với mã nguồn
hiện tại. Có 2 đường vào: **JSON có cấu trúc** và **OCR tài liệu** (Supplier
Invoice PDF/ảnh). Cả hai đều đổ về đúng một `review()` production. OCR chỉ trích
fact ứng viên, con người xác nhận, quyết định cuối luôn do Decision Guard.

---

## 1. Toàn cảnh (end-to-end)

```mermaid
flowchart TD
    subgraph INPUT["Đầu vào"]
        J["JSON có cấu trúc<br/>(sample / paste / upload)"]
        D["Tài liệu Supplier Invoice<br/>PDF / PNG / JPEG"]
    end

    subgraph OCRPATH["Đường OCR (services/extractor.extract_invoice)"]
        V["file_validation<br/>magic-byte, size, pages, encrypted"]
        R["document_router + pdf_renderer<br/>PDF→ảnh 300DPI / ảnh→RGB PNG"]
        P["image_preprocessing<br/>EXIF, RGB, deskew 0.5–10°"]
        E["OCREngine.analyze()<br/>Paddle local / Mistral hosted"]
        F["invoice_fields<br/>block → field + line item + provenance"]
        ID["identity_resolution<br/>tax-code/SKU khớp chính xác"]
        VAL["extraction_validation<br/>confidence / conflict / LLM"]
        HC["Con người xác nhận<br/>confirm / correct / mark-unknown"]
        CONV["reviewed_invoice_to_evidence<br/>→ evidence JSON (source_type=OCR)"]
    end

    subgraph REVIEW["Đường business (services/reviewer.review)"]
        BT["build_transaction<br/>+ evidence_issues"]
        CHK["run_checks<br/>8 check tất định"]
        POL["build_policy_context<br/>tri-state scope + authority"]
        ASSESS["agent.assess (LLM)<br/>đề xuất có cấu trúc"]
        GUARD["decision.guard<br/>resolve_action là chân lý"]
        DEC(["Decision:<br/>AUTO_PROCESS / REQUEST_INFO / ESCALATE"])
    end

    AUD[("Audit timeline<br/>append-only, 1 chuỗi ID")]

    J --> BT
    D --> V --> R --> P --> E --> F --> ID --> VAL --> HC --> CONV --> BT
    BT --> CHK --> POL --> ASSESS --> GUARD --> DEC

    OCRPATH -.ghi sự kiện.-> AUD
    REVIEW -.ghi sự kiện.-> AUD
    DEC -.->|Stop / Override| AUD

    classDef ocr fill:#e8f0fe,stroke:#4285f4;
    classDef rev fill:#e6f4ea,stroke:#34a853;
    classDef dec fill:#fef7e0,stroke:#f9ab00;
    class V,R,P,E,F,ID,VAL,HC,CONV ocr;
    class BT,CHK,POL,ASSESS,GUARD rev;
    class DEC dec;
```

---

## 2. Đường OCR chi tiết (ảnh/PDF → evidence)

```mermaid
flowchart TD
    U["UploadedDocument<br/>(bytes + sha256)"] --> VAL{"validate_upload<br/>hợp lệ?"}
    VAL -->|"không"| ERR["DocumentInputError<br/>(lỗi kỹ thuật, KHÔNG phải quyết định)"]
    VAL -->|"có"| ROUTE{"PDF hay ảnh?"}

    ROUTE -->|PDF| PDF["pdf_renderer.render_pdf<br/>mỗi trang 300 DPI + native text"]
    ROUTE -->|"PNG/JPEG"| IMG["render_image<br/>chuẩn hoá RGB PNG"]
    PDF --> PP["preprocess_pages<br/>EXIF · RGB · deskew nhẹ"]
    IMG --> PP

    PP --> ENG{"OCREngine<br/>(chọn theo .env)"}
    ENG -->|"OCR_ENGINE=paddle"| PADDLE["PaddleOCREngine<br/>PP-StructureV3 local"]
    ENG -->|"OCR_ENGINE=mistral"| MIS["MistralOCREngine<br/>API hosted, không tải model"]
    PADDLE --> OD["OCRDocument<br/>OCRBlock[]: text + bbox 0–1 + confidence"]
    MIS --> OD

    OD --> XF["extract_invoice_fields<br/>nhãn:giá trị → header;<br/>TABLE_CELL → line item"]
    XF --> IDR["resolve_invoice_identities<br/>vendor_id/item_id: khớp chính xác<br/>hoặc NEEDS_CONFIRMATION"]
    IDR --> LLM{"LLM mapper?<br/>(tắt mặc định)"}
    LLM -->|bật| LLMM["map_unresolved_fields<br/>grounded, cite block, cần người duyệt"]
    LLM -->|tắt| VLD
    LLMM --> VLD["validate_extraction<br/>gán status theo confidence"]

    VLD --> ST{"status field"}
    ST -->|"< ngưỡng / conflict / LLM"| NC["NEEDS_CONFIRMATION"]
    ST -->|"không đọc được"| MISS["MISSING"]
    ST -->|"đủ tin"| EX["EXTRACTED"]

    NC --> HUMAN
    MISS --> HUMAN
    EX --> HUMAN["Con người: confirm / correct / mark-unknown<br/>(bắt buộc mọi critical field)"]
    HUMAN --> REV{"mọi critical field<br/>đã xử lý?"}
    REV -->|"chưa"| HUMAN
    REV -->|"rồi → REVIEWED"| CONV["reviewed_invoice_to_evidence<br/>field unknown giữ None + flagged=True"]
    CONV --> EVID(["evidence JSON → review()"])

    classDef warn fill:#fce8e6,stroke:#ea4335;
    class ERR,MISS warn;
```

---

## 3. Đường business review (evidence → quyết định)

```mermaid
flowchart TD
    EV["evidence dict"] --> BT["build_transaction<br/>link PO/GR/Invoice/Payment/Approval"]
    BT --> EI["_evidence_issues<br/>sai PO link · PO≠APPROVED · GR≠RECEIVED"]
    EI --> CHK["run_checks — 8 check tất định"]

    subgraph CHECKS["checks/ (chỉ trả fact, không ra action)"]
        C1["vendor P02"]
        C2["item P03"]
        C3["quantity P05"]
        C4["price P06"]
        C5["amount P07"]
        C6["duplicate P09"]
        C7["payment P10/P11"]
        C8["po_limit P08"]
    end
    CHK --> CHECKS

    CHECKS --> POL["build_policy_context<br/>scope tri-state + ngưỡng 50tr"]
    POL --> ASSESS["agent.assess<br/>LLM đề xuất (có provider) / fallback"]
    ASSESS --> GUARD["decision.guard<br/>chạy lại resolve_action, override nếu LLM sai"]

    GUARD --> RA{"resolve_action<br/>(chân lý tất định)"}
    RA -->|"scope UNKNOWN"| RI1["REQUEST_INFO (P01)"]
    RA -->|"scope OUTSIDE_POLICY"| ES1["ESCALATE (P13)"]
    RA -->|"thiếu PO/GR"| RI2["REQUEST_INFO (P01/P04)"]
    RA -->|"invoice flagged"| RI3["REQUEST_INFO (P15)"]
    RA -->|"evidence_issues"| RI4["REQUEST_INFO (P14)"]
    RA -->|"check FAIL/UNKNOWN"| RI5["REQUEST_INFO"]
    RA -->|"vượt thẩm quyền"| ES2["ESCALATE (P12)"]
    RA -->|"tất cả sạch"| AP["AUTO_PROCESS"]

    classDef dec fill:#fef7e0,stroke:#f9ab00;
    class RI1,RI2,RI3,RI4,RI5,ES1,ES2,AP dec;
```

---

## 4. Sở hữu module (kiến trúc theo lớp)

```mermaid
flowchart LR
    subgraph domain["domain/"]
        M["models.py<br/>contracts: Transaction, CheckResult,<br/>OCRBlock, FieldCandidate, EvidenceIssue..."]
    end

    subgraph ingestion["ingestion/"]
        NORM["normalization (fail-closed)"]
        JADP["json_adapter"]
        FVAL["file_validation"]
        REND["document_router / pdf_renderer"]
        PREP["image_preprocessing"]
        OCRM["ocr (OCREngine + Paddle/Mistral)"]
        OCFG["ocr_config (chọn engine)"]
        IFLD["invoice_fields"]
        IDRS["identity_resolution"]
        EVAL["extraction_validation"]
        LMAP["llm_mapper (tuỳ chọn)"]
        PIPE["pipeline (FieldReview, handoff)"]
    end

    subgraph core["Lõi nghiệp vụ"]
        TX["transaction/builder"]
        CHK["checks/ (8 + engine)"]
        POL["policy/ (config + engine)"]
        AG["agent/ (llm_client, service, prompts)"]
        GRD["decision/ (guard, fallback_questions)"]
        AUD["audit/store"]
    end

    subgraph svc["services/"]
        EXT["extractor.extract_invoice"]
        REV["reviewer.review"]
    end

    subgraph edge["Rìa hệ thống"]
        APP["app/ (streamlit + presentation)"]
        VFY["verify/ (harness, manifest, ocr_harness)"]
    end

    APP --> EXT
    APP --> REV
    VFY --> REV
    VFY --> EXT
    EXT --> ingestion
    REV --> TX --> CHK --> POL --> AG --> GRD
    EXT --> AUD
    REV --> AUD
    ingestion --> M
    core --> M
```

---

## 5. Bất biến then chốt (đọc kèm sơ đồ)

- OCR **chỉ trích fact ứng viên**, không bao giờ tự ra action; mọi field máy trích
  có provenance (page + bbox + block IDs).
- `resolve_action` là **nguồn chân lý duy nhất**; Decision Guard chạy lại và
  override nếu đề xuất LLM không an toàn.
- Evidence **fail-closed**: field thiếu giữ `None`, không hoá `""`/`0`; check trả
  `UNKNOWN` khi thiếu fact.
- `vendor_id`/`item_id` chỉ resolve khi **khớp chính xác** tax-code/SKU; không
  đoán từ tên.
- Con người phải confirm/correct/mark-unknown **mọi critical field** trước khi
  vào `review()`.
- Một **audit timeline duy nhất** cho cả extraction, review, Stop, Override.
- Chỉ có 3 action: `AUTO_PROCESS` / `REQUEST_INFO` / `ESCALATE`. Stop đổi workflow
  status, Override giữ nguyên quyết định gốc (chỉ đổi `effective_action`).
