"""Input-side domain models shared by the UI and application services."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field


class EvidenceRole(StrEnum):
    PRIMARY_DOCUMENT = "PRIMARY_DOCUMENT"
    SUPPORTING_DOCUMENT = "SUPPORTING_DOCUMENT"


class ClaimDraft(BaseModel):
    """The email-like claim written by an employee."""

    model_config = ConfigDict(str_strip_whitespace=True)

    recipient: str = "Phòng Kế toán"
    subject: str = ""
    body: str = ""


@dataclass(frozen=True, slots=True)
class UploadPayload:
    """An uploaded file before it is persisted."""

    original_name: str
    content: bytes
    mime_type: str
    role: EvidenceRole

    @property
    def size_bytes(self) -> int:
        return len(self.content)

    @property
    def sha256(self) -> str:
        return sha256(self.content).hexdigest()


class EvidenceRecord(BaseModel):
    """Persisted metadata for one uploaded file."""

    evidence_id: str
    role: EvidenceRole
    original_name: str
    stored_name: str
    mime_type: str
    size_bytes: int = Field(ge=0)
    sha256: str
    relative_path: str


class SubmissionReceipt(BaseModel):
    """Small response returned to the UI after a case is stored."""

    case_id: str
    status: str
    submitted_at: str
    primary_document_count: int = Field(ge=0)
    supporting_document_count: int = Field(ge=0)
    total_size_bytes: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
