# InvoiceReferee — Data Flow và Workflow

Tài liệu này tách hệ thống thành ba góc nhìn. Đọc theo thứ tự:

1. **Data Flow:** dữ liệu nào được tạo ra và truyền sang đâu.
2. **Business Workflow:** hồ sơ đi qua những điều kiện nào để ra quyết định.
3. **Agent Workflow:** Agent gọi tool, LLM và con người theo trình tự nào.

Chi tiết P01-P15 và các điều kiện kỹ thuật đầy đủ nằm trong `AGENT_WORKFLOW.md`.

## 1. Data Flow

```mermaid
flowchart LR
    EMP["Nhân viên"]
    FORM["Form submit<br/>description + evidence"]

    DESC[("Business Context<br/>text gốc")]
    FILES[("Evidence Store<br/>ảnh / PDF / XML / JSON")]

    EXTRACT["Extraction Layer<br/>Parser / EasyOCR / Kimi block check"]
    DOC[("ExtractedDocument<br/>fields + bbox + confidence + warnings")]

    LOOKUP["Internal Data Tools<br/>Company / Vendor / PO / Kiểm kê<br/>Payment / Processed History"]
    SUPPORT[("SupportingEvidence")]

    BUILD["ReviewCase Builder"]
    CASE[("ReviewCase")]

    CHECK["Check Engine<br/>P01-P15"]
    RESULTS[("CheckResult[]<br/>PolicyContext")]

    LLM["Reasoning LLM<br/>explanation + question + target"]
    ASSESS[("AgentAssessment")]

    GUARD["Decision Guard"]
    DECISION[("Decision")]
    AUDIT[("Audit Log")]

    EMP --> FORM
    FORM --> DESC
    FORM --> FILES
    FILES --> EXTRACT --> DOC
    LOOKUP --> SUPPORT
    DESC --> BUILD
    DOC --> BUILD
    SUPPORT --> BUILD
    BUILD --> CASE
    CASE --> CHECK
    CHECK --> RESULTS
    CASE --> LLM
    RESULTS --> LLM
    LLM --> ASSESS
    CASE --> GUARD
    RESULTS --> GUARD
    ASSESS --> GUARD
    GUARD --> DECISION
    DECISION --> AUDIT
    RESULTS --> AUDIT
    ASSESS --> AUDIT
```

### Dữ liệu chính

| Dữ liệu | Nội dung |
| --- | --- |
| `BusinessContext` | description gốc, người chi, mục đích, khách hàng/dự án, số tiền khai báo |
| `ExtractedDocument` | dữ liệu OCR/parser, bbox, confidence, warning, source reference |
| `SupportingEvidence` | hồ sơ công ty, vendor, PO, kiểm kê, nhận hàng, thanh toán, lịch sử |
| `ReviewCase` | toàn bộ dữ liệu của một lần đề nghị kiểm tra/hoàn ứng |
| `CheckResult[]` | kết quả P01-P15, expected, actual, reason, evidence refs |
| `AgentAssessment` | giải thích và câu hỏi do LLM đề xuất |
| `Decision` | `AUTO_PROCESS`, `REQUEST_INFO` hoặc `ESCALATE` |

## 2. Business Workflow

```mermaid
flowchart TD
    A["Nhân viên submit<br/>description + evidence"]
    B{"Input hợp lệ?"}
    B0["INPUT_ERROR"]

    C["Trích xuất evidence<br/>Parser hoặc EasyOCR"]
    D{"Có block OCR<br/>confidence thấp?"}
    E["Kimi kiểm tra block<br/>có quan trọng không"]
    F{"Block quan trọng<br/>hoặc không chắc?"}
    R1["REQUEST_INFO<br/>Hỏi nhân viên/kế toán"]

    G["Chuẩn hóa document"]
    H{"Identity trùng?"}
    R2["ESCALATE<br/>Duplicate chắc chắn"]

    I["Gộp description + documents<br/>+ report/kiểm kê/payment"]
    J["Kiểm tra nghiệp vụ<br/>P01-P15"]

    K{"Thiếu hoặc<br/>mâu thuẫn dữ kiện?"}
    L{"Ngoài policy?"}
    M{"Bất thường?"}
    N{"Vượt thẩm quyền?"}

    R3["ESCALATE<br/>OUTSIDE_POLICY"]
    R4["ESCALATE<br/>SUSPICIOUS"]
    R5["ESCALATE<br/>BEYOND_AUTHORITY"]
    OK["AUTO_PROCESS<br/>Sẵn sàng cho kế toán"]

    HUMAN["Human bổ sung text/evidence<br/>hoặc phê duyệt/ghi đè"]

    A --> B
    B -- "Không" --> B0
    B -- "Có" --> C
    C --> D
    D -- "Có" --> E --> F
    F -- "Có" --> R1
    F -- "Không" --> G
    D -- "Không" --> G
    G --> H
    H -- "Trùng chắc chắn" --> R2
    H -- "Không trùng" --> I
    H -- "Chưa chắc" --> R1
    I --> J --> K
    K -- "Có" --> R1
    K -- "Không" --> L
    L -- "Có" --> R3
    L -- "Không" --> M
    M -- "Có" --> R4
    M -- "Không" --> N
    N -- "Có" --> R5
    N -- "Không" --> OK

    R1 --> HUMAN
    R2 --> HUMAN
    R3 --> HUMAN
    R4 --> HUMAN
    R5 --> HUMAN
    HUMAN -- "Bổ sung hồ sơ" --> A
```

### Ý nghĩa ba kết quả

| Kết quả | Khi nào dùng |
| --- | --- |
| `AUTO_PROCESS` | Extraction rõ, không trùng, dữ liệu nhất quán, đúng policy và trong thẩm quyền |
| `REQUEST_INFO` | Thiếu, mờ, confidence thấp ở vùng quan trọng hoặc evidence mâu thuẫn |
| `ESCALATE` | Dữ kiện đã rõ nhưng trùng, ngoài policy, bất thường hoặc vượt thẩm quyền |

## 3. Agent Workflow

```mermaid
sequenceDiagram
    autonumber
    actor Employee as Nhân viên
    participant Agent as Accounting Agent
    participant OCR as Parser / EasyOCR
    participant Vision as Kimi Vision
    participant Data as Internal Data Tools
    participant Rules as Check + Policy Engine
    participant Reason as Reasoning LLM
    participant Guard as Decision Guard
    actor Human as Kế toán / Finance

    Employee->>Agent: Submit description + evidence
    Agent->>Agent: Validate input và tạo case
    Agent->>Agent: Lưu description làm BusinessContext

    loop Mỗi evidence
        Agent->>OCR: Parse hoặc OCR evidence
        OCR-->>Agent: fields + bbox + confidence + warnings

        alt Có block confidence thấp
            Agent->>Vision: Gửi crop + OCR text + context
            Vision-->>Agent: CRITICAL / NON_CRITICAL / UNKNOWN

            alt CRITICAL hoặc UNKNOWN
                Agent->>Guard: FACTUAL_UNKNOWN
                Guard-->>Employee: REQUEST_INFO + câu hỏi cụ thể
            else NON_CRITICAL
                Agent->>Agent: Giữ warning và tiếp tục
            end
        end
    end

    Agent->>Data: Tra identity và processed history
    Data-->>Agent: duplicate result

    alt Duplicate chắc chắn
        Agent->>Guard: OUTSIDE_POLICY
        Guard-->>Human: ESCALATE duplicate
    else Không trùng
        Agent->>Data: Tra company, vendor, PO, kiểm kê, payment
        Data-->>Agent: SupportingEvidence
        Agent->>Rules: ReviewCase + SupportingEvidence
        Rules-->>Agent: CheckResult[] + PolicyContext
        Agent->>Reason: Facts + checks + policy
        Reason-->>Agent: explanation + question + target
        Agent->>Guard: Checks + policy + LLM proposal

        alt Thiếu hoặc mâu thuẫn dữ kiện
            Guard-->>Employee: REQUEST_INFO
        else Ngoài policy
            Guard-->>Human: ESCALATE / OUTSIDE_POLICY
        else Bất thường
            Guard-->>Human: ESCALATE / SUSPICIOUS
        else Vượt thẩm quyền
            Guard-->>Human: ESCALATE / BEYOND_AUTHORITY
        else Tất cả đều đạt
            Guard-->>Human: AUTO_PROCESS / sẵn sàng cho kế toán
        end
    end
```

## 4. Ai chịu trách nhiệm việc gì?

| Thành phần | Trách nhiệm |
| --- | --- |
| Parser/EasyOCR `TOOL` | Đọc evidence và trả text, field, bbox, confidence |
| Kimi Vision `LLM` | Chỉ đánh giá block confidence thấp có quan trọng hay không |
| Internal Data `TOOL` | Tra company, vendor, duplicate, PO, kiểm kê, payment |
| Check Engine `HARDCODE` | Kiểm tra field, MST, số học, số lượng, tổng tiền và consistency |
| Policy Engine `HARDCODE + CONFIG` | Kiểm tra policy, hạn nộp, danh mục cấm và thẩm quyền |
| Reasoning LLM | Viết giải thích, câu hỏi và chọn người cần trả lời |
| Decision Guard `HARDCODE` | Quyết định cuối, có quyền bác đề xuất sai của LLM |
| Human | Bổ sung evidence, phê duyệt, dừng hoặc ghi đè |

## 5. Hai nguyên tắc không được phá

1. `description` là business context, không thay thế bill/evidence.
2. LLM không được tự `AUTO_PROCESS`; quyết định cuối luôn do Decision Guard dựa trên dữ kiện và policy.
