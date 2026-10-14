"""T6 (integrity core): all 25 original cases / 65 PDFs are present and unchanged.

This verifies the v3 authoring mapping resolves against the original corpus with
matching SHA256 and does not leak gold. It does NOT author runtime gold or run the
25 cases end-to-end; that is a separate larger task (NOT_RUN here).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "data" / "tham-khao" / "uc-03"
MAPPING = CORPUS / "final-case-mapping-v3.json"


def _mapping() -> dict:
    return json.loads(MAPPING.read_text(encoding="utf-8"))


def test_mapping_declares_25_cases_and_65_pdfs() -> None:
    mapping = _mapping()
    assert mapping["source_case_count"] == 25
    assert mapping["source_pdf_count"] == 65
    assert len(mapping["cases"]) == 25


def test_all_original_pdfs_resolve_with_matching_sha256() -> None:
    mapping = _mapping()
    total = 0
    for case in mapping["cases"]:
        for ref in case["source_pdf_refs"]:
            path = CORPUS / ref["path"]
            assert path.is_file(), f"{case['case_id']}: missing {ref['path']}"
            assert hashlib.sha256(path.read_bytes()).hexdigest() == ref["sha256"], ref["path"]
            total += 1
    assert total == 65


def test_mapping_is_authoring_only_and_not_runtime_readable() -> None:
    mapping = _mapping()
    assert mapping["runtime_must_not_read_this_file"] is True
    assert mapping["authoring_only"] is True


def test_mapping_does_not_carry_runtime_gold_amounts() -> None:
    # The v3 mapping must not carry a runtime `expected`/gold money oracle; the
    # old expected.json is reference-only metadata, not runtime gold.
    text = MAPPING.read_text(encoding="utf-8")
    assert '"expected_amounts"' not in text


def test_inventory_builder_reports_verified() -> None:
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from build_hoangha_general_inventory import build_inventory

    inventory = build_inventory()
    assert inventory["verified"] is True
    assert inventory["case_count"] == 25
    assert inventory["pdf_count"] == 65
    assert inventory["problems"] == []
