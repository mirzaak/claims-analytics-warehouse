"""Check whether BigQuery keeps partitions dated 2008 to 2010 in this project.

The BigQuery sandbox expires partitions after 60 days, measured from the partition
date. This script loads a few rows into three test tables and reports which rows
survive. It creates and then deletes the `spike_partitions` dataset.

Run from the repository root: .venv/bin/python scripts/check_partition_expiry.py
"""

from __future__ import annotations

import os
from datetime import date

from dotenv import load_dotenv
from google.api_core.exceptions import GoogleAPICallError
from google.cloud import bigquery

DATASET = "spike_partitions"
SCHEMA = [
    bigquery.SchemaField("member_id", "STRING"),
    bigquery.SchemaField("service_date", "DATE"),
    bigquery.SchemaField("service_year_month", "INT64"),
]


def sample_rows() -> list[dict]:
    dates = [date(2008, 1, 15), date(2009, 6, 30), date(2010, 12, 31), date.today()]
    return [
        {
            "member_id": f"M{i}",
            "service_date": day.isoformat(),
            "service_year_month": day.year * 100 + day.month,
        }
        for i, day in enumerate(dates)
    ]


def load_and_count(client: bigquery.Client, table: bigquery.Table) -> list[str]:
    config = bigquery.LoadJobConfig(
        schema=SCHEMA, write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
    )
    client.load_table_from_json(sample_rows(), table, job_config=config).result()
    rows = client.list_rows(table)
    return sorted(row["service_date"].isoformat() for row in rows)


def create(client: bigquery.Client, table_id: str, **partitioning) -> bigquery.Table:
    client.delete_table(table_id, not_found_ok=True)
    table = bigquery.Table(table_id, schema=SCHEMA)
    for name, value in partitioning.items():
        setattr(table, name, value)
    return client.create_table(table)


def main() -> None:
    load_dotenv()
    project = os.environ["GCP_PROJECT_ID"]
    location = os.environ.get("GCP_LOCATION", "US")
    client = bigquery.Client(project=project, location=location)
    dataset_id = f"{project}.{DATASET}"
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = location
    dataset = client.create_dataset(dataset, exists_ok=True)
    print(f"dataset default table expiration ms: {dataset.default_table_expiration_ms}")
    print(
        f"dataset default partition expiration ms: {dataset.default_partition_expiration_ms}"
    )
    print(
        f"rows loaded into each table: {[row['service_date'] for row in sample_rows()]}\n"
    )

    try:
        by_date = create(
            client,
            f"{dataset_id}.by_date",
            time_partitioning=bigquery.TimePartitioning(field="service_date"),
        )
        print(
            f"A. date partitions, defaults: expiration ms {by_date.partition_expiration}"
        )
        print(f"   rows kept: {load_and_count(client, by_date)}")

        try:
            client.query(
                f"ALTER TABLE `{dataset_id}.by_date` SET OPTIONS (partition_expiration_days = NULL)"
            ).result()
            refreshed = client.get_table(f"{dataset_id}.by_date")
            print(
                f"B. date partitions, expiration removed: expiration ms {refreshed.partition_expiration}"
            )
            print(f"   rows kept: {load_and_count(client, refreshed)}")
        except GoogleAPICallError as exc:
            print(f"B. removing partition expiration failed: {exc.message}")

        by_month = create(
            client,
            f"{dataset_id}.by_year_month",
            range_partitioning=bigquery.RangePartitioning(
                field="service_year_month",
                range_=bigquery.PartitionRange(start=200801, end=203001, interval=1),
            ),
        )
        print("C. integer-range partitions on service_year_month")
        print(f"   rows kept: {load_and_count(client, by_month)}")
    finally:
        client.delete_dataset(dataset_id, delete_contents=True, not_found_ok=True)
        print(f"\ncleaned up dataset {DATASET}")


if __name__ == "__main__":
    main()
