# Phase B+C: 4 Immediate Tasks — Step-by-Step Walkthrough

This document provides detailed instructions for completing the final 4 tasks before production deployment.

---

## TASK 1: Apply RLS Gap Remediation (2 min) ✅ Ready to Execute

### What This Does
Fixes 3 critical RLS (Row-Level Security) gaps in Supabase database:
1. **exception_queue**: RLS enabled but zero policies → adds admin-only read policy
2. **audit_logs**: Missing INSERT policy → allows audit trail creation
3. **students/assessments**: Overly broad enumeration → restricts student access to own records

### Where
**File**: `backend/rls_gap_remediation.sql`

### How to Execute (Choose One)

#### Option A: Supabase Web UI (easiest)
```
1. Open https://app.supabase.com
2. Select your AuraGrade project
3. Click "SQL Editor" in left sidebar
4. Click "New Query" button
5. Copy entire contents of: backend/rls_gap_remediation.sql
6. Paste into the query editor
7. Click "Execute" button (top right)
8. Wait for "✓ Query executed successfully" message
```

#### Option B: psql Command Line
```bash
psql -h <your-supabase-host> \
     -U postgres \
     -d postgres \
     -f backend/rls_gap_remediation.sql
```

### How to Verify Success
In Supabase SQL Editor, run:
```sql
SELECT polname, polcmd FROM pg_policies 
WHERE tablename IN ('students', 'grades', 'audit_logs') 
ORDER BY tablename, polname;
```

**Expected Result**: Should see 3+ rows per table (was 1 before)

### Rollback (if needed)
```sql
-- Remove the policies we just added
DROP POLICY IF EXISTS "students_select_fixed" ON students;
DROP POLICY IF EXISTS "assessments_select_fixed" ON assessments;
DROP POLICY IF EXISTS "audit_logs_insert" ON audit_logs;
DROP POLICY IF EXISTS "audit_logs_select" ON audit_logs;
```

---

## TASK 2: Deploy Environment Variables (5 min) ✅ Ready to Execute

### What This Does
Configures your production backend with critical secrets needed for:
- Gemini API authentication
- Supabase database connection
- JWT token validation
- CORS origin whitelisting

### Where
**File**: `.env.example` (template)  
**Deploy To**: `backend/.env` (production server)

### Step 1: Create Backend .env File

Copy the template:
```bash
cp .env.example backend/.env
```

Edit `backend/.env` and fill in these values:

| Variable | Source | Example |
|----------|--------|---------|
| `SUPABASE_URL` | Supabase Dashboard > Settings > API | `https://xyz.supabase.co` |
| `SUPABASE_KEY` | Supabase Dashboard > Settings > API > **service_role** key | `eyJhbGc...` |
| `SUPABASE_JWT_SECRET` | Supabase Dashboard > Settings > Database > JWT Secret | `super-secret-key` |
| `GEMINI_API_KEY` | Google Cloud Console > Credentials | `AIzaSy...` |
| `CORS_ORIGIN` | Your deployment domains (comma-separated) | `https://yourdomain.com` |

### Step 2: Find Your Supabase Credentials

**Navigate to Supabase Dashboard**:
```
1. Go to https://app.supabase.com
2. Select your AuraGrade project
3. Click "Settings" (bottom left)
4. Click "API" tab

You'll see:
- Project URL (for SUPABASE_URL)
- anon key (for frontend, not needed here)
- service_role key (for SUPABASE_KEY) ⚠️ KEEP SECRET
- JWT Secret (for SUPABASE_JWT_SECRET) ⚠️ KEEP SECRET
```

**Navigate to Database Settings**:
```
1. In Settings, click "Database" tab
2. Look for "JWT Settings" section
3. Copy the JWT Secret value
```

### Step 3: Find Your Gemini API Key

```
1. Go to https://console.cloud.google.com
2. Create or select a project
3. Enable "Generative Language API"
4. Go to "Credentials"
5. Create an API Key (or use existing one)
6. Copy the key value
```

### Step 4: Deploy to Production

**If using Docker**:
```bash
# Copy .env to your container
docker cp backend/.env <container-id>:/app/.env

# Or set env vars in docker-compose.yml
environment:
  - SUPABASE_URL=https://xyz.supabase.co
  - SUPABASE_KEY=eyJhbGc...
  - etc.
```

**If using Heroku/Railway/Vercel**:
```
1. Go to deployment platform dashboard
2. Find "Environment Variables" or "Config Vars" section
3. Add each variable from backend/.env
4. Trigger redeploy
```

**If self-hosted**:
```bash
# Copy .env to server
scp backend/.env user@server:/path/to/auragrade/backend/.env

# Or SSH in and create file directly
ssh user@server
nano /path/to/auragrade/backend/.env
# Paste contents
```

### Step 5: Verify Startup

After deploying, start the backend and check logs:

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Expected Output**:
```
✅ All env vars validated
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**If you see error**:
```
❌ FATAL: SUPABASE_URL not set
```
Then the .env file wasn't loaded correctly. Check:
- File exists at `backend/.env`
- All required vars are present
- No typos in variable names

---

## TASK 3: Configure GitHub Secrets for CI Tests (5 min) ✅ Ready to Execute

### What This Does
Enables automated auth boundary tests in GitHub Actions CI pipeline. The tests verify:
- Invalid tokens → 401 error
- Student tokens on staff-only routes → 403 error
- Rate limiting triggers correctly
- Request ID headers present

### Where
**GitHub**: Your repo → Settings → Secrets and Variables → Actions

### Step 1: Generate or Collect Test Tokens

You need 3 valid JWT tokens with specific roles. Options:

#### Option A: Generate Tokens (if you have Supabase CLI)
```bash
# Install Supabase CLI
npm install -g supabase

# Get your anon key
cat .env.local | grep NEXT_PUBLIC_SUPABASE_ANON_KEY

# Generate test token with role
supabase gen --jwt \
  --secret "<your-jwt-secret>" \
  --claims '{"sub":"test-student@example.com","role":"STUDENT"}'
```

#### Option B: Use Existing Auth System
If you already have a staging environment:
```
1. Log in as a Student user
2. Open browser DevTools > Application > Cookies
3. Find session token or JWT
4. Copy and paste as TEST_STUDENT_TOKEN
5. Repeat for EVALUATOR and ADMIN_COE users
```

#### Option C: Placeholder Tokens (for CI gate testing only)
```
TEST_STUDENT_TOKEN=Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzdHVkZW50QGV4YW1wbGUuY29tIiwicm9sZSI6IlNUVURFTlQifQ.placeholder
TEST_EVALUATOR_TOKEN=Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJldmFsdWF0b3JAZXhhbXBsZS5jb20iLCJyb2xlIjoiRVZBTFVBVE9SIn0.placeholder
TEST_ADMIN_TOKEN=Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbkBleGFtcGxlLmNvbSIsInJvbGUiOiJBRE1JTl9DT0UifQ.placeholder
```

### Step 2: Add Secrets to GitHub

```
1. Go to https://github.com/your-org/AuraGrade-Frontend (or Backend)
2. Click "Settings" tab (top navigation)
3. Click "Secrets and variables" (left sidebar)
4. Click "Actions" (left sidebar)
5. Click "New repository secret" button
6. Add each secret (repeat 7 times):
```

| Secret Name | Value | Source |
|-------------|-------|--------|
| `TEST_GEMINI_API_KEY` | Staging Gemini API key | Google Cloud Console (staging project) |
| `TEST_SUPABASE_URL` | Staging Supabase URL | Supabase > Settings > API |
| `TEST_SUPABASE_KEY` | Staging service_role key | Supabase > Settings > API (staging) |
| `TEST_SUPABASE_JWT_SECRET` | Staging JWT secret | Supabase > Settings > Database (staging) |
| `TEST_STUDENT_TOKEN` | Valid student JWT | Generated above (Option A/B/C) |
| `TEST_EVALUATOR_TOKEN` | Valid evaluator JWT | Generated above (Option A/B/C) |
| `TEST_ADMIN_TOKEN` | Valid admin JWT | Generated above (Option A/B/C) |

### Step 3: Test CI Execution

```
1. Create a dummy PR or push to a branch
2. Go to GitHub > "Actions" tab
3. You should see workflow running
4. Click the workflow to see detailed logs
5. Check if "auth_matrix tests" step completes (may have some failures initially)
```

**What to Expect**:
- First run may show failures if tokens aren't valid (that's OK, it proves the tests are running)
- Once fixed, you should see: `failed: 0 passed: X`

---

## TASK 4: Delete Broken Middleware, Commit & Push ✅ COMPLETED

### Status
✅ **ALREADY DONE** — Both repositories have been committed and pushed

**Backend Commit**: `1b08456` — Phase B+C implementation  
**Frontend Commit**: `0f6fcc7` — Middleware fix + CI pipelines

**What Was Done**:
- ✅ `src/proxy.ts` deleted (was broken export: `proxy`)
- ✅ `src/middleware.ts` created (correct export: `middleware`)
- ✅ All Phase B/C files committed
- ✅ Pushed to origin/master in both repos

**Verification**:
```bash
cd d:\PROJECTS\AuraGrade
git log --oneline -3
# Should show: 0f6fcc7 Phase B+C: Frontend middleware fix...

git status
# Should show: Your branch is up to date with 'origin/master'.
```

---

## Final Verification Checklist

Run this to check readiness:

```bash
cd d:\PROJECTS\AuraGrade
python PHASE_B_C_TASKS.py
```

This will verify:
- ✅ All files created and staged correctly
- ✅ Git commits pushed
- ✅ CI workflows configured
- ✅ Environment template ready

---

## Production Deployment Sequence

Once all 4 tasks are complete:

### 1. Database (5 min)
```bash
# Run TASK 1: Apply RLS remediation in Supabase
# (SQL execution via web UI or psql)
```

### 2. Backend (10 min)
```bash
# Deploy .env with production secrets (TASK 2)
uvicorn backend/main.py --host 0.0.0.0 --port 8000
# Verify: ✅ All env vars validated
```

### 3. Frontend (10 min)
```bash
# Update .env.local with production API URL
# Rebuild and deploy
npm run build && npm run deploy
```

### 4. CI/CD (5 min)
```bash
# GitHub Secrets already configured (TASK 3)
# Just push a commit to trigger CI testing
```

### 5. Validation (15 min)
```bash
# Run auth matrix tests against production
pytest backend/test_auth_matrix.py -v

# Manual curl tests
curl -X GET http://your-prod-backend/api/system/readiness  # Should 401
curl -X GET -H "Authorization: Bearer $TOKEN" http://your-prod-backend/api/system/readiness  # Should 200
```

---

## Troubleshooting

### TASK 1: SQL execution fails
- ✅ Check: Do you have Supabase project access?
- ✅ Check: No syntax errors (spaces/special chars)?
- ✅ Try: Run just one policy at a time
- ✅ Contact: Supabase support if RLS is locked

### TASK 2: Backend won't start with env vars
- ✅ Check: .env file is in `backend/` directory (not root)
- ✅ Check: No extra spaces in variable names
- ✅ Check: Values are not quoted (use `KEY=value` not `KEY="value"`)
- ✅ Try: `source backend/.env && python -c "import os; print(os.getenv('SUPABASE_URL'))"`

### TASK 3: CI tests show 401 errors
- ✅ Check: Test tokens are valid (not expired)
- ✅ Check: Tokens use correct role names (STUDENT, EVALUATOR, ADMIN_COE)
- ✅ Try: Manually hit the API with the token: `curl -H "Authorization: Bearer $TOKEN" ...`

### TASK 4: Middleware not running
- ✅ Check: File is `src/middleware.ts` (not `src/proxy.ts`)
- ✅ Check: Function exports as `export async function middleware`
- ✅ Try: Clear .next build cache: `rm -rf .next && npm run build`

---

## Emergency Rollback

If something breaks in production:

```bash
# Rollback commits
git revert HEAD~2..HEAD  # Revert last 2 commits

# Or restore from backup
git checkout <previous-safe-commit-hash>
git push origin master --force-with-lease

# Rollback RLS changes in Supabase
# (Run TASK 1 rollback SQL from above)
```

---

## Questions?

Refer to:
- **Auth Issues**: Check `backend/auth_guard.py` and `backend/main.py` lines 81-99
- **Middleware Issues**: Check `src/middleware.ts` export function name
- **Environment Issues**: Check `.env.example` template
- **CI Issues**: Check `.github/workflows/*.yml` gate definitions
