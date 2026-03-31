# AuraGrade Production Deployment — Complete Checklist

**Deployment Date:** March 31, 2026  
**Status:** ✅ **READY FOR DEPLOYMENT**

---

## 🎯 Quick Summary

Two production-ready zips have been extracted and deployed:
- ✅ **AuraGrade-Backend-production.zip** → backend/ folder deployed
- ✅ **AuraGrade-Frontend-production.zip** → frontend/ folder deployed

**Next Actions:**
1. ✋ **Step 1** — Run SQL migrations in Supabase (5 minutes)
2. ✋ **Step 2** — Already done: backend files deployed
3. ✋ **Step 3** — Already done: frontend files deployed  
4. ✋ **Step 4** — Configure environment variables (15 minutes)

---

## 📋 Step-by-Step Deployment Checklist

### Step 1: Database Migrations (Supabase)

**Status:** 🔴 **ACTION REQUIRED**

**What:** Run 3 SQL scripts in Supabase SQL Editor (IN CORRECT ORDER)  
**Time:** 5 minutes  
**Risk:** Low — scripts use `IF NOT EXISTS` and are idempotent

**Files to run (IN THIS ORDER):**

| # | File | Purpose | Location |
|---|------|---------|----------|
| 1 | `schema.sql` | Create all tables (prerequisite!) | `backend/` |
| 2 | `rls_gap_remediation.sql` | Fix RLS policy gaps on 4 tables | `backend/` |
| 3 | `batch_jobs_migration.sql` | Add persistent batch job tracking | `backend/` |

⚠️ **IMPORTANT:** If you see error "relation does not exist", you skipped schema.sql. See [DATABASE_MIGRATION_ERROR_FIX.md](./DATABASE_MIGRATION_ERROR_FIX.md)

**Complete Instructions:** See [DEPLOYMENT_STEP_1_DATABASE.md](./DEPLOYMENT_STEP_1_DATABASE.md)

**Verification After:**
```sql
-- Should show batch_jobs table
SELECT table_name FROM information_schema.tables 
WHERE table_name = 'batch_jobs';

-- Should show 3 exception_queue policies
SELECT policyname FROM pg_policies 
WHERE tablename = 'exception_queue';
```

---

### Step 2: Backend Repo (Already Deployed ✅)

**Status:** ✅ **COMPLETE**

**What:** All files in `backend/` have been replaced with production versions

**Key Files Changed:**

| File | Size | What Changed |
|------|------|--------------|
| `main.py` | 147 KB | All 62 endpoints protected (Phase A+B+C) |
| `requirements.txt` | 205 B | Added PyJWT, slowapi dependencies |
| `rate_limiter.py` | 3.5 KB | **NEW** — per-user AI rate limiting |
| `request_logger.py` | 3.3 KB | **NEW** — structured JSON logging |
| `test_auth_matrix.py` | 13 KB | **NEW** — 311-line auth test suite |
| `rls_gap_remediation.sql` | 7 KB | **NEW** — fixes RLS gaps |
| `batch_jobs_migration.sql` | 4.2 KB | **NEW** — persistent job storage |
| `.env.example` | 1.8 KB | **NEW** — documents all required vars |
| `.github/workflows/ci.yml` | NEW | 4-gate CI pipeline |
| `README.md` | 2.1 KB | **NEW** — updated documentation |

**Verification:**
```bash
cd backend
ls -la main.py rate_limiter.py request_logger.py rls_gap_remediation.sql
```
All should exist ✅

---

### Step 3: Frontend Repo (Already Deployed ✅)

**Status:** ✅ **COMPLETE**

**What:** All files in `frontend/` have been replaced with production versions

**Critical Changes:**

| File | Status | Why Important |
|------|--------|---------------|
| `src/middleware.ts` | ✨ **NEW** | Session refresh middleware — now properly exported |
| `src/proxy.ts` | ❌ **DELETED** | Silently ignored by Next.js — removed |
| `src/app/api/generate-rubric/route.ts` | 🔒 Auth guard added | Prevents unauthorized rubric generation |
| `mobile/lib/api.ts` | Fixed | Hardcoded IP removed, throws on missing env var |
| `.github/workflows/ci.yml` | ✨ **NEW** | Typecheck + lint + build + middleware name check |

**Verification:**
```bash
cd frontend
ls -la src/middleware.ts src/app/api/generate-rubric/route.ts mobile/lib/api.ts
# All should exist
```

**Post-Deployment Check:**
```bash
cd frontend
npm run build  # Should succeed without errors
```

---

### Step 4: Environment Variables (ACTION REQUIRED)

**Status:** 🔴 **ACTION REQUIRED**

**What:** Configure 3 environment files with production secrets  
**Time:** 15 minutes  
**Risk:** Critical — app won't start without these

**Files to Configure:**

#### Backend: `backend/.env`
```bash
# Required — app refuses to start without these
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your_supabase_service_role_key  # ⚠️ SENSITIVE
SUPABASE_JWT_SECRET=your_jwt_secret
GEMINI_API_KEY=your_gemini_api_key

# Recommended
CORS_ORIGIN=https://your-frontend-domain.com

# Optional
GEMINI_EXTRA_KEYS=backup_key1,backup_key2
```

#### Mobile: `frontend/mobile/.env`
```bash
EXPO_PUBLIC_SUPABASE_URL=https://your-project-id.supabase.co
EXPO_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
EXPO_PUBLIC_API_URL=https://api.auragrade.com
```

#### Frontend: `frontend/.env.local`
```bash
NEXT_PUBLIC_SUPABASE_URL=https://your-project-id.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
NEXT_PUBLIC_API_URL=https://api.auragrade.com
```

**Complete Instructions:** See [DEPLOYMENT_STEP_4_ENVIRONMENT_VARIABLES.md](./DEPLOYMENT_STEP_4_ENVIRONMENT_VARIABLES.md)

**Checklist:**
- [ ] Backend `.env` created with all required vars
- [ ] Mobile `mobile/.env` created with all required vars
- [ ] Frontend `.env.local` created with all required vars
- [ ] NEVER committed to git (`.gitignore` protects them)
- [ ] All values from correct sources (Supabase, Gemini API)
- [ ] CORS_ORIGIN matches your actual frontend domain
- [ ] API_URL points to correct backend server

---

## 🔍 What Changed vs. Original Deployment

### Backend Improvements (main.py)

| Aspect | Before | After |
|--------|--------|-------|
| **Protected Endpoints** | 45/62 | **62/62** ✅ |
| **Rate Limiting** | Not implemented | Per-user AI rate limiting ✅ |
| **Logging** | Print statements | Structured JSON + X-Request-ID ✅ |
| **Auth Testing** | Manual | 311-line test suite ✅ |
| **RLS Policies** | 3 gaps | All fixed ✅ |
| **Batch Jobs** | In-memory only | Persistent (Supabase table) ✅ |
| **Dependencies** | Incomplete | Complete (PyJWT, slowapi) ✅ |

### Frontend Improvements

| Aspect | Before | After |
|--------|--------|-------|
| **Middleware Export** | Broken (not exported) | ✅ Correctly exported |
| **Unused Files** | `src/proxy.ts` silently ignored | ✅ Deleted |
| **Auth Guards** | Missing from rubric endpoint | ✅ Added |
| **Mobile API** | Hardcoded IP | ✅ Env var with validation |
| **CI Pipeline** | Not automated | ✅ 4-gate pipeline |

---

## 📦 Files Deployed

### From Backend Zip
```
backend/
├── main.py (147 KB) — Core backend
├── rate_limiter.py — AI rate limiting
├── request_logger.py — Structured logging
├── test_auth_matrix.py — Auth test suite
├── rls_gap_remediation.sql — Database fixes
├── batch_jobs_migration.sql — Persistent storage
├── requirements.txt — Dependencies
├── .env.example — Config template
├── .github/workflows/ci.yml — CI pipeline
├── README.md — Documentation
└── [20 other Python modules]
```

### From Frontend Zip
```
frontend/
├── src/
│   ├── middleware.ts (NEW) — Session refresh
│   ├── app/api/generate-rubric/route.ts — Auth guard added
│   └── [other pages/components]
├── mobile/
│   ├── lib/api.ts — Fixed hardcoded IP
│   └── [React Native code]
├── .github/workflows/ci.yml (NEW) — CI pipeline
├── package.json — Dependencies
└── [config files]
```

---

## ⚠️ Critical Security Notes

### Do NOT
- ❌ Commit `.env` files (protected by `.gitignore`)
- ❌ Share `SUPABASE_KEY` in messages, emails, or Slack
- ❌ Use same API keys across dev/test/production
- ❌ Log `GEMINI_API_KEY` or `SUPABASE_KEY`

### Do
- ✅ Rotate keys annually
- ✅ Use separate Supabase projects per environment
- ✅ Store secrets in secure manager (AWS Secrets, GCP Secret Manager)
- ✅ Regenerate if accidentally exposed
- ✅ Use RLS policies for row-level access control

---

## 🚀 Next: How to Start Services

### Backend (Python/Flask)
```bash
cd backend
pip install -r requirements.txt
python main.py
# Should start on http://localhost:8000
# Requires Step 1 (DB migrations) + Step 4 (.env vars)
```

### Frontend (Next.js)
```bash
cd frontend
npm install
npm run build
npm run start
# Should start on http://localhost:3000
# Requires Step 4 (.env.local vars)
```

### Mobile (React Native/Expo)
```bash
cd frontend/mobile
npm install
npm run start
# Should open Expo dev server
# Requires Step 4 (mobile/.env vars)
```

---

## 📞 Troubleshooting

### Backend won't start: "Missing required variable"
- [ ] Check `backend/.env` exists (not `.env.example`)
- [ ] Verify `SUPABASE_URL`, `SUPABASE_KEY`, `GEMINI_API_KEY` are set
- [ ] Check no typos in variable names

### Database migration fails in Supabase
- [ ] Ensure you're logged in as project owner
- [ ] Try running simpler query first: `SELECT now();`
- [ ] Check service_role key has write access
- [ ] Both SQL files use `IF NOT EXISTS` — safe to re-run

### Frontend build fails
- [ ] Check `frontend/.env.local` exists with all `NEXT_PUBLIC_*` vars
- [ ] Clear `.next/` folder: `rm -rf .next/`
- [ ] Rebuild: `npm run build`

### Mobile app can't connect to backend
- [ ] Check `mobile/.env` has correct `EXPO_PUBLIC_API_URL`
- [ ] Verify backend is actually running and accessible
- [ ] Check CORS policy in backend `.env` allows the mobile app domain

---

## ✅ Deployment Complete Checklist

- [ ] Step 1: SQL migrations run in Supabase
- [ ] Step 2: Backend folder deployed (already done)
- [ ] Step 3: Frontend folder deployed (already done)
- [ ] Step 4: All `.env` files configured
- [ ] Backend starts without errors
- [ ] Frontend builds without errors
- [ ] Mobile app connects to backend
- [ ] Database tables created (verify `batch_jobs` exists)
- [ ] RLS policies applied (verify on `exception_queue`)

---

## 📚 Related Documents

- [DEPLOYMENT_STEP_1_DATABASE.md](./DEPLOYMENT_STEP_1_DATABASE.md) — SQL migration instructions
- [DEPLOYMENT_STEP_4_ENVIRONMENT_VARIABLES.md](./DEPLOYMENT_STEP_4_ENVIRONMENT_VARIABLES.md) — Complete env var guide
- [backend/.env.example](./backend/.env.example) — Backend config template
- [frontend/mobile/.env.example](./frontend/mobile/.env.example) — Mobile config template
- [PHASE_B_C_COMPLETION_REPORT.md](./PHASE_B_C_COMPLETION_REPORT.md) — What was implemented

---

**Deployment assembled:** March 31, 2026, 14:30 UTC  
**Status:** Production-ready, awaiting final configuration  
**Next Step:** Complete Step 1 (database), then Step 4 (environment variables)
