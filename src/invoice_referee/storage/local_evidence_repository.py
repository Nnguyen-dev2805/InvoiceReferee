"""Read submitted evidence and persist OCR debug results."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class StoredEvidence:
    case_id: str
    evidence_id: str
    role: str
    original_name: str
    mime_type: str
    size_bytes: int
    relative_path: str
    absolute_path: Path


@dataclass(frozen=True, slots=True)
class StoredCase:
    case_id: str
    submitted_at: str
    subject: str
    body: str
    evidence: tuple[StoredEvidence, ...]


class LocalEvidenceRepository:
    """Filesystem query adapter for evidence created by LocalCaseStore."""

    def __init__(self, submissions_root: Path) -> None:
        self.submissions_root = Path(submissions_root)

    def list_cases(self) -> list[StoredCase]:
        if not self.submissions_root.exists():
            return []

        cases: list[StoredCase] = []
        for metadata_path in self.submissions_root.glob("CASE-*/submission.json"):
            try:
                cases.append(self._read_case(metadata_path))
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
        return sorted(cases, key=lambda case: case.submitted_at, reverse=True)

    def get_case(self, case_id: str) -> StoredCase:
        metadata_path = self._case_dir(case_id) / "submission.json"
        if not metadata_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy hồ sơ: {case_id}")
        return self._read_case(metadata_path)

    def _read_case(self, metadata_path: Path) -> StoredCase:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        case_id = str(payload["case_id"])
        case_dir = metadata_path.parent.resolve()
        claim = payload.get("employee_claim") or {}
        evidence: list[StoredEvidence] = []

        for item in payload.get("evidence", []):
            absolute_path = (case_dir / str(item["relative_path"])).resolve()
            if not absolute_path.is_relative_to(case_dir):
                raise ValueError("Evidence path nằm ngoài case directory.")
            evidence.append(
                StoredEvidence(
                    case_id=case_id,
                    evidence_id=str(item["evidence_id"]),
                    role=str(item["role"]),
                    original_name=str(item["original_name"]),
                    mime_type=str(item.get("mime_type") or "application/octet-stream"),
                    size_bytes=int(item.get("size_bytes") or 0),
                    relative_path=str(item["relative_path"]),
                    absolute_path=absolute_path,
                )
            )

        return StoredCase(
            case_id=case_id,
            submitted_at=str(payload.get("submitted_at") or ""),
            subject=str(claim.get("subject") or "Không có chủ đề"),
            body=str(claim.get("body") or ""),
            evidence=tuple(evidence),
        )

    def save_ocr_result(
        self,
        evidence: StoredEvidence,
        result: dict[str, Any],
    ) -> Path:
        case_dir = self._case_dir(evidence.case_id)
        output_dir = case_dir / "ocr"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{evidence.evidence_id}.json"
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path

    def load_ocr_result(self, evidence: StoredEvidence) -> dict[str, Any] | None:
        output_path = self._case_dir(evidence.case_id) / "ocr" / f"{evidence.evidence_id}.json"
        if not output_path.is_file():
            return None
        return json.loads(output_path.read_text(encoding="utf-8"))

    def save_processing_result(
        self,
        case_id: str,
        result: dict[str, Any],
    ) -> Path:
        case_dir = self._case_dir(case_id)
        output_path = case_dir / "processing.json"
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        audit_path = case_dir / "audit.jsonl"
        audit_event = {
            "event_type": "CASE_PROCESSED",
            "case_id": case_id,
            "actor": "invoice_referee_agent",
            "timestamp": result.get("processed_at"),
            "decision": result.get("decision"),
        }
        with audit_path.open("a", encoding="utf-8") as audit_file:
            audit_file.write(json.dumps(audit_event, ensure_ascii=False) + "\n")
        return output_path

    def load_processing_result(self, case_id: str) -> dict[str, Any] | None:
        output_path = self._case_dir(case_id) / "processing.json"
        if not output_path.is_file():
            return None
        return json.loads(output_path.read_text(encoding="utf-8"))

    def delete_case(self, case_id: str) -> None:
        """Permanently remove one case and all of its stored artifacts."""

        case_dir = self._case_dir(case_id)
        if not case_dir.is_dir():
            raise FileNotFoundError(f"Không tìm thấy hồ sơ: {case_id}")
        shutil.rmtree(case_dir)

    def _case_dir(self, case_id: str) -> Path:
        root = self.submissions_root.resolve()
        if (
            not case_id.startswith("CASE-")
            or Path(case_id).name != case_id
            or case_id in {".", ".."}
        ):
            raise ValueError("Case ID không hợp lệ.")
        case_dir = (root / case_id).resolve()
        if case_dir.parent != root:
            raise ValueError("Case path không hợp lệ.")
        return case_dir
