"""Unit-only test factories (contracts §9).

These build literal, already-verified domain objects directly. They never
simulate OCR quality, never call the Reconciler, and never appear in the
application runtime or the live evaluation path.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from invoice_referee.domain.case import (
    AssessmentInput,
    CaseScope,
    ReadSet,
)
from invoice_referee.domain.common import EvidenceRef, Fact
from invoice_referee.domain.finance import (
    CoverageRecord,
    Expense,
    ExpensePayment,
    MoneyEvent,
    MoneyKind,
)
from invoice_referee.domain.policy import BudgetDecision, Grant, PolicyVersion

TENANT = "tenant:demo"
EMPLOYEE = "employee:employee-a"
APPROVER = "employee:approver"
COMPANY = "company:demo"
VENDOR = "vendor:demo"
ACTIVITY = "activity:travel-a"
PROFILE = "TRAVEL"

DEFAULT_AS_OF = datetime(2026, 10, 13, 3, 0, tzinfo=UTC)

ALL_MONEY_KINDS: tuple[MoneyKind, ...] = (
    "ADVANCE_RECEIVED",
    "REIMBURSEMENT_RECEIVED",
    "EMPLOYEE_RETURN",
    "REVERSAL",
    "OBSERVED_UNALLOCATED",
)


def digest(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def write_test_packet(
    base: Path,
    *,
    root_id: str = "case:test-1",
    profile: str = "TRAVEL",
    split: str = "development",
    strata: str = "routine",
    family: str = "family-1",
    template: str = "template-1",
    layout: str = "layout-1",
    issuer: str = "issuer-1",
    economic_key: str = "invoice:test:1",
    route: str = "AUTO",
    latent: dict[str, object] | None = None,
    observable: dict[str, object] | None = None,
) -> Path:
    """Write a complete packet (input/ + gold/) with a literal, separate gold.

    Returns the packet directory. Gold is written to a different subtree than
    input so a loader that only reads input/ cannot see it.
    """
    import json

    packet = Path(base) / root_id.replace(":", "_")
    input_dir = packet / "input"
    sources_dir = input_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    (packet / "gold").mkdir(parents=True, exist_ok=True)

    (input_dir / "organization.json").write_text(
        json.dumps(
            {
                "tenant": "tenant:demo",
                "profile": profile,
                "records": ["ledger:opening 0 VND"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (input_dir / "submission.json").write_text(
        json.dumps(
            {
                "employee": "employee:employee-a",
                "activity": "activity:test-1",
                "declared_purpose": "Công tác kiểm thử",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (sources_dir / "hoadon.pdf").write_bytes(b"%PDF-1.4\n% test\n%%EOF\n")

    (packet / "gold" / "latent.json").write_text(
        json.dumps({"facts": latent if latent is not None else {"payer": "employee:employee-a"}}),
        encoding="utf-8",
    )
    (packet / "gold" / "observable.json").write_text(
        json.dumps(
            {"facts": observable if observable is not None else {"amount": 450_000}}
        ),
        encoding="utf-8",
    )
    (packet / "gold" / "allowed.json").write_text(
        json.dumps({"route": route, "expected_amounts": {}}), encoding="utf-8"
    )
    return packet


def write_manifest_file(base: Path, entries: list[dict[str, object]]) -> Path:
    """Write a dataset-level manifest.json (one row per root) for inventory tests."""
    import json

    path = Path(base) / "manifest.json"
    path.write_text(
        json.dumps(
            {"dataset": "test", "frozen_at": "2026-10-13T03:00:00+00:00", "entries": entries},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def scope(**overrides: object) -> CaseScope:
    fields: dict[str, object] = {
        "tenant": TENANT,
        "employee": EMPLOYEE,
        "activity": ACTIVITY,
        "profile": PROFILE,
    }
    fields.update(overrides)
    return CaseScope(**fields)  # type: ignore[arg-type]


def coverage(*, opening: int = 0) -> CoverageRecord:
    """A complete history coverage record (contracts §3)."""
    return CoverageRecord(
        scope=ACTIVITY,
        start=DEFAULT_AS_OF - timedelta(days=30),
        as_of=DEFAULT_AS_OF,
        funds=(COMPANY,),
        flow_kinds=ALL_MONEY_KINDS,
        opening_balance=known("ledger:opening", opening, "ledger-opening"),
        ledger_version="ledger:v1",
        witness_refs=(ref("ledger-witness"),),
    )


def ref(seed: str, *, page: int = 1, quote: str = "literal evidence") -> EvidenceRef:
    return EvidenceRef(
        source_id=f"source:{seed}",
        source_sha256=digest(seed),
        page=page,
        exact_quote=quote,
    )


def known(key: str, value: int, seed: str = "seed") -> Fact[int]:
    return Fact[int](key=key, value=value, state="KNOWN", refs=(ref(seed),))


def unknown(key: str, seed: str = "seed") -> Fact[int]:
    return Fact[int](key=key, state="UNKNOWN", refs=(ref(seed),))


def payment(
    key: str, payer: str, payee: str, amount: int, expense_id: str = "expense:1"
) -> ExpensePayment:
    """A verified payment portion (contracts §2): payer paid `amount` for the expense."""
    return ExpensePayment(
        external_key=f"external:{key}",
        payer=payer,
        payee=payee,
        amount=amount,
        expense_id=expense_id,
        received_state="CLEAR",
        refs=(ref(key),),
    )


def expense(
    expense_id: str,
    incurred: int | None,
    *,
    payments: tuple[ExpensePayment, ...] = (),
    eligibility: str = "ELIGIBLE",
    activity: str = ACTIVITY,
    payment_state: str | None = None,
) -> Expense:
    """A verified expense with a literal incurred cost and payment portions.

    `payment_state` defaults to PAID when payment portions are supplied and
    UNPAID otherwise (a literal test figure is a verified basis), so legacy
    builders keep their KNOWN-unpaid behaviour. Pass it explicitly to model an
    unverified payment status.
    """
    incurred_fact = (
        known(f"{expense_id}:incurred", incurred, expense_id)
        if incurred is not None
        else unknown(f"{expense_id}:incurred", expense_id)
    )
    state = payment_state if payment_state is not None else ("PAID" if payments else "UNPAID")
    return Expense(
        id=expense_id,
        economic_key=f"invoice:{expense_id}",
        activity=activity,
        incurred=incurred_fact,
        incurred_at=DEFAULT_AS_OF - timedelta(days=2),
        payments=tuple(payments),
        eligibility=eligibility,  # type: ignore[arg-type]
        refs=(ref(expense_id),),
        payment_state=state,  # type: ignore[arg-type]
    )


def money_event(
    event_id: str,
    kind: MoneyKind,
    amount: int,
    *,
    payer: str,
    payee: str,
    as_of: datetime = DEFAULT_AS_OF,
    scope: str = ACTIVITY,
) -> MoneyEvent:
    return MoneyEvent(
        id=event_id,
        external_key=f"external:{event_id}",
        kind=kind,
        scope=scope,
        payer=payer,
        payee=payee,
        amount=amount,
        event_at=as_of,
        recorded_at=as_of,
        verification_state="CONFIRMED",
        allocation_state="ALLOCATED",
        refs=(ref(event_id),),
    )


def default_grants() -> tuple[Grant, ...]:
    """The committed demo fixture (contracts §5): system 8/4, approver 20."""
    start = DEFAULT_AS_OF - timedelta(days=1)
    return (
        Grant(
            id="grant:system:recognize",
            version="v1",
            actor="system:referee",
            actions=("RECOGNIZE_COST",),
            scope=ACTIVITY,
            max_amount=8_000_000,
            effective_from=start,
        ),
        Grant(
            id="grant:system:issue",
            version="v1",
            actor="system:referee",
            actions=("ISSUE_PAYMENT", "ISSUE_COLLECTION"),
            scope=ACTIVITY,
            max_amount=4_000_000,
            effective_from=start,
        ),
        Grant(
            id="grant:approver:20m",
            version="v1",
            actor=APPROVER,
            actions=(
                "AUTHORIZE_ACTIVITY",
                "SET_BUDGET",
                "RECOGNIZE_COST",
                "EXCEPT_POLICY",
                "ISSUE_PAYMENT",
                "ISSUE_COLLECTION",
                "OVERRIDE",
            ),
            scope=ACTIVITY,
            max_amount=20_000_000,
            effective_from=start,
        ),
    )


def snapshot(
    T: int,
    E: int,
    C: int,
    A: int,
    P: int,
    R: int,
    B: int,
    coverage: bool = True,
    **overrides: object,
) -> AssessmentInput:
    """Build an AssessmentInput from literal figures (contracts §9).

    T is the verified incurred cost; E the eligible employee-paid portion and
    C the company-direct portion are carried as verified payment portions on
    the expense. A, P and R arrive as confirmed ledger events. When coverage
    is False, no zero figure is asserted: the amounts stay UNKNOWN so a caller
    cannot read an unestablished zero as a settled one.
    """
    scope = CaseScope(
        tenant=TENANT,
        employee=EMPLOYEE,
        activity=ACTIVITY,
        profile=PROFILE,
    )
    for name, amount in (
        ("T", T),
        ("E", E),
        ("C", C),
        ("A", A),
        ("P", P),
        ("R", R),
        ("B", B),
    ):
        if amount < 0:
            raise ValueError(
                f"snapshot() {name} must be a non-negative literal VND amount"
            )
    established = coverage or T > 0

    payments: list[ExpensePayment] = []
    if E > 0:
        payments.append(
            ExpensePayment(
                external_key="payment:employee",
                payer=EMPLOYEE,
                payee=VENDOR,
                amount=E,
                expense_id="expense:1",
                received_state="CLEAR",
                refs=(ref("payment-employee"),),
            )
        )
    if C > 0:
        payments.append(
            ExpensePayment(
                external_key="payment:company",
                payer=COMPANY,
                payee=VENDOR,
                amount=C,
                expense_id="expense:1",
                received_state="CLEAR",
                refs=(ref("payment-company"),),
            )
        )

    expense = Expense(
        id="expense:1",
        economic_key="invoice:demo:1",
        activity=ACTIVITY,
        incurred=(
            known("expense:1:incurred", T, "expense-1")
            if established
            else unknown("expense:1:incurred", "expense-1")
        ),
        incurred_at=DEFAULT_AS_OF - timedelta(days=2),
        payments=tuple(payments),
        eligibility="ELIGIBLE" if E > 0 else "INELIGIBLE",
        refs=(ref("expense-1"),),
    )

    ledger: list[MoneyEvent] = []
    if A > 0:
        ledger.append(
            money_event(
                "advance:1",
                "ADVANCE_RECEIVED",
                A,
                payer=COMPANY,
                payee=EMPLOYEE,
            )
        )
    if P > 0:
        ledger.append(
            money_event(
                "reimbursement:1",
                "REIMBURSEMENT_RECEIVED",
                P,
                payer=COMPANY,
                payee=EMPLOYEE,
            )
        )
    if R > 0:
        ledger.append(
            money_event(
                "return:1",
                "EMPLOYEE_RETURN",
                R,
                payer=EMPLOYEE,
                payee=COMPANY,
            )
        )

    coverage_record = (
        CoverageRecord(
            scope=ACTIVITY,
            start=DEFAULT_AS_OF - timedelta(days=30),
            as_of=DEFAULT_AS_OF,
            funds=(COMPANY,),
            flow_kinds=ALL_MONEY_KINDS,
            opening_balance=known("ledger:opening", 0, "ledger-opening"),
            ledger_version="ledger:v1",
            witness_refs=(ref("ledger-witness"),),
        )
        if coverage
        else None
    )

    fields: dict[str, object] = {
        "scope": scope,
        "expense_facts": (expense,),
        "observations": (),
        "relations": (),
        "confirmations": (),
        "ledger": tuple(ledger),
        "coverage": coverage_record,
        "policy": (
            PolicyVersion(
                id="policy:v1",
                version="v1",
                effective_from=DEFAULT_AS_OF - timedelta(days=60),
                profile=PROFILE,
                rules=("TRAVEL_CORE", "INVOICE_REQUIRED"),
            ),
        ),
        "grants": default_grants(),
        "budget": (
            BudgetDecision(
                id="budget:1",
                activity=ACTIVITY,
                amount=B,
                effect_range=(DEFAULT_AS_OF - timedelta(days=30), None),
                actor=APPROVER,
                grant_ref="grant:approver:20m",
                refs=(ref("budget-1"),),
            ),
        ),
        "exceptions": (),
        "previous_eligibility": None,
        # This is an explicitly-tagged STUB/test snapshot: the literal figures
        # are the whole expense set, so it is complete by construction (plan A4).
        "expense_set_complete": True,
        "read_set": ReadSet(
            input_revision=1,
            control_epoch=0,
            context_version=1,
            ledger_version=1,
            usage_version=1,
        ),
        "as_of": DEFAULT_AS_OF,
    }
    fields.update(overrides)
    return AssessmentInput(**fields)


# -- T9 independent scoring literals (contracts §7, §9) ----------------------
# These build literal ActualResult / GoldPacket pairs directly. They never call
# the Reconciler, so the scorer cannot grade the app with the app's own logic.


def _actual(**overrides):
    from invoice_referee.evaluation.scorer import ActualResult

    fields = {"root_id": "case:score-1", "mode": "STUB", "state": "READY_TO_EXECUTE"}
    fields.update(overrides)
    return ActualResult(**fields)


def _gold(route: str, **overrides):
    from invoice_referee.evaluation.models import (
        AllowedGold,
        GoldPacket,
        LatentGold,
        ObservableGold,
    )

    fields = {"route": route}
    fields.update(overrides)
    return GoldPacket(
        latent=LatentGold(),
        observable=ObservableGold(),
        allowed=AllowedGold(**fields),
    )


def actual_affirmed_zero_without_coverage():
    return _actual(state="SETTLED", affirmed_zero_without_coverage=True)


def actual_routine_pay():
    from invoice_referee.evaluation.scorer import ActualInstruction

    return _actual(instructions=(ActualInstruction(direction="PAY", amount=3_000_000),))


def actual_technical_error():
    return _actual(state="TECHNICAL_ERROR", technical_error=True)


def actual_fact_wrong_owner():
    from invoice_referee.evaluation.scorer import ActualIssue

    return _actual(state="WAITING", issues=(ActualIssue(kind="FACT", owner="employee"),))


def actual_routine_bad_ref():
    from invoice_referee.evaluation.scorer import ActualInstruction

    return _actual(
        instructions=(
            ActualInstruction(direction="PAY", amount=3_000_000, refs_ok=False),
        )
    )


def actual_lucky_guess_450():
    from invoice_referee.evaluation.scorer import ActualInstruction

    return _actual(instructions=(ActualInstruction(direction="PAY", amount=450_000),))


def actual_grounded_fact_450_480():
    from invoice_referee.evaluation.scorer import ActualIssue

    return _actual(state="WAITING", issues=(ActualIssue(kind="FACT", owner="employee"),))


def actual_action_and_conclusion_wrong():
    from invoice_referee.evaluation.scorer import ActualInstruction

    return _actual(
        state="SETTLED",
        affirmed_zero_without_coverage=True,
        instructions=(ActualInstruction(direction="PAY", amount=1),),
    )


def gold_requires_fact():
    return _gold("FACT", owner="accountant")


def gold_routine_pay():
    return _gold("AUTO", expected_amounts={"PAY": 3_000_000})


def gold_ambiguous_450_480():
    # The observable source is ambiguous (450 vs 480); the latent truth (450)
    # must not reward a lucky guess.
    return _gold("FACT", owner="employee")
