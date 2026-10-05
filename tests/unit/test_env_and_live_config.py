"""Tests for `.env` loading and live provider key wiring (T15 fix).

These prove an operator can start a live runtime from a `.env` file without
exporting variables by hand, and that a missing key fails closed with
CONFIG_NOT_ACTIVE (never a fake pass).
"""
from __future__ import annotations

import os

import pytest

from invoice_referee.env import load_env_file, parse_env_text
from invoice_referee.extraction.providers import LiveProviders


def test_parse_env_text_handles_comments_quotes_and_export():
    text = (
        '# a comment\n'
        '\n'
        'PLAIN=value\n'
        'export EXPORTED=exported_value\n'
        'QUOTED="quoted value"\n'
        "SINGLE='single'\n"
        'TRAILING=abc   # inline comment\n'
        'HASHY=a#b\n'  # no space before # -> part of the value
    )
    values = parse_env_text(text)
    assert values['PLAIN'] == 'value'
    assert values['EXPORTED'] == 'exported_value'
    assert values['QUOTED'] == 'quoted value'
    assert values['SINGLE'] == 'single'
    assert values['TRAILING'] == 'abc'
    assert values['HASHY'] == 'a#b'


def test_load_env_file_existing_env_wins(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    env_file.write_text('DATA_ROOT=from_file\nPROVIDER_MODE=live\n', encoding='utf-8')
    monkeypatch.setenv('DATA_ROOT', 'from_shell')
    monkeypatch.delenv('PROVIDER_MODE', raising=False)
    load_env_file(env_file)
    assert os.environ['DATA_ROOT'] == 'from_shell'  # shell export wins
    assert os.environ['PROVIDER_MODE'] == 'live'  # file fills the gap


def test_load_env_file_missing_is_noop(tmp_path):
    assert load_env_file(tmp_path / 'nope.env') == {}


def test_live_providers_read_mistral_key_from_env(monkeypatch):
    monkeypatch.setenv('MISTRAL_API_KEY', 'mistral-xyz')
    assert LiveProviders()._mistral_api_key == 'mistral-xyz'


def test_live_providers_read_kimi_api_key_from_env(monkeypatch):
    monkeypatch.setenv('KIMI_API_KEY', 'kimi-key')
    monkeypatch.delenv('KIMI_TOKEN', raising=False)
    monkeypatch.delenv('KIMI_SECRET', raising=False)
    assert LiveProviders()._kimi_api_key == 'kimi-key'


def test_live_providers_combine_kimi_token_and_secret(monkeypatch):
    monkeypatch.delenv('KIMI_API_KEY', raising=False)
    monkeypatch.setenv('KIMI_TOKEN', 'tok')
    monkeypatch.setenv('KIMI_SECRET', 'sec')
    assert LiveProviders()._kimi_api_key == 'tok.sec'


def test_live_providers_no_kimi_key_is_none(monkeypatch):
    for name in ('KIMI_API_KEY', 'KIMI_TOKEN', 'KIMI_SECRET'):
        monkeypatch.delenv(name, raising=False)
    assert LiveProviders()._kimi_api_key is None


def test_explicit_key_argument_wins_over_env(monkeypatch):
    monkeypatch.setenv('MISTRAL_API_KEY', 'from-env')
    assert LiveProviders(mistral_api_key='explicit')._mistral_api_key == 'explicit'


def test_live_provider_without_key_fails_closed(monkeypatch):
    for name in ('MISTRAL_API_KEY', 'KIMI_API_KEY', 'KIMI_TOKEN', 'KIMI_SECRET'):
        monkeypatch.delenv(name, raising=False)
    from invoice_referee.domain.models import DomainError

    providers = LiveProviders()
    with pytest.raises(DomainError) as exc:
        providers._require_ocr_client()
    assert exc.value.code == 'CONFIG_NOT_ACTIVE'
