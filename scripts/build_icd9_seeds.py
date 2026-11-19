"""Build dbt seeds with ICD-9-CM code descriptions from the CMS Version 32 code titles.

The CMS files are public domain. HCPCS Level I (CPT) descriptions are copyrighted by
the AMA, so no procedure names are added for HCPCS codes.

Run from the repository root: .venv/bin/python scripts/build_icd9_seeds.py
"""

from __future__ import annotations

import csv
import re
import zipfile
from pathlib import Path

from claims_ingest.download import download_file

SOURCE_URL = (
    "https://www.cms.gov/medicare/coding/icd9providerdiagnosticcodes/downloads/"
    "icd-9-cm-v32-master-descriptions.zip"
)
ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD = ROOT / "data" / "reference" / "icd-9-cm-v32-master-descriptions.zip"
SEEDS = ROOT / "dbt" / "seeds"


def read_titles(archive: zipfile.ZipFile, pattern: str) -> dict[str, str]:
    names = [name for name in archive.namelist() if re.search(pattern, name, re.IGNORECASE)]
    if len(names) != 1:
        raise SystemExit(f"Expected one file matching {pattern}, found {names}")
    titles = {}
    text = archive.read(names[0]).decode("latin-1")
    for line in text.splitlines():
        if not line.strip():
            continue
        code, _, title = line.strip().partition(" ")
        titles[code.strip()] = " ".join(title.split())
    return titles


def write_seed(path: Path, key: str, short: dict[str, str], long: dict[str, str]) -> int:
    codes = sorted(set(short) | set(long))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow([key, "short_description", "long_description"])
        for code in codes:
            writer.writerow([code, short.get(code, ""), long.get(code, "")])
    return len(codes)


def main() -> None:
    result = download_file(SOURCE_URL, DOWNLOAD)
    print(f"source sha256: {result.sha256}")
    with zipfile.ZipFile(result.path) as archive:
        print(f"archive files: {sorted(archive.namelist())}")
        diagnosis = write_seed(
            SEEDS / "icd9_diagnosis_descriptions.csv",
            "diagnosis_code",
            read_titles(archive, r"DESC_SHORT_DX\.txt$"),
            read_titles(archive, r"DESC_LONG_DX\.txt$"),
        )
        procedure = write_seed(
            SEEDS / "icd9_procedure_descriptions.csv",
            "procedure_code",
            read_titles(archive, r"DESC_SHORT_SG\.txt$"),
            read_titles(archive, r"DESC_LONG_SG\.txt$"),
        )
    print(f"diagnosis codes: {diagnosis}, procedure codes: {procedure}")


if __name__ == "__main__":
    main()
