"""Data passed between pipeline stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol


class RunStatus(StrEnum):
    LOADED = "loaded"
    SKIPPED = "skipped"
    PREPARED = "prepared"
    FAILED = "failed"


@dataclass(frozen=True)
class PreparedFile:
    path: Path
    source_columns: tuple[str, ...]
    rows_read: int
    rows_written: int
    uncompressed_bytes: int
    prepared_bytes: int


@dataclass(frozen=True)
class TableState:
    batch_id: str | None
    expires_at: datetime | None
    row_count: int | None


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    source_key: str
    sample: int
    table_name: str
    source_file: str
    batch_id: str | None
    status: RunStatus
    rows_read: int | None
    rows_written: int | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["status"] = self.status.value
        row["started_at"] = self.started_at.isoformat()
        row["finished_at"] = self.finished_at.isoformat()
        return row


class WarehouseLoader(Protocol):
    """Operations the pipeline needs from a warehouse."""

    def ensure_ready(self) -> None: ...

    def get_table_state(self, table: str) -> TableState | None: ...

    def drop_table(self, table: str) -> None: ...

    def load(self, prepared: PreparedFile, table: str, batch_id: str) -> int: ...

    def record_runs(self, records: list[RunRecord]) -> None: ...
