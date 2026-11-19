# dbt project

Transforms the raw SynPUF tables into staging, intermediate and mart layers in BigQuery.

## Setup

Run these from the repository root, after the ingestion setup in [ingestion/README.md](../ingestion/README.md).

```bash
.venv/bin/pip install -r requirements-dbt.txt
```

```bash
scripts/dbt.sh deps
```

`scripts/dbt.sh` loads `.env` and points dbt at this folder. `profiles.yml` reads every setting from environment variables, so it holds no secrets.

## Build and test

```bash
scripts/dbt.sh build --select "source:synpuf+"
```

```bash
scripts/dbt.sh source freshness
```

## Layers

| Layer | Schema | Materialization | Rule |
|---|---|---|---|
| Staging | `staging` | view | One model per source. Rename, cast and clean codes only. |
| Intermediate | `intermediate` | view | Unpivots and joins that marts reuse. |
| Marts | `marts` | table | Facts, dimensions and analytics marts. |

## Staging models

| Model | Grain | Rows (Sample 1, 10%) |
|---|---|---:|
| `stg_synpuf__beneficiaries` | member, coverage year, sample | 34,132 |
| `stg_synpuf__inpatient_claims` | claim segment, sample | 6,683 |
| `stg_synpuf__outpatient_claims` | claim segment, sample | 77,871 |
| `stg_synpuf__carrier_claims` | claim, sample (files A and B combined) | 472,075 |
| `stg_synpuf__prescription_drug_events` | prescription fill, sample | 561,720 |

Repeated source columns, such as 10 diagnosis codes or 13 carrier lines, stay wide in staging with a `_n` suffix. Intermediate models unpivot them.

## Tests

| Check | Where | What it catches |
|---|---|---|
| `columns_castable` | raw sources | Any non-blank date, integer or amount that would silently become null when cast. |
| Unique keys | every staging model | Duplicate members per year, claim segments, carrier claims or fills. |
| `relationships` | claims and fills | A member ID that is missing from every beneficiary year. |
| Accepted values and ranges | beneficiaries | Unknown sex or race codes, coverage months outside 0 to 12. |
| Freshness | `raw._ingest_runs` | No ingestion run in 26 hours (warn) or 50 hours (error). |

The latest build passed 69 checks with 3 warnings. The warnings are real source issues, reported and kept rather than dropped:

| Warning | Rows |
|---|---:|
| Inpatient claims with no `claim_from_date` | 3 |
| Outpatient claims with no `claim_from_date` | 1,172 |
| Drug events whose product code is not 11 characters | 3 |

Profiling also found 6 inpatient and 240 outpatient claims with negative payments. Business-rule tests in the marts will flag these.

## Cost guardrails

- `maximum_bytes_billed` in `profiles.yml` fails any query that would scan more than 2 GB.
- A full staging build processed 121 MB and billed 1,017 MB. BigQuery bills at least 10 MB per query, so the 72 small test queries dominate the bill.
- At one build a day, that is about 3% of the sandbox's 1 TiB monthly query allowance.

## Portability

Warehouse-specific SQL is isolated in `macros/casting.sql`. For example, `parse_yyyymmdd` uses `safe.parse_date` on BigQuery and `try_to_date` elsewhere, so the same models can run on Snowflake.
