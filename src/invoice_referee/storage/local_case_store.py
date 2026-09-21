"""Local filesystem storage for Sprint 1 submissions."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from invoice_referee.domain import (
    ClaimDraft,
    EvidenceRecord,
    EvidenceRole,
    SubmissionReceipt,
    UploadPayload,
)

VIETNAM_TZ = timezone(timedelta(hours=7))


def _now_vietnam() -> datetime:
    return datetime.now(tz=VIETNAM_TZ)


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name or "unnamed-file")[:140]


class LocalCaseStore:
    """Write each case to its own directory using an atomic final rename."""

    def __init__(
        self,
        root: Path,
        clock: Callable[[], datetime] = _now_vietnam,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.root = Path(root)
        self.clock = clock
        self.id_factory = id_factory or self._new_case_id

    def _new_case_id(self) -> str:
        return f"CASE-{self.clock():%Y%m%d}-{uuid4().hex[:8].upper()}"

    def save_submission(
        self,
        claim: ClaimDraft,
        uploads: list[UploadPayload],
        warnings: list[str],
    ) -> SubmissionReceipt:
        self.root.mkdir(parents=True, exist_ok=True)
        case_id = self.id_factory()
        final_dir = self.root / case_id
        if final_dir.exists():
            raise FileExistsError(f"Case đã tồn tại: {case_id}")

        temp_dir = self.root / f".{case_id}-{uuid4().hex}.tmp"
        submitted_at = self.clock().isoformat()
        evidence_records: list[EvidenceRecord] = []

        try:
            temp_dir.mkdir(parents=True, exist_ok=False)
            for upload in uploads:
                role_dir = (
                    "primary"
                    if upload.role == EvidenceRole.PRIMARY_DOCUMENT
                    else "supporting"
                )
                destination_dir = temp_dir / role_dir
                destination_dir.mkdir(parents=True, exist_ok=True)

                evidence_id = f"EV-{uuid4().hex[:10].upper()}"
                stored_name = f"{evidence_id}__{_safe_filename(upload.original_name)}"
                relative_path = Path(role_dir) / stored_name
                (temp_dir / relative_path).write_bytes(upload.content)

                evidence_records.append(
                    EvidenceRecord(
                        evidence_id=evidence_id,
                        role=upload.role,
                        original_name=upload.original_name,
                        stored_name=stored_name,
                        mime_type=upload.mime_type,
                        size_bytes=upload.size_bytes,
                        sha256=upload.sha256,
                        relative_path=relative_path.as_posix(),
                    )
                )

            metadata = {
                "schema_version": "1.0",
                "case_id": case_id,
                "case_type": "EMPLOYEE_EXPENSE_CLAIM",
                "workflow_status": "ACTIVE",
                "processing_status": "RECEIVED",
                "submitted_at": submitted_at,
                "employee_claim": claim.model_dump(),
                "evidence": [record.model_dump(mode="json") for record in evidence_records],
                "warnings": warnings,
            }
            (temp_dir / "submission.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            audit_events = [
                {
                    "event_type": "CASE_CREATED",
                    "case_id": case_id,
                    "actor": "employee_submission",
                    "timestamp": submitted_at,
                    "reason": "Nhân viên gửi hồ sơ chi phí",
                },
                *[
                    {
                        "event_type": "EVIDENCE_ATTACHED",
                        "case_id": case_id,
                        "actor": "employee_submission",
                        "timestamp": submitted_at,
                        "evidence_id": record.evidence_id,
                        "role": record.role.value,
                        "source_ref": record.relative_path,
                    }
                    for record in evidence_records
                ],
            ]
            (temp_dir / "audit.jsonl").write_text(
                "".join(
                    json.dumps(event, ensure_ascii=False) + "\n"
                    for event in audit_events
                ),
                encoding="utf-8",
            )
            temp_dir.replace(final_dir)
        except Exception:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            raise

        primary_count = sum(
            record.role == EvidenceRole.PRIMARY_DOCUMENT for record in evidence_records
        )
        supporting_count = len(evidence_records) - primary_count
        return SubmissionReceipt(
            case_id=case_id,
            status="RECEIVED",
            submitted_at=submitted_at,
            primary_document_count=primary_count,
            supporting_document_count=supporting_count,
            total_size_bytes=sum(record.size_bytes for record in evidence_records),
            warnings=warnings,
        )
