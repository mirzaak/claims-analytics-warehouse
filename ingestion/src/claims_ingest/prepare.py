"""Turn a source archive into a load-ready file with metadata columns.

Source values are copied unchanged. The only row filter is the member sample.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from claims_ingest.catalog import SourceFile
from claims_ingest.errors import SourceFormatError
from claims_ingest.models import PreparedFile

METADATA_COLUMNS = ("_loaded_at", "_source_file", "_batch_id")
MEMBER_ID_COLUMN = "DESYNPUF_ID"
MAX_UNCOMPRESSED_BYTES = 20 * 1024**3
PREPARE_FORMAT_VERSION = "1"


def compute_batch_id(source_sha256: str, sample_pct: int) -> str:
    """Identify a batch by its content, so the same input always gets the same ID."""
    payload = f"{PREPARE_FORMAT_VERSION}:{source_sha256}:{sample_pct}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def keep_member(member_id: str, sample_pct: int) -> bool:
    """Choose members by hash, so a member is kept or dropped in every file alike."""
    if sample_pct >= 100:
        return True
    bucket = int.from_bytes(hashlib.sha256(member_id.encode()).digest()[:8], "big") % 100
    return bucket < sample_pct


def _find_csv_member(archive: zipfile.ZipFile, filename: str) -> zipfile.ZipInfo:
    members = [
        info
        for info in archive.infolist()
        if not info.is_dir()
        and info.filename.lower().endswith(".csv")
        and not info.filename.startswith("__MACOSX/")
    ]
    if len(members) != 1:
        raise SourceFormatError(f"{filename}: expected 1 CSV file, found {len(members)}.")
    if members[0].file_size > MAX_UNCOMPRESSED_BYTES:
        raise SourceFormatError(
            f"{filename}: CSV is {members[0].file_size} bytes, "
            f"above the {MAX_UNCOMPRESSED_BYTES} byte limit."
        )
    return members[0]


def _validate_header(header: list[str], source: SourceFile) -> tuple[str, ...]:
    columns = tuple(column.strip() for column in header)
    duplicates = sorted({column for column in columns if columns.count(column) > 1})
    if duplicates:
        raise SourceFormatError(f"{source.filename}: duplicate columns {duplicates}.")

    missing = sorted(source.required_columns - set(columns))
    if missing:
        raise SourceFormatError(f"{source.filename}: missing required columns {missing}.")

    reserved = sorted(set(columns) & set(METADATA_COLUMNS))
    if reserved:
        raise SourceFormatError(f"{source.filename}: reserved column names {reserved}.")
    return columns


def _copy_rows(
    reader: csv.reader,
    writer: csv.writer,
    source: SourceFile,
    columns: tuple[str, ...],
    metadata: tuple[str, str, str],
    sample_pct: int,
) -> tuple[int, int]:
    member_index = columns.index(MEMBER_ID_COLUMN)
    rows_read = 0
    rows_written = 0
    for row in reader:
        if not row:
            continue
        rows_read += 1
        if len(row) != len(columns):
            raise SourceFormatError(
                f"{source.filename}: line {reader.line_num} has {len(row)} fields, "
                f"expected {len(columns)}."
            )
        member_id = row[member_index].strip()
        if not member_id:
            raise SourceFormatError(
                f"{source.filename}: line {reader.line_num} has an empty {MEMBER_ID_COLUMN}."
            )
        if keep_member(member_id, sample_pct):
            writer.writerow([*row, *metadata])
            rows_written += 1
    return rows_read, rows_written


def prepare_file(
    zip_path: Path,
    source: SourceFile,
    batch_id: str,
    sample_pct: int,
    output_dir: Path,
    loaded_at: datetime,
) -> PreparedFile:
    """Write a gzip CSV holding the sampled source rows plus load metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{source.table}__{batch_id}.csv.gz"
    partial = output.with_name(f"{output.name}.part")
    loaded_at_text = loaded_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    metadata = (loaded_at_text, source.filename, batch_id)

    try:
        with zipfile.ZipFile(zip_path) as archive:
            member = _find_csv_member(archive, source.filename)
            with archive.open(member) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                reader = csv.reader(text, strict=True)
                header = next(reader, None)
                if header is None:
                    raise SourceFormatError(f"{source.filename}: file is empty.")
                columns = _validate_header(header, source)

                with gzip.open(partial, "wt", encoding="utf-8", newline="", compresslevel=1) as gz:
                    writer = csv.writer(gz, lineterminator="\n")
                    writer.writerow([*columns, *METADATA_COLUMNS])
                    rows_read, rows_written = _copy_rows(
                        reader, writer, source, columns, metadata, sample_pct
                    )

        if rows_read == 0:
            raise SourceFormatError(f"{source.filename}: file has a header but no data rows.")
        os.replace(partial, output)
    except (zipfile.BadZipFile, UnicodeDecodeError, csv.Error) as exc:
        raise SourceFormatError(f"{source.filename}: could not read file: {exc}") from exc
    finally:
        partial.unlink(missing_ok=True)

    return PreparedFile(
        path=output,
        source_columns=columns,
        rows_read=rows_read,
        rows_written=rows_written,
        uncompressed_bytes=member.file_size,
        prepared_bytes=output.stat().st_size,
    )
