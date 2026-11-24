"""Command line entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv

from claims_ingest.catalog import SUPPORTED_SAMPLES, select_sources
from claims_ingest.config import Settings
from claims_ingest.errors import ConfigError, IngestError
from claims_ingest.models import WarehouseLoader
from claims_ingest.pipeline import RunSummary, run_pipeline

EXIT_OK = 0
EXIT_FILE_FAILED = 1
EXIT_RUN_FAILED = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="claims-ingest", description="Load CMS DE-SynPUF files into the raw warehouse layer."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Download, prepare and load source files.")
    run.add_argument(
        "--sample",
        type=int,
        action="append",
        choices=SUPPORTED_SAMPLES,
        help="CMS sample number. Repeat to load several. Default: 1.",
    )
    run.add_argument(
        "--only",
        action="append",
        metavar="SOURCE",
        help="Process only this source, such as beneficiary_2010. Repeat for several.",
    )
    run.add_argument(
        "--dry-run", action="store_true", help="Download and prepare, but skip the warehouse."
    )
    run.add_argument("--force", action="store_true", help="Reload files that are unchanged.")
    run.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))

    check = commands.add_parser(
        "check-row-counts",
        help="Fail when a key table is empty or its row count changed too much since the last run.",
    )
    check.add_argument(
        "--max-change",
        type=float,
        default=0.10,
        help="Largest allowed change as a share of the previous count. Default: 0.10.",
    )
    check.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser


def _with_google_credentials(build):
    from google.auth.exceptions import DefaultCredentialsError

    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    try:
        return build()
    except DefaultCredentialsError as exc:
        raise ConfigError(
            "Google credentials were not found. Set GOOGLE_APPLICATION_CREDENTIALS in .env "
            "to the path of your service account key."
        ) from exc


def build_loader(settings: Settings) -> WarehouseLoader:
    from claims_ingest.bigquery_loader import BigQueryLoader

    project = settings.require_project_id()
    return _with_google_credentials(
        lambda: BigQueryLoader(
            project,
            settings.gcp_location,
            settings.raw_dataset,
            expiration_days=settings.raw_expiration_days,
        )
    )


def check_row_counts(settings: Settings, max_change: float) -> int:
    import uuid

    from claims_ingest.row_counts import BigQueryRowCountStore, run_check

    project = settings.require_project_id()
    store = _with_google_credentials(lambda: BigQueryRowCountStore(project, settings.gcp_location))
    results = run_check(store, uuid.uuid4().hex, max_change)

    print(f"\n{'table':<34}{'previous':>12}{'current':>12}  result")
    for result in results:
        previous = "-" if result.previous is None else f"{result.previous:,}"
        outcome = "OK" if result.problem is None else f"FAIL: {result.problem}"
        print(f"{result.table_name:<34}{previous:>12}{result.current:>12,}  {outcome}")
    failures = [result for result in results if result.problem]
    for result in failures:
        print(f"ROW COUNT ANOMALY {result.table_name}: {result.problem}", file=sys.stderr)
    return EXIT_FILE_FAILED if failures else EXIT_OK


def print_summary(summary: RunSummary) -> None:
    print(f"\nRun {summary.run_id}")
    print(f"{'table':<34}{'status':<10}{'rows read':>12}{'rows written':>14}")
    for record in summary.records:
        rows_read = "-" if record.rows_read is None else f"{record.rows_read:,}"
        rows_written = "-" if record.rows_written is None else f"{record.rows_written:,}"
        print(f"{record.table_name:<34}{record.status.value:<10}{rows_read:>12}{rows_written:>14}")
    for record in summary.failed:
        print(f"\nFAILED {record.table_name}: {record.error_message}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    load_dotenv(Path.cwd() / ".env")

    try:
        settings = Settings.from_env()
        if args.command == "check-row-counts":
            if not 0 < args.max_change < 1:
                raise ConfigError("--max-change must be between 0 and 1, such as 0.10.")
            return check_row_counts(settings, args.max_change)
        sources = select_sources(args.sample or [1], args.only)
        loader = None if args.dry_run else build_loader(settings)
        summary = run_pipeline(sources, settings, loader, force=args.force)
    except IngestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_RUN_FAILED

    print_summary(summary)
    return EXIT_OK if summary.succeeded else EXIT_FILE_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
