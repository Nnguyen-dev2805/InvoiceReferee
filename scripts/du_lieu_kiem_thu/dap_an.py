"""R1 literal gold: su-that-an / quan-sat-duoc / ket-qua-hop-le (plan A.1, B).

Gold is a literal map keyed by case_id — never computed by the Reconciler or the
scorer. `latent` is truth not visible in the source; `observable` is what a
correct reader should see; `allowed` is the acceptable outcome per stage.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Per case: route, owner, expected_amounts, observable facts, optional per-stage
# overrides. Values are literal (plan B / checklist 6.1).
GOLD: dict[str, dict[str, object]] = {
    "D01": {
        "route": "AUTO",
        "expected_amounts": {"PAY": 3_000_000},
        "observable": {"incurred": 8_000_000, "paid_employee": 5_000_000, "paid_company": 3_000_000, "advance": 2_000_000},
    },
    "D02": {
        "route": "AUTO",
        "expected_amounts": {"COLLECT": 500_000},
        "observable": {"incurred": 1_500_000, "paid_employee": 1_500_000, "advance": 2_000_000},
    },
    "D03": {
        "route": "AUTO",
        "expected_amounts": {},
        "observable": {"incurred": 2_000_000, "paid_employee": 2_000_000, "advance": 2_000_000},
    },
    "D04": {
        "route": "FACT",
        "owner": "employee",
        "stages": {
            "ban-dau": {"route": "FACT", "owner": "employee"},
            "bo-sung": {"route": "AUTHORITY", "owner": "approver", "expected_amounts": {"PAY": 5_000_000}},
        },
        "observable": {"incurred": 5_000_000},
    },
    "D05": {
        "route": "FACT",
        "owner": "accountant",
        "observable": {"incurred": 3_000_000, "paid_employee": 3_000_000},
    },
    "D06": {
        "route": "POLICY",
        "owner": "approver",
        "observable": {"incurred": 10_000_000, "budget": 8_000_000},
    },
    "D07": {
        "route": "AUTHORITY",
        "owner": "approver",
        "observable": {"incurred": 9_000_000, "paid_employee": 9_000_000, "advance": 6_000_000},
    },
    "D08": {
        "route": "AUTHORITY",
        "owner": "approver",
        "observable": {"incurred": 8_000_000, "paid_employee": 8_000_000, "advance": 2_000_000},
    },
    "D09": {
        "route": "FACT",
        "owner": "accountant",
        "observable": {"incurred": 3_000_000, "paid_employee": 3_000_000},
    },
    "D10": {
        "route": "AUTO",
        "expected_amounts": {"PAY": 3_000_000},
        "observable": {"incurred": 3_000_000, "paid_employee": 3_000_000},
    },
    "D11": {
        "route": "AUTO",
        "expected_amounts": {},
        "observable": {"excluded": 500_000},
    },
    "D12": {
        "route": "UNSUPPORTED",
        "owner": "accountant",
        "observable": {"currency": "USD", "amount": 200},
    },
    "D13": {
        "route": "FACT",
        "owner": "accountant",
        "observable": {"incurred": 3_000_000, "paid_employee": 3_000_000, "advance_pending": 2_000_000},
    },
    "D14": {
        "route": "AUTO",
        "expected_amounts": {"PAY": 1_000_000},
        "observable": {"incurred": 3_000_000, "paid_employee": 3_000_000, "advance": 2_000_000},
    },
    "D15": {
        "route": "AUTO",
        "stages": {
            "ban-dau": {"route": "AUTO", "expected_amounts": {"PAY": 2_000_000}},
            "bo-sung": {"route": "AUTO", "expected_amounts": {"PAY": 4_000_000}},
        },
        "expected_amounts": {"PAY": 4_000_000},
        "observable": {"incurred": 10_000_000, "paid_employee": 5_000_000, "paid_company": 3_000_000, "advance": 3_000_000},
    },
}


def route_for(case_id: str) -> str:
    return str(GOLD[case_id].get("route", "AUTO"))


def strata_for(case_id: str) -> str:
    route = route_for(case_id)
    if route == "AUTO":
        return "routine"
    if route in ("FACT", "POLICY", "AUTHORITY"):
        return route
    # UNSUPPORTED / TECHNICAL both map to the TECHNICAL strata.
    return "TECHNICAL"


def write_gold(spec, out_dir: Path) -> None:
    """Write the three gold layers, staged, for one case."""
    case_id = spec.case_id
    gold = GOLD[case_id]
    stages = spec.stages
    out_dir.mkdir(parents=True, exist_ok=True)

    latent = {stage: {"facts": gold.get("latent", {})} for stage in stages}
    observable: dict[str, object] = {}
    allowed: dict[str, object] = {}
    for stage in stages:
        stage_override = gold.get("stages", {})
        override = stage_override.get(stage, {}) if isinstance(stage_override, dict) else {}
        observable[stage] = {"facts": override.get("observable_facts", gold.get("observable", {}))}
        route = override.get("route", gold.get("route", "AUTO"))
        allowed[stage] = {
            "route": route,
            "expected_amounts": override.get("expected_amounts", gold.get("expected_amounts", {})),
            "owner": override.get("owner", gold.get("owner")),
            "question_required": route in ("FACT", "POLICY", "AUTHORITY"),
        }

    (out_dir / "su-that-an.json").write_text(
        json.dumps({"case_id": case_id, "stages": latent}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "quan-sat-duoc.json").write_text(
        json.dumps({"case_id": case_id, "stages": observable}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "ket-qua-hop-le.json").write_text(
        json.dumps({"case_id": case_id, "stages": allowed}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def gold_digest(gold_dir: Path) -> str:
    """Hash all three gold layers together (not just latent, plan E4)."""
    parts: list[str] = []
    for name in ("su-that-an.json", "quan-sat-duoc.json", "ket-qua-hop-le.json"):
        path = Path(gold_dir) / name
        parts.append(f"{name}:{hashlib.sha256(path.read_bytes()).hexdigest()}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
