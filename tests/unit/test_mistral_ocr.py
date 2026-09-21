import base64
from pathlib import Path

from invoice_referee.extraction import MistralOcrAdapter


class FakeResponse:
    def model_dump(self, **kwargs):
        return {"pages": [{"index": 0, "markdown": "Tổng tiền: 120.000"}]}


class FakeOcrEndpoint:
    def __init__(self) -> None:
        self.request = None

    def process(self, **kwargs):
        self.request = kwargs
        return FakeResponse()


class FakeClient:
    def __init__(self) -> None:
        self.ocr = FakeOcrEndpoint()


def test_adapter_encodes_image_and_requests_word_confidence(tmp_path: Path) -> None:
    image_path = tmp_path / "bill.jpg"
    image_path.write_bytes(b"image-bytes")
    client = FakeClient()
    adapter = MistralOcrAdapter(api_key="test", client=client)

    execution = adapter.process(image_path, "image/jpeg")

    request = client.ocr.request
    expected_base64 = base64.b64encode(b"image-bytes").decode("ascii")
    assert request["document"] == {
        "type": "image_url",
        "image_url": f"data:image/jpeg;base64,{expected_base64}",
    }
    assert request["include_blocks"] is True
    assert request["confidence_scores_granularity"] == "word"
    assert execution.response["pages"][0]["markdown"] == "Tổng tiền: 120.000"


def test_adapter_uses_document_url_for_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-test")
    client = FakeClient()
    adapter = MistralOcrAdapter(api_key="test", client=client)

    adapter.process(pdf_path, "application/pdf")

    assert client.ocr.request["document"]["type"] == "document_url"
