import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def run_cli():
    def invoke(*args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "agc_runtime.cli", *args],
            input=stdin,
            text=True,
            capture_output=True,
            check=False,
        )

    return invoke


@pytest.fixture
def cli(run_cli):
    def invoke(tool: str, root: Path, payload: dict) -> dict:
        result = run_cli(
            tool,
            "--root",
            str(root),
            "--input",
            "-",
            stdin=json.dumps(payload, ensure_ascii=False),
        )
        assert result.returncode == 0, result.stderr or result.stdout
        return json.loads(result.stdout)

    return invoke
