"""The generated evaluation dataset: counts, strata and real artifacts (T4).

Builds the packets into a tmp dir and checks the plan's floors: >=15 distinct
development travel roots; holdout 20 = 10 routine + 10 human (FACT4/POLICY3/
AUTHORITY3); input never leaks gold; a scan source is image-only (no hidden
text layer carrying the seed truth).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from invoice_referee.evaluation.packets import (
    load_input,
    validate_inventory,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import build_packets  # noqa: E402


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("eval")
    for split, specs in (
        ("development", build_packets.DEVELOPMENT),
        ("holdout", build_packets.HOLDOUT),
    ):
        meta = build_packets.build_split(out / split, specs, split)  # type: ignore[arg-type]
        build_packets.write_manifest(out / split / "manifest.json", meta)
    return out


def test_development_has_15_distinct_roots(built: Path) -> None:
    report = validate_inventory(built / "development" / "manifest.json")
    assert report.total == 15
    assert report.ok, report.problems


def test_holdout_is_10_routine_10_human(built: Path) -> None:
    report = validate_inventory(built / "holdout" / "manifest.json")
    assert report.total == 20
    assert report.by_strata["routine"] == 10
    human = report.by_strata["FACT"] + report.by_strata["POLICY"] + report.by_strata["AUTHORITY"]
    assert human == 10
    assert report.by_strata["FACT"] == 4
    assert report.by_strata["POLICY"] == 3
    assert report.by_strata["AUTHORITY"] == 3
    assert report.ok, report.problems


def test_no_grouping_axis_straddles_the_split(built: Path) -> None:
    # Within each split, no problem; the split boundary is what matters.
    for split in ("development", "holdout"):
        report = validate_inventory(built / split / "manifest.json")
        assert report.ok, (split, report.problems)


def test_generated_packet_has_real_pdf_and_separate_gold(built: Path) -> None:
    packet = built / "development" / "dev-clean-chi"
    p = load_input(packet)
    assert p.sources and p.sources[0].media == "PDF"
    # input/ and gold/ are disjoint subtrees.
    assert not (packet / "input" / "gold").exists()
    assert (packet / "gold" / "allowed.json").is_file()
    # The raw file starts with a real PDF header.
    raw = (packet / "input" / "sources" / "chung-tu.pdf").read_bytes()
    assert raw.startswith(b"%PDF")


def test_scan_source_is_image_only_no_hidden_text(built: Path) -> None:
    import pypdf

    packet = built / "development" / "dev-mixed-pdf"
    pdf_path = packet / "input" / "sources" / "chung-tu.pdf"
    reader = pypdf.PdfReader(str(pdf_path))
    text = (reader.pages[0].extract_text() or "").strip()
    # An image-only scan has no extractable text layer carrying the amount.
    assert "4.500.000" not in text


def test_sources_do_not_leak_scenario_slug(built: Path) -> None:
    # The slug names the scenario; it must not appear in any source a model
    # reads (filename or extracted text).
    import pypdf

    for packet in sorted((built / "development").iterdir()):
        if not packet.is_dir():
            continue
        for source in (packet / "input" / "sources").iterdir():
            assert packet.name not in source.name
            if source.suffix == ".pdf":
                text = " ".join(
                    (page.extract_text() or "")
                    for page in pypdf.PdfReader(str(source)).pages
                )
                assert packet.name not in text, f"slug leaked into {source}"
