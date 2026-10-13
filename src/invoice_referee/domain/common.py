"""Strict shared scalars, evidence references and the Fact wrapper (contracts §1–2).

Every domain DTO inherits StrictModel: extra fields are rejected so an
expected/oracle field can never ride along on an application payload, and the
models are frozen value objects.
"""

from __future__ import annotations

from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

# Identity and money scalars (contracts §1).
Id = str
Vnd = Annotated[StrictInt, Field(ge=0)]
SignedVnd = StrictInt
Currency = Literal["VND"]

FactState = Literal["KNOWN", "UNKNOWN", "CONFLICT"]

T = TypeVar("T")


class StrictModel(BaseModel):
    """Base for every domain DTO: forbid unknown fields, immutable by value."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class KnownAmount(StrictModel):
    """A verified, known VND amount. Booleans and floats are not money."""

    value: Vnd
    currency: Currency = "VND"


class EvidenceRef(StrictModel):
    """A locator inside a specific source revision (contracts §1).

    The model may propose a ref but never grants Fact.KNOWN: a ref carries a
    real digest and either a 1-based page or a record key.
    """

    source_id: Id
    source_sha256: str = Field(min_length=1)
    page: Annotated[int | None, Field(default=None, ge=1)] = None
    record_key: str | None = None
    exact_quote: str
    bbox: tuple[float, float, float, float] | None = None

    @model_validator(mode="after")
    def _require_locator(self) -> EvidenceRef:
        if self.page is None and self.record_key is None:
            raise ValueError("EvidenceRef requires a 1-based page or a record_key")
        return self


class Fact(StrictModel, Generic[T]):
    """A derived fact. UNKNOWN/CONFLICT carry no aggregate value (§2)."""

    key: str
    value: T | None = None
    state: FactState
    refs: tuple[EvidenceRef, ...] = ()
    verified_by: Id | None = None

    @model_validator(mode="after")
    def _state_matches_value(self) -> Fact[T]:
        if self.state == "KNOWN" and self.value is None:
            raise ValueError("a KNOWN fact requires a value")
        if self.state != "KNOWN" and self.value is not None:
            raise ValueError(f"a {self.state} fact must not carry an aggregate value")
        return self
