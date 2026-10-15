-- ==============================================================================
-- QueryPilot Production Role & Database Setup for Neon Serverless PostgreSQL
--
-- RUN INSTRUCTIONS:
-- Connect to your Neon cluster using the default admin role (neondb_owner):
-- psql "postgresql://neondb_owner:PASSWORD@ep-xyz.neon.tech/neondb?sslmode=require" -f docker/production/setup_roles.sql
-- ==============================================================================

\echo '--- 1. Creating logical databases in Neon cluster ---'

-- Create querypilot_app database
SELECT 'CREATE DATABASE querypilot_app'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'querypilot_app')\gexec

-- Create sample_shop database
SELECT 'CREATE DATABASE sample_shop'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sample_shop')\gexec

\echo '--- 2. Creating isolated database roles with strong passwords ---'
-- REPLACE THESE PLACEHOLDER PASSWORDS BEFORE EXECUTING!
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_rw') THEN
        CREATE ROLE app_rw WITH LOGIN PASSWORD 'REPLACE_WITH_STRONG_APP_RW_PASS';
    END IF;

    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'readonly_user') THEN
        CREATE ROLE readonly_user WITH LOGIN PASSWORD 'REPLACE_WITH_STRONG_READONLY_PASS';
    END IF;
END
$$;

\echo '--- 3. Configuring role-level defaults and safeguards ---'
-- Enforce read-only transaction mode and statement timeout at the role level
ALTER ROLE readonly_user SET default_transaction_read_only = on;
ALTER ROLE readonly_user SET statement_timeout = '5s';
ALTER ROLE readonly_user CONNECTION LIMIT 20;

-- Database connection privileges
REVOKE CONNECT ON DATABASE querypilot_app FROM PUBLIC;
GRANT CONNECT ON DATABASE querypilot_app TO app_rw;
GRANT ALL PRIVILEGES ON DATABASE querypilot_app TO app_rw;

REVOKE ALL ON DATABASE sample_shop FROM readonly_user;
GRANT CONNECT ON DATABASE sample_shop TO readonly_user;

\echo '--- 4. Configuring permissions inside querypilot_app ---'
\c querypilot_app

GRANT ALL ON SCHEMA public TO app_rw;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO app_rw;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO app_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO app_rw;

\echo '--- 5. Configuring permissions inside sample_shop ---'
\c sample_shop

-- Strict read-only permissions for readonly_user on sample_shop
REVOKE CREATE ON SCHEMA public FROM readonly_user;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;

-- Revoke dangerous utility functions
REVOKE EXECUTE ON FUNCTION pg_sleep(double precision) FROM PUBLIC, readonly_user;

\echo 'QueryPilot production roles and permissions configured successfully.'

