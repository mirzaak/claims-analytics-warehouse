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
2. Authenticate the CLI with your workspace URL:
   ```bash
   databricks auth login --host https://<your-workspace>.cloud.databricks.com
   ```
3. Create a personal access token (**Settings → Developer → Access tokens**). Open **SQL Warehouses → your warehouse → Connection details** for the HTTP path.
4. In `.env`, set `DATABRICKS_HOST`, `DATABRICKS_HTTP_PATH` and `DATABRICKS_TOKEN`.

### Run

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
