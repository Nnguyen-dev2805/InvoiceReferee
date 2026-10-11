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
    company_legal_name: str | None = None
    company_tax_codes: frozenset[str] = frozenset()

    @property
    def submissions_root(self) -> Path:
        return self.data_root / "submissions"

    @property
    def settlement_database_path(self) -> Path:
        return self.data_root / "invoice_referee.sqlite3"

    @property
    def settlement_artifacts_root(self) -> Path:
        return self.data_root / "settlement_cases"

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
        company_legal_name = os.getenv("COMPANY_LEGAL_NAME", "").strip() or None
        company_tax_codes = frozenset(
            value.strip()
            for value in os.getenv("COMPANY_TAX_CODES", "").split(",")
            if value.strip()
        )
        return cls(
            project_root=project_root,
            data_root=data_root,
            ocr_word_review_threshold=threshold,
            company_legal_name=company_legal_name,
            company_tax_codes=company_tax_codes,
        )
