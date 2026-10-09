"""Settlement factory phải nạp repo `.env` để cấu hình copy-paste hoạt động.

Biến đã export trong môi trường luôn thắng file (setdefault); test này khóa
việc factory quên load file — nếu không, `SETTLEMENT_PROVIDER_MODE` trong `.env`
bị bỏ qua và app luôn chạy fake mode.
"""
from __future__ import annotations

from invoice_referee.api import settlement as settlement_api


def test_create_runtime_app_loads_repo_env(tmp_path, monkeypatch):
    calls: list[dict] = []

    def fake_load() -> dict:
        calls.append({"loaded": True})
        return {}

    monkeypatch.setattr(settlement_api, "load_repo_env", fake_load)
    settlement_api.create_runtime_app(db_path=tmp_path / "cases.sqlite",
                                      artifact_root=tmp_path / "artifacts")
    assert calls == [{"loaded": True}]


def test_explicit_service_skips_env_load(tmp_path, monkeypatch):
    """Truyền service có sẵn thì không dựng composition root, không đọc .env."""
    from invoice_referee.settlement.reader import StructuredLedgerReader
    from invoice_referee.settlement.service import Service, ServiceConfig
    from invoice_referee.settlement.store import Store

    calls: list[dict] = []

    def fake_load() -> dict:
        calls.append({"loaded": True})
        return {}

    monkeypatch.setattr(settlement_api, "load_repo_env", fake_load)
    store = Store(tmp_path / "cases.sqlite", tmp_path / "artifacts")
    service = Service(store, StructuredLedgerReader(store.artifact_root),
                      config=ServiceConfig())
    settlement_api.create_runtime_app(service=service)
    assert calls == []
