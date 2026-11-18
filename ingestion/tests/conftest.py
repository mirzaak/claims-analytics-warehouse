from __future__ import annotations

import csv
import gzip
import io
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from claims_ingest.catalog import SourceFile, SourceKind
from claims_ingest.config import Settings
from claims_ingest.models import PreparedFile, RunRecord, TableState

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
BENEFICIARY_HEADER = [
    "DESYNPUF_ID",
    "BENE_BIRTH_DT",
    "BENE_HI_CVRAGE_TOT_MONS",
    "PLAN_CVRG_MOS_NUM",
]


def csv_text(rows: list[list[str]]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    return buffer.getvalue()


def beneficiary_rows(count: int = 3, birth_date: str = "19400101") -> list[list[str]]:
    rows = [[f"MEMBER{i:04d}", birth_date, "12", "12"] for i in range(count)]
    return [BENEFICIARY_HEADER, *rows]


def write_zip(path: Path, members: dict[str, str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return path


def zip_bytes(content: str = "a,b\n1,2\n") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("data.csv", content)
    return buffer.getvalue()


def read_prepared(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def make_source(key: str = "beneficiary_2008", sample: int = 1) -> SourceFile:
    return SourceFile(
        key=key,
        kind=SourceKind.BENEFICIARY,
        sample=sample,
        url=f"https://example.test/{key}_{sample}.zip",
    )


def cache_source(settings: Settings, source: SourceFile, rows: list[list[str]]) -> Path:
    """Place an archive where the downloader finds it, so tests need no network."""
    path = settings.data_dir / "downloads" / f"sample_{source.sample:02d}" / source.filename
    return write_zip(path, {"data.csv": csv_text(rows)})


class FakeWarehouse:
    """In-memory warehouse that replaces a table on every load, like a load job."""

    def __init__(self, fail_tables: set[str] | None = None) -> None:
        self.tables: dict[str, list[dict[str, str]]] = {}
        self.states: dict[str, TableState] = {}
        self.load_calls: list[str] = []
        self.drop_calls: list[str] = []
        self.runs: list[RunRecord] = []
        self.prepared_paths: list[Path] = []
        self.ready = False
        self.fail_tables = fail_tables or set()

    def ensure_ready(self) -> None:
        self.ready = True

    def get_table_state(self, table: str) -> TableState | None:
        return self.states.get(table)

    def drop_table(self, table: str) -> None:
        self.drop_calls.append(table)
        self.tables.pop(table, None)
        self.states.pop(table, None)

    def load(self, prepared: PreparedFile, table: str, batch_id: str) -> int:
        from claims_ingest.errors import LoadError

        self.load_calls.append(table)
        self.prepared_paths.append(prepared.path)
        if table in self.fail_tables:
            raise LoadError(f"simulated failure for {table}")
        rows = read_prepared(prepared.path)
        self.tables[table] = rows
        self.states[table] = TableState(batch_id, NOW + timedelta(days=60), len(rows))
        return len(rows)

    def record_runs(self, records: list[RunRecord]) -> None:
        self.runs.extend(records)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", member_sample_pct=100)


@pytest.fixture
def warehouse() -> FakeWarehouse:
    return FakeWarehouse()
