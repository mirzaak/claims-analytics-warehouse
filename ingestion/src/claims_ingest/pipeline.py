"""Coordinate download, preparation and loading for a set of source files."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

import requests

from claims_ingest.catalog import SourceFile
from claims_ingest.config import Settings
from claims_ingest.download import download_file
from claims_ingest.errors import IngestError
from claims_ingest.models import (
    PreparedFile,
    RunRecord,
    RunStatus,
    TableState,
    WarehouseLoader,
)
from claims_ingest.prepare import compute_batch_id, prepare_file

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]


class Action(StrEnum):
    SKIP = "skip"
    LOAD = "load"
    REFRESH = "refresh"


def utc_now() -> datetime:
    return datetime.now(UTC)


def decide_action(
    state: TableState | None,
    batch_id: str,
    now: datetime,
    refresh_days: int,
    force: bool = False,
) -> Action:
    """Decide what a file needs, given what the warehouse already holds."""
    if state is None or force or state.batch_id != batch_id:
        return Action.LOAD
    if state.expires_at is not None and state.expires_at - now <= timedelta(days=refresh_days):
        return Action.REFRESH
    return Action.SKIP


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    records: tuple[RunRecord, ...]

    @property
    def failed(self) -> tuple[RunRecord, ...]:
        return tuple(record for record in self.records if record.status is RunStatus.FAILED)

    @property
    def succeeded(self) -> bool:
        return not self.failed


def _process_source(
    source: SourceFile,
    run_id: str,
    settings: Settings,
    loader: WarehouseLoader | None,
    session: requests.Session | None,
    clock: Clock,
    force: bool,
) -> RunRecord:
    started_at = clock()
    batch_id: str | None = None
    rows_read: int | None = None
    rows_written: int | None = None

    def record(status: RunStatus, error: str | None = None) -> RunRecord:
        return RunRecord(
            run_id=run_id,
            source_key=source.key,
            sample=source.sample,
            table_name=source.table,
            source_file=source.filename,
            batch_id=batch_id,
            status=status,
            rows_read=rows_read,
            rows_written=rows_written,
            error_message=error,
            started_at=started_at,
            finished_at=clock(),
        )

    prepared = None
    try:
        download_dir = settings.data_dir / "downloads" / f"sample_{source.sample:02d}"
        download = download_file(source.url, download_dir / source.filename, session=session)
        batch_id = compute_batch_id(download.sha256, settings.member_sample_pct)

        action = Action.LOAD
        if loader is not None:
            state = loader.get_table_state(source.table)
            action = decide_action(state, batch_id, clock(), settings.refresh_days, force)
            if action is Action.SKIP:
                rows_written = state.row_count if state else None
                logger.info(
                    "file_skipped table=%s batch_id=%s rows=%s",
                    source.table,
                    batch_id,
                    rows_written,
                )
                return record(RunStatus.SKIPPED)

        prepared = prepare_file(
            download.path,
            source,
            batch_id,
            settings.member_sample_pct,
            settings.data_dir / "prepared",
            clock(),
        )
        rows_read = prepared.rows_read
        rows_written = prepared.rows_written
        logger.info(
            "file_prepared table=%s rows_read=%d rows_written=%d "
            "uncompressed_bytes=%d prepared_bytes=%d",
            source.table,
            prepared.rows_read,
            prepared.rows_written,
            prepared.uncompressed_bytes,
            prepared.prepared_bytes,
        )
        if loader is None:
            return record(RunStatus.PREPARED)

        if action is Action.REFRESH:
            logger.info("table_refresh table=%s reason=near_expiry", source.table)
            loader.drop_table(source.table)
        rows_written = loader.load(prepared, source.table, batch_id)
        logger.info(
            "file_loaded table=%s rows=%d batch_id=%s", source.table, rows_written, batch_id
        )
        return record(RunStatus.LOADED)
    except IngestError as exc:
        logger.error("file_failed table=%s error=%s", source.table, exc)
        return record(RunStatus.FAILED, str(exc))
    except Exception as exc:
        logger.exception("file_failed_unexpectedly table=%s", source.table)
        return record(RunStatus.FAILED, f"{type(exc).__name__}: {exc}")
    finally:
        if prepared is not None:
            prepared.path.unlink(missing_ok=True)


def run_pipeline(
    sources: Iterable[SourceFile],
    settings: Settings,
    loader: WarehouseLoader | None,
    *,
    session: requests.Session | None = None,
    clock: Clock = utc_now,
    force: bool = False,
) -> RunSummary:
    """Process every source. One failed file does not stop the others."""
    run_id = uuid.uuid4().hex
    if loader is not None:
        loader.ensure_ready()

    records = tuple(
        _process_source(source, run_id, settings, loader, session, clock, force)
        for source in sources
    )
    if loader is not None:
        loader.record_runs(list(records))

    summary = RunSummary(run_id, records)
    logger.info(
        "run_finished run_id=%s files=%d failed=%d", run_id, len(records), len(summary.failed)
    )
    return summary


def export_sources(
    sources: Iterable[SourceFile],
    settings: Settings,
    out_dir: Path,
    *,
    session: requests.Session | None = None,
    clock: Clock = utc_now,
) -> list[PreparedFile]:
    """Write each source's load-ready file to out_dir/<table>/<table>__<batch_id>.csv.gz.

    Each table folder keeps only the current batch, so a lakehouse job can load the
    whole folder, and can tell from the file name whether the batch changed.
    """
    exported = []
    for source in sources:
        download_dir = settings.data_dir / "downloads" / f"sample_{source.sample:02d}"
        download = download_file(source.url, download_dir / source.filename, session=session)
        batch_id = compute_batch_id(download.sha256, settings.member_sample_pct)
        table_dir = out_dir / source.table
        prepared = prepare_file(
            download.path, source, batch_id, settings.member_sample_pct, table_dir, clock()
        )
        for old in table_dir.glob("*.csv.gz"):
            if old != prepared.path:
                old.unlink()
        logger.info("file_exported path=%s rows=%d", prepared.path, prepared.rows_written)
        exported.append(prepared)
    return exported
