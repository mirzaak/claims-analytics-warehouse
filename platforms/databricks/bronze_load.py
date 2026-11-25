"""Load exported SynPUF files from a Unity Catalog volume into Delta bronze tables.

The volume acts as a landing zone, the way a vendor drops files on SFTP. Each table has
its own folder holding exactly one file named <table>__<batch_id>.csv.gz, written by
`claims-ingest export`. For each folder the job:

1. Skips the table when its Delta property claims.batch_id already equals the file's batch.
2. Otherwise reads the CSV with every column as a string, failing fast on malformed rows.
3. Overwrites the Delta table in one ACID transaction, so readers never see half a load.
4. Records the batch on the table and appends the outcome to _ingest_runs.

Runs as a Databricks serverless Python task; see databricks.yml at the repository root.
"""

from __future__ import annotations

import argparse
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

FILE_NAME = re.compile(r"^(?P<table>[a-z0-9_]+)__(?P<batch>[0-9a-f]{16})\.csv\.gz$")
BATCH_PROPERTY = "claims.batch_id"


@dataclass(frozen=True)
class LandedFile:
    table: str
    batch_id: str
    path: str


def find_landed_files(volume_path: str) -> tuple[list[LandedFile], list[str]]:
    """Return one landed file per table folder, plus a problem message for any bad folder."""
    files, problems = [], []
    for table in sorted(os.listdir(volume_path)):
        folder = os.path.join(volume_path, table)
        if not os.path.isdir(folder):
            continue
        matches = [FILE_NAME.match(name) for name in os.listdir(folder)]
        matches = [match for match in matches if match]
        if len(matches) != 1:
            problems.append(
                f"{table}: expected one <table>__<batch>.csv.gz file, found {len(matches)}"
            )
            continue
        match = matches[0]
        if match["table"] != table:
            problems.append(f"{table}: file belongs to table {match['table']}")
            continue
        files.append(LandedFile(table, match["batch"], os.path.join(folder, match.string)))
    return files, problems


def current_batch(spark, table_name: str) -> str | None:
    if not spark.catalog.tableExists(table_name):
        return None
    rows = spark.sql(f"show tblproperties {table_name} ('{BATCH_PROPERTY}')").collect()
    value = rows[0]["value"] if rows else None
    return None if value is None or "does not have property" in value else value


def load_file(spark, landed: LandedFile, table_name: str) -> int:
    from pyspark.sql import functions as F

    frame = (
        spark.read.option("header", True)
        .option("inferSchema", False)
        .option("mode", "FAILFAST")
        .option("quote", '"')
        .option("escape", '"')
        .csv(landed.path)
        .withColumn("_loaded_at", F.to_timestamp("_loaded_at"))
    )
    rows = frame.count()
    (
        frame.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(table_name)
    )
    spark.sql(
        f"alter table {table_name} set tblproperties ('{BATCH_PROPERTY}' = '{landed.batch_id}')"
    )
    return rows


def main(argv: list[str] | None = None) -> int:
    from pyspark.sql import SparkSession

    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", default="raw")
    parser.add_argument("--volume", default="landing")
    args = parser.parse_args(argv)

    spark = SparkSession.builder.getOrCreate()
    namespace = f"{args.catalog}.{args.schema}"
    volume_path = f"/Volumes/{args.catalog}/{args.schema}/{args.volume}"
    spark.sql(f"create schema if not exists {namespace}")

    files, problems = find_landed_files(volume_path)
    run_id = uuid.uuid4().hex
    outcomes = []
    for landed in files:
        table_name = f"{namespace}.{landed.table}"
        started = datetime.now(UTC)
        try:
            if current_batch(spark, table_name) == landed.batch_id:
                status, rows, error = "skipped", None, None
            else:
                status, rows, error = "loaded", load_file(spark, landed, table_name), None
        except Exception as exc:  # one bad file must not stop the others
            status, rows, error = "failed", None, f"{type(exc).__name__}: {exc}"[:1000]
        print(f"{landed.table:<34} {status:<8} rows={rows}")
        outcomes.append(
            (run_id, landed.table, landed.batch_id, status, rows, error, started, datetime.now(UTC))
        )

    if outcomes:
        columns = (
            "run_id string, table_name string, batch_id string, status string, "
            "rows_written long, error_message string, started_at timestamp, finished_at timestamp"
        )
        spark.createDataFrame(outcomes, columns).write.format("delta").mode("append").saveAsTable(
            f"{namespace}._ingest_runs"
        )

    for problem in problems:
        print(f"PROBLEM {problem}")
    failed = [outcome for outcome in outcomes if outcome[3] == "failed"]
    if problems or failed or not files:
        raise SystemExit(
            f"Bronze load failed: {len(failed)} failed tables, {len(problems)} bad folders, "
            f"{len(files)} folders found in {volume_path}."
        )
    return 0


if __name__ == "__main__":
    main()
