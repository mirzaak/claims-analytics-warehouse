"""Snowflake loader.

Each file is copied into a fresh loading table, its row count is checked, and only then
is it swapped in with ALTER TABLE ... SWAP WITH, an atomic metadata operation. Readers
see the old table or the new one, never a half-loaded one. A _LOAD_STATE table records
which batch each raw table holds, so unchanged files are skipped.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC
from typing import Any

from claims_ingest.config import SnowflakeSettings
from claims_ingest.errors import LoadError
from claims_ingest.models import PreparedFile, RunRecord, TableState
from claims_ingest.prepare import METADATA_COLUMNS

logger = logging.getLogger(__name__)

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
STATE_TABLE = "_LOAD_STATE"
RUNS_TABLE = "_INGEST_RUNS"
FILE_FORMAT = (
    "type = csv skip_header = 1 field_optionally_enclosed_by = '\"' "
    "escape_unenclosed_field = none compression = gzip "
    'timestamp_format = \'YYYY-MM-DD"T"HH24:MI:SS.FF6"Z"\''
)
RUN_COLUMNS = (
    "RUN_ID",
    "SOURCE_KEY",
    "SYNPUF_SAMPLE",
    "TABLE_NAME",
    "SOURCE_FILE",
    "BATCH_ID",
    "STATUS",
    "ROWS_READ",
    "ROWS_WRITTEN",
    "ERROR_MESSAGE",
    "STARTED_AT",
    "FINISHED_AT",
)


def _identifier(name: str) -> str:
    """Return an upper-case identifier, refusing anything that is not a plain name."""
    if not IDENTIFIER.match(name):
        raise LoadError(f"Unsafe Snowflake identifier {name!r}.")
    return name.upper()


def _utc_naive(value):
    return value.astimezone(UTC).replace(tzinfo=None)


class SnowflakeLoader:
    def __init__(self, connection: Any, schema: str = "RAW") -> None:
        self._connection = connection
        self._schema = _identifier(schema)

    @classmethod
    def connect(cls, settings: SnowflakeSettings, schema: str = "RAW") -> SnowflakeLoader:
        import snowflake.connector

        try:
            connection = snowflake.connector.connect(
                account=settings.account,
                user=settings.user,
                private_key_file=str(settings.private_key_path),
                role=settings.role,
                warehouse=settings.warehouse,
                database=settings.database,
                session_parameters={"QUERY_TAG": "claims_ingest"},
            )
        except snowflake.connector.errors.Error as exc:
            raise LoadError(
                f"Could not connect to Snowflake account {settings.account}: {exc}"
            ) from exc
        return cls(connection, schema)

    def _execute(self, sql: str, params: Any = None) -> list[tuple]:
        from snowflake.connector.errors import Error as SnowflakeError

        try:
            with self._connection.cursor() as cursor:
                cursor.execute(sql, params)
                return list(cursor.fetchall()) if cursor.description else []
        except SnowflakeError as exc:
            raise LoadError(f"Snowflake rejected: {sql.split()[0:4]} ...: {exc}") from exc

    def _name(self, table: str) -> str:
        return f"{self._schema}.{_identifier(table)}"

    def _exists(self, table: str) -> bool:
        rows = self._execute(
            "select count(*) from information_schema.tables "
            "where table_schema = %s and table_name = %s",
            (self._schema, _identifier(table)),
        )
        return bool(rows and rows[0][0])

    def ensure_ready(self) -> None:
        self._execute(f"create schema if not exists {self._schema}")
        self._execute(
            f"create table if not exists {self._name(STATE_TABLE)} ("
            "TABLE_NAME varchar primary key, BATCH_ID varchar not null, "
            "ROW_COUNT number not null, LOADED_AT timestamp_ntz not null)"
        )
        self._execute(
            f"create table if not exists {self._name(RUNS_TABLE)} ("
            "RUN_ID varchar, SOURCE_KEY varchar, SYNPUF_SAMPLE number, TABLE_NAME varchar, "
            "SOURCE_FILE varchar, BATCH_ID varchar, STATUS varchar, ROWS_READ number, "
            "ROWS_WRITTEN number, ERROR_MESSAGE varchar, STARTED_AT timestamp_ntz, "
            "FINISHED_AT timestamp_ntz)"
        )

    def get_table_state(self, table: str) -> TableState | None:
        if not self._exists(table):
            return None
        rows = self._execute(
            f"select BATCH_ID, ROW_COUNT from {self._name(STATE_TABLE)} where TABLE_NAME = %s",
            (_identifier(table),),
        )
        if not rows:
            return TableState(batch_id=None, expires_at=None, row_count=None)
        return TableState(batch_id=rows[0][0], expires_at=None, row_count=int(rows[0][1]))

    def drop_table(self, table: str) -> None:
        self._execute(f"drop table if exists {self._name(table)}")
        self._execute(
            f"delete from {self._name(STATE_TABLE)} where TABLE_NAME = %s", (_identifier(table),)
        )

    def load(self, prepared: PreparedFile, table: str, batch_id: str) -> int:
        target = self._name(table)
        loading_table = f"{_identifier(table)}__LOADING"
        loading = self._name(loading_table)
        source_columns = [f"{_identifier(column)} varchar" for column in prepared.source_columns]
        loaded_at, source_file, batch = (_identifier(column) for column in METADATA_COLUMNS)
        columns = ", ".join(
            [
                *source_columns,
                f"{loaded_at} timestamp_ntz",
                f"{source_file} varchar",
                f"{batch} varchar",
            ]
        )

        self._execute(f"create or replace table {loading} ({columns})")
        stage = f"@{self._schema}.%{loading_table}"
        self._execute(
            f"put 'file://{prepared.path.resolve()}' {stage} auto_compress = false overwrite = true"
        )
        results = self._execute(
            f"copy into {loading} from {stage} file_format = ({FILE_FORMAT}) "
            "on_error = abort_statement purge = true"
        )
        loaded = sum(int(row[3]) for row in results if len(row) > 3 and row[3] is not None)
        if loaded != prepared.rows_written:
            self._execute(f"drop table if exists {loading}")
            expected = prepared.rows_written
            raise LoadError(
                f"Row count mismatch for {table}: prepared {expected}, loaded {loaded}."
            )

        if self._exists(table):
            self._execute(f"alter table {loading} swap with {target}")
            self._execute(f"drop table if exists {loading}")
        else:
            self._execute(f"alter table {loading} rename to {target}")

        self._execute(
            f"merge into {self._name(STATE_TABLE)} as state "
            "using (select %s as TABLE_NAME, %s as BATCH_ID, %s as ROW_COUNT) as latest "
            "on state.TABLE_NAME = latest.TABLE_NAME "
            "when matched then update set BATCH_ID = latest.BATCH_ID, "
            "ROW_COUNT = latest.ROW_COUNT, LOADED_AT = sysdate() "
            "when not matched then insert (TABLE_NAME, BATCH_ID, ROW_COUNT, LOADED_AT) "
            "values (latest.TABLE_NAME, latest.BATCH_ID, latest.ROW_COUNT, sysdate())",
            (_identifier(table), batch_id, loaded),
        )
        return loaded

    def record_runs(self, records: list[RunRecord]) -> None:
        if not records:
            return
        placeholders = ", ".join(["%s"] * len(RUN_COLUMNS))
        rows = [
            (
                record.run_id,
                record.source_key,
                record.sample,
                record.table_name,
                record.source_file,
                record.batch_id,
                record.status.value,
                record.rows_read,
                record.rows_written,
                record.error_message,
                _utc_naive(record.started_at),
                _utc_naive(record.finished_at),
            )
            for record in records
        ]
        from snowflake.connector.errors import Error as SnowflakeError

        try:
            with self._connection.cursor() as cursor:
                cursor.executemany(
                    f"insert into {self._name(RUNS_TABLE)} ({', '.join(RUN_COLUMNS)}) "
                    f"values ({placeholders})",
                    rows,
                )
        except SnowflakeError as exc:
            raise LoadError(f"Could not record the run in {RUNS_TABLE}: {exc}") from exc
