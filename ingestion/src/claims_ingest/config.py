"""Runtime settings read from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from claims_ingest.errors import ConfigError


def _int_setting(env: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}.") from exc
    if not low <= value <= high:
        raise ConfigError(f"{name} must be between {low} and {high}, got {value}.")
    return value


WAREHOUSES = ("bigquery", "snowflake")


def _text(env: Mapping[str, str], name: str, default: str | None = None) -> str | None:
    return (env.get(name) or "").strip() or default


@dataclass(frozen=True)
class SnowflakeSettings:
    account: str
    user: str
    private_key_path: Path
    role: str
    warehouse: str
    database: str


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("data")
    member_sample_pct: int = 10
    refresh_days: int = 14
    # The BigQuery sandbox rejects writes to tables that never expire. 0 means no expiry.
    raw_expiration_days: int = 60
    warehouse: str = "bigquery"
    gcp_project_id: str | None = None
    gcp_location: str = "US"
    raw_dataset: str = "raw"
    snowflake_account: str | None = None
    snowflake_user: str = "CLAIMS_SERVICE"
    snowflake_private_key_path: str | None = None
    snowflake_role: str = "CLAIMS_TRANSFORMER"
    snowflake_warehouse: str = "CLAIMS_WH"
    snowflake_database: str = "CLAIMS_WAREHOUSE"

    def __post_init__(self) -> None:
        if self.raw_expiration_days and self.refresh_days >= self.raw_expiration_days:
            raise ConfigError(
                f"RAW_REFRESH_DAYS ({self.refresh_days}) must be lower than "
                f"RAW_EXPIRATION_DAYS ({self.raw_expiration_days})."
            )
        if self.warehouse not in WAREHOUSES:
            raise ConfigError(
                f"WAREHOUSE_TARGET must be one of {', '.join(WAREHOUSES)}, got {self.warehouse!r}."
            )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if env is None else env
        return cls(
            data_dir=Path(_text(values, "DATA_DIR", "data")),
            member_sample_pct=_int_setting(values, "MEMBER_SAMPLE_PCT", 10, 1, 100),
            refresh_days=_int_setting(values, "RAW_REFRESH_DAYS", 14, 1, 59),
            raw_expiration_days=_int_setting(values, "RAW_EXPIRATION_DAYS", 60, 0, 60),
            warehouse=_text(values, "WAREHOUSE_TARGET", "bigquery").lower(),
            gcp_project_id=_text(values, "GCP_PROJECT_ID"),
            gcp_location=_text(values, "GCP_LOCATION", "US"),
            raw_dataset=_text(values, "RAW_DATASET", "raw"),
            snowflake_account=_text(values, "SNOWFLAKE_ACCOUNT"),
            snowflake_user=_text(values, "SNOWFLAKE_USER", "CLAIMS_SERVICE"),
            snowflake_private_key_path=_text(values, "SNOWFLAKE_PRIVATE_KEY_PATH"),
            snowflake_role=_text(values, "SNOWFLAKE_ROLE", "CLAIMS_TRANSFORMER"),
            snowflake_warehouse=_text(values, "SNOWFLAKE_WAREHOUSE", "CLAIMS_WH"),
            snowflake_database=_text(values, "SNOWFLAKE_DATABASE", "CLAIMS_WAREHOUSE"),
        )

    def require_snowflake(self) -> SnowflakeSettings:
        missing = [
            name
            for name, value in (
                ("SNOWFLAKE_ACCOUNT", self.snowflake_account),
                ("SNOWFLAKE_PRIVATE_KEY_PATH", self.snowflake_private_key_path),
            )
            if not value
        ]
        if missing:
            raise ConfigError(f"{' and '.join(missing)} must be set in .env to load Snowflake.")
        key_path = Path(self.snowflake_private_key_path).expanduser()
        if not key_path.is_file():
            raise ConfigError(f"SNOWFLAKE_PRIVATE_KEY_PATH does not point to a file: {key_path}")
        return SnowflakeSettings(
            account=self.snowflake_account,
            user=self.snowflake_user,
            private_key_path=key_path,
            role=self.snowflake_role,
            warehouse=self.snowflake_warehouse,
            database=self.snowflake_database,
        )

    def require_project_id(self) -> str:
        if not self.gcp_project_id:
            raise ConfigError(
                "GCP_PROJECT_ID is not set. Add it to .env, or use --dry-run to skip the warehouse."
            )
        return self.gcp_project_id
