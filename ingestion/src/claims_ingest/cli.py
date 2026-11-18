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
    return parser


def build_loader(settings: Settings) -> WarehouseLoader:
    from google.auth.exceptions import DefaultCredentialsError

    from claims_ingest.bigquery_loader import BigQueryLoader

    project = settings.require_project_id()
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    try:
        return BigQueryLoader(project, settings.gcp_location, settings.raw_dataset)
    except DefaultCredentialsError as exc:
        raise ConfigError(
            "Google credentials were not found. Set GOOGLE_APPLICATION_CREDENTIALS in .env "
            "to the path of your service account key."
        ) from exc


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
