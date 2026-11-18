import pytest
from conftest import beneficiary_rows, cache_source

from claims_ingest.catalog import sources_for_sample
from claims_ingest.cli import EXIT_FILE_FAILED, EXIT_OK, EXIT_RUN_FAILED, main
from claims_ingest.config import Settings


@pytest.fixture
def cli_settings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MEMBER_SAMPLE_PCT", "100")
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    return Settings.from_env()


def beneficiary_2008():
    return next(source for source in sources_for_sample(1) if source.key == "beneficiary_2008")


def test_dry_run_prints_row_counts(cli_settings, capsys):
    cache_source(cli_settings, beneficiary_2008(), beneficiary_rows(3))

    code = main(["run", "--dry-run", "--only", "beneficiary_2008"])

    output = capsys.readouterr().out
    assert code == EXIT_OK
    assert "beneficiary_2008_s01" in output
    assert "prepared" in output


def test_invalid_file_returns_the_file_failure_code(cli_settings, capsys):
    cache_source(cli_settings, beneficiary_2008(), [["WRONG"], ["1"]])

    code = main(["run", "--dry-run", "--only", "beneficiary_2008"])

    assert code == EXIT_FILE_FAILED
    assert "missing required columns" in capsys.readouterr().err


def test_missing_project_returns_the_run_failure_code(cli_settings, capsys):
    code = main(["run", "--only", "beneficiary_2008"])

    assert code == EXIT_RUN_FAILED
    assert "GCP_PROJECT_ID is not set" in capsys.readouterr().err


def test_unknown_source_returns_the_run_failure_code(cli_settings, capsys):
    code = main(["run", "--dry-run", "--only", "dental_claims"])

    assert code == EXIT_RUN_FAILED
    assert "Unknown source" in capsys.readouterr().err
