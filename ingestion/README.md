# Ingestion

Downloads CMS DE-SynPUF files and loads them into the warehouse `raw` dataset without changing source values. Each row gains three metadata columns: `_loaded_at`, `_source_file` and `_batch_id`.

## Setup

Run these from the repository root.

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install "./ingestion[dev]"
```

```bash
cp .env.example .env
```

## Try it without a warehouse

A dry run downloads and prepares every file, then prints row counts. It needs no credentials.

```bash
.venv/bin/claims-ingest run --sample 1 --dry-run
```

## Connect BigQuery

1. Create a Google Cloud project and open BigQuery. The sandbox needs no billing account.
2. Create a service account with the **BigQuery Data Editor** and **BigQuery Job User** roles.
3. Create a JSON key and store it outside this repository.
4. In `.env`, set `GCP_PROJECT_ID` and set `GOOGLE_APPLICATION_CREDENTIALS` to the key's full path.

```bash
.venv/bin/claims-ingest run --sample 1
```

## Common commands

| Goal | Command |
|---|---|
| Add another CMS sample | `claims-ingest run --sample 1 --sample 2` |
| Process one file | `claims-ingest run --only beneficiary_2010` |
| Reload unchanged files | `claims-ingest run --force` |

## How a run behaves

| Requirement | Approach |
|---|---|
| Idempotent | A batch ID is a hash of the file contents and sample rate. A table that already holds that batch is skipped. |
| No duplicates | Each load job replaces the whole table, and a failed job leaves the old table in place. |
| Incremental | Each file has its own table, such as `carrier_claims_a_s01`, so a new sample adds tables and leaves others alone. |
| Sandbox expiry | A table within `RAW_REFRESH_DAYS` (default 14) of its 60-day expiry is dropped and reloaded. |
| Retries | Network errors, rate limits and server errors back off exponentially. Permanent errors fail at once. |
| Failure handling | One failed file does not stop the others. The command exits with a non-zero code. |
| Audit trail | Every file outcome is appended to `raw._ingest_runs`, which freshness checks will use. |

Exit codes: `0` success, `1` at least one file failed, `2` the run could not start or finish.

## Member sampling

`MEMBER_SAMPLE_PCT` (default 10) keeps a fixed share of members, chosen by a hash of `DESYNPUF_ID`. A selected member keeps all of their rows in every file, so joins between files stay complete.

## Measured results for Sample 1

From a dry run at the 10% sample rate.

| Table | Source rows | Rows kept | Uncompressed size (MB) |
|---|---:|---:|---:|
| `beneficiary_2008_s01` | 116,352 | 11,550 | 14.6 |
| `beneficiary_2009_s01` | 114,538 | 11,379 | 14.5 |
| `beneficiary_2010_s01` | 112,754 | 11,203 | 14.1 |
| `inpatient_claims_s01` | 66,773 | 6,683 | 16.7 |
| `outpatient_claims_s01` | 790,790 | 77,871 | 161.8 |
| `carrier_claims_a_s01` | 2,370,667 | 234,713 | 1,236.5 |
| `carrier_claims_b_s01` | 2,370,668 | 237,362 | 1,236.5 |
| `prescription_drug_events_s01` | 5,552,421 | 561,720 | 425.0 |
| **Total** | **11,494,963** | **1,152,481** | **3,119.7** |

## Tests

```bash
cd ingestion && ../.venv/bin/pytest
```

The BigQuery loader is tested against a fake client. A real load has not been run yet.
