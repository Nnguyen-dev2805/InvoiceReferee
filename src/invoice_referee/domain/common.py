"""Strict shared scalars, evidence references and the Fact wrapper (contracts §1–2).

Every domain DTO inherits StrictModel: extra fields are rejected so an
expected/oracle field can never ride along on an application payload, and the
models are frozen value objects.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    model_validator,
)

# Identity and money scalars (contracts §1).
Id = str
Vnd = Annotated[StrictInt, Field(ge=0)]
SignedVnd = StrictInt
Currency = Literal["VND"]

FactState = Literal["KNOWN", "UNKNOWN", "CONFLICT"]

T = TypeVar("T")


def _parse_iso_datetime(value: Any) -> Any:
    """Accept an ISO-8601 string (FastAPI JSON bodies parse to a dict first)."""
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def _to_utc(value: datetime) -> datetime:
    """Require timezone-awareness and normalize every timestamp to UTC (§1)."""
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware (UTC normalized)")
    return value.astimezone(UTC)


# Every timestamp in the domain uses this type: aware, ISO-8601 at the JSON
# boundary, stored normalized to UTC so comparisons never mix naive/aware.
UtcDatetime = Annotated[datetime, BeforeValidator(_parse_iso_datetime), AfterValidator(_to_utc)]


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
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page: Annotated[int | None, Field(default=None, ge=1)] = None
    record_key: str | None = None
    exact_quote: str = Field(min_length=1)
    bbox: tuple[float, float, float, float] | None = None

    @model_validator(mode="after")
    def _require_locator(self) -> EvidenceRef:
        page_missing = self.page is None
        key = (self.record_key or "").strip()
        if page_missing and not key:
            raise ValueError("EvidenceRef requires a 1-based page or a record_key")
        if not self.exact_quote.strip():
            raise ValueError("EvidenceRef requires a non-blank exact_quote")
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

    @model_validator(mode="after")
    def _typed_when_generic_is_unbound(self) -> Fact[T]:
        # A bare `Fact` (no type argument) is a latent trap: it would accept a
        # bool/float/str as "money". Every real field uses Fact[T] (T money or
        # signed money); reject values on an unparameterized Fact.
        meta = getattr(type(self), "__pydantic_generic_metadata__", None)
        if meta is not None and meta.get("origin") is None and self.value is not None:
            raise ValueError("Fact must be parameterized, e.g. Fact[Vnd]")
        return self
