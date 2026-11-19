# Claims Analytics Warehouse

An end-to-end ELT pipeline for synthetic healthcare claims, built on free tiers: Python ingestion, dbt models in a star schema, automated data quality tests, scheduled orchestration, failure alerts, and a BI dashboard.

**Status:** in progress. [Ingestion](ingestion/README.md) loads Sample 1 into BigQuery, and [dbt](dbt/README.md) builds the staging layer, the star schema, five analytics marts and data-quality checks, with all 181 tests passing and raw totals reconciling to the cent. Orchestration and the dashboard are next. See the [project plan](docs/PROJECT_PLAN.md).

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
