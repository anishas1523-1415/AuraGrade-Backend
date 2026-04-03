-- ============================================================
-- COE Portal Schema
-- Dedicated login + staff management for COE office members
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS coe_office_members (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name       TEXT NOT NULL,
    dob             DATE NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'ADMIN_COE' CHECK (role IN ('ADMIN_COE')),
        designation     TEXT,
    department      TEXT,
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE coe_office_members
    ADD COLUMN IF NOT EXISTS designation TEXT;

CREATE TABLE IF NOT EXISTS coe_staff_profiles (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name       TEXT NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('EVALUATOR', 'HOD_AUDITOR')),
    subjects        JSONB NOT NULL DEFAULT '[]'::jsonb,
    departments     JSONB NOT NULL DEFAULT '[]'::jsonb,
    years           JSONB NOT NULL DEFAULT '[]'::jsonb,
    password_hash   TEXT NOT NULL,
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_coe_office_members_email ON coe_office_members (email);
CREATE INDEX IF NOT EXISTS idx_coe_staff_profiles_email ON coe_staff_profiles (email);
CREATE INDEX IF NOT EXISTS idx_coe_staff_profiles_role ON coe_staff_profiles (role);

ALTER TABLE coe_office_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE coe_staff_profiles ENABLE ROW LEVEL SECURITY;

-- Service-role backend access bypasses RLS in Supabase, but we keep the tables
-- locked down for any future direct client access.
DO $$ BEGIN
    CREATE POLICY coe_office_members_service_role_only
    ON coe_office_members
    FOR ALL
    USING (false)
    WITH CHECK (false);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY coe_staff_profiles_service_role_only
    ON coe_staff_profiles
    FOR ALL
    USING (false)
    WITH CHECK (false);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
