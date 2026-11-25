"""Tests for the pure parts of platforms/databricks/bronze_load.py. Spark is not needed."""

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "platforms" / "databricks" / "bronze_load.py"
spec = importlib.util.spec_from_file_location("bronze_load", SCRIPT)
bronze_load = importlib.util.module_from_spec(spec)
sys.modules["bronze_load"] = bronze_load  # dataclasses look their module up here
spec.loader.exec_module(bronze_load)


def land(root: Path, table: str, *names: str) -> None:
    folder = root / table
    folder.mkdir(parents=True)
    for name in names:
        (folder / name).write_bytes(b"")


def test_one_file_per_table_is_found_with_its_batch(tmp_path):
    land(tmp_path, "inpatient_claims_s01", "inpatient_claims_s01__a714bb2d1848c0d7.csv.gz")

    files, problems = bronze_load.find_landed_files(str(tmp_path))

    assert problems == []
    assert files[0].table == "inpatient_claims_s01"
    assert files[0].batch_id == "a714bb2d1848c0d7"


def test_two_batches_in_one_folder_is_a_problem(tmp_path):
    land(
        tmp_path,
        "members_s01",
        "members_s01__0000000000000001.csv.gz",
        "members_s01__0000000000000002.csv.gz",
    )

    files, problems = bronze_load.find_landed_files(str(tmp_path))

    assert files == []
    assert "found 2" in problems[0]


def test_file_for_another_table_is_a_problem(tmp_path):
    land(tmp_path, "members_s01", "claims_s01__0000000000000001.csv.gz")

    files, problems = bronze_load.find_landed_files(str(tmp_path))

    assert files == []
    assert "belongs to table claims_s01" in problems[0]


def test_other_files_are_ignored(tmp_path):
    land(tmp_path, "members_s01", "members_s01__0000000000000001.csv.gz", "notes.txt")

    files, problems = bronze_load.find_landed_files(str(tmp_path))

    assert len(files) == 1
    assert problems == []
