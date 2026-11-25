from pathlib import Path

import pytest

from claims_ingest.config import Settings
from claims_ingest.errors import ConfigError


def test_unknown_warehouse_is_rejected():
    with pytest.raises(ConfigError, match="WAREHOUSE_TARGET must be one of bigquery, snowflake"):
        Settings.from_env({"WAREHOUSE_TARGET": "redshift"})


def test_snowflake_needs_account_and_key():
    with pytest.raises(ConfigError, match="SNOWFLAKE_ACCOUNT and SNOWFLAKE_PRIVATE_KEY_PATH"):
        Settings.from_env({"WAREHOUSE_TARGET": "snowflake"}).require_snowflake()


def test_snowflake_key_path_must_exist(tmp_path):
    settings = Settings.from_env(
        {"SNOWFLAKE_ACCOUNT": "org-acct", "SNOWFLAKE_PRIVATE_KEY_PATH": str(tmp_path / "no.p8")}
    )

    with pytest.raises(ConfigError, match="does not point to a file"):
        settings.require_snowflake()


def test_snowflake_defaults_match_the_setup_script(tmp_path):
    key = tmp_path / "key.p8"
    key.write_text("key")
    settings = Settings.from_env(
        {"SNOWFLAKE_ACCOUNT": "org-acct", "SNOWFLAKE_PRIVATE_KEY_PATH": str(key)}
    ).require_snowflake()

    assert (settings.user, settings.role, settings.warehouse, settings.database) == (
        "CLAIMS_SERVICE",
        "CLAIMS_TRANSFORMER",
        "CLAIMS_WH",
        "CLAIMS_WAREHOUSE",
    )


def test_defaults_apply_when_values_are_blank():
    settings = Settings.from_env({"MEMBER_SAMPLE_PCT": "", "GCP_PROJECT_ID": " "})

    assert settings.member_sample_pct == 10
    assert settings.data_dir == Path("data")
    assert settings.gcp_project_id is None


@pytest.mark.parametrize("value", ["0", "101", "ten"])
def test_invalid_sample_percentage_is_rejected(value):
    with pytest.raises(ConfigError, match="MEMBER_SAMPLE_PCT"):
        Settings.from_env({"MEMBER_SAMPLE_PCT": value})


def test_raw_tables_expire_after_60_days_by_default():
    assert Settings.from_env({}).raw_expiration_days == 60


def test_expiry_can_be_turned_off_for_billing_projects():
    assert Settings.from_env({"RAW_EXPIRATION_DAYS": "0"}).raw_expiration_days == 0


def test_expiry_above_the_sandbox_limit_is_rejected():
    with pytest.raises(ConfigError, match="RAW_EXPIRATION_DAYS must be between 0 and 60"):
        Settings.from_env({"RAW_EXPIRATION_DAYS": "61"})


def test_refresh_window_must_be_shorter_than_expiry():
    with pytest.raises(ConfigError, match="must be lower than RAW_EXPIRATION_DAYS"):
        Settings.from_env({"RAW_EXPIRATION_DAYS": "10", "RAW_REFRESH_DAYS": "10"})


def test_missing_project_id_explains_the_fix():
    with pytest.raises(ConfigError, match="GCP_PROJECT_ID is not set"):
        Settings.from_env({}).require_project_id()
