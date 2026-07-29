import subprocess
import sys

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
