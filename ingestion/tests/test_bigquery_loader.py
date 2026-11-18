from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from conftest import NOW
from google.api_core import exceptions as google_errors
from google.cloud import bigquery

from claims_ingest.bigquery_loader import (
    BigQueryLoader,
    build_schema,
    is_transient_bigquery_error,
)
from claims_ingest.errors import LoadError
from claims_ingest.models import PreparedFile, RunRecord, RunStatus

TABLE_ID = "demo-project.raw.members_s01"


class FakeJob:
    def __init__(self, output_rows: int = 0, error: Exception | None = None) -> None:
        self.output_rows = output_rows
        self.error = error

    def result(self, timeout: int | None = None) -> None:
        if self.error:
            raise self.error


class FakeClient:
    def __init__(self, load_errors: list[Exception] | None = None, row_delta: int = 0) -> None:
        self.load_errors = list(load_errors or [])
        self.row_delta = row_delta
        self.tables: dict[str, SimpleNamespace] = {}
        self.load_configs: list[bigquery.LoadJobConfig] = []
        self.payloads: list[bytes] = []
        self.json_loads: list[tuple[list[dict], str, bigquery.LoadJobConfig]] = []
        self.deleted: list[str] = []
        self.datasets: list[bigquery.Dataset] = []

    def create_dataset(self, dataset, exists_ok=False):
        self.datasets.append(dataset)

    def get_table(self, table_id):
        if table_id not in self.tables:
            raise google_errors.NotFound("missing")
        return self.tables[table_id]

    def delete_table(self, table_id, not_found_ok=False):
        self.deleted.append(table_id)

    def update_table(self, table, fields):
        assert fields == ["labels"]

    def load_table_from_file(self, handle, table_id, job_config, location):
        payload = handle.read()
        self.payloads.append(payload)
        self.load_configs.append(job_config)
        if self.load_errors:
            return FakeJob(error=self.load_errors.pop(0))
        rows = payload.count(b"\n") - 1 + self.row_delta
        self.tables[table_id] = SimpleNamespace(labels={}, expires=None, num_rows=rows)
        return FakeJob(output_rows=rows)

    def load_table_from_json(self, rows, table_id, job_config, location):
        self.json_loads.append((rows, table_id, job_config))
        return FakeJob()


def make_loader(client: FakeClient) -> BigQueryLoader:
    return BigQueryLoader("demo-project", "US", "raw", client=client, sleep=lambda _: None)


@pytest.fixture
def prepared(tmp_path) -> PreparedFile:
    path = tmp_path / "members.csv"
    path.write_bytes(b"ID,_loaded_at,_source_file,_batch_id\n1,t,f,b\n2,t,f,b\n")
    return PreparedFile(path, ("ID",), 2, 2, 100, 50)


def test_schema_keeps_source_columns_as_strings():
    schema = {field.name: field.field_type for field in build_schema(("ID", "AMOUNT"))}

    assert schema == {
        "ID": "STRING",
        "AMOUNT": "STRING",
        "_loaded_at": "TIMESTAMP",
        "_source_file": "STRING",
        "_batch_id": "STRING",
    }


def test_load_replaces_the_table_and_rejects_bad_rows(prepared):
    client = FakeClient()

    rows = make_loader(client).load(prepared, "members_s01", "batch1")

    config = client.load_configs[0]
    assert rows == 2
    assert config.write_disposition == bigquery.WriteDisposition.WRITE_TRUNCATE
    assert config.skip_leading_rows == 1
    assert config.max_bad_records == 0


def test_batch_is_recorded_on_the_table_after_a_load(prepared):
    client = FakeClient()

    make_loader(client).load(prepared, "members_s01", "batch1")

    assert client.tables[TABLE_ID].labels == {"batch_id": "batch1"}


def test_row_count_mismatch_fails_and_leaves_the_batch_unrecorded(prepared):
    client = FakeClient(row_delta=-1)

    with pytest.raises(LoadError, match="prepared 2, loaded 1"):
        make_loader(client).load(prepared, "members_s01", "batch1")

    assert client.tables[TABLE_ID].labels == {}


def test_transient_load_failure_resends_the_whole_file(prepared):
    client = FakeClient(load_errors=[google_errors.ServiceUnavailable("try later")])

    rows = make_loader(client).load(prepared, "members_s01", "batch1")

    assert rows == 2
    assert len(client.payloads) == 2
    assert client.payloads[0] == client.payloads[1]


def test_rejected_load_is_reported_without_retrying(prepared):
    client = FakeClient(load_errors=[google_errors.BadRequest("bad schema")])

    with pytest.raises(LoadError, match="rejected the load into members_s01.*bad schema"):
        make_loader(client).load(prepared, "members_s01", "batch1")

    assert len(client.payloads) == 1


def test_missing_table_has_no_state():
    assert make_loader(FakeClient()).get_table_state("members_s01") is None


def test_table_state_reads_batch_expiry_and_rows():
    client = FakeClient()
    expires = NOW + timedelta(days=30)
    client.tables[TABLE_ID] = SimpleNamespace(
        labels={"batch_id": "batch1"}, expires=expires, num_rows=7
    )

    state = make_loader(client).get_table_state("members_s01")

    assert (state.batch_id, state.expires_at, state.row_count) == ("batch1", expires, 7)


def test_run_records_are_appended():
    client = FakeClient()
    record = RunRecord(
        run_id="run1",
        source_key="members",
        sample=1,
        table_name="members_s01",
        source_file="members.zip",
        batch_id="batch1",
        status=RunStatus.LOADED,
        rows_read=2,
        rows_written=2,
        error_message=None,
        started_at=NOW,
        finished_at=NOW,
    )

    make_loader(client).record_runs([record])

    rows, table_id, config = client.json_loads[0]
    assert table_id == "demo-project.raw._ingest_runs"
    assert config.write_disposition == bigquery.WriteDisposition.WRITE_APPEND
    assert rows[0]["status"] == "loaded"
    assert rows[0]["started_at"] == NOW.isoformat()


def test_empty_run_records_make_no_call():
    client = FakeClient()

    make_loader(client).record_runs([])

    assert client.json_loads == []


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (google_errors.ServiceUnavailable("busy"), True),
        (google_errors.TooManyRequests("slow down"), True),
        (google_errors.Forbidden("limit", errors=[{"reason": "rateLimitExceeded"}]), True),
        (google_errors.Forbidden("denied", errors=[{"reason": "accessDenied"}]), False),
        (google_errors.BadRequest("bad"), False),
        (google_errors.NotFound("missing"), False),
    ],
)
def test_transient_error_classification(error, expected):
    assert is_transient_bigquery_error(error) is expected
