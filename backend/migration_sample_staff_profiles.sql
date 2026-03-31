-- ============================================================
-- Migration: Sample Staff Profiles (Upsert-Safe)
-- AuraGrade
-- ============================================================
-- Purpose:
-- 1) Seed sample staff roster (ADMIN/HOD/EVALUATOR/PROCTOR)
-- 2) Upsert into profiles table by matching auth.users email
-- 3) Show which emails are missing from auth.users
--
-- Run this in Supabase SQL Editor after creating auth users.

WITH staff_seed(email, full_name, department, role) AS (
  VALUES
    ('coe.admin@skct.edu.in',     'Dr. Meenakshi R',    'COE',         'ADMIN_COE'),
    ('hod.ds@skct.edu.in',        'Dr. Karthikeyan P',  'Data Science','HOD_AUDITOR'),
    ('eval.ds1@skct.edu.in',      'Prof. Harini S',     'Data Science','EVALUATOR'),
    ('eval.ds2@skct.edu.in',      'Prof. Vignesh K',    'Data Science','EVALUATOR'),
    ('eval.cse1@skct.edu.in',     'Prof. Nivetha M',    'CSE',         'EVALUATOR'),
    ('proctor.main@skct.edu.in',  'Mr. Aravind T',      'COE',         'PROCTOR'),
    ('audit.hod@skct.edu.in',     'Dr. Sharmila V',     'AI&DS',       'HOD_AUDITOR'),
    ('exam.cell@skct.edu.in',     'Ms. Priya R',        'COE',         'ADMIN_COE')
),
matched_users AS (
  SELECT
    u.id,
    s.email,
    s.full_name,
    s.department,
    s.role
  FROM auth.users u
  INNER JOIN staff_seed s
    ON lower(u.email) = lower(s.email)
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

-- ============================================================
-- Verification 1: Seeded/Updated staff profiles
-- ============================================================
SELECT id, full_name, email, department, role, created_at
FROM profiles
WHERE lower(email) IN (
  'coe.admin@skct.edu.in',
  'hod.ds@skct.edu.in',
  'eval.ds1@skct.edu.in',
  'eval.ds2@skct.edu.in',
  'eval.cse1@skct.edu.in',
  'proctor.main@skct.edu.in',
  'audit.hod@skct.edu.in',
  'exam.cell@skct.edu.in'
)
ORDER BY role, full_name;

-- ============================================================
-- Verification 2: Missing auth users (create these accounts first)
-- ============================================================
WITH staff_seed(email, full_name, department, role) AS (
  VALUES
    ('coe.admin@skct.edu.in',     'Dr. Meenakshi R',    'COE',         'ADMIN_COE'),
    ('hod.ds@skct.edu.in',        'Dr. Karthikeyan P',  'Data Science','HOD_AUDITOR'),
    ('eval.ds1@skct.edu.in',      'Prof. Harini S',     'Data Science','EVALUATOR'),
    ('eval.ds2@skct.edu.in',      'Prof. Vignesh K',    'Data Science','EVALUATOR'),
    ('eval.cse1@skct.edu.in',     'Prof. Nivetha M',    'CSE',         'EVALUATOR'),
    ('proctor.main@skct.edu.in',  'Mr. Aravind T',      'COE',         'PROCTOR'),
    ('audit.hod@skct.edu.in',     'Dr. Sharmila V',     'AI&DS',       'HOD_AUDITOR'),
    ('exam.cell@skct.edu.in',     'Ms. Priya R',        'COE',         'ADMIN_COE')
)
SELECT s.*
FROM staff_seed s
LEFT JOIN auth.users u
  ON lower(u.email) = lower(s.email)
WHERE u.id IS NULL
ORDER BY s.role, s.full_name;
