-- ============================================================
-- AuraGrade Migration: Student Master Roster + Exception Queue
-- Run this in your Supabase SQL Editor
-- ============================================================

-- 1. Add 'course' column to students table (if not already present)
ALTER TABLE students ADD COLUMN IF NOT EXISTS course TEXT DEFAULT 'General';

-- 2. Clear old test data & insert the SKCT Master Roster
DELETE FROM students;

INSERT INTO students (reg_no, name, email, course) VALUES
    ('AD010', 'A.S. Anish',  'anish@skct.edu.in',  'Data Science'),
    ('AD011', 'Arun',        'arun@skct.edu.in',   'Data Science'),
    ('AD038', 'Vijay',       'vijay@skct.edu.in',   'Data Science'),
    ('AD008', 'Akash',       'akash@skct.edu.in',   'Data Science');

-- 3. Create the Exception Queue table (Ghost Student Dashboard)
CREATE TABLE IF NOT EXISTS exception_queue (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    extracted_reg_no TEXT NOT NULL,
    extracted_name   TEXT,
    assessment_id    UUID REFERENCES assessments(id) ON DELETE SET NULL,
    ai_score         FLOAT,
    confidence       FLOAT,
    feedback         JSONB DEFAULT '[]'::jsonb,
    image_url        TEXT,
    reason           TEXT NOT NULL DEFAULT 'Student not found in master roster',
    status           TEXT NOT NULL DEFAULT 'PENDING',   -- PENDING | RESOLVED | REJECTED
    resolved_by      TEXT,
    resolved_at      TIMESTAMPTZ,
    resolution_note  TEXT,
    created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_exception_queue_status ON exception_queue (status);
CREATE INDEX IF NOT EXISTS idx_exception_queue_reg ON exception_queue (extracted_reg_no);

ALTER TABLE exception_queue ENABLE ROW LEVEL SECURITY;

-- RLS: Only ADMIN_COE / HOD_AUDITOR / EVALUATOR can access exception_queue
CREATE POLICY "Staff manage exceptions" ON exception_queue
  FOR ALL USING (
    auth.uid() IN (SELECT id FROM profiles WHERE role IN ('ADMIN_COE', 'HOD_AUDITOR', 'EVALUATOR'))
  );

-- 4. Verify the roster
SELECT reg_no, name, course FROM students ORDER BY reg_no;
