"""Persist PaddleOCR-VL weights in Modal for repeatable deployments."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import modal

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

APP_NAME = "invoice-referee-paddleocr-vl"
VOLUME_NAME = "invoice-referee-paddleocr-vl-models"
MODEL_REPO = "PaddlePaddle/PaddleOCR-VL-1.6"
# Pin the snapshot so a later upstream update cannot silently change production.
MODEL_REVISION = "14e49e712dfa8ac6ff89aa88f1a21c8f30e0cf29"

MODEL_ROOT = Path("/model-store")
MODEL_DIR = MODEL_ROOT / "PaddleOCR-VL-1.6"
HF_CACHE_DIR = MODEL_ROOT / ".huggingface"
MANIFEST_PATH = MODEL_DIR / "invoice-referee-model.json"
REQUIRED_FILES = (
    "config.json",
    "model.safetensors",
    "processor_config.json",
    "tokenizer.json",
)

app = modal.App(APP_NAME)
model_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

download_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "huggingface_hub[hf_xet]>=0.35,<1",
    )
    .env(
        {
            "HF_HOME": HF_CACHE_DIR.as_posix(),
            "HF_HUB_CACHE": (HF_CACHE_DIR / "hub").as_posix(),
            "HF_HUB_DISABLE_PROGRESS_BARS": "1",
            "HF_XET_HIGH_PERFORMANCE": "1",
        }
    )
)

status_image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "fastapi[standard]>=0.116,<1",
)

inference_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04",
        add_python="3.12",
    )
    .apt_install("libgl1", "libglib2.0-0", "libgomp1")
    .pip_install(
        "paddlepaddle-gpu==3.2.1",
        index_url="https://www.paddlepaddle.org.cn/packages/stable/cu126/",
    )
    .pip_install(
        "paddleocr[doc-parser]>=3.6,<4",
        "pillow>=11,<13",
        "pymupdf>=1.26,<2",
    )
    .env(
        {
            "HF_HOME": HF_CACHE_DIR.as_posix(),
            "PADDLE_PDX_CACHE_HOME": (MODEL_ROOT / ".paddlex").as_posix(),
            "PYTHONUNBUFFERED": "1",
        }
    )
    .add_local_python_source("invoice_referee")
)


def _weights_are_complete() -> bool:
    if not MANIFEST_PATH.is_file():
        return False
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if manifest.get("repo_id") != MODEL_REPO:
        return False
    if manifest.get("revision") != MODEL_REVISION:
        return False
    return all(
        (MODEL_DIR / relative_path).is_file()
        and (MODEL_DIR / relative_path).stat().st_size > 0
        for relative_path in REQUIRED_FILES
    )


def _model_inventory() -> dict[str, object]:
    files = [path for path in MODEL_DIR.rglob("*") if path.is_file()]
    return {
        "repo_id": MODEL_REPO,
        "revision": MODEL_REVISION,
        "model_dir": MODEL_DIR.as_posix(),
        "ready": _weights_are_complete(),
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
    }


@app.function(
    image=download_image,
    volumes={MODEL_ROOT.as_posix(): model_volume},
    cpu=4,
    memory=8192,
    timeout=60 * 60,
)
def download_weights(force: bool = False) -> dict[str, object]:
    """Download a pinned public model snapshot into a persistent Volume."""

    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import disable_progress_bars

    disable_progress_bars()

    model_volume.reload()
    if _weights_are_complete() and not force:
        inventory = _model_inventory()
        inventory["downloaded"] = False
        inventory["message"] = "Weights already exist; download skipped."
        return inventory

    if force and MODEL_DIR.exists():
        shutil.rmtree(MODEL_DIR)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    snapshot_download(
        repo_id=MODEL_REPO,
        revision=MODEL_REVISION,
        local_dir=MODEL_DIR,
    )

    missing = [
        relative_path
        for relative_path in REQUIRED_FILES
        if not (MODEL_DIR / relative_path).is_file()
    ]
    if missing:
        raise RuntimeError(
            "Model snapshot is incomplete; missing: " + ", ".join(missing)
        )

    inventory = _model_inventory()
    manifest = {
        **inventory,
        "ready": True,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    model_volume.commit()

    inventory = _model_inventory()
    inventory["downloaded"] = True
    inventory["message"] = "PaddleOCR-VL weights downloaded and committed."
    return inventory


@app.function(
    image=status_image,
    volumes={MODEL_ROOT.as_posix(): model_volume},
)
@modal.fastapi_endpoint(method="GET", docs=True)
def model_status() -> dict[str, object]:
    """Health endpoint proving that a deployment can see persisted weights."""

    model_volume.reload()
    return _model_inventory()


def _jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _result_json(result: object) -> dict[str, object]:
    value = getattr(result, "json", None)
    if callable(value):
        value = value()
    normalized = _jsonable(value)
    if not isinstance(normalized, dict):
        raise RuntimeError("PaddleOCR returned an unsupported result object.")
    return normalized


@app.cls(
    image=inference_image,
    gpu="L4",
    memory=24576,
    timeout=20 * 60,
    startup_timeout=20 * 60,
    scaledown_window=5 * 60,
    volumes={MODEL_ROOT.as_posix(): model_volume},
)
class PaddleOCRStructureService:
    """Run OCR and document structure models, then merge their bboxes."""

    @modal.enter()
    def load_models(self) -> None:
        from paddleocr import LayoutDetection, PaddleOCR

        print("[startup] Reloading model volume.", flush=True)
        model_volume.reload()
        if not _weights_are_complete():
            raise RuntimeError(
                "PaddleOCR-VL weights are missing. Run the download entrypoint first."
            )

        print("[startup] Loading PP-OCRv5.", flush=True)
        self.ocr = PaddleOCR(
            ocr_version="PP-OCRv5",
            device="gpu",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            text_rec_score_thresh=0.0,
        )
        print("[startup] PP-OCRv5 ready.", flush=True)
        print("[startup] Loading PP-DocLayoutV3.", flush=True)
        self.structure = LayoutDetection(
            model_name="PP-DocLayoutV3",
            device="gpu",
        )
        print("[startup] PP-DocLayoutV3 ready.", flush=True)

    @staticmethod
    def _decode_pages(file_name: str, mime_type: str, content: bytes) -> list[object]:
        from io import BytesIO

        import numpy as np
        from PIL import Image, ImageOps

        is_pdf = mime_type == "application/pdf" or file_name.lower().endswith(".pdf")
        if is_pdf:
            import fitz

            document = fitz.open(stream=content, filetype="pdf")
            if len(document) > 20:
                raise ValueError("PDF exceeds the 20-page test limit.")
            pages: list[object] = []
            for page in document:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72), alpha=False)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                pages.append(np.asarray(image))
            document.close()
            return pages

        with Image.open(BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
        return [np.asarray(image)]

    @modal.method()
    def scan(
        self,
        file_name: str,
        mime_type: str,
        content: bytes,
        review_threshold: float = 0.85,
    ) -> dict[str, object]:
        from invoice_referee.extraction.ocr_structure import (
            build_ocr_structure_document,
            merge_ocr_structure_page,
            normalize_paddle_ocr_page,
            normalize_paddle_structure_page,
        )

        page_images = self._decode_pages(file_name, mime_type, content)
        merged_pages: list[dict[str, object]] = []
        for page_index, page_image in enumerate(page_images):
            # Both models receive this exact same preprocessed page array.
            ocr_results = list(self.ocr.predict(page_image))
            structure_results = list(
                self.structure.predict(
                    page_image,
                    batch_size=1,
                    threshold=0.3,
                    layout_nms=True,
                )
            )
            if not ocr_results:
                raise RuntimeError(f"PP-OCR returned no result for page {page_index + 1}.")
            if not structure_results:
                raise RuntimeError(
                    f"PP-DocLayoutV3 returned no result for page {page_index + 1}."
                )

            ocr_payload = _result_json(ocr_results[0])
            structure_payload = _result_json(structure_results[0])
            ocr_regions = normalize_paddle_ocr_page(
                ocr_payload,
                page_index=page_index,
            )
            structure_blocks = normalize_paddle_structure_page(
                structure_payload,
                page_index=page_index,
            )
            height, width = page_image.shape[:2]
            merged_pages.append(
                merge_ocr_structure_page(
                    page_index=page_index,
                    width=int(width),
                    height=int(height),
                    ocr_regions=ocr_regions,
                    structure_blocks=structure_blocks,
                    review_threshold=review_threshold,
                )
            )

        document = build_ocr_structure_document(
            merged_pages,
            file_name=file_name,
            ocr_model="PP-OCRv5",
            structure_model="PP-DocLayoutV3 (PaddleOCR-VL layout stage)",
        )
        document["preprocessing"] = {
            "single_pass": True,
            "steps": ["pdf_render_200_dpi" if len(page_images) > 1 else "exif_transpose", "rgb"],
        }
        return document


@app.local_entrypoint()
def main(force: bool = False) -> None:
    """One-time setup command invoked through `modal run`."""

    result = download_weights.remote(force=force)
    print(json.dumps(result, indent=2))


@app.local_entrypoint()
def test_image(
    image_path: str,
    output_path: str = "",
    review_threshold: float = 0.85,
) -> None:
    """Send a local image/PDF to the hybrid Modal OCR pipeline."""

    source = Path(image_path).expanduser().resolve(strict=True)
    mime_type = "application/pdf" if source.suffix.lower() == ".pdf" else "image/jpeg"
    result = PaddleOCRStructureService().scan.remote(
        source.name,
        mime_type,
        source.read_bytes(),
        review_threshold,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if output_path:
        Path(output_path).expanduser().write_text(rendered, encoding="utf-8")
    print(rendered)
