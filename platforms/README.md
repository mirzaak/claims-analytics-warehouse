# Snowflake and Databricks

The same pipeline runs on three platforms. BigQuery is the scheduled, always-on target. Snowflake and Databricks show the design is portable, and they cover tools that healthcare data teams commonly use.

| | BigQuery sandbox | Snowflake trial | Databricks Free Edition |
|---|---|---|---|
| Raw load | Python load job, replace on load | Python `PUT` + `COPY`, then atomic `SWAP` | Files land in a Unity Catalog volume; a PySpark job writes Delta bronze tables |
| Skip unchanged files | Batch ID in a table label | Batch ID in `RAW._LOAD_STATE` | Batch ID in a Delta table property |
| Transformations | dbt, target `dev` | dbt, target `snowflake` | dbt, target `databricks` |
| Member history (SCD2) | Window functions | Window functions, plus a real `dbt snapshot` checked against them | Window functions |
| Runs | Daily in GitHub Actions | Manually | Manually, plus a Databricks Job for the bronze load |

The same batch ID (a hash of the source file and sample rate) identifies a file on every platform, so loads can be compared across warehouses.

## Results

| | BigQuery | Databricks | Snowflake |
|---|---|---|---|
| Status | Runs daily | Run on November 28, 2026 | Not run yet: the trial signup did not complete |
| Raw rows loaded | 1,152,481 | 1,152,481 | |
| dbt build | 181 pass, 3 warn | 181 pass, 3 warn | |
| Medical claim lines, paid total | 1,021,603 lines, $127,373,970 | Same | |
| Pharmacy events, gross drug cost | 561,720 events, $34,474,750 | Same | |
| Quarantined records | 57,768 | 57,768 | |
| Medical PMPM, 2008 / 2009 / 2010 | $363.07 / $393.20 / $223.51 | Same | |
| dbt build time | About 3 minutes in GitHub Actions | 2 minutes 14 seconds from a laptop | |

The three warnings are the same source-data issues on both platforms: missing claim start dates and three malformed NDC codes. They are flagged, not dropped.

The Snowflake loader and dbt target are covered by unit tests that use a fake connection, but they have not run against a real account.

## Snowflake

### One-time setup

1. Sign up for a [Snowflake trial](https://signup.snowflake.com/). Any cloud and region work.
2. Generate a key pair outside the repository:
   ```bash
   openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out ~/.config/claims-warehouse/snowflake_rsa_key.p8 -nocrypt
   ```
   ```bash
   openssl rsa -in ~/.config/claims-warehouse/snowflake_rsa_key.p8 -pubout -out ~/.config/claims-warehouse/snowflake_rsa_key.pub
   ```
3. Paste [setup.sql](snowflake/setup.sql) into a Snowsight worksheet, replace `<PUBLIC_KEY>` with the public key's body, and run it all. It creates a least-privilege role, an extra-small warehouse that suspends after 60 seconds, a key-pair service user with no password, and a resource monitor capped at 20 credits.
4. In `.env`, set `SNOWFLAKE_ACCOUNT` to the value the last query prints, and `SNOWFLAKE_PRIVATE_KEY_PATH` to the private key's full path.

### Run

```bash
.venv/bin/pip install "./ingestion[snowflake]" -r requirements-dbt-platforms.txt
```

```bash
.venv/bin/claims-ingest run --sample 1 --warehouse snowflake
```

```bash
scripts/dbt.sh build --target snowflake
```

```bash
scripts/replay_member_snapshot.sh
```

```bash
scripts/dbt.sh test --target snowflake --select assert_snapshot_matches_window_function_scd2
```

`replay_member_snapshot.sh` feeds the snapshot one coverage year at a time, oldest first, because the source holds one state per year. The last test proves the snapshot and the window-function model produce the same member versions.

## Databricks

### One-time setup

1. Sign up for [Databricks Free Edition](https://www.databricks.com/learn/free-edition).
2. Create a personal access token (**Settings → Developer → Access tokens**). Paste it straight into `.env`; never paste it into a chat or a commit.
3. Open **SQL Warehouses → your warehouse → Connection details** for the HTTP path.
4. In `.env`, set `DATABRICKS_HOST`, `DATABRICKS_HTTP_PATH` and `DATABRICKS_TOKEN`. The Databricks CLI and dbt both read these.

### Run

Load `.env` into the shell first, so the Databricks CLI picks up the host and token:

```bash
set -a; source .env; set +a
```

```bash
scripts/databricks_land_files.sh
```

```bash
databricks bundle deploy
```

```bash
databricks bundle run claims_bronze_load
```

```bash
scripts/dbt.sh build --target databricks
```

`databricks_land_files.sh` exports load-ready files and uploads them to the `workspace.raw.landing` volume, one folder per table. The bundle in [databricks.yml](../databricks.yml) deploys [bronze_load.py](databricks/bronze_load.py) as a serverless job, which writes the Delta tables in `workspace.raw`.

Medallion naming maps onto the dbt layers: bronze is `raw`, silver is `staging` and `intermediate`, and gold is `marts`.
