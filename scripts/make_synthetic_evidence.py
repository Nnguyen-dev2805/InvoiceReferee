"""Generate the synthetic Verify corpus (T11).

Fixed reference date, fixed seed, distinct synthetic bytes per case so file hashes
differ. Every case emits: the Claim, synthetic upload files, replay artifacts
(document + registry, keyed by kind), and the expected outcome. Gold comes from
the rulebook, never from running the production rule and copying its answer.

Run: `rtk proxy .venv/bin/python scripts/make_synthetic_evidence.py`
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from invoice_referee.domain.models import (  # noqa: E402
    Claim,
    DocumentFacts,
    FieldFact,
    ItemFacts,
    MappingProposal,
    QualityObservation,
    SourceBlock,
    SourceRef,
    SourceRegistry,
    SourceWord,
)
from invoice_referee.verify.manifest import (  # noqa: E402
    ExpectedOutcome,
    FixtureUpload,
    VerifyCase,
    VerifyManifest,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures'
REFERENCE_DATE = date(2026, 10, 1)
POLICY_VERSION = 'demo-expense-v0.1-proposed'
MERCHANT = 'Nha cung cap Demo'


# --- low-level fact/registry builders -----------------------------------------

def _word(value: str, score: str | None = '0.99', wid: str = 'w') -> SourceWord:
    return SourceWord(id=wid, text=value, score=score)


def _fact(field: str, value: str, ref: SourceRef, reading: str = 'READABLE',
          verify: bool = False) -> FieldFact:
    return FieldFact(
        field=field, raw_value=value, normalized_value=value, refs=[ref],
        source_kind='DOCUMENT',
        observations=[QualityObservation(field=field, reading=reading, requires_verification=verify, refs=[ref])],
        usability='USABLE', normalization_trace=[f'{field}: "{value}" -> "{value}"'],
    )


def _registry(evidence_id: str, values: dict[str, str], *, score: str | None = '0.99') -> SourceRegistry:
    words, locators = [], {}
    for name, value in values.items():
        wid = f'w-{name}'
        words.append(_word(value, score, wid))
        locators[name] = [wid]
    block = SourceBlock(
        evidence_id=evidence_id, page_index=0, block_id='b-1',
        text=' '.join(values.values()), words=words, locators=locators,
    )
    return SourceRegistry(evidence_id=evidence_id, blocks=[block])


def _header_doc(evidence_id: str, amount: str, *, kind: str = 'BILL',
                score: str | None = '0.99', reading: str = 'READABLE',
                verify: bool = False, currency: str = 'VND',
                date_value: str = '2026-10-01') -> tuple[DocumentFacts, SourceRegistry]:
    values = {'merchant': MERCHANT, 'date': date_value, 'currency': currency, 'total': amount}
    registry = _registry(evidence_id, values, score=score)
    refs = {name: SourceRef(evidence_id=evidence_id, page_index=0, block_id='b-1',
                            locator=name, raw_value=value) for name, value in values.items()}
    fields = {name: _fact(name, value, refs[name], reading, verify) for name, value in values.items()}
    doc = DocumentFacts(evidence_id=evidence_id, kind=kind, template='TOTAL_ONLY',
                        fields=fields, items=[], covered_item_regions=[])
    return doc, registry


def _itemized_doc(evidence_id: str, amount: str, *, kind: str,
                  quantity: str = '1', unit: str = 'kg',
                  unit_price: str | None = None, name: str = 'Vat tu demo',
                  item_id: str = 'i-primary-1') -> tuple[DocumentFacts, SourceRegistry]:
    price = unit_price if unit_price is not None else amount
    values = {
        'merchant': MERCHANT, 'date': '2026-10-01', 'currency': 'VND', 'total': amount,
        'item_name_1': name, 'item_quantity_1': quantity, 'item_unit_1': unit,
        'item_unit_price_1': price, 'item_line_amount_1': amount,
    }
    registry = _registry(evidence_id, values)
    refs = {name: SourceRef(evidence_id=evidence_id, page_index=0, block_id='b-1',
                            locator=name, raw_value=value) for name, value in values.items()}
    header = {name: _fact(name, values[name], refs[name]) for name in
              ('merchant', 'date', 'currency', 'total')}
    item = ItemFacts(
        id=item_id,
        name=_fact('name', name, refs['item_name_1']),
        quantity=_fact('quantity', quantity, refs['item_quantity_1']),
        unit=_fact('unit', unit, refs['item_unit_1']),
        unit_price=_fact('unit_price', price, refs['item_unit_price_1']),
        line_amount=_fact('line_amount', amount, refs['item_line_amount_1']),
    )
    doc = DocumentFacts(evidence_id=evidence_id, kind=kind, template='SIMPLE_ITEMIZED',
                        fields=header, items=[item], covered_item_regions=['line-1'])
    return doc, registry


def _claim(profile: str, amount: int | None, *, purpose_type: str = 'BUSINESS',
           purpose: str = 'Cong tac demo', trip: str = 'Chuyen cong tac demo',
           payer: str = 'PERSONAL',
           received_full: bool | None = None) -> Claim:
    return Claim(
        employee_id='emp-demo', profile=profile, purpose_type=purpose_type,
        purpose=purpose, trip=trip,
        requested_amount_vnd=amount, payer_type=payer, received_full=received_full,
    )


def _pdf(case_id: str, role: str, amount: int | None) -> bytes:
    return (f'%PDF-1.4\n% synthetic {case_id} {role} amount={amount}\n%%EOF\n').encode('utf-8')


def _expected(action: str, *, status: str = 'SUCCEEDED', basis: str | None = None,
              classes: list[str] | None = None, owners: list[str] | None = None,
              rules: list[str] | None = None, amount: int | None = None,
              requests: int = 0, reason: str = '') -> ExpectedOutcome:
    return ExpectedOutcome(
        execution_status=status, action=action, completion_basis=basis,
        issue_classes=classes or [], owners=owners or [], required_rules=rules or [],
        amount_vnd=amount, request_count=requests, reason=reason,
    )


# --- case recipes --------------------------------------------------------------

def build_development() -> list[VerifyCase]:
    cases: list[VerifyCase] = []

    def add(case_id, desc, claim, roles_amounts, artifacts, expected, *, reference=REFERENCE_DATE):
        uploads = []
        for role, amount in roles_amounts:
            rel = f'documents/{case_id}-{role.lower()}.pdf'
            (FIXTURES / 'development' / rel).parent.mkdir(parents=True, exist_ok=True)
            content = _pdf(case_id, role, amount)
            (FIXTURES / 'development' / rel).write_bytes(content)
            uploads.append(FixtureUpload(path=rel, sha256=hashlib.sha256(content).hexdigest(),
                                         role=role, mime='application/pdf'))
        replay = {}
        for kind, payload in artifacts.items():
            rel = f'ocr/{case_id}-{kind}.json'
            (FIXTURES / 'development' / rel).parent.mkdir(parents=True, exist_ok=True)
            (FIXTURES / 'development' / rel).write_text(
                json.dumps(payload, ensure_ascii=False), encoding='utf-8')
            replay[kind] = rel
        gold_rel = f'gold/{case_id}.json'
        (FIXTURES / 'development' / gold_rel).parent.mkdir(parents=True, exist_ok=True)
        (FIXTURES / 'development' / gold_rel).write_text(
            json.dumps(expected.model_dump(mode='json'), ensure_ascii=False), encoding='utf-8')
        cases.append(VerifyCase(
            id=case_id, description=desc, provenance='synthetic',
            claim=claim, uploads=uploads, mode='PIPELINE_FAKE_OR_REPLAY',
            policy_version=POLICY_VERSION, expected=expected, reference_date=reference,
            raw_ground_truth_path=str((FIXTURES / 'development' / gold_rel)),
            replay_artifacts=replay,
        ))

    # TC01 TRAVEL 1.2m routine
    doc, reg = _header_doc('e-primary', '1200000')
    add('TC01', 'TRAVEL 1.200.000đ đủ purpose/bill', _claim('TRAVEL', 1_200_000),
        [('PRIMARY_BILL', 1_200_000)],
        {'document': doc.model_dump(mode='json'), 'registry': reg.model_dump(mode='json')},
        _expected('CREATE_PAYMENT_REQUEST', basis='ROUTINE_AUTO', amount=1_200_000,
                  requests=1, reason='Hồ sơ thường quy trong quyền tự động'))

    # TC02 CLIENT_MEAL 1.8m
    doc, reg = _header_doc('e-primary', '1800000')
    add('TC02', 'CLIENT_MEAL 1.800.000đ đủ khai báo', _claim(
        'CLIENT_MEAL', 1_800_000, purpose='Tiep khach'),
        [('PRIMARY_BILL', 1_800_000)],
        {'document': doc.model_dump(mode='json'), 'registry': reg.model_dump(mode='json')},
        _expected('CREATE_PAYMENT_REQUEST', basis='ROUTINE_AUTO', amount=1_800_000,
                  requests=1, reason='Tiếp khách đủ điều kiện, không cần report kho'))

    # TC03 WORK_PURCHASE 900k (bill/receipt khớp)
    pd, pr = _itemized_doc('e-primary', '900000', kind='BILL', quantity='1', unit='kg',
                           unit_price='900000', item_id='i-primary-1')
    rd, rr = _itemized_doc('e-receipt', '900000', kind='GOODS_RECEIPT', quantity='1000',
                           unit='g', unit_price='900', item_id='i-receipt-1')
    add('TC03', 'WORK_PURCHASE 900.000đ bill/receipt khớp', _claim(
        'WORK_PURCHASE', 900_000, purpose='Mua vat tu', received_full=True),
        [('PRIMARY_BILL', 900_000), ('GOODS_RECEIPT', 900_000)],
        {'document': pd.model_dump(mode='json'), 'registry': pr.model_dump(mode='json'),
         'receipt_document': rd.model_dump(mode='json'), 'receipt_registry': rr.model_dump(mode='json')},
        _expected('CREATE_PAYMENT_REQUEST', basis='ROUTINE_AUTO', amount=900_000,
                  requests=1, rules=['INV-01', 'INV-02'], reason='Inventory checks chạy, khớp'))

    # TC04 no primary bill -> SRC-01 REQUEST_INFO
    add('TC04', 'Claim có nội dung nhưng thiếu primary bill', _claim('TRAVEL', 1_200_000),
        [],
        {},
        _expected('REQUEST_INFO', classes=['FACTUAL_UNKNOWN'], owners=['EMPLOYEE'],
                  rules=['SRC-01'], reason='Thiếu primary bill bắt buộc'))

    # TC05 quality-uncertain -> REVIEWER
    doc, reg = _header_doc('e-primary', '1200000', score=None, reading='UNREADABLE', verify=True)
    add('TC05', 'Bill total rõ nhưng OCR/quality chưa đủ căn cứ', _claim('TRAVEL', 1_200_000),
        [('PRIMARY_BILL', 1_200_000)],
        {'document': doc.model_dump(mode='json'), 'registry': reg.model_dump(mode='json')},
        _expected('REQUEST_INFO', classes=['FACTUAL_UNKNOWN'], owners=['REVIEWER'],
                  rules=['SRC-02'], reason='Quality chưa đủ căn cứ; reviewer xem ảnh gốc'))

    # TC06 amount mismatch 1.28m bill vs 1.48m requested -> AMT-01
    doc, reg = _header_doc('e-primary', '1280000')
    add('TC06', 'Bill 1.280.000đ, requested 1.480.000đ', _claim('TRAVEL', 1_480_000),
        [('PRIMARY_BILL', 1_280_000)],
        {'document': doc.model_dump(mode='json'), 'registry': reg.model_dump(mode='json')},
        _expected('REQUEST_INFO', classes=['FACTUAL_UNKNOWN'], owners=['EMPLOYEE'],
                  rules=['AMT-01'], reason='Chênh 200.000đ chưa có căn cứ; không chọn min/max'))

    # TC07 TRAVEL thiếu trip -> CTX-01
    doc, reg = _header_doc('e-primary', '1800000')
    add('TC07', 'TRAVEL có bill nhưng thiếu khai báo chuyến đi', _claim(
        'TRAVEL', 1_800_000, purpose='Cong tac', trip=''),
        [('PRIMARY_BILL', 1_800_000)],
        {'document': doc.model_dump(mode='json'), 'registry': reg.model_dump(mode='json')},
        _expected('REQUEST_INFO', classes=['FACTUAL_UNKNOWN'], owners=['EMPLOYEE'],
                  rules=['CTX-01'], reason='Thiếu khai báo chuyến đi'))

    # TC08 OTHER -> SCOPE-01 OUTSIDE_POLICY POLICY_OWNER
    doc, reg = _header_doc('e-primary', '1200000')
    add('TC08', 'OTHER: chi phí ngoài catalog', _claim('OTHER', 1_200_000),
        [('PRIMARY_BILL', 1_200_000)],
        {'document': doc.model_dump(mode='json'), 'registry': reg.model_dump(mode='json')},
        _expected('ESCALATE', classes=['OUTSIDE_POLICY'], owners=['POLICY_OWNER'],
                  rules=['SCOPE-01'], reason='Ngoài catalog B1'))

    # TC09 PERSONAL purpose -> ELIG-01 REJECT
    doc, reg = _header_doc('e-primary', '1200000')
    add('TC09', 'Khai báo PERSONAL, không chi cho công việc', _claim(
        'TRAVEL', 1_200_000, purpose_type='PERSONAL'),
        [('PRIMARY_BILL', 1_200_000)],
        {'document': doc.model_dump(mode='json'), 'registry': reg.model_dump(mode='json')},
        _expected('REJECT', classes=[], owners=[],
                  rules=['ELIG-01'], reason='Known refusal: chi cá nhân không phục vụ công việc'))

    # TC10 exactly 2.000.000 -> routine
    doc, reg = _header_doc('e-primary', '2000000')
    add('TC10', 'Case hợp lệ đúng 2.000.000đ', _claim('TRAVEL', 2_000_000),
        [('PRIMARY_BILL', 2_000_000)],
        {'document': doc.model_dump(mode='json'), 'registry': reg.model_dump(mode='json')},
        _expected('CREATE_PAYMENT_REQUEST', basis='ROUTINE_AUTO', amount=2_000_000,
                  requests=1, reason='Biên inclusive 2.000.000'))

    # TC11 2.000.001 -> BEYOND_AUTHORITY APPROVER
    doc, reg = _header_doc('e-primary', '2000001')
    add('TC11', 'Case hợp lệ 2.000.001đ', _claim('TRAVEL', 2_000_001),
        [('PRIMARY_BILL', 2_000_001)],
        {'document': doc.model_dump(mode='json'), 'registry': reg.model_dump(mode='json')},
        _expected('ESCALATE', classes=['BEYOND_AUTHORITY'], owners=['APPROVER'],
                  rules=['AUTH-01'], reason='Vượt quyền tự động, cần approver'))

    # TC12 exactly 5.000.000 -> APPROVER, not outside policy
    doc, reg = _header_doc('e-primary', '5000000')
    add('TC12', 'Case hợp lệ đúng 5.000.000đ', _claim('TRAVEL', 5_000_000),
        [('PRIMARY_BILL', 5_000_000)],
        {'document': doc.model_dump(mode='json'), 'registry': reg.model_dump(mode='json')},
        _expected('ESCALATE', classes=['BEYOND_AUTHORITY'], owners=['APPROVER'],
                  rules=['AUTH-01'], reason='Đúng policy max, không ngoài policy'))

    # TC13 5.000.001 -> LIM-01 + AUTH-01 POLICY_OWNER
    doc, reg = _header_doc('e-primary', '5000001')
    add('TC13', 'Case hợp lệ 5.000.001đ', _claim('TRAVEL', 5_000_001),
        [('PRIMARY_BILL', 5_000_001)],
        {'document': doc.model_dump(mode='json'), 'registry': reg.model_dump(mode='json')},
        _expected('ESCALATE', classes=['OUTSIDE_POLICY', 'BEYOND_AUTHORITY'],
                  owners=['POLICY_OWNER'], rules=['LIM-01', 'AUTH-01'],
                  reason='Vượt policy + vượt quyền, cần policy owner'))

    # TC14 quantity conflict bill 10 vs receipt 8 -> INV-02
    pd, pr = _itemized_doc('e-primary', '900000', kind='BILL', quantity='10', unit='kg',
                           unit_price='90000', item_id='i-primary-1')
    rd, rr = _itemized_doc('e-receipt', '900000', kind='GOODS_RECEIPT', quantity='8',
                           unit='kg', unit_price='112500', item_id='i-receipt-1')
    add('TC14', 'Bill quantity 10, receipt 8', _claim(
        'WORK_PURCHASE', 900_000, purpose='Mua vat tu', received_full=True),
        [('PRIMARY_BILL', 900_000), ('GOODS_RECEIPT', 900_000)],
        {'document': pd.model_dump(mode='json'), 'registry': pr.model_dump(mode='json'),
         'receipt_document': rd.model_dump(mode='json'), 'receipt_registry': rr.model_dump(mode='json')},
        _expected('REQUEST_INFO', classes=['FACTUAL_UNKNOWN'], owners=['REVIEWER'],
                  rules=['INV-02'], reason='Số lượng bill/receipt conflict; reviewer đối chiếu nguồn'))

    # TC15 duplicate item IDs -> technical (SRC-03)
    pd, pr = _itemized_doc('e-primary', '900000', kind='BILL', quantity='1', unit='kg',
                           unit_price='900000', item_id='i-dup')
    dup = pd.items[0].model_copy(update={'id': 'i-dup'})
    pd = pd.model_copy(update={'items': [pd.items[0], dup]})
    add('TC15', 'Model trả item ID trùng', _claim(
        'WORK_PURCHASE', 900_000, purpose='Mua vat tu', received_full=True),
        [('PRIMARY_BILL', 900_000)],
        {'document': pd.model_dump(mode='json'), 'registry': pr.model_dump(mode='json')},
        _expected('NONE', status='FAILED', reason='Duplicate item IDs -> technical invalid'))

    return cases


def _routine_variant(case_id: str, amount: int, folder: str, *, profile: str = 'TRAVEL') -> VerifyCase:
    doc, reg = _header_doc('e-primary', str(amount))
    return VerifyCase(
        id=case_id, description=f'routine {amount}', provenance='synthetic',
        claim=_claim(profile, amount), uploads=[], mode='PIPELINE_FAKE_OR_REPLAY',
        policy_version=POLICY_VERSION,
        expected=_expected('CREATE_PAYMENT_REQUEST', basis='ROUTINE_AUTO', amount=amount, requests=1),
        reference_date=REFERENCE_DATE, raw_ground_truth_path='',
        replay_artifacts={},
    )


def build_split(prefix: str, counts: dict, folder: str) -> list[VerifyCase]:
    """Build a split with the required class distribution (routine/factual/outside/authority)."""
    cases: list[VerifyCase] = []
    n = 0
    for kind, count in counts.items():
        for _ in range(count):
            n += 1
            cid = f'{prefix}{n:02d}'
            if kind == 'routine':
                cases.append(_routine_ci(cid, folder))
            elif kind == 'factual':
                cases.append(_factual_ci(cid, folder))
            elif kind == 'outside':
                cases.append(_outside_ci(cid, folder))
            else:
                cases.append(_authority_ci(cid, folder))
    return cases


def _routine_ci(cid, folder):
    amount = 1_000_000 + (int(cid[-2:]) * 1_000)
    doc, reg = _header_doc('e-primary', str(amount))
    return _finish(cid, folder, amount, doc, reg,
                   _expected('CREATE_PAYMENT_REQUEST', basis='ROUTINE_AUTO', amount=amount, requests=1))


def _factual_ci(cid, folder):
    amount = 1_000_000
    doc, reg = _header_doc('e-primary', str(amount))
    return _finish(cid, folder, amount, doc, reg,
                   _expected('REQUEST_INFO', classes=['FACTUAL_UNKNOWN'], owners=['EMPLOYEE'], rules=['AMT-01']),
                   claim_amount=amount + 200_000)


def _outside_ci(cid, folder):
    amount = 6_000_000
    doc, reg = _header_doc('e-primary', str(amount))
    return _finish(cid, folder, amount, doc, reg,
                   _expected('ESCALATE', classes=['OUTSIDE_POLICY', 'BEYOND_AUTHORITY'],
                             owners=['POLICY_OWNER'], rules=['LIM-01', 'AUTH-01']))


def _authority_ci(cid, folder):
    amount = 2_500_000
    doc, reg = _header_doc('e-primary', str(amount))
    return _finish(cid, folder, amount, doc, reg,
                   _expected('ESCALATE', classes=['BEYOND_AUTHORITY'], owners=['APPROVER'], rules=['AUTH-01']))


def _finish(cid, folder, amount, doc, reg, expected, *, claim_amount=None) -> VerifyCase:
    rel_doc = f'ocr/{cid}-document.json'
    rel_reg = f'ocr/{cid}-registry.json'
    base = FIXTURES / folder
    (base / 'ocr').mkdir(parents=True, exist_ok=True)
    (base / 'gold').mkdir(parents=True, exist_ok=True)
    (base / 'documents').mkdir(parents=True, exist_ok=True)
    (base / rel_doc).write_text(json.dumps(doc.model_dump(mode='json'), ensure_ascii=False), encoding='utf-8')
    (base / rel_reg).write_text(json.dumps(reg.model_dump(mode='json'), ensure_ascii=False), encoding='utf-8')
    gold_rel = f'gold/{cid}.json'
    (base / gold_rel).write_text(json.dumps(expected.model_dump(mode='json'), ensure_ascii=False), encoding='utf-8')
    # A synthetic upload is required so the case has a PRIMARY_BILL evidence; the
    # replay provider supplies the analyzed facts (no OCR of these bytes).
    up_rel = f'documents/{cid}-primary_bill.pdf'
    content = _pdf(cid, 'PRIMARY_BILL', amount)
    (base / up_rel).write_bytes(content)
    upload = FixtureUpload(path=up_rel, sha256=hashlib.sha256(content).hexdigest(),
                           role='PRIMARY_BILL', mime='application/pdf')
    return VerifyCase(
        id=cid, description=f'{folder} {cid}', provenance='synthetic',
        claim=_claim('TRAVEL', claim_amount if claim_amount is not None else amount),
        uploads=[upload], mode='PIPELINE_FAKE_OR_REPLAY', policy_version=POLICY_VERSION,
        expected=expected, reference_date=REFERENCE_DATE,
        raw_ground_truth_path=str(base / gold_rel),
        replay_artifacts={'document': rel_doc, 'registry': rel_reg},
    )


def _write_manifest(folder: str, suite: str, cases: list[VerifyCase]) -> None:
    manifest = VerifyManifest(version=f'b1-{suite}-v1', suite=suite,
                              mode='PIPELINE_FAKE_OR_REPLAY', policy_version=POLICY_VERSION, cases=cases)
    manifest = manifest.model_copy(update={'sha256': manifest.content_hash()})
    out = FIXTURES / folder / 'manifest.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest.model_dump(mode='json'), ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'wrote {out}: {len(cases)} cases, hash {manifest.sha256[:12]}')


def main() -> None:
    dev = build_development()
    _write_manifest('development', 'development', dev)

    cal = build_split('CAL', {'routine': 4, 'factual': 4, 'outside': 2, 'authority': 2}, 'calibration')
    _write_manifest('calibration', 'calibration', cal)

    hld = build_split('HLD', {'routine': 6, 'factual': 6, 'outside': 4, 'authority': 4}, 'holdout')
    _write_manifest('holdout', 'holdout', hld)


if __name__ == '__main__':
    main()
