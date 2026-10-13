"""Packet loaders and manifest validation (contracts §7, §11).

`load_input` reads only the input/ layer; `load_gold` reads only the gold/
layer. Keeping them separate is what stops an expected/oracle value from
reaching the application or a model prompt. `validate_inventory` enforces the
grouping rules that keep splits independent.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from invoice_referee.evaluation.models import (
    AllowedGold,
    GoldPacket,
    InventoryReport,
    LatentGold,
    ManifestEntry,
    ObservableGold,
    OrganizationContext,
    PacketInput,
    PacketMetadata,
    PacketSource,
    Submission,
    Transcription,
)


class PacketError(ValueError):
    """A malformed or inconsistent packet on disk."""


def _read_text(path: Path) -> str:
    if not path.is_file():
        raise PacketError(f"missing packet file: {path}")
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> object:
    return json.loads(_read_text(path))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_input(packet_dir: Path) -> PacketInput:
    """Load the application-visible layer only. Never reads gold/."""
    packet_dir = Path(packet_dir)
    input_dir = packet_dir / "input"
    # model_validate_json, not model_validate: a StrictModel is strict=True, so
    # a JSON array only coerces to a tuple through the JSON path.
    organization = OrganizationContext.model_validate_json(
        _read_text(input_dir / "organization.json")
    )
    submission = Submission.model_validate_json(
        _read_text(input_dir / "submission.json")
    )

    sources: list[PacketSource] = []
    sources_dir = input_dir / "sources"
    if sources_dir.is_dir():
        for path in sorted(sources_dir.iterdir()):
            if not path.is_file():
                continue
            media = _media_for(path.name)
            sources.append(
                PacketSource(filename=path.name, media=media, sha256=_sha256_file(path))
            )

    transcription_path = input_dir / "transcription.json"
    transcription = (
        Transcription.model_validate_json(_read_text(transcription_path))
        if transcription_path.is_file()
        else None
    )

    return PacketInput(
        root_id=submission.activity,  # the root is keyed by the activity
        profile=organization.profile,
        sources=tuple(sources),
        organization=organization,
        submission=submission,
        transcription=transcription,
    )


def load_gold(packet_dir: Path) -> GoldPacket:
    """Load the scorer-only layer. Must never be called on the app path."""
    packet_dir = Path(packet_dir)
    gold_dir = packet_dir / "gold"
    return GoldPacket(
        latent=LatentGold.model_validate_json(_read_text(gold_dir / "latent.json")),
        observable=ObservableGold.model_validate_json(
            _read_text(gold_dir / "observable.json")
        ),
        allowed=AllowedGold.model_validate_json(_read_text(gold_dir / "allowed.json")),
    )


def _media_for(filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower()
    if suffix == "pdf":
        return "PDF"
    if suffix in ("png",):
        return "PNG"
    if suffix in ("jpg", "jpeg"):
        return "JPEG"
    raise PacketError(f"unsupported source extension: {filename}")


def load_manifest(manifest: Path) -> PacketMetadata:
    return PacketMetadata.model_validate_json(_read_text(Path(manifest)))


# Grouping axes that must not straddle a split boundary (§11). A shared
# font/A4 alone is not leakage, so font/page-size are deliberately absent.
_GROUP_AXES = ("economic_key", "family", "template", "layout", "issuer")


def validate_inventory(manifest: Path) -> InventoryReport:
    """Validate manifest.json: splits, counts and cross-split group leakage."""
    meta = load_manifest(manifest)
    entries = meta.entries

    by_split: dict[str, int] = {}
    by_strata: dict[str, int] = {}
    problems: list[str] = []

    seen_roots: set[str] = set()
    for entry in entries:
        by_split[entry.split] = by_split.get(entry.split, 0) + 1
        by_strata[entry.strata] = by_strata.get(entry.strata, 0) + 1
        if entry.root_id in seen_roots:
            problems.append(f"duplicate root in manifest: {entry.root_id}")
        seen_roots.add(entry.root_id)

    # Cross-split leakage: a grouping axis value shared by entries in more than
    # one split means those roots are not independent.
    for axis in _GROUP_AXES:
        axis_splits: dict[str, set[str]] = {}
        for entry in entries:
            value = getattr(entry, axis)
            axis_splits.setdefault(value, set()).add(entry.split)
        for value, splits in axis_splits.items():
            if len(splits) > 1:
                problems.append(
                    f"{axis} '{value}' appears across splits {sorted(splits)}"
                )

    # A group value shared by roots within the same split is a disclosure (so a
    # caller does not claim an unseen family), not a hard failure.
    disclosures: list[str] = []
    for axis in ("family", "template", "layout"):
        counts: dict[str, int] = {}
        for entry in entries:
            counts[getattr(entry, axis)] = counts.get(getattr(entry, axis), 0) + 1
        for value, count in counts.items():
            if count > 1:
                disclosures.append(
                    f"{axis} '{value}' shared by {count} roots (within-family disclosure)"
                )

    return InventoryReport(
        total=len(entries),
        by_split=by_split,
        by_strata=by_strata,
        problems=tuple(problems),
        disclosures=tuple(disclosures),
    )


def digest_packet_input(packet_dir: Path) -> str:
    """A stable digest of the whole input layer, for the manifest."""
    input_dir = Path(packet_dir) / "input"
    parts: list[str] = []
    for path in sorted(input_dir.rglob("*")):
        if path.is_file():
            parts.append(f"{path.relative_to(input_dir)}:{_sha256_file(path)}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def write_manifest(manifest: Path, meta: PacketMetadata) -> None:
    Path(manifest).write_text(
        meta.model_dump_json(indent=2), encoding="utf-8"
    )


def entry_from_packet(
    packet_dir: Path,
    *,
    root_id: str,
    split: str,
    strata: str,
    profile: str,
    economic_key: str,
    family: str,
    template: str,
    layout: str,
    issuer: str,
) -> ManifestEntry:
    return ManifestEntry(
        root_id=root_id,
        split=split,  # type: ignore[arg-type]
        strata=strata,  # type: ignore[arg-type]
        profile=profile,
        economic_key=economic_key,
        family=family,
        template=template,
        layout=layout,
        issuer=issuer,
        input_digest=digest_packet_input(packet_dir),
        gold_digest=_sha256_file(Path(packet_dir) / "gold" / "latent.json"),
    )
