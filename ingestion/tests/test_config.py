from pathlib import Path

import pytest

from claims_ingest.config import Settings
from claims_ingest.errors import ConfigError


def test_defaults_apply_when_values_are_blank():
    settings = Settings.from_env({"MEMBER_SAMPLE_PCT": "", "GCP_PROJECT_ID": " "})

    assert settings.member_sample_pct == 10
    assert settings.data_dir == Path("data")
    assert settings.gcp_project_id is None


@pytest.mark.parametrize("value", ["0", "101", "ten"])
def test_invalid_sample_percentage_is_rejected(value):
    with pytest.raises(ConfigError, match="MEMBER_SAMPLE_PCT"):
        Settings.from_env({"MEMBER_SAMPLE_PCT": value})


def test_missing_project_id_explains_the_fix():
    with pytest.raises(ConfigError, match="GCP_PROJECT_ID is not set"):
        Settings.from_env({}).require_project_id()
