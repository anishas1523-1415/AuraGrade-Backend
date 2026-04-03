# AuraGrade: Immediate Next Steps After App Launch

## Current Status ✅
- Frontend running on http://localhost:3000
- Backend running on http://localhost:8000
- Environment variables loaded
- Authentication ready

## REQUIRED: Database Schema Setup (5 min)

The app is running but the **Supabase database tables don't exist yet**. You must create them:

### Step 1: Open Supabase SQL Editor
1. Go to https://app.supabase.com
2. Select your **AuraGrade** project (etlezdyfyuoslalpuelg)
3. Click **SQL Editor** in the left sidebar

### Step 2: Create Database Schema
1. Click **New Query** button
2. Copy contents of: `backend/schema.sql`
3. Paste into the editor
4. Click **Execute** button
5. Wait for: "✓ Query executed successfully"

### Step 3: Apply Security Patches
1. Click **New Query** button
2. Copy contents of: `backend/rls_gap_remediation.sql`
3. Paste into the editor  
4. Click **Execute** button
5. Wait for: "✓ Query executed successfully"

### Step 4: (Optional) Load Sample Data
If you want test data, run:
- `backend/migration_students.sql` — creates sample students
- `backend/migration_excel_students.sql` — additional student data

---

## After Database Setup: You Can Now Login

Once the schema is created:

1. **Refresh** http://localhost:3000 in your browser
2. **Sign in** with your Supabase credentials
3. You should see: "Exam Configuration Portal"
4. Select or create an assessment
5. Upload a PDF rubric and start grading

---

## Files to Keep Handy

- **Frontend env**: `d:\PROJECTS\AuraGrade\.env.local` (Supabase public keys)
- **Backend env**: `d:\PROJECTS\AuraGrade\backend\.env` (service secrets)
- **Schema**: `d:\PROJECTS\AuraGrade\backend\schema.sql` (copy to Supabase SQL Editor)
- **RLS fixes**: `d:\PROJECTS\AuraGrade\backend\rls_gap_remediation.sql` (copy to Supabase)

---

## Troubleshooting

**"Failed to load assessments"**
→ Schema not created. Follow Steps 1-3 above.

**"Invalid token error"**  
→ Backend env loaded but Supabase project mismatch. Check SUPABASE_URL in backend/.env matches project in Supabase dashboard.

**"Frontend won't load"**
→ Frontend env missing. Verify `.env.local` has NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.

---

Contact support if blocked beyond schema setup.
