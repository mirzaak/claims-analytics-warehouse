"""Row-count anomaly check for key warehouse tables.

Compares each table's current row count with the count recorded by the previous run,
fails when a table is empty or changed by more than the allowed share, and records
the current counts for the next run.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from google.api_core import exceptions as google_errors
from google.cloud import bigquery

from claims_ingest.bigquery_loader import is_transient_bigquery_error
from claims_ingest.errors import LoadError
from claims_ingest.retry import retry_call

logger = logging.getLogger(__name__)

MONITORED_TABLES = (
    "marts.fact_medical_claim_line",
    "marts.fact_pharmacy_claim",
    "marts.fact_member_month",
    "marts.dim_member",
    "quality.dq_quarantine",
)
HISTORY_TABLE = "quality.row_count_history"
HISTORY_SCHEMA = (
    bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("checked_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("table_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("row_count", "INT64", mode="REQUIRED"),
)


@dataclass(frozen=True)
class RowCountResult:
    table_name: str
    previous: int | None
    current: int
    problem: str | None

    @property
    def change_rate(self) -> float | None:
        if not self.previous:
            return None
        return (self.current - self.previous) / self.previous


def compare_counts(
    previous: Mapping[str, int], current: Mapping[str, int], max_change_rate: float
) -> list[RowCountResult]:
    """Flag empty tables and changes larger than max_change_rate in either direction."""
    results = []
    for table_name, count in current.items():
        before = previous.get(table_name)
        problem = None
        if count == 0:
            problem = "table is empty"
        elif before and abs(count - before) / before > max_change_rate:
            problem = (
                f"row count changed by {(count - before) / before:+.1%}, "
                f"more than the allowed {max_change_rate:.0%}"
            )
        results.append(RowCountResult(table_name, before, count, problem))
    return results


class BigQueryRowCountStore:
    def __init__(
        self,
        project: str,
        location: str,
        *,
        expiration_days: int | None = None,
        client: bigquery.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client or bigquery.Client(project=project, location=location)
        self._project = project
        self._location = location
        self._expiration_days = expiration_days or None
        self._sleep = sleep
        self._clock = clock

    def _retry(self, operation, description: str):
        return retry_call(
            operation,
            should_retry=is_transient_bigquery_error,
            description=description,
            sleep=self._sleep,
        )

    @property
    def _history_id(self) -> str:
        return f"{self._project}.{HISTORY_TABLE}"

    def current_counts(self, tables: tuple[str, ...]) -> dict[str, int]:
        """Read row counts from table metadata, which costs no query bytes."""
        counts = {}
        for table in tables:
            try:
                found = self._retry(
                    lambda name=table: self._client.get_table(f"{self._project}.{name}"),
                    f"read {table}",
                )
            except google_errors.NotFound:
                counts[table] = 0
                continue
            except google_errors.GoogleAPICallError as exc:
                raise LoadError(f"Could not read row count of {table}: {exc}") from exc
            counts[table] = int(found.num_rows or 0)
        return counts

    def previous_counts(self) -> dict[str, int]:
        sql = f"""
            select table_name, row_count
            from `{self._history_id}`
            where true
            qualify row_number() over (partition by table_name order by checked_at desc) = 1
        """
        try:
            rows = self._retry(
                lambda: list(self._client.query(sql, location=self._location).result()),
                "read row count history",
            )
        except google_errors.NotFound:
            return {}
        except google_errors.GoogleAPICallError as exc:
            raise LoadError(f"Could not read {HISTORY_TABLE}: {exc}") from exc
        return {row["table_name"]: int(row["row_count"]) for row in rows}

    def record(self, run_id: str, counts: Mapping[str, int]) -> None:
        checked_at = self._clock().isoformat()
        rows = [
            {"run_id": run_id, "checked_at": checked_at, "table_name": name, "row_count": count}
            for name, count in counts.items()
        ]
        config = bigquery.LoadJobConfig(
            schema=list(HISTORY_SCHEMA),
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )

        def append() -> None:
            self._client.load_table_from_json(
                rows, self._history_id, job_config=config, location=self._location
            ).result()

        try:
            self._retry(append, f"append {HISTORY_TABLE}")
            if self._expiration_days:
                self._extend_expiry()
        except google_errors.GoogleAPICallError as exc:
            raise LoadError(f"Could not record row counts in {HISTORY_TABLE}: {exc}") from exc

    def _extend_expiry(self) -> None:
        """Keep the history from expiring while runs continue; the sandbox caps it at 60 days."""
        table = self._retry(lambda: self._client.get_table(self._history_id), "read history")
        table.expires = self._clock() + timedelta(days=self._expiration_days)
        self._retry(lambda: self._client.update_table(table, ["expires"]), "extend history")


def run_check(
    store: BigQueryRowCountStore,
    run_id: str,
    max_change_rate: float,
    tables: tuple[str, ...] = MONITORED_TABLES,
) -> list[RowCountResult]:
    previous = store.previous_counts()
    current = store.current_counts(tables)
    results = compare_counts(previous, current, max_change_rate)
    store.record(run_id, current)
    for result in results:
        logger.info(
            "row_count table=%s previous=%s current=%d problem=%s",
            result.table_name,
            result.previous,
            result.current,
            result.problem,
        )
    return results
