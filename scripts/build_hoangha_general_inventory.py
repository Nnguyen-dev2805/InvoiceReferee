"""T6 core: build an integrity inventory of the 25 original Hoangha cases.

This does NOT author runtime gold. It reads the authoring-only v3 mapping and
verifies every one of the 65 original PDFs resolves with the recorded SHA256,
then writes an inventory manifest under the git-ignored `.runtime/` area for the
Verify adapter. Gold/context authoring per case is a separate, larger effort and
is not claimed here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "tham-khao" / "uc-03"
MAPPING = CORPUS / "final-case-mapping-v3.json"


def build_inventory(*, verify: bool = True) -> dict:
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    entries = []
    total = 0
    problems = []
    for case in mapping["cases"]:
        refs = []
        for ref in case["source_pdf_refs"]:
            path = CORPUS / ref["path"]
            total += 1
            if verify:
                if not path.is_file():
                    problems.append(f"{case['case_id']}: missing {ref['path']}")
                    continue
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest != ref["sha256"]:
                    problems.append(f"{case['case_id']}: hash mismatch {ref['path']}")
            refs.append({"path": ref["path"], "sha256": ref["sha256"], "pages": ref["pages"]})
        entries.append({
            "case_id": case["case_id"],
            "source_folder": case["source_folder"],
            "source_profile": case.get("source_profile"),
            "category_focus": case.get("category_focus"),
            "target_after_supported_context": case.get("target_after_supported_context"),
            "sources": refs,
        })
    return {
        "schema_version": "hoangha-general-inventory/v1",
        "source_mapping": str(MAPPING.relative_to(ROOT)),
        "authoring_only": True,
        "runtime_must_not_read_this_file": True,
        "case_count": len(entries),
        "pdf_count": total,
        "verified": verify and not problems,
        "problems": problems,
        "cases": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".runtime" / "general-expense" / "inventory.json")
    args = parser.parse_args()
    inventory = build_inventory()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"inventory: {inventory['case_count']} cases / {inventory['pdf_count']} pdfs, verified={inventory['verified']}")
    if inventory["problems"]:
        raise SystemExit("\n".join(inventory["problems"]))


if __name__ == "__main__":
    main()
