from __future__ import annotations

from types import SimpleNamespace

import pytest
from conftest import NOW
from google.api_core import exceptions as google_errors

from claims_ingest.cli import EXIT_RUN_FAILED, main
from claims_ingest.row_counts import BigQueryRowCountStore, compare_counts, run_check


def test_unchanged_counts_pass():
    results = compare_counts({"t": 100}, {"t": 100}, 0.1)

    assert results[0].problem is None
    assert results[0].change_rate == 0


@pytest.mark.parametrize("current", [111, 89])
def test_change_beyond_the_limit_fails_in_either_direction(current):
    result = compare_counts({"t": 100}, {"t": current}, 0.1)[0]

    assert "more than the allowed 10%" in result.problem


@pytest.mark.parametrize("current", [110, 90])
def test_change_at_the_limit_passes(current):
    assert compare_counts({"t": 100}, {"t": current}, 0.1)[0].problem is None


def test_empty_table_fails_even_without_history():
    assert compare_counts({}, {"t": 0}, 0.1)[0].problem == "table is empty"


def test_first_run_has_nothing_to_compare():
    result = compare_counts({}, {"t": 5}, 0.1)[0]

    assert result.problem is None
    assert result.previous is None
    assert result.change_rate is None


class FakeQueryJob:
    def __init__(self, rows):
        self.rows = rows

    def result(self):
        return self.rows


class FakeClient:
    def __init__(self, counts, history=None, missing_history=False):
        self.counts = counts
        self.history = history or []
        self.missing_history = missing_history
        self.appended = []
        self.history_table = SimpleNamespace(expires=None)
        self.expiry_updates = 0

    def get_table(self, table_id):
        if table_id.endswith("row_count_history"):
            return self.history_table
        name = table_id.split(".", 1)[1]
        if name not in self.counts:
            raise google_errors.NotFound("missing")
        return SimpleNamespace(num_rows=self.counts[name])

    def query(self, sql, location):
        if self.missing_history:
            raise google_errors.NotFound("no history yet")
        return FakeQueryJob(self.history)

    def load_table_from_json(self, rows, table_id, job_config, location):
        self.appended.extend(rows)
        return FakeQueryJob([])

    def update_table(self, table, fields):
        assert fields == ["expires"]
        self.expiry_updates += 1
        return table


def make_store(client):
    return BigQueryRowCountStore(
        "demo",
        "US",
        client=client,
        sleep=lambda _: None,
        clock=lambda: NOW,
    )


def test_run_compares_with_history_and_records_current_counts():
    client = FakeClient(
        counts={"marts.a": 100, "marts.b": 50},
        history=[
            {"table_name": "marts.a", "row_count": 100},
            {"table_name": "marts.b", "row_count": 80},
        ],
    )

    results = run_check(make_store(client), "run1", 0.1, tables=("marts.a", "marts.b"))

    assert [r.problem is None for r in results] == [True, False]
    assert [row["row_count"] for row in client.appended] == [100, 50]
    assert {row["run_id"] for row in client.appended} == {"run1"}


def test_first_run_without_history_table_passes():
    client = FakeClient(counts={"marts.a": 10}, missing_history=True)

    results = run_check(make_store(client), "run1", 0.1, tables=("marts.a",))

    assert results[0].problem is None
    assert len(client.appended) == 1


def test_missing_table_counts_as_empty():
    client = FakeClient(counts={}, missing_history=True)

    results = run_check(make_store(client), "run1", 0.1, tables=("marts.gone",))

    assert results[0].problem == "table is empty"


def test_recording_never_changes_the_history_expiry():
    # The sandbox rejects expiries more than 60 days after a table's creation.
    client = FakeClient(counts={"marts.a": 10}, missing_history=True)

    run_check(make_store(client), "run1", 0.1, tables=("marts.a",))

    assert client.expiry_updates == 0


def test_cli_rejects_an_invalid_change_limit(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GCP_PROJECT_ID", "demo")

    code = main(["check-row-counts", "--max-change", "5"])

    assert code == EXIT_RUN_FAILED
    assert "--max-change must be between 0 and 1" in capsys.readouterr().err
