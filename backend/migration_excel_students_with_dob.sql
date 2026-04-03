-- ============================================================
-- Migration: Insert 63 Students from Excel DB
-- AuraGrade student DB1.xlsx
-- ============================================================
-- This migration syncs students from the Excel file
-- Date of birth + exact XLS gmail IDs included

INSERT INTO students (reg_no, name, email, dob, course)
VALUES
  ('23TUAD001', 'AATHITHIYA S U', '727823tuad001@skct.edu.in', '2005-10-26', 'Data Science'),
  ('23TUAD002', 'AKIL SARAVANAN K', '727823tuad002@skct.edu.in', '2005-07-10', 'Data Science'),
  ('23TUAD003', 'AKILESH D', '727823tuad003@skct.edu.in', '2005-11-18', 'Data Science'),
  ('23TUAD004', 'ALANSHO.J', '727823tuad004@skct.edu.in', '2005-04-29', 'Data Science'),
  ('23TUAD005', 'ALLEN WILKINS T', '727823tuad005@skct.edu.in', '2006-05-07', 'Data Science'),
  ('23TUAD006', 'ANAND V B', '727823tuad006@skct.edu.in', '2006-04-07', 'Data Science'),
  ('23TUAD007', 'ANANIAS REMO A', '727823tuad007@skct.edu.in', '2006-04-19', 'Data Science'),
  ('23TUAD008', 'ANBARASU S', '727823tuad008@skct.edu.in', '2005-12-14', 'Data Science'),
  ('23TUAD009', 'ANBUSELVAN S', '727823tuad009@skct.edu.in', '2005-09-24', 'Data Science'),
  ('23TUAD010', 'ANISH A S', '727823tuad010@skct.edu.in', '2005-09-15', 'Data Science'),
  ('23TUAD011', 'ANUSHALAKSHMI S', '727823tuad011@skct.edu.in', '2005-09-09', 'Data Science'),
  ('23TUAD012', 'ASHWIN S', '727823tuad012@skct.edu.in', '2006-11-07', 'Data Science'),
  ('23TUAD013', 'ASHWITA K', '727823tuad013@skct.edu.in', '2006-02-11', 'Data Science'),
  ('23TUAD014', 'BALA SANKAR S', '727823tuad014@skct.edu.in', '2005-07-10', 'Data Science'),
  ('23TUAD015', 'BALAJI S', '727823tuad015@skct.edu.in', '2004-07-31', 'Data Science'),
  ('23TUAD016', 'BANUMATHI M', '727823tuad016@skct.edu.in', '2003-06-30', 'Data Science'),
  ('23TUAD017', 'BIRUNDHA M S', '727823tuad017@skct.edu.in', '2005-07-24', 'Data Science'),
  ('23TUAD018', 'BOOMIKA T', '727823tuad018@skct.edu.in', '2006-01-20', 'Data Science'),
  ('23TUAD019', 'DARANEESH B', '727823tuad019@skct.edu.in', '2005-05-04', 'Data Science'),
  ('23TUAD020', 'DEEPAKKUMARAN V S', '727823tuad020@skct.edu.in', '2005-08-13', 'Data Science'),
  ('23TUAD021', 'DHAMODHAR P', '727823tuad021@skct.edu.in', '2005-09-08', 'Data Science'),
  ('23TUAD022', 'DHANASEKAR B', '727823tuad022@skct.edu.in', '2006-03-18', 'Data Science'),
  ('23TUAD023', 'DHANU SREE. P', '727823tuad023@skct.edu.in', '2005-11-12', 'Data Science'),
  ('23TUAD024', 'DHANUSH KUMAR K', '727823tuad024@skct.edu.in', '2004-04-07', 'Data Science'),
  ('23TUAD025', 'DHARINEESH T K', '727823tuad025@skct.edu.in', '2006-02-15', 'Data Science'),
  ('23TUAD026', 'DHARSHINI M', '727823tuad026@skct.edu.in', '2005-10-15', 'Data Science'),
  ('23TUAD027', 'DHARSHNI D', '727823tuad027@skct.edu.in', '2005-10-05', 'Data Science'),
  ('23TUAD028', 'DHIVAGAR V', '727823tuad028@skct.edu.in', '2006-03-01', 'Data Science'),
  ('23TUAD029', 'DINESHKUMAR N', '727823tuad029@skct.edu.in', '2005-08-08', 'Data Science'),
  ('23TUAD030', 'DIVYA DHARSHINI . N', '727823tuad030@skct.edu.in', '2006-03-19', 'Data Science'),
  ('23TUAD031', 'ELANGOVAN M', '727823tuad031@skct.edu.in', '2006-08-05', 'Data Science'),
  ('23TUAD032', 'GOKUL K 03.08.2005', '727823tuad032@skct.edu.in', '2005-08-03', 'Data Science'),
  ('23TUAD033', 'GOKUL K 12.10.2005', '727823tuad033@skct.edu.in', '2005-10-12', 'Data Science'),
  ('23TUAD034', 'GOKULKRISHNAN M', '727823tuad034@skct.edu.in', '2005-10-24', 'Data Science'),
  ('23TUAD035', 'HAREES AHAMED K', '727823tuad035@skct.edu.in', '2005-05-24', 'Data Science'),
  ('23TUAD036', 'HARISH RAGHAVENDRAA G', '727823tuad036@skct.edu.in', '2006-04-03', 'Data Science'),
  ('23TUAD037', 'HARISH S', '727823tuad037@skct.edu.in', '2006-01-13', 'Data Science'),
  ('23TUAD038', 'HAVISHKUMAR S', '727823tuad038@skct.edu.in', '2006-07-25', 'Data Science'),
  ('23TUAD039', 'HEERA MOHAMED A M', '727823tuad039@skct.edu.in', '2006-03-09', 'Data Science'),
  ('23TUAD040', 'JOTHI KRITHICK ROSHAN S', '727823tuad040@skct.edu.in', '2006-04-23', 'Data Science'),
  ('23TUAD041', 'KALKI S', '727823tuad041@skct.edu.in', '2005-12-17', 'Data Science'),
  ('23TUAD042', 'KANISHKAR P', '727823tuad042@skct.edu.in', '2003-04-08', 'Data Science'),
  ('23TUAD043', 'KARTHIK RAJA A', '727823tuad043@skct.edu.in', '2006-03-22', 'Data Science'),
  ('23TUAD044', 'KARTHIKEYAN V S', '727823tuad044@skct.edu.in', '2005-09-25', 'Data Science'),
  ('23TUAD045', 'KAVIBHARATHI G', '727823tuad045@skct.edu.in', '2005-12-07', 'Data Science'),
  ('23TUAD046', 'KAVIN KUMAR.M', '727823tuad046@skct.edu.in', '2005-04-14', 'Data Science'),
  ('23TUAD047', 'KAVIYA S', '727823tuad047@skct.edu.in', '2005-09-26', 'Data Science'),
  ('23TUAD048', 'KIRUTHI SWETHA. S', '727823tuad048@skct.edu.in', '2005-10-13', 'Data Science'),
  ('23TUAD049', 'KOWSALYA B', '727823tuad049@skct.edu.in', '2005-08-31', 'Data Science'),
  ('23TUAD050', 'KRITHICK BALA B', '727823tuad050@skct.edu.in', '2006-03-07', 'Data Science'),
  ('23TUAD051', 'LAVANYA N', '727823tuad051@skct.edu.in', '2005-08-21', 'Data Science'),
  ('23TUAD052', 'LOGAKEERTHI SOMU', '727823tuad052@skct.edu.in', '2005-09-21', 'Data Science'),
  ('23TUAD053', 'LOKESH T', '727823tuad053@skct.edu.in', '2006-09-11', 'Data Science'),
  ('23TUAD054', 'MAHA SHREE P', '727823tuad054@skct.edu.in', '2005-03-06', 'Data Science'),
  ('23TUAD055', 'MANOJ BALAJI T', '727823tuad055@skct.edu.in', '2005-03-23', 'Data Science'),
  ('23TUAD056', 'MITHILESH ES', '727823tuad056@skct.edu.in', '2005-11-23', 'Data Science'),
  ('23TUAD057', 'MOHAMED SABEER M', '727823tuad057@skct.edu.in', '2005-02-25', 'Data Science'),
  ('23TUAD058', 'MOHANA A', '727823tuad058@skct.edu.in', '2005-12-22', 'Data Science'),
  ('23TUAD059', 'MOHANAPRIYAN M', '727823tuad059@skct.edu.in', '2006-01-18', 'Data Science'),
  ('23TUAD060', 'MANOJ BBOOPATHI G R', '727823tuad060@skct.edu.in', '2005-11-24', 'Data Science'),
  ('23TUAD061', 'DIVITH L', '23tuad061@example.edu', '2004-12-10', 'Data Science'),
  ('23TUAD062', 'KAMAL S', '23tuad062@example.edu', '2006-01-03', 'Data Science'),
  ('23TUAD063', 'MOHANRAMU M', '23tuad063@example.edu', '2002-11-28', 'Data Science')
ON CONFLICT (reg_no) DO UPDATE SET
  name = EXCLUDED.name,
  email = COALESCE(EXCLUDED.email, students.email),
  dob = EXCLUDED.dob,
  course = EXCLUDED.course;


-- Verify insertion
SELECT COUNT(*) as total_students FROM students;