"""T08 integration runtime fixture — one CaseService, real SQLite, fake providers.

The OCR call waits on a ``threading.Event`` barrier so tests can drive the exact
Stop/finalize orderings deterministically (no sleeps). Teardown ALWAYS releases
the barrier and closes the service, so a blocked worker can never hang the suite.

This is a FAKE-provider proof of wiring (executor slot, Stop guard, closure). It
does NOT prove live OCR/Kimi quality: the bundle is injected at the persistence
boundary via ``seed_case``.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from invoice_referee.application.service import CaseService
from invoice_referee.config import activate_demo_policy
from invoice_referee.domain.models import SourceRegistry
from invoice_referee.extraction.providers import FakeProviders
from invoice_referee.storage.repository import Repository
from tests.builders import demo_policy, text_registry
from tests.integration.support import _remap, seed_case


class BarrierProviders(FakeProviders):
    """FakeProviders whose OCR blocks on a release event until the test proceeds."""

    def __init__(self, entered: threading.Event, release: threading.Event, **kwargs) -> None:
        super().__init__(**kwargs)
        self.entered = entered
        self.release = release

    def ocr(self, evidence):
        self.entered.set()
        if not self.release.wait(timeout=10):
            raise AssertionError('barrier never released; test teardown failed to unblock')
        return super().ocr(evidence)


class Runtime:
    def __init__(self, service, repo, providers, case_id, entered, release) -> None:
        self.service = service
        self.repo = repo
        self.providers = providers
        self.case_id = case_id
        self.entered = entered
        self.release = release

    def close(self) -> None:
        # Always release first so a blocked worker can finish; then wait for it.
        self.release.set()
        self.service.close()


def build_runtime(
    tmp_path: Path,
    *,
    amount: int = 1_200_000,
    profile: str = 'TRAVEL',
    score: str | None = '0.99',
) -> Runtime:
    """Real repo + seeded case + barrier fake providers + an ACTIVE service policy."""
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, bundle = seed_case(repo, amount=amount, profile=profile)
    entered, release = threading.Event(), threading.Event()

    # Rebuild registries at the requested word score. The builder keys the item
    # basis off the ``receipt`` suffix, so build with the builder's LOGICAL id for
    # the role then remap that id to the real seeded id (WORK_PURCHASE has two
    # documents whose bases differ: primary kg vs receipt g).
    builder_id = {'PRIMARY_BILL': 'e-primary', 'GOODS_RECEIPT': 'e-receipt'}
    registries = {}
    for ev in case.evidence:
        logical_id = builder_id.get(ev.role, ev.id)
        registry = text_registry(evidence_id=logical_id, amount=str(amount), score=score)
        registries[ev.id] = SourceRegistry.model_validate(
            _remap(registry.model_dump(mode='json'), {logical_id: ev.id})
        )
    providers = BarrierProviders(
        entered, release,
        documents={d.evidence_id: d for d in bundle.documents},
        registries=registries,
        mapping=bundle.mapping,
    )
    policy = activate_demo_policy(demo_policy(active=False), 'fixture activation')
    # Persist the fixture activation so the service's persisted-active-policy path
    # and set_policy(idle) are exercised (startup uses persisted config if present).
    repo.record_policy_change(policy, actor_mode='SYSTEM', reason='fixture activation')
    service = CaseService(repo, providers, policy)
    return Runtime(service, repo, providers, case.id, entered, release)


@pytest.fixture
def runtime(tmp_path):
    rt = build_runtime(tmp_path)
    try:
        yield rt
    finally:
        rt.close()
