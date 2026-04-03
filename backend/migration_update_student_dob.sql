-- ============================================================
-- Migration: Update Student DOB Records
-- Add DOB for ANISH, VIJAY, AKASH and leave some without DOB
-- ============================================================

-- Update ANISH A S with DOB
UPDATE students 
SET dob = '2005-09-15'
WHERE reg_no = '23TUAD010' AND name = 'ANISH A S';

-- Add DOB for VIJAY (AD038)
UPDATE students 
SET dob = '2005-08-12'
WHERE reg_no = 'AD038' AND name = 'Vijay';

-- Add DOB for AKASH (AD008)
UPDATE students 
SET dob = '2005-11-20'
WHERE reg_no = 'AD008' AND name = 'Akash';

-- Verify the updates
SELECT reg_no, name, dob FROM students 
WHERE reg_no IN ('23TUAD010', 'AD038', 'AD008')
ORDER BY reg_no;

-- Show students without DOB (sample)
SELECT COUNT(*) as students_without_dob FROM students WHERE dob IS NULL;
