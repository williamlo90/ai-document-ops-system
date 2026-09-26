-- Runtime repositories record compatibility migrations without a display name.
ALTER TABLE schema_migrations ALTER COLUMN name SET DEFAULT '';
