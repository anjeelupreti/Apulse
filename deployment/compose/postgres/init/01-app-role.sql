-- The application connects as a NON-superuser without BYPASSRLS so row-level security
-- is enforced in development and tests exactly as in production.
-- CREATEDB is granted only so the test runner can create test databases.
CREATE ROLE npms_app LOGIN PASSWORD 'npms_app' NOSUPERUSER NOCREATEROLE CREATEDB NOBYPASSRLS;
ALTER DATABASE npms OWNER TO npms_app;
