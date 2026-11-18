"""Catalog of the DE-SynPUF files this project can ingest."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from claims_ingest.errors import ConfigError

_CMS_DOWNLOADS = (
    "https://www.cms.gov/research-statistics-data-and-systems/"
    "downloadable-public-use-files/synpufs/downloads"
)
_CMS_STATISTICS = (
    "https://www.cms.gov/research-statistics-data-and-systems/"
    "statistics-trends-and-reports/synpufs/downloads"
)
_CMS_FILES = "https://downloads.cms.gov/files"

SUPPORTED_SAMPLES = (1, 2)


class SourceKind(StrEnum):
    BENEFICIARY = "beneficiary"
    INPATIENT = "inpatient"
    OUTPATIENT = "outpatient"
    CARRIER = "carrier"
    PRESCRIPTION = "prescription"


REQUIRED_COLUMNS: dict[SourceKind, frozenset[str]] = {
    SourceKind.BENEFICIARY: frozenset(
        {"DESYNPUF_ID", "BENE_BIRTH_DT", "BENE_HI_CVRAGE_TOT_MONS", "PLAN_CVRG_MOS_NUM"}
    ),
    SourceKind.INPATIENT: frozenset(
        {"DESYNPUF_ID", "CLM_ID", "SEGMENT", "CLM_FROM_DT", "CLM_THRU_DT", "CLM_PMT_AMT"}
    ),
    SourceKind.OUTPATIENT: frozenset(
        {"DESYNPUF_ID", "CLM_ID", "SEGMENT", "CLM_FROM_DT", "CLM_THRU_DT", "CLM_PMT_AMT"}
    ),
    SourceKind.CARRIER: frozenset(
        {
            "DESYNPUF_ID",
            "CLM_ID",
            "CLM_FROM_DT",
            "CLM_THRU_DT",
            "LINE_NCH_PMT_AMT_1",
            "LINE_ALOWD_CHRG_AMT_1",
        }
    ),
    SourceKind.PRESCRIPTION: frozenset(
        {"DESYNPUF_ID", "PDE_ID", "SRVC_DT", "PROD_SRVC_ID", "TOT_RX_CST_AMT"}
    ),
}


@dataclass(frozen=True)
class SourceFile:
    key: str
    kind: SourceKind
    sample: int
    url: str

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]

    @property
    def table(self) -> str:
        return f"{self.key}_s{self.sample:02d}"

    @property
    def required_columns(self) -> frozenset[str]:
        return REQUIRED_COLUMNS[self.kind]


def _beneficiary_url(sample: int, year: int) -> str:
    # The CMS Sample 1 page publishes its 2010 file under a sample_20 file name.
    if sample == 1 and year == 2010:
        return f"{_CMS_STATISTICS}/de1_0_2010_beneficiary_summary_file_sample_20.zip"
    return f"{_CMS_DOWNLOADS}/de1_0_{year}_beneficiary_summary_file_sample_{sample}.zip"


def sources_for_sample(sample: int) -> tuple[SourceFile, ...]:
    if sample not in SUPPORTED_SAMPLES:
        supported = ", ".join(str(value) for value in SUPPORTED_SAMPLES)
        raise ConfigError(f"Sample {sample} is not supported. Supported samples: {supported}.")

    claims = "de1_0_2008_to_2010"
    files = "DE1_0_2008_to_2010"
    beneficiaries = [
        SourceFile(
            f"beneficiary_{year}",
            SourceKind.BENEFICIARY,
            sample,
            _beneficiary_url(sample, year),
        )
        for year in (2008, 2009, 2010)
    ]
    return (
        *beneficiaries,
        SourceFile(
            "inpatient_claims",
            SourceKind.INPATIENT,
            sample,
            f"{_CMS_DOWNLOADS}/{claims}_inpatient_claims_sample_{sample}.zip",
        ),
        SourceFile(
            "outpatient_claims",
            SourceKind.OUTPATIENT,
            sample,
            f"{_CMS_DOWNLOADS}/{claims}_outpatient_claims_sample_{sample}.zip",
        ),
        SourceFile(
            "carrier_claims_a",
            SourceKind.CARRIER,
            sample,
            f"{_CMS_FILES}/{files}_Carrier_Claims_Sample_{sample}A.zip",
        ),
        SourceFile(
            "carrier_claims_b",
            SourceKind.CARRIER,
            sample,
            f"{_CMS_FILES}/{files}_Carrier_Claims_Sample_{sample}B.zip",
        ),
        SourceFile(
            "prescription_drug_events",
            SourceKind.PRESCRIPTION,
            sample,
            f"{_CMS_FILES}/{files}_Prescription_Drug_Events_Sample_{sample}.zip",
        ),
    )


def select_sources(
    samples: Iterable[int], only: Iterable[str] | None = None
) -> tuple[SourceFile, ...]:
    selected = [
        source for sample in dict.fromkeys(samples) for source in sources_for_sample(sample)
    ]
    wanted = set(only or ())
    if not wanted:
        return tuple(selected)

    unknown = wanted - {source.key for source in selected}
    if unknown:
        valid = ", ".join(sorted({source.key for source in selected}))
        raise ConfigError(f"Unknown source {sorted(unknown)}. Valid sources: {valid}.")
    return tuple(source for source in selected if source.key in wanted)
