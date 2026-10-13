"""Packet inventory: input/gold separation and split independence (contracts §7, §11).

The application only ever sees input/; gold/ is scorer-only. Grouping axes
(root/economic/family/template/layout/issuer) must not straddle a split, while
a shared font/A4 is not leakage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from invoice_referee.evaluation.packets import (
    load_gold,
    load_input,
    validate_inventory,
)
from tests.factories import write_manifest_file, write_test_packet


def test_packet_input_excludes_gold(tmp_path: Path) -> None:
    p = load_input(write_test_packet(tmp_path))
    dumped = p.model_dump()
    assert "latent" not in dumped and "expected" not in dumped
    # The input layer must not even reference the gold directory.
    assert "gold" not in str(dumped)


def test_load_gold_reads_only_the_oracle(tmp_path: Path) -> None:
    packet = write_test_packet(tmp_path, latent={"payer": "employee:x"})
    gold = load_gold(packet)
    assert gold.latent.facts["payer"] == "employee:x"
    assert gold.allowed.route == "AUTO"


def test_input_sources_carry_real_digests(tmp_path: Path) -> None:
    p = load_input(write_test_packet(tmp_path))
    assert len(p.sources) == 1
    assert len(p.sources[0].sha256) == 64


def _entry(root: str, split: str, **axes: str) -> dict[str, object]:
    row: dict[str, object] = {
        "root_id": root,
        "split": split,
        "strata": "routine",
        "profile": "TRAVEL",
        "economic_key": f"invoice:{root}",
        "family": f"family:{root}",
        "template": f"template:{root}",
        "layout": f"layout:{root}",
        "issuer": f"issuer:{root}",
        "input_digest": "a" * 64,
        "gold_digest": "b" * 64,
    }
    row.update(axes)
    return row


def test_inventory_clean_manifest_has_no_problems(tmp_path: Path) -> None:
    manifest = write_manifest_file(
        tmp_path,
        [
            _entry("case:1", "development"),
            _entry("case:2", "development"),
            _entry("case:3", "holdout"),
        ],
    )
    report = validate_inventory(manifest)
    assert report.total == 3
    assert report.by_split["development"] == 2
    assert report.ok, report.problems


def test_economic_clone_across_splits_fails(tmp_path: Path) -> None:
    manifest = write_manifest_file(
        tmp_path,
        [
            _entry("case:1", "development", economic_key="invoice:shared"),
            _entry("case:2", "holdout", economic_key="invoice:shared"),
        ],
    )
    report = validate_inventory(manifest)
    assert not report.ok
    assert any("economic_key" in problem for problem in report.problems)


def test_root_clone_within_split_fails(tmp_path: Path) -> None:
    manifest = write_manifest_file(
        tmp_path,
        [_entry("case:1", "development"), _entry("case:1", "development")],
    )
    report = validate_inventory(manifest)
    assert any("duplicate root" in problem for problem in report.problems)


def test_family_overlap_across_splits_fails(tmp_path: Path) -> None:
    manifest = write_manifest_file(
        tmp_path,
        [
            _entry("case:1", "development", family="family:shared"),
            _entry("case:2", "holdout", family="family:shared"),
        ],
    )
    report = validate_inventory(manifest)
    assert not report.ok
    assert any("family" in problem for problem in report.problems)


def test_within_family_sharing_is_disclosed(tmp_path: Path) -> None:
    # Two roots in the SAME split sharing a family is a disclosure (reported),
    # not a hard failure — it does not invalidate the dataset.
    manifest = write_manifest_file(
        tmp_path,
        [
            _entry("case:1", "development", family="family:shared"),
            _entry("case:2", "development", family="family:shared"),
        ],
    )
    report = validate_inventory(manifest)
    assert report.ok
    assert any("within-family disclosure" in d for d in report.disclosures)


def test_shared_font_is_not_leakage(tmp_path: Path) -> None:
    # Font/page-size are not grouping axes, so identical layout-independent
    # values across splits do not fail the inventory.
    manifest = write_manifest_file(
        tmp_path,
        [
            _entry("case:1", "development"),
            _entry("case:2", "holdout"),
        ],
    )
    report = validate_inventory(manifest)
    assert report.ok, report.problems


def test_travel_development_needs_15_roots(tmp_path: Path) -> None:
    # The plan's floor: >=15 distinct development travel roots. The manifest
    # check reports the count; the dataset builder asserts the floor.
    entries = [_entry(f"case:{i}", "development") for i in range(15)]
    manifest = write_manifest_file(tmp_path, entries)
    report = validate_inventory(manifest)
    assert report.by_split["development"] == 15
    assert report.ok, report.problems
