#!/usr/bin/env bash
set -e

# Ensure passwords are provided
if [ -z "$APP_RW_PASSWORD" ] || [ -z "$READONLY_PASSWORD" ]; then
    echo "ERROR: APP_RW_PASSWORD and READONLY_PASSWORD environment variables must be set!"
    exit 1
fi

echo "Initializing QueryPilot databases and roles..."

# Create databases and roles in the default postgres database
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create databases if not existing
    SELECT 'CREATE DATABASE querypilot_app'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'querypilot_app')\gexec

    SELECT 'CREATE DATABASE sample_shop'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sample_shop')\gexec

    -- Create or update roles with environment variable passwords
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_rw') THEN
            CREATE ROLE app_rw WITH LOGIN PASSWORD '$APP_RW_PASSWORD';
        ELSE
            ALTER ROLE app_rw WITH PASSWORD '$APP_RW_PASSWORD';
        END IF;

        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'readonly_user') THEN
            CREATE ROLE readonly_user WITH LOGIN PASSWORD '$READONLY_PASSWORD';
        ELSE
            ALTER ROLE readonly_user WITH PASSWORD '$READONLY_PASSWORD';
        END IF;
    END
    \$\$;

    -- Database connection privileges
    REVOKE CONNECT ON DATABASE querypilot_app FROM PUBLIC;
    GRANT CONNECT ON DATABASE querypilot_app TO app_rw;
    GRANT ALL PRIVILEGES ON DATABASE querypilot_app TO app_rw;

    GRANT CONNECT ON DATABASE sample_shop TO readonly_user;
EOSQL

# Grant permissions within querypilot_app
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "querypilot_app" <<-EOSQL
    GRANT ALL ON SCHEMA public TO app_rw;
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO app_rw;
    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO app_rw;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO app_rw;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO app_rw;
EOSQL

# Ensure readonly_user has no write access anywhere on sample_shop
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "sample_shop" <<-EOSQL
    REVOKE CREATE ON SCHEMA public FROM readonly_user;
    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM readonly_user;
EOSQL

echo "Database and role initialization completed successfully."
