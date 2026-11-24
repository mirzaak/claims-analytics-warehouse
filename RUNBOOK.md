# Runbook

The [Pipeline workflow](.github/workflows/pipeline.yml) runs daily at 06:17 UTC and on demand. When a step fails, a Discord alert names the step and links the run log and the matching section below.

**First moves for any alert**

1. Open the run log from the alert and expand the failed step.
2. Download the `dbt-results` artifact from the run for `run_results.json`, `sources.json` and `dbt.log`.
3. Fix the cause, then re-run with **Actions → Pipeline → Run workflow**. Every step is idempotent, so a full re-run is safe.

## Install

**Means:** pip could not install the ingestion package or dbt.

**Diagnose:** look for a version conflict or a network error in the step log. Check whether a pinned version in `requirements-dbt.txt` or `ingestion/pyproject.toml` was yanked.

**Fix:** if the error is a network timeout, re-run. Otherwise, pin a working version, run the tests locally, and push.

## Configure credentials

**Means:** the repository variable `GCP_PROJECT_ID` or the secret `GCP_SA_KEY` is missing.

**Diagnose:** the step log names the missing value. Check **Settings → Secrets and variables → Actions**.

**Fix:** set the missing value, as described in the README setup. If the key was rotated, store the new JSON key in `GCP_SA_KEY`.

## Ingest

**Means:** at least one source file failed to download, prepare or load. The other files still loaded.

**Diagnose:** the summary table at the end of the step shows each file's status, and `FAILED <table>:` lines give the reason. The `raw._ingest_runs` table holds the same outcome for every run.

| Error contains | Cause | Fix |
|---|---|---|
| `HTTP 404` | CMS moved or removed a file | Update the URL in `ingestion/src/claims_ingest/catalog.py`. |
| `after 5 attempts` | CMS was unreachable | Re-run later. |
| `missing required columns` or `line N has` | The source file format changed | Inspect the file and update the catalog or staging models. |
| `403` and `permission` | The service account lost a role | Grant BigQuery Data Editor and BigQuery Job User again. |
| `Table expiration time must be less than 60 days` | A table has no expiry in the sandbox | Re-run. The loader sets expiries before loading. |

## Install dbt packages

**Means:** `dbt deps` could not download `dbt_utils` from the dbt package hub.

**Diagnose:** usually a network error, shown in the step log.

**Fix:** re-run. If the hub is down for long, wait, because the build needs the package.

## Source freshness

**Means:** `raw._ingest_runs` has no row newer than 50 hours (error), or 26 hours (warning), so ingestion has not recorded a run.

**Diagnose:** if Ingest passed in this same run, query `raw._ingest_runs` for its latest `finished_at`. A failed audit append makes Ingest fail too.

**Fix:** re-run the pipeline. If the schedule stopped, see [Scheduled runs stopped](#scheduled-runs-stopped).

## dbt build

**Means:** a model failed to build, or a test failed. The step log lists each `ERROR` or `FAIL`.

| Failed node | Means | Fix |
|---|---|---|
| `dq_rule_violation_rate_within_threshold` | A business rule's violation rate passed its threshold | Query `quality.dq_rule_summary` for the rule, and `quality.dq_quarantine` for the rows. If the source changed, fix upstream. If the new rate is expected, raise the threshold in `macros/data_quality.sql` and say why in the commit. |
| `assert_raw_paid_reconciles_to_facts` | Money was lost, duplicated or mis-cast between raw and facts | The failing rows show the measure and both totals. Compare row counts from raw through staging to the fact for that claim type. |
| `assert_pmpm_mart_reconciles_to_facts` | The PMPM mart lost or double-counted cost | Check joins in `mart_cost_pmpm` against `fact_member_month`. |
| `relationships_*` | A fact key has no dimension row | Check the dimension's unknown row and the key macro in `macros/modeling.sql`. |
| `unique_*`, `unique_combination_*` | Duplicate keys | Look for a fan-out join, often a point-in-time member join with overlapping versions. |
| `source_columns_castable_*` | A raw value no longer casts to its type | The failing rows show the column and value. Update the cast in staging if the format changed. |
| `Query exceeded limit for bytes billed` | A query would scan more than 2 GB | Find the query in `dbt.log`. It usually needs a filter or a single-scan rewrite. Only raise `maximum_bytes_billed` in `dbt/profiles.yml` with a reason. |
| `Quota exceeded` | The 1 TiB monthly query allowance is used up | Pause the schedule until the month resets. Check `run_results.json` for unexpected `bytes_billed`. |

If the run was started with **force_failure**, this failure is expected. It only proves alerting works.

## Row-count anomaly check

**Means:** a key fact or dimension is empty, or its row count changed by more than 10% since the previous run. The source files are static, so any change is unexpected.

**Diagnose:** the step prints previous and current counts per table. History is in `quality.row_count_history`.

**Fix:** if a table is empty, check the dbt build log for that model. If counts moved because of a deliberate change, such as a new sample or sample rate, re-run once. The new counts become the baseline.

## Generate or publish dbt docs

**Means:** `dbt docs generate` failed, or GitHub Pages rejected the deployment.

**Diagnose:** a generate failure is usually a BigQuery permission or network error. A publish failure usually means Pages is not set to deploy from GitHub Actions.

**Fix:** in **Settings → Pages**, set the source to **GitHub Actions**, then re-run.

## Scheduled runs stopped

GitHub disables scheduled workflows in public repositories after 60 days without repository activity. The workflow page then shows a banner, and no alert is sent.

**Fix:** re-enable the workflow on its Actions page, and push a commit from time to time.

## Tables disappeared

The BigQuery sandbox deletes every table at most 60 days after it was created, and it rejects any expiry beyond that, so an expiry can never be extended. Tables stay alive only by being recreated:

| Tables | How they are kept |
|---|---|
| dbt models | Rebuilt by every `dbt build`, which resets their 60 days |
| Raw source tables | Dropped and reloaded by ingestion 14 days before they expire |
| `raw._ingest_runs`, `quality.row_count_history` | Append-only logs. They expire 60 days after creation and are recreated by the next run, which starts a fresh baseline. |

If the schedule stopped for long enough, tables can vanish.

**Fix:** run the pipeline. Ingestion reloads missing raw tables, and dbt rebuilds everything else.
