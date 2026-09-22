"""Runtime configuration loaded at the application boundary."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppSettings:
    project_root: Path
    data_root: Path
    ocr_word_review_threshold: float = 0.85

    @property
    def submissions_root(self) -> Path:
        return self.data_root / "submissions"

    @property
    def verify_runs_root(self) -> Path:
        return self.data_root / "verify_runs"

    @property
    def testcase_root(self) -> Path:
        return self.project_root / "data" / "testcase"

    @classmethod
    def from_environment(cls, project_root: Path) -> "AppSettings":
        configured_data_root = os.getenv("INVOICE_REFEREE_DATA_DIR")
        data_root = (
            Path(configured_data_root).expanduser().resolve()
            if configured_data_root
            else project_root / "data"
        )
        threshold = float(os.getenv("OCR_WORD_REVIEW_THRESHOLD", "0.85"))
        if not 0 < threshold <= 1:
            raise ValueError("OCR_WORD_REVIEW_THRESHOLD phải nằm trong (0, 1].")
        return cls(
            project_root=project_root,
            data_root=data_root,
            ocr_word_review_threshold=threshold,
        )
