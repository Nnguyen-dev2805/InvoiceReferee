"""Runtime configuration loaded at the application boundary."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppSettings:
    project_root: Path
    data_root: Path

    @property
    def submissions_root(self) -> Path:
        return self.data_root / "submissions"

    @classmethod
    def from_environment(cls, project_root: Path) -> "AppSettings":
        configured_data_root = os.getenv("INVOICE_REFEREE_DATA_DIR")
        data_root = (
            Path(configured_data_root).expanduser().resolve()
            if configured_data_root
            else project_root / "data"
        )
        return cls(project_root=project_root, data_root=data_root)
