# PaddleOCR-VL trên Modal

Module `modal_apps/paddleocr_vl.py` lưu snapshot đã pin của
`PaddlePaddle/PaddleOCR-VL-1.6` vào Modal Volume
`invoice-referee-paddleocr-vl-models`. Weights không nằm trong image build nên
không bị tải lại khi code hoặc dependencies thay đổi.

## 1. Cấu hình Modal một lần

```powershell
C:\Users\namth\AppData\Local\Programs\Python\Python312\python.exe -m pip install -r requirements-modal.txt
C:\Users\namth\AppData\Local\Programs\Python\Python312\python.exe -m modal setup
```

## 2. Tải weights một lần

```powershell
C:\Users\namth\AppData\Local\Programs\Python\Python312\python.exe -m modal run modal_apps/paddleocr_vl.py
```

Hàm download kiểm tra manifest và các file bắt buộc. Chạy lại lệnh trên sẽ bỏ
qua download nếu snapshot đã đầy đủ. Chỉ dùng `--force` khi chủ động muốn tải
lại snapshot đã pin:

```powershell
C:\Users\namth\AppData\Local\Programs\Python\Python312\python.exe -m modal run modal_apps/paddleocr_vl.py --force
```

Kiểm tra Volume:

```powershell
C:\Users\namth\AppData\Local\Programs\Python\Python312\python.exe -m modal volume ls invoice-referee-paddleocr-vl-models
```

## 3. Deploy

Sau khi Volume đã có weights, các lần sau chỉ cần:

```powershell
C:\Users\namth\AppData\Local\Programs\Python\Python312\python.exe -m modal deploy modal_apps/paddleocr_vl.py
```

Modal sẽ in URL của endpoint `model_status`. Endpoint này xác nhận deployment
đang nhìn thấy đúng model, revision, số file và tổng dung lượng. Service
inference sẽ dùng cùng `model_volume` và `MODEL_DIR`, không download lại weights.

## 4. Quét thử một ảnh

Lệnh dưới đây chạy đúng pipeline của tab `OCR cấu trúc`: PP-OCRv5 đọc text và
confidence, PP-DocLayoutV3 (stage layout của PaddleOCR-VL) tìm block, sau đó
Merge Engine ghép OCR region vào block theo bbox.

```powershell
$env:PYTHONIOENCODING="utf-8"
& "C:\Users\namth\AppData\Local\Programs\Python\Python312\python.exe" -m modal run modal_apps/paddleocr_vl.py::test_image --image-path "data\image\Hoa_don_dien_tu.jpg" --output-path "data\output\paddle_ocr_structure_test.json"
```

Structured JSON sử dụng confidence theo `text_region`, không giả lập confidence
theo word. `block_confidence` là giá trị nhỏ nhất của các `rec_score` đã ghép
vào block. `layout_confidence` chỉ là score phân loại vùng của PP-DocLayoutV3.

Full PaddleOCR-VL native có thể sinh nội dung cho từng block nhưng quá chậm cho
luồng UI tương tác trên L4. Pipeline hiện tại chỉ dùng stage layout của nó; weight
VLM vẫn nằm trong Volume để dùng cho fallback block khó ở giai đoạn sau.

## Cấu hình đã pin

```text
Repository: PaddlePaddle/PaddleOCR-VL-1.6
Revision:   14e49e712dfa8ac6ff89aa88f1a21c8f30e0cf29
Volume:     invoice-referee-paddleocr-vl-models
Path:       /model-store/PaddleOCR-VL-1.6
```

Model Hugging Face này chứa VLM weights cho element-level OCR/document parsing.
Full page-level PaddleOCR-VL pipeline còn cần layout/preprocessing models; các
model đó sẽ được bổ sung vào cùng Volume khi triển khai inference pipeline.
