import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import generate_tickets
import merge_ticket
import pick_ticket

# Issue bodies contain emoji and em-dashes. On Windows, subprocess text mode
# defaults to cp1252 and crashes decoding these (byte 0x8d is undefined there).
UTF8_TEXT = "café — Estratégia 🎉 ✅"


@pytest.mark.parametrize("module", [pick_ticket, merge_ticket, generate_tickets])
def test_run_gh_decodes_as_utf8(module, monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    module.run_gh(["issue", "list"])

    assert captured["encoding"] == "utf-8"


def test_run_shell_decodes_utf8_output():
    code = f"import sys; sys.stdout.buffer.write({UTF8_TEXT!r}.encode('utf-8'))"
    returncode, stdout, _ = merge_ticket.run_shell([sys.executable, "-c", code])

    assert returncode == 0
    assert stdout == UTF8_TEXT
