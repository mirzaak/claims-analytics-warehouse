"""Tests for scripts/send_alert.py, which runs outside the package."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "send_alert.py"
spec = importlib.util.spec_from_file_location("send_alert", SCRIPT)
send_alert = importlib.util.module_from_spec(spec)
spec.loader.exec_module(send_alert)

ENV = {
    "FAILED_STEP": "dbt build",
    "RUN_URL": "https://github.com/owner/repo/actions/runs/1",
    "REPOSITORY_URL": "https://github.com/owner/repo",
    "TRIGGER": "schedule",
    "COMMIT_SHA": "abcdef1234567",
}


def test_message_names_the_step_run_and_runbook_section():
    message = send_alert.build_message(ENV)

    assert "at step: **dbt build**" in message
    assert "Run log: https://github.com/owner/repo/actions/runs/1" in message
    assert "RUNBOOK.md#dbt-build" in message
    assert "Commit: abcdef1" in message


def test_unknown_step_links_to_the_runbook_top():
    message = send_alert.build_message({**ENV, "FAILED_STEP": "Something new"})

    assert message.endswith("/blob/main/RUNBOOK.md")


@pytest.mark.parametrize("step", sorted(send_alert.RUNBOOK_SECTIONS))
def test_every_step_has_a_runbook_section(step):
    section = send_alert.RUNBOOK_SECTIONS[step]
    runbook = (SCRIPT.parents[1] / "RUNBOOK.md").read_text()

    headings = {
        line.lstrip("#").strip().lower().replace(" ", "-").replace(",", "")
        for line in runbook.splitlines()
        if line.startswith("## ")
    }
    assert section in headings


def test_missing_webhook_only_logs(monkeypatch, capsys):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    assert send_alert.main() == 0
    assert "only logged" in capsys.readouterr().out
