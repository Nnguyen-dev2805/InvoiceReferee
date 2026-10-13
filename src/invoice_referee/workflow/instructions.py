"""Instruction lifecycle: retain / supersede / issue one actionable order (§10.1).

The workflow owns the transaction; this module owns the *decision* about the
current actionable instruction given the assessment's allowed effect. It is
pure over the inputs so the retain/suspend/supersede rules are testable without
a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

InstructionAction = Literal["RETAIN", "REACTIVATE", "SUSPEND", "REPLACE", "ISSUE"]


@dataclass(frozen=True)
class InstructionState:
    """The current actionable instruction, if any."""

    id: str
    direction: str
    amount: int
    cost_basis: str
    fulfilled_amount: int
    execution_state: str
    status: str

    @property
    def remaining(self) -> int:
        return max(self.amount - self.fulfilled_amount, 0)


@dataclass(frozen=True)
class InstructionDecision:
    action: InstructionAction
    result_state: str  # the case state to commit
    reason: str


def reconcile_instruction(
    active: InstructionState | None,
    *,
    direction: str,
    amount: int,
    cost_basis: str,
) -> InstructionDecision:
    """Decide what to do with the actionable instruction (contracts §10.1).

    - No active instruction => ISSUE abs(S).
    - Same basis/direction/remaining => RETAIN (or REACTIVATE a suspended one).
    - An unresolved execution (OPEN/UNKNOWN) that would be replaced => SUSPEND
      and wait for external verification.
    - Otherwise REPLACE the remainder with the full current abs(S).
    """
    if active is None:
        return InstructionDecision("ISSUE", "READY_TO_EXECUTE", "no active instruction")

    same_basis = active.cost_basis == cost_basis
    same_direction = active.direction == direction
    same_amount = active.remaining == amount
    if same_basis and same_direction and same_amount:
        if active.status in ("SUSPENDED", "EXECUTION_UNKNOWN"):
            if active.execution_state in ("OPEN", "UNKNOWN"):
                return InstructionDecision(
                    "REACTIVATE", "WAITING", "handed-off execution still unknown"
                )
            return InstructionDecision("REACTIVATE", "READY_TO_EXECUTE", "reactivate remainder")
        return InstructionDecision("RETAIN", "READY_TO_EXECUTE", "nothing material changed")

    if active.execution_state in ("OPEN", "UNKNOWN"):
        return InstructionDecision(
            "SUSPEND", "WAITING", "cannot replace an unresolved execution"
        )
    return InstructionDecision("REPLACE", "READY_TO_EXECUTE", "changed basis/direction/amount")
