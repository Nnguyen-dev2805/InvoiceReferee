"""Deploy-readiness: the entrypoint must import from any working directory.

Streamlit Community Cloud runs the app as ``streamlit run app/streamlit_app.py``
without ``python -m``, so the repository root is not placed on ``sys.path`` the
way a local ``python -m streamlit run`` invocation does. The entrypoint must
therefore make its own ``app`` package importable.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = PROJECT_ROOT / "app" / "streamlit_app.py"


def test_entrypoint_imports_app_package_from_foreign_cwd(tmp_path: Path) -> None:
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env["INVOICE_REFEREE_DATA_DIR"] = str(tmp_path)
    code = (
        "from streamlit.testing.v1 import AppTest;"
        f"at = AppTest.from_file({str(ENTRYPOINT)!r}, default_timeout=60).run();"
        "print('EXCEPTIONS', len(at.exception));"
        "[print('MESSAGE', e.value) for e in at.exception]"
    )

    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert "EXCEPTIONS 0" in proc.stdout, (
        "entrypoint failed from a foreign working directory\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
