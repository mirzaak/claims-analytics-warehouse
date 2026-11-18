from dataclasses import replace
from datetime import timedelta

import pytest
from conftest import NOW, FakeWarehouse, beneficiary_rows, cache_source, make_source

from claims_ingest.models import RunStatus, TableState
from claims_ingest.pipeline import Action, decide_action, run_pipeline


def clock():
    return NOW


def run(sources, settings, warehouse, **kwargs):
    return run_pipeline(sources, settings, warehouse, clock=clock, **kwargs)


@pytest.mark.parametrize(
    ("state", "batch_id", "force", "expected"),
    [
        (None, "new", False, Action.LOAD),
        (TableState("old", NOW + timedelta(days=60), 5), "new", False, Action.LOAD),
        (TableState("same", NOW + timedelta(days=60), 5), "same", True, Action.LOAD),
        (TableState("same", NOW + timedelta(days=60), 5), "same", False, Action.SKIP),
        (TableState("same", None, 5), "same", False, Action.SKIP),
        (TableState("same", NOW + timedelta(days=14), 5), "same", False, Action.REFRESH),
        (TableState("same", NOW + timedelta(days=15), 5), "same", False, Action.SKIP),
    ],
)
def test_decide_action(state, batch_id, force, expected):
    assert decide_action(state, batch_id, NOW, refresh_days=14, force=force) is expected


def test_first_run_loads_rows_with_metadata(settings, warehouse):
    source = make_source()
    cache_source(settings, source, beneficiary_rows(3))

    summary = run([source], settings, warehouse)

    assert summary.succeeded
    assert summary.records[0].status is RunStatus.LOADED
    assert summary.records[0].rows_written == 3
    rows = warehouse.tables[source.table]
    assert len(rows) == 3
    assert {row["_batch_id"] for row in rows} == {summary.records[0].batch_id}


def test_rerunning_the_same_batch_does_not_duplicate_rows(settings, warehouse):
    source = make_source()
    cache_source(settings, source, beneficiary_rows(3))

    run([source], settings, warehouse)
    second = run([source], settings, warehouse)

    assert second.records[0].status is RunStatus.SKIPPED
    assert second.records[0].rows_written == 3
    assert warehouse.load_calls == [source.table]
    assert len(warehouse.tables[source.table]) == 3


def test_changed_source_replaces_the_table(settings, warehouse):
    source = make_source()
    cache_source(settings, source, beneficiary_rows(3))
    run([source], settings, warehouse)

    cache_source(settings, source, beneficiary_rows(2))
    summary = run([source], settings, warehouse)

    assert summary.records[0].status is RunStatus.LOADED
    assert len(warehouse.tables[source.table]) == 2


def test_new_sample_loads_without_reloading_existing_files(settings, warehouse):
    first = make_source(sample=1)
    second = make_source(sample=2)
    cache_source(settings, first, beneficiary_rows(3))
    cache_source(settings, second, beneficiary_rows(4))
    run([first], settings, warehouse)

    summary = run([first, second], settings, warehouse)

    assert [record.status for record in summary.records] == [RunStatus.SKIPPED, RunStatus.LOADED]
    assert warehouse.load_calls == [first.table, second.table]


def test_changing_the_sample_rate_reloads_the_file(settings, warehouse):
    source = make_source()
    cache_source(settings, source, beneficiary_rows(50))
    run([source], settings, warehouse)

    summary = run([source], replace(settings, member_sample_pct=50), warehouse)

    assert summary.records[0].status is RunStatus.LOADED
    assert len(warehouse.load_calls) == 2


def test_table_close_to_expiry_is_recreated(settings, warehouse):
    source = make_source()
    cache_source(settings, source, beneficiary_rows(3))
    run([source], settings, warehouse)
    state = warehouse.states[source.table]
    warehouse.states[source.table] = replace(state, expires_at=NOW + timedelta(days=3))

    summary = run([source], settings, warehouse)

    assert summary.records[0].status is RunStatus.LOADED
    assert warehouse.drop_calls == [source.table]
    assert len(warehouse.tables[source.table]) == 3


def test_force_reloads_an_unchanged_file(settings, warehouse):
    source = make_source()
    cache_source(settings, source, beneficiary_rows(3))
    run([source], settings, warehouse)

    summary = run([source], settings, warehouse, force=True)

    assert summary.records[0].status is RunStatus.LOADED
    assert len(warehouse.tables[source.table]) == 3


def test_one_failed_file_does_not_stop_the_others(settings):
    bad = make_source("beneficiary_2008")
    good = make_source("beneficiary_2009")
    cache_source(settings, bad, beneficiary_rows(3))
    cache_source(settings, good, beneficiary_rows(3))
    warehouse = FakeWarehouse(fail_tables={bad.table})

    summary = run([bad, good], settings, warehouse)

    assert not summary.succeeded
    assert summary.failed[0].table_name == bad.table
    assert "simulated failure" in summary.failed[0].error_message
    assert good.table in warehouse.tables


def test_every_file_outcome_is_recorded_once(settings):
    bad = make_source("beneficiary_2008")
    good = make_source("beneficiary_2009")
    cache_source(settings, bad, beneficiary_rows(3))
    cache_source(settings, good, beneficiary_rows(3))
    warehouse = FakeWarehouse(fail_tables={bad.table})

    summary = run([bad, good], settings, warehouse)

    assert [record.status for record in warehouse.runs] == [RunStatus.FAILED, RunStatus.LOADED]
    assert {record.run_id for record in warehouse.runs} == {summary.run_id}


def test_prepared_files_are_removed_after_success_and_failure(settings):
    bad = make_source("beneficiary_2008")
    good = make_source("beneficiary_2009")
    cache_source(settings, bad, beneficiary_rows(3))
    cache_source(settings, good, beneficiary_rows(3))
    warehouse = FakeWarehouse(fail_tables={bad.table})

    run([bad, good], settings, warehouse)

    assert len(warehouse.prepared_paths) == 2
    assert not any(path.exists() for path in warehouse.prepared_paths)


def test_dry_run_reports_counts_without_a_warehouse(settings):
    source = make_source()
    cache_source(settings, source, beneficiary_rows(3))

    summary = run_pipeline([source], settings, None, clock=clock)

    assert summary.records[0].status is RunStatus.PREPARED
    assert summary.records[0].rows_read == 3
    assert list((settings.data_dir / "prepared").iterdir()) == []
