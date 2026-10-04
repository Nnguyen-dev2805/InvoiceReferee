"""Shared integration fixtures for T04+ (master plan §3.3).

``seed_case`` is a persistence/fake-boundary fixture: it uploads SYNTHETIC PDF
bytes through the real intake path, then remaps the builder's logical evidence
IDs (``e-primary``/``e-receipt``) to the real IDs ``Repository`` assigns. It is
**not** an OCR/PDF quality proof — the bundle is injected straight into the
persistence boundary; no provider is called.
"""
from __future__ import annotations

from invoice_referee.domain.models import CaseRecord, EvidenceBundle, Upload
from invoice_referee.storage.repository import Repository
from tests.builders import resolved_bundle, routine_snapshot


def _synthetic_pdf(role: str, amount: int) -> bytes:
    """Distinct synthetic bytes per role so dedup does not collapse uploads."""
    body = f'%PDF-1.4\n% synthetic evidence\n% role={role}\n% amount={amount}\n%%EOF\n'
    return body.encode('utf-8')


def _remap(obj, mapping: dict[str, str]):
    """Recursively replace logical evidence IDs with the real assigned IDs."""
    if isinstance(obj, dict):
        return {(mapping.get(k, k) if k in mapping else k): _remap(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_remap(v, mapping) for v in obj]
    if isinstance(obj, str) and obj in mapping:
        return mapping[obj]
    return obj


def seed_case(
    repo: Repository, amount: int = 1_200_000, profile: str = 'TRAVEL'
) -> tuple[CaseRecord, EvidenceBundle]:
    """Create a real case (with evidence artifacts) and a remapped bundle."""
    snapshot = routine_snapshot(amount=amount, profile=profile)
    uploads = [
        Upload(
            original_name=f'{ev.role.lower()}.pdf',
            mime='application/pdf',
            content=_synthetic_pdf(ev.role, amount),
            role=ev.role,
        )
        for ev in snapshot.evidence
    ]
    case = repo.create_case(snapshot.claim, uploads)

    # Remap BOTH naming schemes to the real assigned evidence IDs:
    #  - the snapshot's logical IDs ('e-1'/'e-2') by role;
    #  - the builder bundle's logical IDs ('e-primary'/'e-receipt') by role.
    role_to_real = {ev.role: ev.id for ev in case.evidence}
    mapping: dict[str, str] = {}
    for logical_ev in snapshot.evidence:
        if logical_ev.role in role_to_real:
            mapping[logical_ev.id] = role_to_real[logical_ev.role]
    if 'PRIMARY_BILL' in role_to_real:
        mapping['e-primary'] = role_to_real['PRIMARY_BILL']
    if 'GOODS_RECEIPT' in role_to_real:
        mapping['e-receipt'] = role_to_real['GOODS_RECEIPT']

    raw = resolved_bundle(str(amount), profile=profile).model_dump(mode='json')
    bundle = EvidenceBundle.model_validate(_remap(raw, mapping))
    return case, bundle
