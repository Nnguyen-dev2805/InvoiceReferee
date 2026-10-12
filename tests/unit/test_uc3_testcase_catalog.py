"""Regression checks for the versioned UC-03 testcase corpus."""

from __future__ import annotations

import json
from pathlib import Path


CORPUS_ROOT = Path(__file__).resolve().parents[2] / "data" / "testcase_uc3_v2"
VALID_DECISIONS = {
    "READY_FOR_APPROVAL",
    "REQUEST_INFO",
    "ACCOUNTANT_REVIEW",
    "ESCALATE",
    "RECOMMEND_REJECT",
}


def test_uc3_v2_manifest_has_five_complete_groups() -> None:
    manifest = json.loads((CORPUS_ROOT / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "2.0"
    assert manifest["case_count"] == 50
    assert len(manifest["groups"]) == 5
    assert len(manifest["cases"]) == 50

    group_counts: dict[str, int] = {}
    case_ids: set[str] = set()
    for entry in manifest["cases"]:
        group_counts[entry["group_id"]] = group_counts.get(entry["group_id"], 0) + 1
        assert entry["case_id"] not in case_ids
        case_ids.add(entry["case_id"])
        assert entry["expected_decision"] in VALID_DECISIONS
        assert entry["implementation_status"] in {"COVERED", "PLANNED"}

    assert set(group_counts.values()) == {10}


def test_uc3_v2_cases_contain_uploadable_documents_and_oracles() -> None:
    manifest = json.loads((CORPUS_ROOT / "manifest.json").read_text(encoding="utf-8"))

    for entry in manifest["cases"]:
        case_dir = CORPUS_ROOT / entry["folder"]
        expected_path = case_dir / "expected.json"
        assert (case_dir / "request_form.docx").is_file()
        assert (case_dir / "request_form.pdf").is_file()
        assert expected_path.is_file()

        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        assert expected["case_id"] == entry["case_id"]
        assert expected["expected"]["automation_decision"] == entry["expected_decision"]
        for evidence_name in expected["submission"]["evidence_files"]:
            evidence_path = case_dir / evidence_name
            assert evidence_path.is_file()
            assert evidence_path.with_suffix(".docx").is_file()
