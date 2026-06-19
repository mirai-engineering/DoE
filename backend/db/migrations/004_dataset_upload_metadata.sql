-- Add upload integrity metadata expected by data-intake runtime writes.
-- Existing Railway databases may have datasets from 002 before these columns existed.

BEGIN;

ALTER TABLE datasets
    ADD COLUMN IF NOT EXISTS sha256 text,
    ADD COLUMN IF NOT EXISTS size_bytes bigint;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'datasets_size_bytes_nonnegative'
          AND conrelid = 'datasets'::regclass
    ) THEN
        ALTER TABLE datasets
            ADD CONSTRAINT datasets_size_bytes_nonnegative
            CHECK (size_bytes IS NULL OR size_bytes >= 0);
    END IF;
END $$;

COMMIT;
