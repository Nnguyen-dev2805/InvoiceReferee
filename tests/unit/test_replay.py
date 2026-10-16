"""Unit tests for RECORDED_REPLAY reader and classifier (contracts §5, §7).

Replay serves recorded OCR and LLM outputs without provider I/O.
A missing or mismatched recording fails loudly with MissingRecordingError.
"""

from __future__ import annotations

import pytest
from invoice_referee.domain.evidence import SourceRef
from invoice_referee.evidence.replay import (
    MissingRecordingError,
    ReplayClassifier,
    ReplayReader,
)
from invoice_referee.evidence.trace import RunBudget
from invoice_referee.evidence.replay import request_key,canonical_request


def _source(digest: str = "a" * 64, name: str = "doc.pdf") -> SourceRef:
    return SourceRef(
        id="source:1",
        digest=digest,
        tenant="tenant:demo",
        media="PDF",
        storage_key=f"tenant:demo/root/{name}",
        upload_role="paper",
    )


@pytest.mark.asyncio
async def test_replay_reader_serves_ocr_file_when_present():
    data = {
        "ocr": {
            "a" * 64: {
                "pages": [
                    {"page": 1, "markdown": "GIẤY ĐỀ NGHỊ HOÀN ỨNG", "blocks": []}
                ], "complete": True
            }
        }
    }
    reader = ReplayReader(data)
    source = _source("a" * 64)
    result = await reader.ocr_file(
        source,
        budget=RunBudget(),
        artifacts=None,
        source_bytes=b"",
    )
    assert result.source_digest == "a" * 64
    assert len(result.pages) == 1
    assert result.pages[0].markdown == "GIẤY ĐỀ NGHỊ HOÀN ỨNG"
    assert result.complete is True


@pytest.mark.asyncio
async def test_replay_reader_raises_missing_recording_when_digest_absent():
    reader = ReplayReader({"ocr": {}})
    source = _source("b" * 64)
    with pytest.raises(MissingRecordingError, match="no OCR recording"):
        await reader.ocr_file(
            source,
            budget=RunBudget(),
            artifacts=None,
            source_bytes=b"",
        )


@pytest.mark.asyncio
async def test_replay_classifier_serves_paper_extraction():
    data = {
        "extractions": {
            "paper": {
                "role_fit": "FIT",
                "actual_type": "SETTLEMENT_FORM",
                "fields": [
                    {"field": "declared_advance", "state": "FOUND", "value": 4000000, "quote": "4.000.000", "page": 1}
                ],
                "line_items": []
            }
        }
    }
    system="SETTLEMENT_FORM extraction" if "paper" in data["extractions"] else "Evidence extraction"
    user='{"upload_role": "paper"}' if "paper" in data["extractions"] else '{"upload_role": "evidence"}'
    response=next(iter(data["extractions"].values()))
    classifier = ReplayClassifier({"calls":{request_key(system,user):{"request":canonical_request(system,user),"response":response}}})
    result = await classifier.complete_json(
        system="SETTLEMENT_FORM extraction",
        user='{"upload_role": "paper"}',
        budget=RunBudget(),
    )
    assert result["role_fit"] == "FIT"
    assert classifier.calls == 1


@pytest.mark.asyncio
async def test_replay_classifier_serves_evidence_extraction():
    data = {
        "extractions": {
            "evidence": {
                "document_type": "E_INVOICE",
                "fields": [
                    {"field": "total_amount", "state": "FOUND", "value": 3240000, "quote": "3.240.000", "page": 1}
                ],
                "line_items": []
            }
        }
    }
    system="SETTLEMENT_FORM extraction" if "paper" in data["extractions"] else "Evidence extraction"
    user='{"upload_role": "paper"}' if "paper" in data["extractions"] else '{"upload_role": "evidence"}'
    response=next(iter(data["extractions"].values()))
    classifier = ReplayClassifier({"calls":{request_key(system,user):{"request":canonical_request(system,user),"response":response}}})
    result = await classifier.complete_json(
        system="Evidence extraction",
        user='{"upload_role": "evidence"}',
        budget=RunBudget(),
    )
    assert result["document_type"] == "E_INVOICE"
    assert classifier.calls == 1


@pytest.mark.asyncio
async def test_replay_classifier_raises_missing_recording_when_absent():
    classifier = ReplayClassifier({"extractions": {}})
    with pytest.raises(MissingRecordingError, match="no exact request"):
        await classifier.complete_json(
            system="SETTLEMENT_FORM extraction",
            user='{"upload_role": "paper"}',
            budget=RunBudget(),
        )
