"""RECORDED_REPLAY reader (contracts §5, §7; plan T5).

Replays real read outputs captured earlier, keyed by source/representation/page.
A replay never invents a read it does not have: a missing recording is NOT_READ,
not a fabricated page. Replay outputs are tagged so a scorer can tell a real
recorded read from a STUB hand-transcription.
"""

from __future__ import annotations

import json
from pathlib import Path

from invoice_referee.domain.evidence import SourceRef


class ReplayReader:
    """Serves page text from a recording file written by a LIVE run."""

    def __init__(self, recording_path: Path) -> None:
        self.recording_path = Path(recording_path)
        self._data: dict[str, dict[str, str]] = {}
        if self.recording_path.is_file():
            self._data = json.loads(self.recording_path.read_text(encoding="utf-8"))

    @property
    def tag(self) -> str:
        return "RECORDED_REPLAY"

    async def ocr_page(self, source: SourceRef, page: int) -> str:
        # Keyed by source digest + page so a different source cannot reuse a read.
        key = f"{source.digest}:{page}"
        for recorded in self._data.values():
            if key in recorded:
                return recorded[key]
        raise TimeoutError(f"no recording for {key}")
