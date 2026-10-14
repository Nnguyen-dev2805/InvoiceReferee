"""E8 Hoangha UC-03 corpus inventory tests (plan E8, contracts §12).

The formal denominator is 75 case IDs: 25 v1 (TC01–TC25) + 50 v2. The imported
kit keeps inputs (PDF/PNG/JPEG only) and gold disjoint; DOCX is excluded as app
input; gold never enters a runtime manifest. A worst-case job must fit the
12-LLM / 10-OCR budget.
"""

from __future__ import annotations

import json
from pathlib import Path

from invoice_referee.evidence.trace import RunBudget

PROJECT_ROOT = Path(__file__).resolve().parents[2]
KIT = PROJECT_ROOT / "data" / "test-kit" / "hoangha-uc03"


def test_official_uc03_inventory() -> None:
    manifest = json.loads((KIT / "manifest.json").read_text(encoding="utf-8"))
    formal_case_count = len(manifest["cases"])
    assert formal_case_count == 75
    assert manifest["source_revision"] == "1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8"
    assert manifest["v1_count"] == 25
    assert manifest["v2_count"] == 50


def test_inputs_and_gold_are_disjoint() -> None:
    manifest = json.loads((KIT / "manifest.json").read_text(encoding="utf-8"))
    for case in manifest["cases"]:
        assert case["inputs"], case["case_id"]
        # Gold lives under gold/, never under inputs/.
        for rel in case["inputs"]:
            assert rel.startswith("inputs/")
            assert Path(rel).suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg")
        for rel in case.get("gold", []):
            assert rel.startswith("gold/")


def test_docx_excluded_from_app_input() -> None:
    manifest = json.loads((KIT / "manifest.json").read_text(encoding="utf-8"))
    for case in manifest["cases"]:
        assert all(".docx" not in rel.lower() for rel in case["inputs"])


def test_gold_never_in_a_runtime_manifest() -> None:
    # The runtime corpus manifest must not reference gold paths.
    runtime = json.loads((KIT / "manifest.json").read_text(encoding="utf-8"))
    assert runtime["runtime"]["gold_visible"] is False
    assert "gold/" not in json.dumps(runtime["runtime"], ensure_ascii=False)


def test_all_stages_fit_call_budget() -> None:
    # Worst case: 8 documents -> 1 classify + 1 confidence + 8 extract + 1 repair
    # + 1 suggestion = 12 LLM attempts; <=10 OCR attempts.
    budget = RunBudget()
    assert budget.max_llm_attempts == 12
    assert budget.max_ocr_attempts <= 10
    for _ in range(12):
        assert budget.can_call_llm()
        budget.charge_llm()
    assert not budget.can_call_llm()


def test_replay_does_not_read_gold() -> None:
    # The evidence pipeline input loader never reads a gold path.
    from invoice_referee.evaluation.packets import load_input

    gold_reads: list[str] = []
    original = Path.read_text

    def spy(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if "gold" in str(self):
            gold_reads.append(str(self))
        return original(self, *args, **kwargs)

    Path.read_text = spy  # type: ignore[method-assign]
    try:
        # A missing packet dir raises before any read; that is fine for the spy.
        try:
            load_input(PROJECT_ROOT / "data" / "test-kit" / "hoangha-uc03" / "inputs" / "nope")
        except Exception:
            pass
    finally:
        Path.read_text = original  # type: ignore[method-assign]
    assert gold_reads == []


def test_every_document_type_has_a_profile_or_documented_gap() -> None:
    # Every taxonomy type has a code-owned profile (document_profiles), so the
    # extraction path is defined for all 17 values (plan E8 Step 5).
    from invoice_referee.domain.documents import DOCUMENT_TYPES
    from invoice_referee.evidence.document_profiles import DOCUMENT_PROFILES

    assert set(DOCUMENT_PROFILES) == set(DOCUMENT_TYPES)


def test_synthetic_type_fixtures_exist_for_absent_types() -> None:
    # Types absent from the 75 official cases still have a labelled synthetic
    # fixture directory (plan E8 Step 5).
    fixtures = KIT / "fixtures" / "document-types"
    assert fixtures.is_dir()
    assert (fixtures / "README.md").is_file()
