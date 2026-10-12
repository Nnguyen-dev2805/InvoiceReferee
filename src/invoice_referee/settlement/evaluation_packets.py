"""Settlement evaluation packet loading (v1 + v2).

Strict, hash-verified loading of a corpus packet: typed context, versioned
oracle and replay sidecars. ``evaluation.py`` re-exports these names for the
suite runner and tests.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from invoice_referee.shared.errors import DomainError
from invoice_referee.settlement.models import AuthorityGrant, Submission

PACKET_SCHEMA_V2 = "settlement-packet-v2"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class Packet:
    directory: Path
    manifest: dict[str, Any]
    case_id: str
    job: str
    family_id: str
    dataset_role: str
    as_of: str
    input_files: list[Path] = field(default_factory=list)
    followup_files: list[Path] = field(default_factory=list)
    expected_initial: dict[str, Any] = field(default_factory=dict)
    expected_after: dict[str, Any] | None = None
    gold_status: str | None = None
    # --- v2 additions (plan Task 1) ---------------------------------------
    context: "PacketContextV2 | None" = None
    expected_v2: "ExpectedV2 | None" = None
    replay_observations: Path | None = None
    replay_relations: Path | None = None
    followup_context: "PacketContextV2 | None" = None
    followup_replay_observations: Path | None = None
    followup_replay_relations: Path | None = None


# --- v2 contracts (plan Task 1) ------------------------------------------------

class PacketContextV2(BaseModel):
    """Typed packet context: submission, policy, scoped authority (v2)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    submission: Submission
    policy: dict[str, Any]
    authority: list[AuthorityGrant]
    synthetic: Literal[True]
    policy_files: list[dict[str, Any]] = Field(default_factory=list)
    context_refs: list[str] = Field(default_factory=list)


class ExpectedV2(BaseModel):
    """Versioned oracle: components, net, critical facts, issues (v2).

    ``external_basis_present`` describes a source, not an assertion that the
    store already holds a decision; ``forbidden_actions`` lists automatic
    actions the run must NOT take. ``close_allowed`` is never used to infer
    the case is closed.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    completion: Literal["COMPLETE", "INCOMPLETE"]
    components: dict[str, StrictInt | None]
    calculated_net_vnd: StrictInt | None
    proposed_net_vnd: StrictInt | None
    direction: Literal["COMPANY_TO_EMPLOYEE", "EMPLOYEE_TO_COMPANY",
                       "BALANCED"] | None = None
    critical_facts: dict[str, StrictInt | str | None] = Field(default_factory=dict)
    expected_relations: list[dict[str, Any]] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    external_basis_present: bool = False
    gold_status: Literal["SOURCE_REVIEWED_DEVELOPMENT_NOT_INDEPENDENT"]

    @property
    def is_routine(self) -> bool:
        return self.completion == "COMPLETE" and not self.issues


# --- packet loading ------------------------------------------------------------

def _verify_entry(entry: Mapping[str, Any], packet_dir: Path) -> Path:
    path = packet_dir / str(entry["path"])
    if not path.is_file():
        raise DomainError(
            "DATASET_HASH_MISMATCH",
            f"Packet {packet_dir.name}: thiếu file {entry['path']} đã đóng băng.",
        )
    actual = _sha256_bytes(path.read_bytes())
    if actual != str(entry["sha256"]):
        raise DomainError(
            "DATASET_HASH_MISMATCH",
            f"Packet {packet_dir.name}: hash {entry['path']} không khớp bản đóng "
            f"băng ({actual} != {entry['sha256']}); từ chối chạy dataset.",
        )
    return path


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """object_pairs_hook: reject duplicate JSON keys before dict overwrite."""
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise DomainError(
                "DATASET_CONTEXT_INVALID",
                f"JSON có key trùng {key!r}; từ chối để không ghi đè âm thầm.",
            )
        seen[key] = value
    return seen


def _load_json_strict(path: Path, packet_dir: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=_no_duplicate_keys)
    except DomainError:
        raise
    except (json.JSONDecodeError, OSError) as error:
        raise DomainError(
            "DATASET_CONTEXT_INVALID",
            f"Packet {packet_dir.name}: JSON {path.name} không đọc được ({error}).",
        ) from error


def _validate_anchor_refs(refs: list[str], packet_dir: Path,
                          known_anchors: set[str]) -> None:
    """Reject refs to anchors that do not exist in the declared sources."""
    for ref in refs:
        if "#" not in ref:
            continue
        anchor = ref.rsplit("#", 1)[1]
        if anchor and anchor not in known_anchors:
            raise DomainError(
                "DATASET_CONTEXT_INVALID",
                f"Packet {packet_dir.name}: ref {ref!r} trỏ anchor không tồn tại.",
            )


def _collect_anchors(packet_dir: Path, files: list[Path]) -> set[str]:
    anchors: set[str] = set()
    for path in files:
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                anchors.add(stripped.lstrip("#").strip().lower().replace(" ", "-"))
    return anchors


def _load_packet_v2(packet_dir: Path, manifest: dict[str, Any]) -> Packet:
    """Strict v2 loader: typed context, versioned oracle, replay sidecars."""
    pdir = Path(packet_dir)
    input_files = [_verify_entry(e, pdir)
                   for e in manifest.get("initial_input_files")
                   or manifest.get("input_files") or []]
    followup_files = [_verify_entry(e, pdir)
                      for e in manifest.get("followup_input_files") or []]
    if manifest.get("expected_is_input"):
        raise DomainError(
            "EXPECTED_IS_INPUT",
            f"Packet {pdir.name}: expected không được phép là input.",
        )
    if manifest.get("followup_is_initial_input"):
        raise DomainError(
            "FOLLOWUP_IS_INPUT",
            f"Packet {pdir.name}: followup phải là phase riêng.",
        )

    context_entry = manifest.get("context_file")
    if not context_entry:
        raise DomainError(
            "DATASET_CONTEXT_INVALID",
            f"Packet {pdir.name}: v2 cần khai báo context_file.",
        )
    context_path = _verify_entry(context_entry, pdir)
    context = PacketContextV2.model_validate(_load_json_strict(context_path, pdir))

    # Every declared policy file is hash-verified: a tampered snapshot is refused.
    for entry in manifest.get("policy_files") or []:
        if entry.get("path"):
            _verify_entry(entry, pdir)
    for entry in manifest.get("policy_runtime_context_files") or []:
        _verify_entry(entry, pdir)

    replay_obs = replay_rel = None
    if manifest.get("replay_observations_file"):
        replay_obs = _verify_entry(manifest["replay_observations_file"], pdir)
    if manifest.get("replay_relations_file"):
        replay_rel = _verify_entry(manifest["replay_relations_file"], pdir)
    followup_context = None
    followup_replay_obs = followup_replay_rel = None
    if manifest.get("followup_context_file"):
        followup_context = PacketContextV2.model_validate(
            _load_json_strict(_verify_entry(manifest["followup_context_file"], pdir),
                              pdir))
    if manifest.get("followup_replay_observations_file"):
        followup_replay_obs = _verify_entry(
            manifest["followup_replay_observations_file"], pdir)
    if manifest.get("followup_replay_relations_file"):
        followup_replay_rel = _verify_entry(
            manifest["followup_replay_relations_file"], pdir)

    expected_after = None
    expected_initial_path = None
    if manifest.get("expected_files"):
        for entry in manifest["expected_files"]:
            name = Path(entry["path"]).name
            if name in ("initial.json", "before.json"):
                expected_initial_path = _verify_entry(entry, pdir)
            elif name == "after.json":
                expected_after = _load_json_strict(_verify_entry(entry, pdir), pdir)
    if expected_initial_path is None:
        expected_initial_path = _verify_entry(
            {"path": manifest["expected_path"],
             "sha256": manifest["expected_sha256"]}, pdir)
    expected_v2 = ExpectedV2.model_validate(
        _load_json_strict(expected_initial_path, pdir))

    # anchors: expected refs must point at real source anchors, never invented.
    anchors = _collect_anchors(pdir, input_files + followup_files)
    for issue in expected_v2.issues:
        _validate_anchor_refs(list(issue.get("refs") or []), pdir, anchors)
    for fact in expected_v2.critical_facts:
        pass  # values only; refs live on issues/relations

    return Packet(
        directory=pdir, manifest=manifest,
        case_id=str(manifest["evaluation_case_id"]), job=str(manifest["job"]),
        family_id=str(manifest["family_id"]),
        dataset_role=str(manifest.get("dataset_role", "UNKNOWN")),
        as_of=str(manifest.get("as_of") or context.submission.money_as_of.isoformat()),
        input_files=input_files, followup_files=followup_files,
        expected_initial=expected_v2.model_dump(mode="json"),
        expected_after=expected_after,
        gold_status=expected_v2.gold_status,
        context=context, expected_v2=expected_v2,
        replay_observations=replay_obs, replay_relations=replay_rel,
        followup_context=followup_context,
        followup_replay_observations=followup_replay_obs,
        followup_replay_relations=followup_replay_rel,
    )


def load_packet(packet_dir: Path) -> Packet:
    manifest_path = Path(packet_dir) / "manifest.json"
    if not manifest_path.is_file():
        raise DomainError("PACKET_NOT_FOUND",
                          f"Không tìm thấy manifest trong {packet_dir}.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") == PACKET_SCHEMA_V2:
        return _load_packet_v2(Path(packet_dir), manifest)
    if manifest.get("expected_is_input"):
        raise DomainError(
            "EXPECTED_IS_INPUT",
            f"Packet {packet_dir.name}: expected không được phép là input; "
            f"gold phải tách khỏi nguồn nạp vào engine.",
        )
    if manifest.get("followup_is_initial_input"):
        raise DomainError(
            "FOLLOWUP_IS_INPUT",
            f"Packet {packet_dir.name}: followup phải là phase riêng, không "
            f"trộn vào input ban đầu.",
        )
    input_entries = (manifest.get("initial_input_files")
                     or manifest.get("input_files") or [])
    input_files = [_verify_entry(entry, Path(packet_dir))
                   for entry in input_entries]
    followup_files = [_verify_entry(entry, Path(packet_dir))
                      for entry in manifest.get("followup_input_files") or []]

    expected_after: dict[str, Any] | None = None
    expected_initial: dict[str, Any]
    if manifest.get("expected_files"):
        expected_files = {Path(e["path"]).name: _verify_entry(e, Path(packet_dir))
                          for e in manifest["expected_files"]}
        if "before.json" in expected_files:
            before_path = expected_files["before.json"]
        elif "initial.json" in expected_files:
            before_path = expected_files["initial.json"]
        elif len(expected_files) == 1:
            before_path = next(iter(expected_files.values()))
        else:
            raise DomainError(
                "EXPECTED_SHAPE_UNKNOWN",
                f"Packet {packet_dir.name}: expected_files phải khai báo "
                f"before.json/initial.json (initial) và after.json (tùy chọn).",
            )
        expected_initial = json.loads(before_path.read_text(encoding="utf-8"))
        if "after.json" in expected_files:
            expected_after = json.loads(
                expected_files["after.json"].read_text(encoding="utf-8"))
    elif manifest.get("expected_path"):
        expected_path = _verify_entry(
            {"path": manifest["expected_path"],
             "sha256": manifest["expected_sha256"]}, Path(packet_dir))
        expected_initial = json.loads(expected_path.read_text(encoding="utf-8"))
    else:
        raise DomainError(
            "EXPECTED_SHAPE_UNKNOWN",
            f"Packet {packet_dir.name}: manifest không khai báo expected.",
        )

    as_of = (manifest.get("as_of") or manifest.get("as_of_money")
             or expected_initial.get("as_of")
             or expected_initial.get("as_of_money"))
    if not as_of:
        raise DomainError(
            "EXPECTED_SHAPE_UNKNOWN",
            f"Packet {packet_dir.name}: không có mốc tiền as_of để dựng case.",
        )
    return Packet(
        directory=Path(packet_dir), manifest=manifest,
        case_id=str(manifest["evaluation_case_id"]), job=str(manifest["job"]),
        family_id=str(manifest["family_id"]),
        dataset_role=str(manifest.get("dataset_role", "UNKNOWN")),
        as_of=str(as_of), input_files=input_files,
        followup_files=followup_files, expected_initial=expected_initial,
        expected_after=expected_after,
        gold_status=expected_initial.get("gold_status")
        or expected_initial.get("status"),
    )


def discover_packets(corpus_dir: Path) -> list[Packet]:
    corpus = Path(corpus_dir)
    packets = []
    for manifest_path in sorted(corpus.rglob("manifest.json")):
        # ``origin/`` holds the v1 manifest for provenance, not a packet.
        if "origin" in manifest_path.relative_to(corpus).parts:
            continue
        packets.append(load_packet(manifest_path.parent))
    packets.sort(key=lambda p: p.case_id)
    return packets
