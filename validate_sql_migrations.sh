#!/bin/bash
# SQL Migration Validation Script
# Tests schema.sql, rls_gap_remediation.sql, batch_jobs_migration.sql for issues

echo "========================================="
echo "AuraGrade SQL Migration Validator"
echo "========================================="
echo

# Check 1: Verify all SQL files exist
echo "✓ Checking SQL files exist..."
if [ -f "backend/schema.sql" ] && [ -f "backend/rls_gap_remediation.sql" ] && [ -f "backend/batch_jobs_migration.sql" ]; then
    echo "  ✓ All 3 SQL files present"
else
    echo "  ✗ Missing SQL files"
    exit 1
fi
echo

# Check 2: Verify schema.sql table creation order
echo "✓ Checking schema.sql table creation order..."
tables=$(grep "^CREATE TABLE" backend/schema.sql | grep -v "IF NOT EXISTS")
student_line=$(grep -n "CREATE TABLE students" backend/schema.sql | cut -d: -f1)
assessment_line=$(grep -n "CREATE TABLE assessments" backend/schema.sql | cut -d: -f1)
exception_line=$(grep -n "CREATE TABLE exception_queue" backend/schema.sql | cut -d: -f1)
grades_line=$(grep -n "CREATE TABLE grades" backend/schema.sql | cut -d: -f1)

if [ "$assessment_line" -lt "$exception_line" ] && [ "$exception_line" -lt "$grades_line" ]; then
    echo "  ✓ Table creation order correct:"
    echo "    - students (line $student_line)"
    echo "    - assessments (line $assessment_line) <- BEFORE exception_queue"
    echo "    - exception_queue (line $exception_line) <- Can safely reference assessments"
    echo "    - grades (line $grades_line)"
else
    echo "  ✗ Table creation order WRONG"
    echo "    assessments must come before exception_queue"
    exit 1
fi
echo

# Check 3: Verify ENUM IF NOT EXISTS
echo "✓ Checking ENUM type declarations..."
prof_enum=$(grep "CREATE TYPE.*prof_status_enum" backend/schema.sql)
user_enum=$(grep "CREATE TYPE.*user_role" backend/schema.sql)

if echo "$prof_enum" | grep -q "IF NOT EXISTS"; then
    echo "  ✓ prof_status_enum has IF NOT EXISTS"
else
    echo "  ✗ prof_status_enum missing IF NOT EXISTS"
    exit 1
fi

if echo "$user_enum" | grep -q "IF NOT EXISTS"; then
    echo "  ✓ user_role has IF NOT EXISTS"
else
    echo "  ✗ user_role missing IF NOT EXISTS"
    exit 1
fi
echo

# Check 4: Verify RLS tables have policies
echo "✓ Checking RLS policy files..."
if grep -q "CREATE POLICY" backend/rls_gap_remediation.sql; then
    policy_count=$(grep -c "CREATE POLICY" backend/rls_gap_remediation.sql)
    echo "  ✓ rls_gap_remediation.sql contains $policy_count RLS policies"
else
    echo "  ✗ rls_gap_remediation.sql missing RLS policies"
    exit 1
fi
echo

# Check 5: Verify batch_jobs migration
echo "✓ Checking batch_jobs_migration.sql..."
if grep -q "CREATE TABLE.*batch_jobs" backend/batch_jobs_migration.sql; then
    echo "  ✓ batch_jobs table definition present"
else
    echo "  ✗ batch_jobs table definition missing"
    exit 1
fi

if grep -q "CREATE POLICY" backend/batch_jobs_migration.sql; then
    echo "  ✓ RLS policies present for batch_jobs"
else
    echo "  ✗ RLS policies missing for batch_jobs"
    exit 1
fi
echo

echo "========================================="
echo "✓ ALL VALIDATION CHECKS PASSED"
echo "========================================="
echo
echo "SQL migrations are ready for deployment:"
echo "1. Run: backend/schema.sql"
echo "2. Run: backend/rls_gap_remediation.sql"
echo "3. Run: backend/batch_jobs_migration.sql"
echo
echo "Time to execute: ~5 minutes in Supabase"
