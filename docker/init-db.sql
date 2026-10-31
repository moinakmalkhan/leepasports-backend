-- Runs once when the Postgres volume is created. Extensions are also created by
-- the catalog migration, but having them here lets `make psql` use them immediately.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
