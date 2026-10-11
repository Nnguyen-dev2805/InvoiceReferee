"""Bounded retries and readable diagnostics for external AI services."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from time import sleep
from typing import TypeVar

Result = TypeVar("Result")

TRANSIENT_EXCEPTION_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "ConnectError",
    "ConnectTimeout",
    "ReadTimeout",
    "RemoteProtocolError",
    "TimeoutException",
}
TRANSIENT_SOCKET_CODES = {13, 10013, 10048, 10053, 10054, 10060, 10061}


class ExternalServiceUnavailableError(RuntimeError):
    """An external service stayed unavailable after bounded retries."""

    def __init__(self, service: str, attempts: int, cause: Exception) -> None:
        self.service = service
        self.attempts = attempts
        self.cause = cause
        detail = str(cause).strip() or type(cause).__name__
        if _socket_code(cause) == 10013:
            detail = (
                "Windows từ chối mở kết nối mạng cho tiến trình Python "
                "(WinError 10013)"
            )
        super().__init__(
            f"Không thể kết nối {service} sau {attempts} lần thử: {detail}. "
            "Đây là lỗi kết nối dịch vụ, không phải lỗi nội dung chứng từ."
        )


def _exception_chain(error: Exception):
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _socket_code(error: Exception) -> int | None:
    for item in _exception_chain(error):
        for attribute in ("winerror", "errno"):
            value = getattr(item, attribute, None)
            if isinstance(value, int) and value in TRANSIENT_SOCKET_CODES:
                return value
        if "WinError 10013" in str(item):
            return 10013
    return None


def _status_code(error: Exception) -> int | None:
    for item in _exception_chain(error):
        value = getattr(item, "status_code", None)
        if isinstance(value, int):
            return value
        response = getattr(item, "response", None)
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
    return None


def is_transient_service_error(error: Exception) -> bool:
    if _socket_code(error) is not None:
        return True
    status_code = _status_code(error)
    if status_code == 429 or (status_code is not None and status_code >= 500):
        return True
    return any(
        type(item).__name__ in TRANSIENT_EXCEPTION_NAMES
        for item in _exception_chain(error)
    )


def call_with_service_retry(
    operation: Callable[[], Result],
    *,
    service: str,
    retry_delays: Sequence[float] = (0.75, 2.0),
) -> Result:
    attempts = len(retry_delays) + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            if not is_transient_service_error(exc):
                raise
            last_error = exc
            if attempt < len(retry_delays):
                sleep(max(0.0, retry_delays[attempt]))
    assert last_error is not None
    raise ExternalServiceUnavailableError(service, attempts, last_error) from last_error
