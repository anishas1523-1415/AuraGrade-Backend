-- ============================================================
-- AuraGrade — Real Staff Role + Allocation Seed
-- Run this in Supabase SQL Editor after schema.sql and rls_gap_remediation.sql
-- ============================================================

-- Notes:
-- 1) Ensure these emails already exist in auth.users (created via Supabase Auth).
-- 2) Update the VALUES blocks below with your institution's real staff records.
-- 3) Re-running this script is safe (upsert + conflict handling).

BEGIN;

-- ------------------------------------------------------------
-- Ensure the allocation table exists before seeding it
-- ------------------------------------------------------------
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

-- ------------------------------------------------------------
-- A) Real staff role mapping into profiles
-- ------------------------------------------------------------
WITH role_seed(email, full_name, department, role) AS (
  VALUES
    ('coe.admin@skct.edu.in',    'Dr. Meenakshi R',   'COE',          'ADMIN_COE'),
    ('hod.ds@skct.edu.in',       'Dr. Karthikeyan P', 'Data Science', 'HOD_AUDITOR'),
    ('lovelyking1415@gmail.com',  'Lovely King',       'Data Science', 'EVALUATOR'),
    ('eval.ds1@skct.edu.in',     'Prof. Harini S',    'Data Science', 'EVALUATOR'),
    ('eval.ds2@skct.edu.in',     'Prof. Vignesh K',   'Data Science', 'EVALUATOR'),
    ('proctor.main@skct.edu.in', 'Mr. Aravind T',     'COE',          'PROCTOR')
),
matched_users AS (
  SELECT
    u.id,
    r.email,
    r.full_name,
    r.department,
    r.role
  FROM auth.users u
  INNER JOIN role_seed r
    ON lower(u.email) = lower(r.email)
)
INSERT INTO profiles (id, full_name, email, department, role)
SELECT
  m.id,
  m.full_name,
  m.email,
  m.department,
  m.role::user_role
FROM matched_users m
ON CONFLICT (id) DO UPDATE SET
  full_name = EXCLUDED.full_name,
  email = EXCLUDED.email,
  department = EXCLUDED.department,
  role = EXCLUDED.role;


-- ------------------------------------------------------------
-- B) Real evaluator subject/class/semester allocations
-- ------------------------------------------------------------
WITH allocation_seed(staff_email, subject_id, class_id, semester, department) AS (
  VALUES
    ('lovelyking1415@gmail.com', 'AIDS-IA1-UNIT1', 'AIDS-A', '3', 'Data Science'),
    ('eval.ds1@skct.edu.in', 'AIDS-IA1-UNIT1', 'AIDS-A', '3', 'Data Science'),
    ('eval.ds1@skct.edu.in', 'AIDS-IA1-UNIT2', 'AIDS-A', '3', 'Data Science'),
    ('eval.ds2@skct.edu.in', 'AIDS-IA1-UNIT1', 'AIDS-B', '3', 'Data Science'),
    ('eval.ds2@skct.edu.in', 'AIDS-IA1-UNIT2', 'AIDS-B', '3', 'Data Science')
),
resolved AS (
  SELECT
    p.id AS staff_id,
    p.email AS staff_email,
    a.subject_id,
    a.class_id,
    a.semester,
    a.department
  FROM allocation_seed a
  INNER JOIN profiles p
    ON lower(p.email) = lower(a.staff_email)
)
INSERT INTO staff_allocations (
  staff_id,
  staff_email,
  subject_id,
  class_id,
  semester,
  department,
  is_active,
  updated_at
)
SELECT
  r.staff_id,
  r.staff_email,
  r.subject_id,
  r.class_id,
  r.semester,
  r.department,
  true,
  now()
FROM resolved r
ON CONFLICT (staff_email, subject_id, class_id, semester)
DO UPDATE SET
  staff_id = EXCLUDED.staff_id,
  department = EXCLUDED.department,
  is_active = true,
  updated_at = now();

COMMIT;


-- ------------------------------------------------------------
-- Verification 1: role mappings present in profiles
-- ------------------------------------------------------------
SELECT
  p.id,
  p.full_name,
  p.email,
  p.department,
  p.role,
  p.created_at
FROM profiles p
WHERE lower(p.email) IN (
  'coe.admin@skct.edu.in',
  'hod.ds@skct.edu.in',
  'eval.ds1@skct.edu.in',
  'eval.ds2@skct.edu.in',
  'proctor.main@skct.edu.in'
)
ORDER BY p.role, p.full_name;


-- ------------------------------------------------------------
-- Verification 2: allocation mappings present
-- ------------------------------------------------------------
SELECT
  sa.staff_email,
  sa.subject_id,
  sa.class_id,
  sa.semester,
  sa.department,
  sa.is_active,
  sa.created_at,
  sa.updated_at
FROM staff_allocations sa
WHERE lower(sa.staff_email) IN (
  'eval.ds1@skct.edu.in',
  'eval.ds2@skct.edu.in'
)
ORDER BY sa.staff_email, sa.subject_id, sa.class_id, sa.semester;


-- ------------------------------------------------------------
-- Verification 3: missing auth users (create these in Auth first)
-- ------------------------------------------------------------
WITH role_seed(email, full_name, department, role) AS (
  VALUES
    ('coe.admin@skct.edu.in',    'Dr. Meenakshi R',   'COE',          'ADMIN_COE'),
    ('hod.ds@skct.edu.in',       'Dr. Karthikeyan P', 'Data Science', 'HOD_AUDITOR'),
    ('lovelyking1415@gmail.com',  'Lovely King',       'Data Science', 'EVALUATOR'),
    ('eval.ds1@skct.edu.in',     'Prof. Harini S',    'Data Science', 'EVALUATOR'),
    ('eval.ds2@skct.edu.in',     'Prof. Vignesh K',   'Data Science', 'EVALUATOR'),
    ('proctor.main@skct.edu.in', 'Mr. Aravind T',     'COE',          'PROCTOR')
)
SELECT r.*
FROM role_seed r
LEFT JOIN auth.users u
  ON lower(u.email) = lower(r.email)
WHERE u.id IS NULL
ORDER BY r.role, r.full_name;
