"""R2: publish the new corpus and retire the unusable evaluation data (plan R2).

The dataset source root is a single Settings value (data/kiem-thu); the old
data/evaluation generator and packets are gone; UC-03 is a reference only and is
never loaded as final data.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_settings_dataset_root_is_kiem_thu() -> None:
    from invoice_referee.config import Settings

    settings = Settings()
    assert Path(settings.dataset_root).name == "kiem-thu"


def test_old_evaluation_generator_is_gone() -> None:
    assert not (PROJECT_ROOT / "scripts" / "build_packets.py").exists()


def test_old_evaluation_packets_are_gone() -> None:
    # The 55 source-clone PDFs are retired; only the new corpus remains.
    old = PROJECT_ROOT / "data" / "evaluation"
    assert not old.exists(), "data/evaluation must be removed in R2"


def test_new_corpus_exists_and_is_managed() -> None:
    corpus = PROJECT_ROOT / "data" / "kiem-thu"
    assert (corpus / "manifest.json").is_file()
    assert (corpus / "case-01-cong-ty-chi-them").is_dir()


def test_uc3_is_reference_only_not_loaded_as_final() -> None:
    # UC-03 is moved under data/tham-khao and never consumed by the app/Verify.
    ref = PROJECT_ROOT / "data" / "tham-khao" / "uc-03"
    assert ref.is_dir()
    from invoice_referee.evaluation.packets import load_input

    # A reference dir is not a packet (no context/submission) -> must not load.
    case = next((p for p in ref.iterdir() if p.is_dir()), None)
    assert case is not None
    try:
        load_input(case)
    except Exception:
        return
    raise AssertionError("UC-03 reference must not load as a final packet")


def test_cli_default_dataset_is_kiem_thu() -> None:
    # The CLI default dataset path points at the new corpus (single source root).
    source = (PROJECT_ROOT / "src" / "invoice_referee" / "cli.py").read_text(encoding="utf-8")
    assert "data\" / \"kiem-thu\"" in source or "data/kiem-thu" in source
