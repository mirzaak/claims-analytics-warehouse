from __future__ import annotations

import gzip
from datetime import timedelta, timezone

import pytest
from conftest import NOW, beneficiary_rows, cache_source, make_source

from claims_ingest.errors import LoadError
from claims_ingest.models import PreparedFile, RunRecord, RunStatus
from claims_ingest.pipeline import run_pipeline
from claims_ingest.snowflake_loader import SnowflakeLoader


class FakeCursor:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.description = None
        self.rows: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.connection.statements.append(" ".join(sql.split()))
        rows = self.connection.respond(" ".join(sql.split()), params)
        self.description = None if rows is None else [("column",)]
        self.rows = rows or []

    def fetchall(self):
        return self.rows

    def executemany(self, sql, rows):
        self.connection.many.append((sql, rows))


class FakeConnection:
    """Mimics the Snowflake statements the loader issues, including PUT and COPY."""

    def __init__(self, tables=(), state=None, copy_delta=0):
        self.tables = set(tables)
        self.state = dict(state or {})
        self.copy_delta = copy_delta
        self.statements: list[str] = []
        self.many: list = []
        self.staged_rows = 0

    def cursor(self):
        return FakeCursor(self)

    def respond(self, sql, params):
        words = sql.split()
        low = sql.lower()
        if "information_schema.tables" in low:
            return [(1 if params[1] in self.tables else 0,)]
        if low.startswith("select batch_id"):
            table = params[0]
            return [self.state[table]] if table in self.state else []
        if low.startswith("create or replace table"):
            self.tables.add(words[4].split(".")[1])
        if low.startswith("put "):
            path = sql.split("'")[1].removeprefix("file://")
            with gzip.open(path, "rt") as handle:
                self.staged_rows = sum(1 for _ in handle) - 1
            return [("file", "UPLOADED")]
        if low.startswith("copy into"):
            loaded = self.staged_rows + self.copy_delta
            return [("file", "LOADED", loaded, loaded, 1, 0)]
        if low.startswith("alter table") and " rename to " in low:
            self.tables.discard(words[2].split(".")[1])
            self.tables.add(words[5].split(".")[1])
        if low.startswith("drop table if exists"):
            self.tables.discard(words[4].split(".")[1])
        if low.startswith("merge into"):
            self.state[params[0]] = (params[1], params[2])
        if low.startswith("delete from"):
            self.state.pop(params[0], None)
        return None


@pytest.fixture
def prepared(tmp_path) -> PreparedFile:
    import gzip

    path = tmp_path / "members.csv.gz"
    with gzip.open(path, "wt") as handle:
        handle.write("ID,_loaded_at,_source_file,_batch_id\n1,t,f,b\n2,t,f,b\n")
    return PreparedFile(path, ("ID",), 2, 2, 100, 50)


def test_first_load_renames_the_loading_table_and_records_the_batch(prepared):
    connection = FakeConnection()

    rows = SnowflakeLoader(connection).load(prepared, "members_s01", "batch1")

    assert rows == 2
    assert "MEMBERS_S01" in connection.tables
    assert "MEMBERS_S01__LOADING" not in connection.tables
    assert any("rename to RAW.MEMBERS_S01" in s for s in connection.statements)
    assert connection.state["MEMBERS_S01"] == ("batch1", 2)


def test_reload_swaps_the_new_table_in_atomically(prepared):
    connection = FakeConnection(tables={"MEMBERS_S01"}, state={"MEMBERS_S01": ("old", 5)})

    SnowflakeLoader(connection).load(prepared, "members_s01", "batch2")

    assert any("swap with RAW.MEMBERS_S01" in s for s in connection.statements)
    assert "MEMBERS_S01__LOADING" not in connection.tables
    assert connection.state["MEMBERS_S01"] == ("batch2", 2)


def test_copy_uses_strict_csv_settings(prepared):
    connection = FakeConnection()

    SnowflakeLoader(connection).load(prepared, "members_s01", "batch1")

    copy = next(s for s in connection.statements if s.startswith("copy into"))
    assert "on_error = abort_statement" in copy
    assert "escape_unenclosed_field = none" in copy
    assert "compression = gzip" in copy


def test_row_count_mismatch_drops_the_loading_table_and_keeps_the_old_one(prepared):
    connection = FakeConnection(
        tables={"MEMBERS_S01"}, state={"MEMBERS_S01": ("old", 5)}, copy_delta=-1
    )

    with pytest.raises(LoadError, match="prepared 2, loaded 1"):
        SnowflakeLoader(connection).load(prepared, "members_s01", "batch2")

    assert not any("swap with" in s for s in connection.statements)
    assert "MEMBERS_S01__LOADING" not in connection.tables
    assert connection.state["MEMBERS_S01"] == ("old", 5)


def test_unsafe_column_names_are_refused(tmp_path):
    bad = PreparedFile(tmp_path / "x.csv.gz", ("ID; drop table x",), 1, 1, 1, 1)

    with pytest.raises(LoadError, match="Unsafe Snowflake identifier"):
        SnowflakeLoader(FakeConnection()).load(bad, "members_s01", "batch1")


def test_table_state_for_missing_table_is_none():
    assert SnowflakeLoader(FakeConnection()).get_table_state("members_s01") is None


def test_table_state_reads_batch_and_rows():
    connection = FakeConnection(tables={"MEMBERS_S01"}, state={"MEMBERS_S01": ("b1", 7)})

    state = SnowflakeLoader(connection).get_table_state("members_s01")

    assert (state.batch_id, state.row_count, state.expires_at) == ("b1", 7, None)


def test_table_without_state_has_no_batch():
    connection = FakeConnection(tables={"MEMBERS_S01"})

    assert SnowflakeLoader(connection).get_table_state("members_s01").batch_id is None


def test_run_records_use_sample_column_name_and_naive_utc_times():
    connection = FakeConnection()
    started = NOW.astimezone(timezone(timedelta(hours=2)))
    record = RunRecord(
        "run1",
        "members",
        1,
        "members_s01",
        "m.zip",
        "b1",
        RunStatus.LOADED,
        2,
        2,
        None,
        started,
        started,
    )

    SnowflakeLoader(connection).record_runs([record])

    sql, rows = connection.many[0]
    assert "SYNPUF_SAMPLE" in sql
    assert rows[0][6] == "loaded"
    assert rows[0][10] == NOW.replace(tzinfo=None)


def test_pipeline_skips_unchanged_files_on_snowflake(settings):
    source = make_source()
    cache_source(settings, source, beneficiary_rows(3))
    connection = FakeConnection()
    loader = SnowflakeLoader(connection)

    first = run_pipeline([source], settings, loader, clock=lambda: NOW)
    second = run_pipeline([source], settings, loader, clock=lambda: NOW)

    assert first.records[0].status is RunStatus.LOADED
    assert second.records[0].status is RunStatus.SKIPPED
    assert sum(s.startswith("copy into") for s in connection.statements) == 1
