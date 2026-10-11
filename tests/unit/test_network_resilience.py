import pytest

from invoice_referee.extraction import (
    ExternalServiceUnavailableError,
    call_with_service_retry,
)


def test_retry_recovers_from_winerror_10013() -> None:
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise OSError(10013, "socket access forbidden")
        return "ok"

    assert call_with_service_retry(
        operation,
        service="Test API",
        retry_delays=(0, 0),
    ) == "ok"
    assert calls == 3


def test_retry_reports_service_after_socket_error_is_exhausted() -> None:
    with pytest.raises(ExternalServiceUnavailableError) as error:
        call_with_service_retry(
            lambda: (_ for _ in ()).throw(
                OSError(10013, "socket access forbidden")
            ),
            service="Mistral OCR",
            retry_delays=(0, 0),
        )

    message = str(error.value)
    assert "Mistral OCR" in message
    assert "3 lần thử" in message
    assert "WinError 10013" in message
    assert "không phải lỗi nội dung chứng từ" in message


def test_retry_does_not_repeat_non_network_validation_error() -> None:
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        raise ValueError("invalid schema")

    with pytest.raises(ValueError, match="invalid schema"):
        call_with_service_retry(
            operation,
            service="Test API",
            retry_delays=(0, 0),
        )
    assert calls == 1
