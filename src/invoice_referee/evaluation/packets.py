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


# Stage folder names (plan A): the physical home of each stage's documents.
# Several stage ids may share a folder (e.g. bo-sung-payer -> 02-bo-sung).
STAGE_FOLDERS: dict[str, str] = {
    "ban-dau": "01-nop-ban-dau",
    "bo-sung": "02-bo-sung",
    "bo-sung-payer": "02-bo-sung",
    "bo-sung-thanh-toan": "02-bo-sung",
    "duyet-chi": "03-duyet-chi",
    "thuc-hien-tien": "03-thuc-hien-tien",
}
# Physical folder order, for a stage's read-set cutoff.
_FOLDER_ORDER: tuple[str, ...] = (
    "01-nop-ban-dau",
    "02-bo-sung",
    "03-duyet-chi",
    "03-thuc-hien-tien",
)
# Layout markers: the new corpus uses Vietnamese folders; the legacy layout uses
# input/ + gold/. The loader detects which so both load during the R1->R2 move.
_NEW_INPUT = "dau-vao"
_NEW_CONTEXT = "cau-hinh"
_NEW_GOLD = "dap-an"


def _available_folders(stage_id: str) -> tuple[str, ...]:
    """Folders whose documents are in the read-set at ``stage_id``."""
    folder = STAGE_FOLDERS.get(stage_id, "01-nop-ban-dau")
    cutoff = _FOLDER_ORDER.index(folder) if folder in _FOLDER_ORDER else 0
    return _FOLDER_ORDER[: cutoff + 1]


def _is_new_layout(packet_dir: Path) -> bool:
    return (packet_dir / _NEW_INPUT).is_dir() or (packet_dir / _NEW_GOLD).is_dir()


def load_input(packet_dir: Path, *, stage_id: str = "ban-dau") -> PacketInput:
    """Load the application-visible layer only. Never reads gold/.

    Supports both the new Vietnamese layout (dau-vao/<stage>/ + cau-hinh/) and
    the legacy input/ layout. A later stage's documents are absent from an
    earlier stage's read-set (plan A.1).
    """
    packet_dir = Path(packet_dir)
    if _is_new_layout(packet_dir):
        return _load_input_new(packet_dir, stage_id=stage_id)
    return _load_input_legacy(packet_dir)


def _load_input_new(packet_dir: Path, *, stage_id: str) -> PacketInput:
    context_dir = packet_dir / _NEW_CONTEXT
    # model_validate_json (not model_validate): a StrictModel is strict=True, so
    # a JSON list only coerces to a tuple through the JSON path.
    organization = OrganizationContext.model_validate_json(
        _read_text(context_dir / "to-chuc.json")
    )
    submission = Submission.model_validate_json(
        _read_text(context_dir / "khai-bao.json")
    )

    # Sources available at this stage: every folder up to and including it.
    sources: list[PacketSource] = []
    for folder_name in _available_folders(stage_id):
        folder = packet_dir / _NEW_INPUT / folder_name
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            media = _media_for(path.name)
            sources.append(
                PacketSource(filename=path.name, media=media, sha256=_sha256_file(path))
            )

    return PacketInput(
        root_id=submission.activity,
        profile=organization.profile,
        sources=tuple(sources),
        organization=organization,
        submission=submission,
        transcription=None,
    )


def _load_input_legacy(packet_dir: Path) -> PacketInput:
    input_dir = packet_dir / "input"
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
        root_id=submission.activity,
        profile=organization.profile,
        sources=tuple(sources),
        organization=organization,
        submission=submission,
        transcription=transcription,
    )


def load_gold(packet_dir: Path, *, stage_id: str = "ban-dau") -> GoldPacket:
    """Load the scorer-only layer. Must never be called on the app path."""
    packet_dir = Path(packet_dir)
    if _is_new_layout(packet_dir):
        gold_dir = packet_dir / _NEW_GOLD
        latent_raw = json.loads(_read_text(gold_dir / "su-that-an.json"))
        observable_raw = json.loads(_read_text(gold_dir / "quan-sat-duoc.json"))
        allowed_raw = json.loads(_read_text(gold_dir / "ket-qua-hop-le.json"))
        stage = stage_id if stage_id in latent_raw.get("stages", {}) else "ban-dau"
        # model_validate_json for strict tuples.
        return GoldPacket(
            latent=LatentGold.model_validate_json(
                json.dumps(latent_raw["stages"][stage])
            ),
            observable=ObservableGold.model_validate_json(
                json.dumps(observable_raw["stages"][stage])
            ),
            allowed=AllowedGold.model_validate_json(
                json.dumps(allowed_raw["stages"][stage])
            ),
        )
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


def digest_packet_input(packet_dir: Path, *, stage_id: str = "ban-dau") -> str:
    """A stable digest of the input basis available at ``stage_id`` (plan R1).

    Only the context and the documents available at that stage are hashed, so a
    later-stage proof does not change the initial basis.
    """
    packet_dir = Path(packet_dir)
    if _is_new_layout(packet_dir):
        parts: list[str] = []
        context_dir = packet_dir / _NEW_CONTEXT
        if context_dir.is_dir():
            for path in sorted(context_dir.rglob("*")):
                if path.is_file() and path.name != "ban-doc-stub.json":
                    parts.append(f"{path.relative_to(packet_dir)}:{_sha256_file(path)}")
        for folder_name in _available_folders(stage_id):
            folder = packet_dir / _NEW_INPUT / folder_name
            if not folder.is_dir():
                continue
            for path in sorted(folder.rglob("*")):
                if path.is_file():
                    parts.append(f"{path.relative_to(packet_dir)}:{_sha256_file(path)}")
        return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    input_dir = packet_dir / "input"
    parts = []
    for path in sorted(input_dir.rglob("*")):
        if path.is_file():
            parts.append(f"{path.relative_to(input_dir)}:{_sha256_file(path)}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def write_manifest(manifest: Path, meta: PacketMetadata) -> None:
    Path(manifest).write_text(
        meta.model_dump_json(indent=2), encoding="utf-8"
    )


def bind_sources(case_dir: Path, packet: PacketInput, *, stage_id: str = "ban-dau"):
    """Return a resolver that materializes exactly this stage's source bytes.

    The resolver only accepts a ``PacketSource`` already bound to this case and
    stage; it validates an allowlisted relative file, media/size, a case-contained
    resolved path (no symlink/traversal) and the SHA256 at read time. The path and
    the case name live only in the closure, never serialized into a prompt (plan
    A.2).
    """
    case_dir = Path(case_dir).resolve()
    allowed: dict[tuple[str, str], Path] = {}
    for folder_name in _available_folders(stage_id):
        folder = case_dir / _NEW_INPUT / folder_name
        if folder.is_dir():
            for path in sorted(folder.rglob("*")):
                if path.is_file():
                    allowed[(folder_name, path.name)] = path
    # Also accept the legacy input/sources layout.
    legacy = case_dir / "input" / "sources"
    if legacy.is_dir():
        for path in sorted(legacy.rglob("*")):
            if path.is_file():
                allowed[("input", path.name)] = path

    bound = {(s.filename, s.sha256) for s in packet.sources}

    def resolve(source: PacketSource) -> bytes:
        if (source.filename, source.sha256) not in bound:
            raise PacketError(f"source not bound to this stage: {source.filename}")
        path = None
        for (_folder, name), candidate in allowed.items():
            if name == source.filename:
                path = candidate
                break
        if path is None:
            raise PacketError(f"unknown source file: {source.filename}")
        resolved = path.resolve()
        if not resolved.is_relative_to(case_dir):
            raise PacketError(f"source escapes the case dir: {source.filename}")
        if resolved.is_symlink():
            raise PacketError(f"source must not be a symlink: {source.filename}")
        data = resolved.read_bytes()
        if hashlib.sha256(data).hexdigest() != source.sha256:
            raise PacketError(f"source digest mismatch: {source.filename}")
        return data

    return resolve


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
