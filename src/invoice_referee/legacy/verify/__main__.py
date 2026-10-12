"""Verify CLI (T11): run a suite through the real CaseService and print a table.

`python -m invoice_referee.verify --suite core|escalation|all --mode replay|live --output PATH`

Exit code is based on test verdicts (any FAIL -> non-zero), never on a business
auto badge. ``live`` mode is not wired (needs live providers + spend
authorization); it reports INCONCLUSIVE rather than fabricating a result.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from invoice_referee.application.service import CaseService
from invoice_referee.storage.repository import Repository
from invoice_referee.verify.manifest import VerifyManifest, load_manifest
from invoice_referee.verify.replay import ReplayProviders
from invoice_referee.verify.runner import VerifyRunner

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / 'tests' / 'fixtures'

SUITES = {
    'core': ['TC01', 'TC03', 'TC04', 'TC11'],
    'escalation': ['TC01', 'TC02', 'TC03', 'TC06', 'TC11'],
    'all': None,
}


def _select(manifest: VerifyManifest, suite: str) -> VerifyManifest:
    ids = SUITES[suite]
    cases = manifest.cases if ids is None else [c for c in manifest.cases if c.id in ids]
    selected = manifest.model_copy(update={'cases': cases, 'suite': suite})
    return selected.model_copy(update={'sha256': selected.content_hash()})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='invoice_referee.verify')
    parser.add_argument('--suite', choices=['core', 'escalation', 'all'], default='all')
    parser.add_argument('--mode', choices=['replay', 'live'], default='replay')
    parser.add_argument('--output', default='data/verify')
    parser.add_argument('--db', default=None)
    args = parser.parse_args(argv)

    manifest = load_manifest(FIXTURES / 'development' / 'manifest.json')
    selected = _select(manifest, args.suite)
    if args.mode == 'live':
        selected = selected.model_copy(update={'mode': 'LIVE_END_TO_END'})

    out_root = Path(args.output)
    db_path = Path(args.db) if args.db else out_root / 'verify.sqlite'
    db_path.parent.mkdir(parents=True, exist_ok=True)
    repo = Repository(db_path, out_root / 'artifacts')
    service = CaseService(repo, ReplayProviders(), repo.get_active_policy() or _inactive_policy())
    # Activate the proposed demo policy for the replay run (recorded as SYSTEM).
    from invoice_referee.config import activate_demo_policy

    service.activate_policy(activate_demo_policy(service.policy, 'Verify replay corpus'),
                            reason='Verify replay corpus')
    try:
        report = VerifyRunner(service, out_root / 'runs').run(selected)
    finally:
        service.close()

    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / f'report-{report.id}.json').write_text(
        json.dumps(report.model_dump(mode='json'), ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'{"case":6} {"expected":22} {"actual":22} {"verdict":12}')
    for row in report.results:
        print(f'{row.case_id:6} {row.expected.action:22} {str(row.actual.get("action")):22} {row.verdict:12}')
    m = report.metrics
    print(f'\ntotal={m["total_cases"]} pass={m["verdicts"]["pass"]} fail={m["verdicts"]["fail"]} '
          f'inconclusive={m["verdicts"]["inconclusive"]}')
    return 1 if m['verdicts']['fail'] else 0


def _inactive_policy():
    from invoice_referee.config import load_policy

    return load_policy(ROOT / 'config' / 'demo-policy.json')


if __name__ == '__main__':
    sys.exit(main())
