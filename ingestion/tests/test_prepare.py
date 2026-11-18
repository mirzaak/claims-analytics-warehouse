from datetime import UTC, datetime

import pytest
from conftest import (
    BENEFICIARY_HEADER,
    beneficiary_rows,
    csv_text,
    make_source,
    read_prepared,
    write_zip,
)

from claims_ingest.errors import SourceFormatError
from claims_ingest.prepare import compute_batch_id, keep_member, prepare_file

LOADED_AT = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def prepare(tmp_path, content, sample_pct=100):
    archive = write_zip(tmp_path / "source.zip", {"data.csv": content})
    return prepare_file(archive, make_source(), "batch123", sample_pct, tmp_path / "out", LOADED_AT)


def test_source_values_are_unchanged_and_metadata_is_added(tmp_path):
    rows = [BENEFICIARY_HEADER, ["00A1", " 19400101 ", "012", "12"]]

    result = prepare(tmp_path, csv_text(rows))

    assert read_prepared(result.path) == [
        {
            "DESYNPUF_ID": "00A1",
            "BENE_BIRTH_DT": " 19400101 ",
            "BENE_HI_CVRAGE_TOT_MONS": "012",
            "PLAN_CVRG_MOS_NUM": "12",
            "_loaded_at": "2026-01-15T12:00:00.000000Z",
            "_source_file": "beneficiary_2008_1.zip",
            "_batch_id": "batch123",
        }
    ]
    assert result.source_columns == tuple(BENEFICIARY_HEADER)


def test_row_counts_are_reported(tmp_path):
    result = prepare(tmp_path, csv_text(beneficiary_rows(5)))

    assert (result.rows_read, result.rows_written) == (5, 5)
    assert result.uncompressed_bytes > 0
    assert result.prepared_bytes > 0


def test_sampling_keeps_all_rows_of_the_selected_members(tmp_path):
    ids = [f"MEMBER{i:04d}" for i in range(500)]
    rows = [BENEFICIARY_HEADER]
    for member_id in ids:
        rows.extend([[member_id, "19400101", "12", "12"]] * 2)

    result = prepare(tmp_path, csv_text(rows), sample_pct=20)

    written = [row["DESYNPUF_ID"] for row in read_prepared(result.path)]
    expected = [member_id for member_id in ids if keep_member(member_id, 20)]
    assert sorted(written) == sorted(expected * 2)
    assert result.rows_read == 1000
    assert result.rows_written == len(expected) * 2


def test_member_sample_rate_is_close_to_the_requested_share():
    kept = sum(keep_member(f"MEMBER{i}", 10) for i in range(20_000))

    assert 0.09 < kept / 20_000 < 0.11


def test_member_selection_is_stable():
    assert keep_member("MEMBER0001", 10) == keep_member("MEMBER0001", 10)


def test_sample_of_100_keeps_everyone():
    assert all(keep_member(f"MEMBER{i}", 100) for i in range(100))


def test_batch_id_depends_only_on_content_and_sample_rate():
    original = compute_batch_id("abc", 10)

    assert compute_batch_id("abc", 10) == original
    assert compute_batch_id("abd", 10) != original
    assert compute_batch_id("abc", 20) != original


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "file is empty"),
        (csv_text([BENEFICIARY_HEADER]), "no data rows"),
        (csv_text([["DESYNPUF_ID", "OTHER"], ["1", "2"]]), "missing required columns"),
        (csv_text([[*BENEFICIARY_HEADER, "DESYNPUF_ID"], ["1"] * 5]), "duplicate columns"),
        (csv_text([[*BENEFICIARY_HEADER, "_batch_id"], ["1"] * 5]), "reserved column names"),
        (csv_text([BENEFICIARY_HEADER, ["1", "2"]]), "line 2 has 2 fields, expected 4"),
        (csv_text([BENEFICIARY_HEADER, ["", "2", "3", "4"]]), "line 2 has an empty DESYNPUF_ID"),
    ],
)
def test_invalid_files_fail_with_a_clear_message(tmp_path, content, message):
    with pytest.raises(SourceFormatError, match=message):
        prepare(tmp_path, content)

    assert list((tmp_path / "out").iterdir()) == []


def test_archive_without_a_csv_is_rejected(tmp_path):
    archive = write_zip(tmp_path / "source.zip", {"notes.txt": "hello"})

    with pytest.raises(SourceFormatError, match="expected 1 CSV file, found 0"):
        prepare_file(archive, make_source(), "b", 100, tmp_path / "out", LOADED_AT)


def test_archive_with_two_csvs_is_rejected(tmp_path):
    archive = write_zip(tmp_path / "source.zip", {"a.csv": "x", "b.csv": "y"})

    with pytest.raises(SourceFormatError, match="expected 1 CSV file, found 2"):
        prepare_file(archive, make_source(), "b", 100, tmp_path / "out", LOADED_AT)


def test_corrupt_archive_is_rejected(tmp_path):
    archive = tmp_path / "source.zip"
    archive.write_bytes(b"not a zip")

    with pytest.raises(SourceFormatError, match="could not read file"):
        prepare_file(archive, make_source(), "b", 100, tmp_path / "out", LOADED_AT)
