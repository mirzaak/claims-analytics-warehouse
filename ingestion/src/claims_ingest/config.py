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


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("data")
    member_sample_pct: int = 10
    refresh_days: int = 14
    # The BigQuery sandbox rejects writes to tables that never expire. 0 means no expiry.
    raw_expiration_days: int = 60
    gcp_project_id: str | None = None
    gcp_location: str = "US"
    raw_dataset: str = "raw"

    def __post_init__(self) -> None:
        if self.raw_expiration_days and self.refresh_days >= self.raw_expiration_days:
            raise ConfigError(
                f"RAW_REFRESH_DAYS ({self.refresh_days}) must be lower than "
                f"RAW_EXPIRATION_DAYS ({self.raw_expiration_days})."
            )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if env is None else env
        return cls(
            data_dir=Path((values.get("DATA_DIR") or "data").strip()),
            member_sample_pct=_int_setting(values, "MEMBER_SAMPLE_PCT", 10, 1, 100),
            refresh_days=_int_setting(values, "RAW_REFRESH_DAYS", 14, 1, 59),
            raw_expiration_days=_int_setting(values, "RAW_EXPIRATION_DAYS", 60, 0, 60),
            gcp_project_id=(values.get("GCP_PROJECT_ID") or "").strip() or None,
            gcp_location=(values.get("GCP_LOCATION") or "US").strip(),
            raw_dataset=(values.get("RAW_DATASET") or "raw").strip(),
        )

    def require_project_id(self) -> str:
        if not self.gcp_project_id:
            raise ConfigError(
                "GCP_PROJECT_ID is not set. Add it to .env, or use --dry-run to skip the warehouse."
            )
        return self.gcp_project_id
