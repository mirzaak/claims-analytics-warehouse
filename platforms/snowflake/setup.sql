-- One-time Snowflake setup. Run in a Snowsight worksheet as ACCOUNTADMIN.
-- Replace <PUBLIC_KEY> with the body of your public key (the lines between
-- "BEGIN PUBLIC KEY" and "END PUBLIC KEY", joined into one line).
--
-- Creates a least-privilege role, an extra-small warehouse that suspends after 60 seconds,
-- a database the role owns, a key-pair service user (no password), and a resource monitor
-- that suspends the warehouse before it can use up the trial credits.

use role accountadmin;

create role if not exists claims_transformer;
grant role claims_transformer to role sysadmin;

create warehouse if not exists claims_wh
    warehouse_size = xsmall
    auto_suspend = 60
    auto_resume = true
    initially_suspended = true;
grant usage, operate on warehouse claims_wh to role claims_transformer;

create database if not exists claims_warehouse;
grant ownership on database claims_warehouse to role claims_transformer copy current grants;

create user if not exists claims_service
    type = service
    default_role = claims_transformer
    default_warehouse = claims_wh
    rsa_public_key = '<PUBLIC_KEY>';
grant role claims_transformer to user claims_service;

create resource monitor if not exists claims_monitor
    with credit_quota = 20
    triggers on 75 percent do notify
             on 90 percent do suspend
             on 100 percent do suspend_immediate;
alter warehouse claims_wh set resource_monitor = claims_monitor;

-- Your account identifier for SNOWFLAKE_ACCOUNT in .env (format: orgname-accountname).
select current_organization_name() || '-' || current_account_name() as snowflake_account;
