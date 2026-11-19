# Project plan

Status: Step 1 (ingestion) is complete. Sample 1 is loaded into BigQuery, and a second run loaded nothing new.

Open question: the `claims-warehouse` project has billing enabled, so it is not the BigQuery sandbox. DML works and tables do not expire. Decisions D1, D2 and D10 assumed the sandbox and need a final choice.

## Goal

Build an end-to-end ELT pipeline for synthetic Medicare claims. It loads CMS DE-SynPUF files into a cloud warehouse, models them as a star schema with dbt, tests data quality, runs on a schedule, alerts on failure, and feeds a BI dashboard. Total cost: $0.

## Warehouse strategy

| | BigQuery sandbox | Snowflake trial |
|---|---|---|
| Role | Primary, always-on target | Second target that proves the models are portable |
| Runs | Scheduled daily | Manual workflow only |
| Serves | Looker Studio dashboard, marts | Real `dbt snapshot` run, saved evidence in `docs/snowflake-proof/` |
| Lifetime | No end date, but objects expire after 60 days | 30 days, then the account is suspended |
| Card required | No | No |

Start the Snowflake trial on the last day of the build so the 30 days are not wasted. After it ends, the README keeps the saved evidence and labels Snowflake as a completed portability check.

## Repository structure

```text
claims-analytics-warehouse/
├── .github/workflows/
│   ├── ci.yml                  # pytest, lint, dbt parse on every push
│   ├── pipeline.yml            # daily: ingest -> dbt build -> publish docs -> alert
│   └── snowflake-proof.yml     # manual only
├── ingestion/
│   ├── src/claims_ingest/      # download, sample, load, manifest, retry, CLI
│   └── tests/                  # pytest
├── dbt/
│   ├── models/
│   │   ├── staging/            # one model per source, no business logic
│   │   ├── intermediate/       # unpivots, coverage history, claim unions
│   │   ├── marts/core/         # facts and dimensions
│   │   ├── marts/analytics/    # PMPM, utilization, diagnoses, pharmacy, high cost
│   │   └── quarantine/         # failed rows with a failure reason
│   ├── snapshots/              # Snowflake only, see D1
│   ├── tests/generic/          # reusable business-rule tests
│   ├── tests/singular/         # reconciliation tests
│   ├── macros/                 # BigQuery and Snowflake SQL differences
│   └── seeds/                  # small code reference tables
├── docs/
│   ├── PROJECT_PLAN.md
│   ├── images/                 # architecture diagram, ERD, dashboard screenshot
│   └── snowflake-proof/        # saved run results from the trial
├── scripts/                    # one-command rebuild, forced-failure test
├── .env.example
├── README.md
└── RUNBOOK.md
```

## Time plan (20 hours)

| Session | Hours | Work | Done when |
|---|---:|---|---|
| Weekend 1, Saturday | 1 | Create BigQuery project, run the spikes in the next section | Each spike has a written result |
| | 4 | Ingestion to BigQuery with pytest | A second run adds zero rows, row counts are logged |
| Weekend 1, Sunday | 2 | Staging models and source tests | Every source has a tested staging model |
| | 3 | Dimensions, SCD2 member history, start of facts | Dimension keys are unique and not null |
| Weekend 2, Saturday | 1 | Finish the three facts | Relationship tests pass |
| | 1.5 | Five analytics marts | Marts build from core models only |
| | 2.5 | Business rules, quarantine, reconciliation | Raw paid total equals mart paid total |
| Weekend 2, Sunday | 1.5 | GitHub Actions, alerts, RUNBOOK | A forced failure sends an alert |
| | 1.5 | Snowflake target and saved proof | `dbt build` passes on Snowflake |
| | 0.5 | Partitioning before/after measurement | Bytes scanned are recorded |
| | 0.5 | Looker Studio dashboard | Public link works |
| | 1 | README, ERD, architecture diagram, masked view | A fresh clone runs from the README |

If time runs short, cut in this order. Tests and docs are never cut.

1. Dagster or Airflow stretch goal (already out of the plan).
2. `mart_high_cost_members`.
3. Snowflake snapshot comparison, keeping only `dbt build` on Snowflake.
4. Snowflake entirely, keeping BigQuery complete.

## Spikes to run first

Each of these can change the design.

1. **Old-date partitions (resolved for this project).** `scripts/check_partition_expiry.py` loaded 2008, 2009, 2010 and current dates into date-partitioned and integer-range tables. All rows survived, because this billing-enabled project sets no partition expiration. A sandbox project was not tested.
2. **2010 beneficiary file (resolved).** The CMS link is named `sample_20`, but the archive contains `DE1_0_2010_Beneficiary_Summary_File_Sample_1.csv`. All 112,754 of its members also appear in the 2009 Sample 1 file, so it is safe to load.
3. **Data volume (partly resolved).** Sample 1 is 11,494,963 rows and 3.12 GB uncompressed. The 10% sample keeps 1,152,481 rows. Bytes scanned per rebuild can only be measured once dbt runs.

## Decisions that change the original brief

| ID | Decision | Why |
|---|---|---|
| D1 | Build SCD2 `dim_member` from the 2008, 2009 and 2010 beneficiary files with a window-function model. Also run a real `dbt snapshot` on Snowflake and compare the results. | The BigQuery sandbox does not support DML, and snapshots must update existing rows. |
| D2 | Partition the largest BigQuery fact by integer `service_year_month` and cluster by member key, unless spike 1 shows date partitions survive. | Sandbox partitions expire after 60 days, and BigQuery expires old-dated partitions immediately on load. All claim dates are 2008 to 2010. |
| D3 | Use the CMS sample number as the incremental unit. Beneficiary files add a year within a sample. | Claim files cover 2008 to 2010 together, so they cannot be loaded one year at a time. |
| D4 | Derive `fact_member_month` from yearly coverage month counts and document the assumption. Months are assigned from January forward and stop at death date. | SynPUF has total coverage months per year, not monthly enrollment flags. The "enrolled in month of service" rule is therefore approximate. |
| D5 | Fact grain is one row per carrier line, and one row per claim segment for inpatient and outpatient. Allowed amount is null for inpatient and outpatient. | Only carrier has line-level paid and allowed amounts. Inpatient and outpatient have claim-level payment only, and allocating it would invent data. |
| D6 | `dim_drug` holds the product code only. Generic vs brand is left out unless a public reference file is added later. | The drug events file has no drug name or brand flag. |
| D7 | Keep a deterministic 10% sample of members, the same members in every file. Revisit the rate after measuring bytes scanned per rebuild. | It protects the 10 GiB storage limit and 1 TiB monthly query limit while keeping every member's claims complete. |
| D8 | Load the CMS `sample_20` link as the Sample 1 2010 beneficiary file. | Its contents were checked and match Sample 1 (spike 2). |
| D9 | Load each source file to its own raw table with a replace-on-load job on BigQuery. Use a delete and `COPY` in one transaction on Snowflake. | Replace-on-load keeps re-runs idempotent without DML. |
| D10 | Record every pipeline run in an append-only `_ingest_runs` table and point freshness checks at it. Reload raw tables before they reach 60 days. | Source files never change, so `_loaded_at` alone would look stale, and sandbox tables would otherwise expire. |
| D11 | Use a Discord webhook for alerts and key-pair auth for Snowflake. | Both are free and keep passwords out of CI. |

## Accounts and secrets needed

Secrets are stored in GitHub Actions secrets and a local `.env` file, never in the repo.

- Google Cloud project with the BigQuery sandbox and a service account.
- Discord webhook URL.
- Snowflake trial account with a key-pair service user (last day only).
- Looker Studio access with the same Google account.

## Sources

- [BigQuery sandbox limits](https://docs.cloud.google.com/bigquery/docs/sandbox)
- [BigQuery partition expiration](https://docs.cloud.google.com/bigquery/docs/managing-partitioned-tables)
- [Snowflake trial accounts](https://docs.snowflake.com/en/user-guide/admin-trial-account)
- [dbt snapshots](https://docs.getdbt.com/docs/build/snapshots)
- [CMS DE-SynPUF Sample 1](https://www.cms.gov/data-research/statistics-trends-and-reports/medicare-claims-synthetic-public-use-files/cms-2008-2010-data-entrepreneurs-synthetic-public-use-file-de-synpuf/de10-sample-1)
- [DE-SynPUF codebook](https://www.cms.gov/files/document/de-10-codebook.pdf-0)
