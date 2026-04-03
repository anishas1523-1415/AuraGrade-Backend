-- ============================================================
-- AuraGrade Database Schema
-- Run this in your Supabase SQL Editor (https://supabase.com/dashboard)
-- ============================================================

-- 1. Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. Custom ENUM for professor review status
-- Use DO block because IF NOT EXISTS doesn't work with CREATE TYPE
DO $$ BEGIN
  CREATE TYPE prof_status_enum AS ENUM ('Pending', 'Approved', 'Overridden', 'Flagged', 'Audited');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================
-- Table: students
-- Core student records linked to college register numbers
-- ============================================================
CREATE TABLE IF NOT EXISTS students (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reg_no      TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    email       TEXT,
    course      TEXT DEFAULT 'General',
    dob         DATE,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Index for fast lookups by register number
CREATE INDEX IF NOT EXISTS idx_students_reg_no ON students (reg_no);

-- ============================================================
-- Table: assessments
-- Stores exam metadata and the rubric the AI uses for grading
-- MUST be created BEFORE exception_queue (which references it)
-- ============================================================
CREATE TABLE IF NOT EXISTS assessments (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  subject_id      TEXT,
    subject         TEXT NOT NULL,
  class_id        TEXT,
  semester        TEXT,
  department      TEXT,
  staff_email     TEXT,
    title           TEXT NOT NULL DEFAULT 'Untitled Assessment',
    model_answer    TEXT,
    rubric_json     JSONB DEFAULT '{}'::jsonb,
    is_locked       BOOLEAN DEFAULT false,
    locked_at       TIMESTAMPTZ,
    locked_by       TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- Table: exception_queue
-- Routes unmatched / "ghost" student scripts for manual review
-- Now assessment_id FK will resolve (created above)
-- ============================================================
CREATE TABLE IF NOT EXISTS exception_queue (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    extracted_reg_no TEXT NOT NULL,
    extracted_name   TEXT,
    assessment_id    UUID REFERENCES assessments(id) ON DELETE SET NULL,
    ai_score         FLOAT,
    confidence       FLOAT,
    feedback         JSONB DEFAULT '[]'::jsonb,
    image_url        TEXT,
    reason           TEXT NOT NULL DEFAULT 'Student not found in master roster',
    status           TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING, RESOLVED, REJECTED
    resolved_by      TEXT,
    resolved_at      TIMESTAMPTZ,
    resolution_note  TEXT,
    created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_exception_queue_status ON exception_queue (status);
CREATE INDEX IF NOT EXISTS idx_exception_queue_reg ON exception_queue (extracted_reg_no);

ALTER TABLE exception_queue ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- Table: staff_allocations
-- COE-controlled map of staff_email → subject/class/semester
-- ============================================================
CREATE TABLE IF NOT EXISTS staff_allocations (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  staff_id        UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  staff_email     TEXT NOT NULL,
  subject_id      TEXT NOT NULL,
  class_id        TEXT NOT NULL,
  semester        TEXT NOT NULL,
  department      TEXT,
  is_active       BOOLEAN DEFAULT true,
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_staff_allocations_unique
  ON staff_allocations (staff_email, subject_id, class_id, semester);
CREATE INDEX IF NOT EXISTS idx_staff_allocations_staff ON staff_allocations (staff_id);
CREATE INDEX IF NOT EXISTS idx_staff_allocations_subject ON staff_allocations (subject_id, class_id, semester);

ALTER TABLE staff_allocations ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- Table: grades (The Connector)
-- Links a student + assessment to the AI's grading output
-- ============================================================
CREATE TABLE IF NOT EXISTS grades (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id      UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    assessment_id   UUID NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    ai_score        FLOAT NOT NULL,
    confidence      FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    feedback        JSONB DEFAULT '[]'::jsonb,
    is_flagged      BOOLEAN DEFAULT false,
    prof_status     prof_status_enum DEFAULT 'Pending',
    appeal_reason   TEXT,
    audit_feedback  JSONB,
    audit_score     FLOAT,
    audit_notes     TEXT,
    graded_at       TIMESTAMPTZ DEFAULT now(),
    reviewed_at     TIMESTAMPTZ
);

-- Index for fast lookups per student and assessment
CREATE INDEX IF NOT EXISTS idx_grades_student ON grades (student_id);
CREATE INDEX IF NOT EXISTS idx_grades_assessment ON grades (assessment_id);
CREATE INDEX IF NOT EXISTS idx_grades_status ON grades (prof_status);

-- Unique constraint: one grade per student per assessment
CREATE UNIQUE INDEX IF NOT EXISTS idx_grades_student_assessment ON grades (student_id, assessment_id);

-- ============================================================
-- Row Level Security (RLS) - Optional but recommended
-- ============================================================
ALTER TABLE students ENABLE ROW LEVEL SECURITY;
ALTER TABLE assessments ENABLE ROW LEVEL SECURITY;
ALTER TABLE grades ENABLE ROW LEVEL SECURITY;

-- Removed broad service role policies. Use granular policies below with auth checks.

-- ============================================================
-- Seed Data (Optional - for testing)
-- ============================================================
INSERT INTO students (reg_no, name, email, course) VALUES
    ('AD010', 'A.S. Anish',  'anish@skct.edu.in',  'Data Science'),
    ('AD011', 'Arun',        'arun@skct.edu.in',   'Data Science'),
    ('AD038', 'Vijay',       'vijay@skct.edu.in',   'Data Science'),
    ('AD008', 'Akash',       'akash@skct.edu.in',   'Data Science')
ON CONFLICT (reg_no) DO NOTHING;

INSERT INTO assessments (subject, title, rubric_json) VALUES
    ('AI & Data Science', 'Internal Assessment I', '{
        "conceptual_clarity": {"max_marks": 4, "description": "Does the student understand the core AI concept?"},
        "accuracy": {"max_marks": 4, "description": "Are the formulas/definitions correct?"},
        "presentation": {"max_marks": 2, "description": "Is the logic structured?"}
    }'::jsonb)
ON CONFLICT DO NOTHING;


-- ============================================================
-- Migration: Add Audit columns (run in Supabase SQL Editor)
-- ============================================================
-- If your tables already exist, run these ALTER statements:
--
-- ALTER TYPE prof_status_enum ADD VALUE IF NOT EXISTS 'Audited';
-- ALTER TABLE grades ADD COLUMN IF NOT EXISTS audit_feedback JSONB;
-- ALTER TABLE grades ADD COLUMN IF NOT EXISTS audit_score FLOAT;
-- ALTER TABLE grades ADD COLUMN IF NOT EXISTS audit_notes TEXT;


-- ============================================================
-- INSTITUTIONAL LAYER — RBAC & Tamper-Proof Audit Trail
-- ============================================================

-- 1. Role Enum for institutional access control
DO $$ BEGIN
  CREATE TYPE user_role AS ENUM ('ADMIN_COE', 'HOD_AUDITOR', 'EVALUATOR', 'PROCTOR');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- 2. Profiles table — links Supabase Auth users to institutional roles
CREATE TABLE IF NOT EXISTS profiles (
    id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name   TEXT NOT NULL DEFAULT '',
    email       TEXT,
    department  TEXT,
    role        user_role DEFAULT 'EVALUATOR',
    created_at  TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
-- Removed broad service role policy for profiles. Use granular policies below.

-- 3. Institutional Audit Log — tamper-proof trail of every mark change
CREATE TABLE IF NOT EXISTS audit_logs (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    grade_id    UUID REFERENCES grades(id) ON DELETE SET NULL,
    action      TEXT NOT NULL,              -- 'OVERRIDE', 'APPROVE', 'AUDIT_ADJUST', 'APPEAL_SUBMIT'
    changed_by  TEXT NOT NULL DEFAULT 'system',  -- user id or 'system' / 'ai_audit_agent'
    old_score   FLOAT,
    new_score   FLOAT,
    reason      TEXT NOT NULL,
    metadata    JSONB DEFAULT '{}'::jsonb,   -- extra context (verdict, confidence delta, etc.)
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_grade ON audit_logs (grade_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs (action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs (created_at DESC);

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
-- Removed broad service role policy for audit_logs. Use granular policies below.

-- RLS for grades: Evaluators see only their department's grades
-- (Requires profiles table + auth.uid())
-- CREATE POLICY "Evaluator_Dept_Access" ON grades
-- FOR SELECT USING (
--   auth.uid() IN (SELECT id FROM profiles WHERE role = 'EVALUATOR')
-- );


-- ============================================================
-- Migration: RBAC & Audit Logs (run on existing database)
-- ============================================================
-- CREATE TYPE user_role AS ENUM ('ADMIN_COE', 'HOD_AUDITOR', 'EVALUATOR', 'PROCTOR');
--
-- CREATE TABLE profiles (
--     id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
--     full_name TEXT NOT NULL DEFAULT '',
--     email TEXT,
--     department TEXT,
--     role user_role DEFAULT 'EVALUATOR',
--     created_at TIMESTAMPTZ DEFAULT now()
-- );
--
-- CREATE TABLE audit_logs (
--     id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
--     grade_id UUID REFERENCES grades(id) ON DELETE SET NULL,
--     action TEXT NOT NULL,
--     changed_by TEXT NOT NULL DEFAULT 'system',
--     old_score FLOAT,
--     new_score FLOAT,
--     reason TEXT NOT NULL,
--     metadata JSONB DEFAULT '{}'::jsonb,
--     created_at TIMESTAMPTZ DEFAULT now()
-- );
-- CREATE INDEX idx_audit_logs_grade ON audit_logs (grade_id);
-- CREATE INDEX idx_audit_logs_action ON audit_logs (action);
-- CREATE INDEX idx_audit_logs_created ON audit_logs (created_at DESC);


-- ============================================================
-- ERP EXPORT LAYER — Ledger Hashes & Assessment Locking
-- ============================================================

-- 4. Ledger hash records — digital seal for exported marks
CREATE TABLE IF NOT EXISTS ledger_hashes (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    assessment_id   UUID NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    format          TEXT NOT NULL DEFAULT 'csv',       -- 'csv' or 'xlsx'
    sha256_hash     TEXT NOT NULL,
    record_count    INT NOT NULL DEFAULT 0,
    generated_by    TEXT NOT NULL DEFAULT 'system',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ledger_hashes_assessment ON ledger_hashes (assessment_id);

ALTER TABLE ledger_hashes ENABLE ROW LEVEL SECURITY;
-- Removed broad service role policy for ledger_hashes. Use granular policies below.


-- ============================================================
-- Migration: ERP Export Layer (run on existing database)
-- ============================================================
-- ALTER TABLE assessments ADD COLUMN IF NOT EXISTS is_locked BOOLEAN DEFAULT false;
-- ALTER TABLE assessments ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ;
-- ALTER TABLE assessments ADD COLUMN IF NOT EXISTS locked_by TEXT;
--
-- CREATE TABLE IF NOT EXISTS ledger_hashes (
--     id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
--     assessment_id UUID NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
--     filename TEXT NOT NULL,
--     format TEXT NOT NULL DEFAULT 'csv',
--     sha256_hash TEXT NOT NULL,
--     record_count INT NOT NULL DEFAULT 0,
--     generated_by TEXT NOT NULL DEFAULT 'system',
--     created_at TIMESTAMPTZ DEFAULT now()
-- );
-- CREATE INDEX IF NOT EXISTS idx_ledger_hashes_assessment ON ledger_hashes (assessment_id);


-- ============================================================
-- AUTHENTICATION & ROW-LEVEL SECURITY POLICIES
-- ============================================================

-- Enable RLS on all core tables
ALTER TABLE students ENABLE ROW LEVEL SECURITY;
ALTER TABLE assessments ENABLE ROW LEVEL SECURITY;
ALTER TABLE grades ENABLE ROW LEVEL SECURITY;

-- Students: Authenticated users can read all students
CREATE POLICY "Authenticated read students" ON students
  FOR SELECT USING (auth.role() = 'authenticated');

-- Students: Only ADMIN_COE / HOD_AUDITOR can insert/update/delete
CREATE POLICY "Admin manage students" ON students
  FOR ALL USING (
    auth.uid() IN (SELECT id FROM profiles WHERE role IN ('ADMIN_COE', 'HOD_AUDITOR'))
  );

-- Assessments: All authenticated users can read
CREATE POLICY "Authenticated read assessments" ON assessments
  FOR SELECT USING (auth.role() = 'authenticated');

-- Assessments: Only ADMIN_COE / EVALUATOR can create/update
CREATE POLICY "Staff manage assessments" ON assessments
  FOR ALL USING (
    auth.uid() IN (SELECT id FROM profiles WHERE role IN ('ADMIN_COE', 'EVALUATOR', 'HOD_AUDITOR'))
  );

-- Grades: Evaluators and above can read all grades
CREATE POLICY "Staff read grades" ON grades
  FOR SELECT USING (
    auth.uid() IN (SELECT id FROM profiles WHERE role IN ('ADMIN_COE', 'HOD_AUDITOR', 'EVALUATOR'))
  );

-- Grades: Students can only read their own grades (via student_id link)
-- (Requires the student's auth.uid to match their profiles.id linked to students)
CREATE POLICY "Student read own grades" ON grades
  FOR SELECT USING (
    student_id IN (
      SELECT s.id FROM students s
      JOIN profiles p ON p.email = s.email
      WHERE p.id = auth.uid()
    )
  );

-- Grades: Only EVALUATOR+ can insert/update
CREATE POLICY "Staff manage grades" ON grades
  FOR ALL USING (
    auth.uid() IN (SELECT id FROM profiles WHERE role IN ('ADMIN_COE', 'HOD_AUDITOR', 'EVALUATOR'))
  );

-- Profiles: Users can read their own profile
CREATE POLICY "Users read own profile" ON profiles
  FOR SELECT USING (auth.uid() = id);

-- Profiles: ADMIN_COE can read all profiles (for role management)
CREATE POLICY "Admin read all profiles" ON profiles
  FOR SELECT USING (
    auth.uid() IN (SELECT id FROM profiles WHERE role = 'ADMIN_COE')
  );

-- Profiles: Users can update their own name/department
CREATE POLICY "Users update own profile" ON profiles
  FOR UPDATE USING (auth.uid() = id)
  WITH CHECK (auth.uid() = id);

-- Audit Logs: Only ADMIN_COE / HOD_AUDITOR can read
CREATE POLICY "Admin read audit logs" ON audit_logs
  FOR SELECT USING (
    auth.uid() IN (SELECT id FROM profiles WHERE role IN ('ADMIN_COE', 'HOD_AUDITOR'))
  );

-- Ledger Hashes: Only ADMIN_COE can read
CREATE POLICY "Admin read ledger hashes" ON ledger_hashes
  FOR SELECT USING (
    auth.uid() IN (SELECT id FROM profiles WHERE role = 'ADMIN_COE')
  );

-- ============================================================
-- Mobile Push Tokens (Expo)
-- ============================================================
CREATE TABLE IF NOT EXISTS device_push_tokens (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    push_token  TEXT UNIQUE NOT NULL,
    user_id     UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    email       TEXT,
    role        TEXT NOT NULL DEFAULT 'STUDENT',
    reg_no      TEXT,
    platform    TEXT NOT NULL DEFAULT 'android',
    is_active   BOOLEAN NOT NULL DEFAULT true,
    updated_at  TIMESTAMPTZ DEFAULT now(),
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_device_push_tokens_reg_no ON device_push_tokens (reg_no);
CREATE INDEX IF NOT EXISTS idx_device_push_tokens_user_id ON device_push_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_device_push_tokens_active ON device_push_tokens (is_active);

ALTER TABLE device_push_tokens ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'device_push_tokens'
      AND policyname = 'Users manage own push tokens'
  ) THEN
    CREATE POLICY "Users manage own push tokens" ON device_push_tokens
      FOR ALL USING (auth.uid() = user_id)
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'device_push_tokens'
      AND policyname = 'Admin read push tokens'
  ) THEN
    CREATE POLICY "Admin read push tokens" ON device_push_tokens
      FOR SELECT USING (
        auth.uid() IN (SELECT id FROM profiles WHERE role IN ('ADMIN_COE', 'HOD_AUDITOR'))
      );
  END IF;
END $$;

-- ============================================================
-- Migration: Auth & RLS Policies (run on existing database)
-- ============================================================
-- Copy the RLS section above and run it in Supabase SQL Editor.
-- NOTE: The anon key should NOT have broad access.
-- The service_role key (used by backend) bypasses RLS entirely.
