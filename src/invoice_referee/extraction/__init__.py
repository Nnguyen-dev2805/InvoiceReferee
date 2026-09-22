"""Document extraction adapters."""

from .confidence import (
    LOW_CONFIDENCE_THRESHOLD,
    REVIEW_CONFIDENCE_THRESHOLD,
    confidence_level,
    extract_word_confidence_rows,
)
from .mistral_ocr import MistralOcrAdapter, OcrExecution
from .kimi_reasoning import KimiReasoningAdapter, KimiResponseError
from .conflict_reasoning import CONFLICT_SYSTEM_PROMPT
from .word_block_mapper import restructure_mistral_ocr
from .ocr_quality import (
    DEFAULT_WORD_REVIEW_THRESHOLD,
    collect_low_confidence_blocks,
    is_meaningful_ocr_word,
)
from .ocr_structure import (
    bbox_from_any,
    build_ocr_structure_document,
    merge_ocr_structure_page,
    normalize_paddle_ocr_page,
    normalize_paddle_structure_page,
)
from .modal_ocr_structure import ModalOcrStructureAdapter

__all__ = [
    "LOW_CONFIDENCE_THRESHOLD",
    "DEFAULT_WORD_REVIEW_THRESHOLD",
    "REVIEW_CONFIDENCE_THRESHOLD",
    "MistralOcrAdapter",
    "KimiReasoningAdapter",
    "KimiResponseError",
    "CONFLICT_SYSTEM_PROMPT",
    "OcrExecution",
    "confidence_level",
    "collect_low_confidence_blocks",
    "extract_word_confidence_rows",
    "is_meaningful_ocr_word",
    "restructure_mistral_ocr",
    "bbox_from_any",
    "build_ocr_structure_document",
    "merge_ocr_structure_page",
    "normalize_paddle_ocr_page",
    "normalize_paddle_structure_page",
    "ModalOcrStructureAdapter",
]
