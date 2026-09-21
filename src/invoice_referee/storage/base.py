"""Storage port for accepted submissions."""

from __future__ import annotations

from typing import Protocol

from invoice_referee.domain import ClaimDraft, SubmissionReceipt, UploadPayload


class CaseStore(Protocol):
    def save_submission(
        self,
        claim: ClaimDraft,
        uploads: list[UploadPayload],
        warnings: list[str],
    ) -> SubmissionReceipt:
        """Persist a submission atomically and return its receipt."""
