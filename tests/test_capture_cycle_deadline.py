import os
import subprocess
import sys
import time
from pathlib import Path
import pytest


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows scheduled task containment')
def test_deadline_terminates_capture_and_its_child(tmp_path):
    marker = tmp_path / 'child-finished'
    child = 'import time; from pathlib import Path; time.sleep(4); Path(%r).touch()' % str(marker)
    script = """
import subprocess, sys, time
from agc_runtime.capture_deadline import cycle_deadline
with cycle_deadline(1):
    subprocess.Popen([sys.executable, '-c', %r])
    time.sleep(30)
""" % child
    result = subprocess.run([sys.executable, '-c', script], timeout=10, capture_output=True)
    assert result.returncode == 124, result.stderr.decode(errors='replace')
    time.sleep(4)
    assert not marker.exists()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows scheduled task containment')
def test_successful_cycle_cancels_deadline():
    script = """
import time
from agc_runtime.capture_deadline import cycle_deadline
with cycle_deadline(.1):
    pass
time.sleep(.3)
"""
    result = subprocess.run([sys.executable, '-c', script], timeout=10, capture_output=True)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
