"""BigQuery loader built on load jobs, because the sandbox does not support DML."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import requests
from google.api_core import exceptions as google_errors
from google.cloud import bigquery

from claims_ingest.errors import LoadError
from claims_ingest.models import PreparedFile, RunRecord, TableState
from claims_ingest.prepare import METADATA_COLUMNS
from claims_ingest.retry import retry_call

logger = logging.getLogger(__name__)

BATCH_LABEL = "batch_id"
RUNS_TABLE = "_ingest_runs"
JOB_TIMEOUT_SECONDS = 1800
RATE_LIMIT_REASONS = frozenset({"rateLimitExceeded", "backendError"})
MS_PER_DAY = 86_400_000
EXPIRATION_FIELDS = ("default_table_expiration_ms", "default_partition_expiration_ms")

RUNS_SCHEMA = (
    bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("source_key", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("sample", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("table_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("source_file", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("batch_id", "STRING"),
    bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("rows_read", "INT64"),
    bigquery.SchemaField("rows_written", "INT64"),
    bigquery.SchemaField("error_message", "STRING"),
    bigquery.SchemaField("started_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("finished_at", "TIMESTAMP", mode="REQUIRED"),
)


def is_transient_bigquery_error(exc: Exception) -> bool:
    if isinstance(
        exc,
        (
            google_errors.TooManyRequests,
            google_errors.InternalServerError,
            google_errors.BadGateway,
            google_errors.ServiceUnavailable,
            google_errors.GatewayTimeout,
            requests.ConnectionError,
            requests.Timeout,
            ConnectionError,
            TimeoutError,
        ),
    ):
        return True
    if isinstance(exc, google_errors.Forbidden):
        return any(error.get("reason") in RATE_LIMIT_REASONS for error in exc.errors or [])
    return False


def build_schema(source_columns: tuple[str, ...]) -> list[bigquery.SchemaField]:
    """Keep source columns as STRING. Typing belongs to the dbt staging layer."""
    schema = [bigquery.SchemaField(column, "STRING") for column in source_columns]
    schema.append(bigquery.SchemaField(METADATA_COLUMNS[0], "TIMESTAMP", mode="REQUIRED"))
    schema.extend(
        bigquery.SchemaField(column, "STRING", mode="REQUIRED") for column in METADATA_COLUMNS[1:]
    )
    return schema


class BigQueryLoader:
    def __init__(
        self,
        project: str,
        location: str,
        dataset: str,
        *,
        expiration_days: int | None = None,
        client: bigquery.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client or bigquery.Client(project=project, location=location)
        self._project = project
        self._location = location
        self._dataset = dataset
        self._expiration_days = expiration_days or None
        self._sleep = sleep
        self._clock = clock

    @property
    def _dataset_id(self) -> str:
        return f"{self._project}.{self._dataset}"

    @property
    def _expiration_ms(self) -> int | None:
        return self._expiration_days * MS_PER_DAY if self._expiration_days else None

    def _table_id(self, table: str) -> str:
        return f"{self._dataset_id}.{table}"

    def _retry(self, operation, description: str):
        return retry_call(
            operation,
            should_retry=is_transient_bigquery_error,
            description=description,
            sleep=self._sleep,
        )

    def ensure_ready(self) -> None:
        """Create the dataset and make sure every table in it has an expiry.

        The sandbox rejects writes to any table without one, including tables created
        while the project had billing enabled.
        """
        dataset = bigquery.Dataset(self._dataset_id)
        dataset.location = self._location
        if self._expiration_ms:
            dataset.default_table_expiration_ms = self._expiration_ms
            dataset.default_partition_expiration_ms = self._expiration_ms
        try:
            found = self._retry(
                lambda: self._client.create_dataset(dataset, exists_ok=True),
                f"create dataset {self._dataset}",
            )
            if self._expiration_ms:
                self._apply_dataset_defaults(found)
                self._apply_missing_table_expiry()
        except google_errors.GoogleAPICallError as exc:
            raise LoadError(f"Could not prepare dataset {self._dataset}: {exc}") from exc

    def _apply_dataset_defaults(self, dataset: bigquery.Dataset) -> None:
        fields = [field for field in EXPIRATION_FIELDS if getattr(dataset, field) is None]
        if not fields:
            return
        for field in fields:
            setattr(dataset, field, self._expiration_ms)
        self._retry(
            lambda: self._client.update_dataset(dataset, fields),
            f"set expiry defaults on {self._dataset}",
        )
        logger.info("dataset_expiry_set dataset=%s days=%d", self._dataset, self._expiration_days)

    def _apply_missing_table_expiry(self) -> None:
        items = self._retry(
            lambda: list(self._client.list_tables(self._dataset_id)),
            f"list tables in {self._dataset}",
        )
        for item in items:
            if item.expires is not None:
                continue
            table = self._retry(
                lambda ref=item.reference: self._client.get_table(ref), f"read {item.table_id}"
            )
            table.expires = self._clock() + timedelta(days=self._expiration_days)
            self._retry(
                lambda current=table: self._client.update_table(current, ["expires"]),
                f"set expiry on {item.table_id}",
            )
            logger.info(
                "table_expiry_set table=%s expires=%s", item.table_id, table.expires.isoformat()
            )

    def get_table_state(self, table: str) -> TableState | None:
        try:
            found = self._retry(
                lambda: self._client.get_table(self._table_id(table)), f"read table {table}"
            )
        except google_errors.NotFound:
            return None
        except google_errors.GoogleAPICallError as exc:
            raise LoadError(f"Could not read table {table}: {exc}") from exc
        return TableState(
            batch_id=(found.labels or {}).get(BATCH_LABEL),
            expires_at=found.expires,
            row_count=found.num_rows,
        )

    def drop_table(self, table: str) -> None:
        try:
            self._retry(
                lambda: self._client.delete_table(self._table_id(table), not_found_ok=True),
                f"drop table {table}",
            )
        except google_errors.GoogleAPICallError as exc:
            raise LoadError(f"Could not drop table {table}: {exc}") from exc

    def load(self, prepared: PreparedFile, table: str, batch_id: str) -> int:
        """Replace the table atomically, verify the row count, then record the batch."""
        table_id = self._table_id(table)
        config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            schema=build_schema(prepared.source_columns),
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            max_bad_records=0,
        )

        def submit() -> bigquery.LoadJob:
            with prepared.path.open("rb") as handle:
                job = self._client.load_table_from_file(
                    handle, table_id, job_config=config, location=self._location
                )
            job.result(timeout=JOB_TIMEOUT_SECONDS)
            return job

        try:
            job = self._retry(submit, f"load table {table}")
        except google_errors.GoogleAPICallError as exc:
            raise LoadError(f"BigQuery rejected the load into {table}: {exc}") from exc

        if job.output_rows != prepared.rows_written:
            raise LoadError(
                f"Row count mismatch for {table}: prepared {prepared.rows_written}, "
                f"loaded {job.output_rows}."
            )

        def label() -> None:
            current = self._client.get_table(table_id)
            current.labels = {**(current.labels or {}), BATCH_LABEL: batch_id}
            self._client.update_table(current, ["labels"])

        try:
            self._retry(label, f"label table {table}")
        except google_errors.GoogleAPICallError as exc:
            raise LoadError(f"Loaded {table} but could not record its batch: {exc}") from exc
        return int(job.output_rows)

    def record_runs(self, records: list[RunRecord]) -> None:
        if not records:
            return
        config = bigquery.LoadJobConfig(
            schema=list(RUNS_SCHEMA),
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )
        rows = [record.to_row() for record in records]

        def submit() -> None:
            job = self._client.load_table_from_json(
                rows, self._table_id(RUNS_TABLE), job_config=config, location=self._location
            )
            job.result(timeout=JOB_TIMEOUT_SECONDS)

        try:
            self._retry(submit, f"append {RUNS_TABLE}")
        except google_errors.GoogleAPICallError as exc:
            raise LoadError(f"Could not record the run in {RUNS_TABLE}: {exc}") from exc
