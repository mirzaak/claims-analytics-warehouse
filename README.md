# Claims Analytics Warehouse

An end-to-end ELT pipeline for synthetic healthcare claims, built on free tiers: Python ingestion, dbt models in a star schema, automated data quality tests, scheduled orchestration, failure alerts, and a BI dashboard.

**Status:** in progress. [Ingestion](ingestion/README.md) loads Sample 1 into BigQuery, and [dbt](dbt/README.md) builds the staging layer, the star schema, five analytics marts and data-quality checks, with all 181 tests passing and raw totals reconciling to the cent. A daily GitHub Actions pipeline with failure alerts is in place. The dashboard is next. See the [project plan](docs/PROJECT_PLAN.md).

## Data

This project uses [CMS DE-SynPUF](https://www.cms.gov/data-research/statistics-trends-and-reports/medicare-claims-synthetic-public-use-files), a synthetic Medicare claims dataset. It contains no real patient data.

## Planned stack

| Layer | Tool |
|---|---|
| Warehouse | BigQuery sandbox, with Snowflake as a second target |
| Ingestion | Python |
| Transformation and tests | dbt Core |
| Orchestration | GitHub Actions |
| BI | Looker Studio |

## Orchestration and monitoring

The [Pipeline workflow](.github/workflows/pipeline.yml) runs daily and on demand:

1. Ingest source files. Unchanged files are skipped.
2. Check source freshness on `raw._ingest_runs`.
3. Run `dbt build`: every model and test, including business-rule thresholds and reconciliation.
4. Check that no key table is empty or changed by more than 10% (`claims-ingest check-row-counts`).
5. Publish dbt docs to GitHub Pages.

If any step fails, a Discord alert names the step and links the run log and the matching [runbook](RUNBOOK.md) section. Run the workflow with **force_failure** to test alerting end to end.

### Setup

The workflow needs these repository settings:

| Name | Kind | Value |
|---|---|---|
| `GCP_PROJECT_ID` | variable | The BigQuery project ID |
| `GCP_SA_KEY` | secret | The service account's JSON key |
| `DISCORD_WEBHOOK_URL` | secret | A Discord channel webhook URL |

GitHub Pages must deploy from GitHub Actions (**Settings → Pages → Source**).
