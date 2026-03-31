# Step 1: Database Migrations (5 minutes)

## Overview
This step fixes critical RLS policy gaps and adds persistent batch job storage. **Must be completed before running the backend.**

## ⚠️ CRITICAL: Prerequisite First

### File 0: `schema.sql` (MUST RUN FIRST)
**Location:** `backend/schema.sql`

This creates all the base tables (users, profiles, assessments, audit_logs, exception_queue, etc.) that rls_gap_remediation.sql depends on.

**Status:** Safe to run (uses `CREATE TABLE IF NOT EXISTS`)

---

## Files to Run in Supabase SQL Editor (In Order)

### File 1: `rls_gap_remediation.sql` 
**Location:** `backend/rls_gap_remediation.sql`

**What it fixes:**
- **GAP 1:** `exception_queue` table had RLS enabled but ZERO policies
  - Backend writes were silently failing
  - Adds 3 policies: staff read, staff update, backend insert
  
- **GAP 2:** `audit_logs` table had no INSERT policy
  - Prevents backend from logging audit events
  - Adds policy allowing service_role (backend) to insert
  
- **GAP 3:** `students` and `assessments` readable by any authenticated user
  - Should be role-based (EVALUATOR, ADMIN_COE only)
  - Adds proper RLS policies with role checks

**Status:** Idempotent — uses `IF NOT EXISTS` checks, safe to run multiple times

---

### File 2: `batch_jobs_migration.sql`
**Location:** `backend/batch_jobs_migration.sql`

**What it does:**
- Creates `batch_jobs` table to replace in-memory `_batch_jobs` dict in `main.py`
- Enables persistent state tracking across server restarts
- Supports multi-worker/container deployments
- Includes 4 indexes for fast queries
- Applies RLS: users see only own jobs, staff see all

**Status:** Safe — uses `CREATE TABLE IF NOT EXISTS`

---

## Execution Steps (In Exact Order)

1. **Log in to Supabase Dashboard**
   - Go to your project → SQL Editor

2. **Run File 0: Paste `schema.sql`** (Database structure)
   - Copy entire contents from `backend/schema.sql`
   - Paste into Supabase SQL Editor
   - Click **Run**
   - ✅ Expected: "Success" — creates all base tables

3. **Run File 1: Paste `rls_gap_remediation.sql`** (Security policies)
   - Copy entire contents from `backend/rls_gap_remediation.sql`
   - Paste into Supabase SQL Editor
   - Click **Run**
   - ✅ Expected: "Success" (no errors)

4. **Run File 2: Paste `batch_jobs_migration.sql`** (Persistent job tracking)
   - Copy entire contents from `backend/batch_jobs_migration.sql`
   - Paste into Supabase SQL Editor
   - Click **Run**
   - ✅ Expected: "Success" (table created)

5. **Verify in Supabase Table Editor**
   - Refresh the Tables list
   - Should see: `batch_jobs`, `exception_queue`, `audit_logs`, `students`, `assessments`, etc.
   - Should see updated RLS policies on all 4 key tables

---

## Post-Deployment Verification

### Check exception_queue policies:
```sql
SELECT tablename, policyname, SUBSTR(qual, 1, 80) as policy_condition
FROM pg_policies
WHERE tablename = 'exception_queue'
ORDER BY policyname;
```
Expected: 3 rows (Staff read, staff update, backend insert)

### Check batch_jobs table exists:
```sql
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name = 'batch_jobs';
```
Expected: 1 row with `batch_jobs`

---

## Troubleshooting

**Error: "table already exists"**
- This is normal and safe — file uses `IF NOT EXISTS`
- You can safely re-run this file

**Error: "policy already exists"**  
- Also normal — same reason
- Safe to re-run

**Error: "permission denied"**
- Check you're logged in as the project owner
- Check service_role key has write access
- Try running a simple SELECT query first to verify access

**Policies not appearing in UI:**
- Hard-refresh Supabase dashboard (Ctrl+F5 / Cmd+Shift+R)
- Check the "Policies" tab under table settings

---

## Next Steps
✅ **Complete Step 1** → Move to **Step 2: Backend Repo Deployment**

See `DEPLOYMENT_COMPLETE.md` for full checklist.
