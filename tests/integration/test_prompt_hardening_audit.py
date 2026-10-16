"""CLI preflight must fail without touching runtime state or providers."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def test_audit_missing_provider_is_not_live_pass(tmp_path):
    env = dict(os.environ)
    for name in ("MISTRAL_API_KEY", "MISTRAL_OCR_MODEL", "XKIRO_API_KEY", "XKIRO_BASE_URL", "INVOICE_REFEREE_LLM_MODEL"):
        env[name] = ""
    env_file = tmp_path / "empty.env"
    env_file.write_text("")
    output = tmp_path / "audit"
    result = subprocess.run([sys.executable, str(ROOT / "scripts/run_prompt_hardening_audit.py"),
        "--mode", "LIVE", "--env-file", str(env_file), "--output-dir", str(output)],
        cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 3
    assert "NOT_RUN" in result.stdout
    assert not list(output.rglob("*.sqlite"))


def test_audit_refuses_partial_case_matrix(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "scripts/run_prompt_hardening_audit.py"),
        "--cases", "TC01", "--output-dir", str(tmp_path / "partial")],
        cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 2
    assert "all required cases" in result.stderr
    assert not (tmp_path / "partial").exists()


def test_audit_scoring_requires_exact_negative_basis():
    sys.path.insert(0, str(ROOT / "scripts"))
    from run_prompt_hardening_audit import score
    base = {"error": None, "state": "WAITING", "instructions": [],
            "issues": [{"kind": "FACT", "field": "expense:arithmetic:line_total",
                        "basis": "expected 500000"}]}
    assert score("TC05", base)
    assert not score("TC05", {**base, "issues": [{"kind": "FACT",
        "field": "expense:arithmetic:line_total", "basis": "difference 400000"}]})
    assert not score("TC03", {"error": None, "state": "WAITING", "instructions": [],
        "issues": [], "conclusion": "OUTSTANDING", "actual_money": {"S": {"state": "KNOWN", "value": 0}}})


def test_audit_difference_matches_vnd_tokens_not_formatting():
    sys.path.insert(0, str(ROOT / "scripts"))
    from run_prompt_hardening_audit import score
    result = {"error": None, "state": "WAITING", "instructions": [], "issues": [{
        "kind": "FACT", "field": "expense:arithmetic:line_total",
        "basis": "Tổng dòng 3.000.000 đ, tổng in 3.500.000 đ, lệch 500.000 đ."}]}
    assert score("TC05", result)
    assert not score("TC05", {**result, "issues": [{**result["issues"][0], "basis": "Lệch 400.000 đ."}]})


def test_audit_rejects_unknown_cases_before_provider(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "scripts/run_prompt_hardening_audit.py"),
        "--cases", "TC99", "--output-dir", str(tmp_path / "audit")],
        cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 2
    assert "Unknown cases" in result.stderr
