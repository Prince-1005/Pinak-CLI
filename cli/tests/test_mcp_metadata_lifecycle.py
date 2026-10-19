"""A hung parser is killed through its actual Python PID, including venv redirectors."""

import contextlib
import json
import subprocess
import sys
import time

import psutil
import pytest

from pinak.mcp_server import media_info
from pinak.mcp_server.policy import ToolFailure

pytest.importorskip("mcp")


def test_outer_probe_timeout_kills_actual_helper_and_descendant(tmp_path, monkeypatch):
    info = tmp_path / "owned-processes.json"
    script = """
import json, os, pathlib, subprocess, sys, time
from pinak.mcp_server import media_info
from pinak.media.decoders.probe import MediaProbe
info = pathlib.Path(sys.argv[1])
sys.argv = ['media_info', *sys.argv[2:]]
def hang(*args, **kwargs):
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    info.write_text(json.dumps({'helper':os.getpid(),'child':child.pid}))
    time.sleep(60)
MediaProbe.probe = hang
media_info.main()
"""
    launch = subprocess.Popen

    def fault_launch(arguments, **kwargs):
        return launch([sys.executable, "-c", script, str(info), *arguments[3:]], **kwargs)

    monkeypatch.setattr(media_info.subprocess, "Popen", fault_launch)
    monkeypatch.setattr(media_info, "PROBE_TIMEOUT_SECONDS", 3)
    before = time.monotonic()
    with pytest.raises(ToolFailure) as failure:
        media_info.inspect_media(tmp_path / "untrusted.wav")
    assert failure.value.code == "METADATA_TIMEOUT"
    assert time.monotonic() - before < 7
    details = json.loads(info.read_text())
    for pid in details.values():
        with contextlib.suppress(psutil.NoSuchProcess):
            psutil.Process(pid).wait(timeout=3)
