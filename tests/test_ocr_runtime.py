import os

import pytest


pytestmark = pytest.mark.ocr_runtime


@pytest.mark.skipif(
    os.environ.get("RUN_OCR_RUNTIME") != "1",
    reason="set RUN_OCR_RUNTIME=1 in an environment with the OCR extra installed",
)
def test_local_ocr_runtime_imports_and_initializes():
    import fitz
    import paddle
    from paddleocr import PPStructureV3

    assert fitz.VersionBind
    assert tuple(int(part) for part in paddle.__version__.split(".")[:2]) >= (3, 3)
    assert PPStructureV3 is not None
