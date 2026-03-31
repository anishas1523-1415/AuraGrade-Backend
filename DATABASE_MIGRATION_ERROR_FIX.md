# 🔧 Database Migration Error — Quick Recovery

**Your Error:** `relation "audit_logs" does not exist`

**Root Cause:** schema.sql (table definitions) must run BEFORE rls_gap_remediation.sql (security policies)

---

## ✅ Fix (2 minutes)

### Step 1: Clear the Error
1. In Supabase SQL Editor, click **Edit** at the top
2. Delete the failed query content
3. Click **Cancel** or clear the editor

### Step 2: Run Migrations in Correct Order

#### First: Copy ALL of `backend/schema.sql`
```bash
# Open this file: backend/schema.sql
# Copy ENTIRE contents (all ~500 lines)
# In Supabase: Paste → Run
# ✅ Should say "Success"
```

#### Second: Copy ALL of `backend/rls_gap_remediation.sql`
```bash
# Open: backend/rls_gap_remediation.sql
# Copy ENTIRE contents  
# In Supabase: Paste → Run
# ✅ Should say "Success"
```

#### Third: Copy ALL of `backend/batch_jobs_migration.sql`
```bash
# Open: backend/batch_jobs_migration.sql
# Copy ENTIRE contents
# In Supabase: Paste → Run
# ✅ Should say "Success"
```

---

## 📋 Why This Order?

| File | Creates | Status |
|------|---------|--------|
| **schema.sql** | Tables: users, profiles, assessments, audit_logs, exception_queue, device_push_tokens, etc. | Must run FIRST |
| **rls_gap_remediation.sql** | RLS policies ON existing tables | Runs AFTER schema.sql |
| **batch_jobs_migration.sql** | New batch_jobs table + policies | Runs AFTER rls_gap_remediation |

---

## 🎯 Verify Success

After all 3 scripts run successfully:

### In Supabase Table Editor, you should see:
- ✅ `batch_jobs` (new)
- ✅ `exception_queue` (with RLS policies)
- ✅ `audit_logs` (with RLS policies)
- ✅ `students` (with RLS policies)
- ✅ `assessments` (with RLS policies)

### Confirm RLS Policies:
```sql
-- Paste this in SQL Editor to verify
SELECT tablename, policyname 
FROM pg_policies 
WHERE tablename IN ('exception_queue', 'audit_logs', 'students', 'assessments')
ORDER BY tablename;

-- Should show ~15 policies across the 4 tables
```

---

## 📚 Updated Documentation

**The DEPLOYMENT_STEP_1_DATABASE.md has been updated** with correct order:
1. ✅ schema.sql (prerequisite)
2. rls_gap_remediation.sql
3. batch_jobs_migration.sql

---

**Next:** Complete the 3 migrations above, then move to Step 4 (environment variables).

Estimated time: 2 minutes to fix + verify ⏱️
