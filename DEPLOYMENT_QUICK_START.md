# 🎯 AuraGrade Production Deployment — Quick Start Guide

**Deployment Status:** ✅ **Files Deployed & Ready**  
**Date:** March 31, 2026  
**Two zips extracted and deployed successfully**

---

## 📋 4-Step Deployment Overview

```
Step 1: Database (5 min)     [🔴 TODO] Run SQL migrations
Step 2: Backend (Done)        [✅ DONE] Files deployed
Step 3: Frontend (Done)       [✅ DONE] Files deployed
Step 4: ENV Vars (15 min)     [🔴 TODO] Configure secrets
```

---

## 🚀 Immediate Action Items

### Action 1: Run Database Migrations (5 minutes)
**📄 Full Guide:** [DEPLOYMENT_STEP_1_DATABASE.md](./DEPLOYMENT_STEP_1_DATABASE.md)  
**🔧 Error Recovery:** [DATABASE_MIGRATION_ERROR_FIX.md](./DATABASE_MIGRATION_ERROR_FIX.md)

**Quick Steps (IN ORDER):**
1. Log in to **Supabase Dashboard** → **SQL Editor**
2. Copy & run **`backend/schema.sql`** (creates all tables)
3. Copy & run **`backend/rls_gap_remediation.sql`** (fixes RLS gaps)
4. Copy & run **`backend/batch_jobs_migration.sql`** (adds batch_jobs table)
5. Verify: Check `batch_jobs` table appears in Tables list + RLS policies show on exception_queue, audit_logs

**Why:** 
- schema.sql = table definitions (prerequisite)
- rls_gap_remediation.sql = security policies for existing tables
- batch_jobs_migration.sql = persistent job tracking table

---

### Action 2: Configure Environment Variables (15 minutes)
**📄 Full Guide:** [DEPLOYMENT_STEP_4_ENVIRONMENT_VARIABLES.md](./DEPLOYMENT_STEP_4_ENVIRONMENT_VARIABLES.md)

**Quick Setup:**

#### Backend (`backend/.env`)
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key
SUPABASE_JWT_SECRET=your_jwt_secret
GEMINI_API_KEY=your_gemini_key
CORS_ORIGIN=https://your-frontend.com
```

#### Mobile (`frontend/mobile/.env`)
```bash
EXPO_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
EXPO_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
EXPO_PUBLIC_API_URL=https://api.your-domain.com
```

#### Frontend (`frontend/.env.local`)
```bash
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
NEXT_PUBLIC_API_URL=https://api.your-domain.com
```

---

## 📂 Key Files in Deployment

### Backend (✅ Deployed)
- `main.py` — 147 KB, all 62 endpoints protected
- `requirements.txt` — Dependencies (PyJWT, slowapi, etc.)
- `rate_limiter.py` — Per-user AI rate limiting
- `request_logger.py` — Structured JSON logging
- `test_auth_matrix.py` — 311-line test suite
- `rls_gap_remediation.sql` → **NEEDED for Step 1**
- `batch_jobs_migration.sql` → **NEEDED for Step 1**
- `.env.example` → Copy to `.env` and fill in values
- `.github/workflows/ci.yml` — 4-gate CI pipeline

### Frontend (✅ Deployed)
- `src/middleware.ts` — Session refresh (NEW, correctly exported)
- `src/app/api/generate-rubric/route.ts` — Auth guard added
- `mobile/lib/api.ts` — Fixed (removed hardcoded IP)
- `mobile/.env.example` → Copy to `mobile/.env`
- `frontend/.env.local` → Create with NEXT_PUBLIC_* vars
- `.github/workflows/ci.yml` — Typecheck + lint + build pipeline

---

## ✅ What Was Fixed (vs. Original)

### Backend (Phase A + B + C)
| Issue | Before | After |
|-------|--------|-------|
| Protected endpoints | 45/62 | **62/62** ✅ |
| Rate limiting | None | AI rate limiting ✅ |
| Logging | Unstructured | JSON + X-Request-ID ✅ |
| Batch jobs | In-memory (lost on restart) | Persistent (Supabase table) ✅ |
| RLS policies | 3 gaps | All fixed ✅ |
| Auth tests | Manual | 311-line automated suite ✅ |

### Frontend
| Issue | Before | After |
|-------|--------|-------|
| Session middleware | Broken (not exported) | ✅ Working |
| Unused files | `src/proxy.ts` ignored | ✅ Deleted |
| Auth guards | Missing on some endpoints | ✅ Added |
| Mobile hardcoded IP | 176.xxx hard-wired | ✅ Uses env var |
| CI/CD | None | ✅ 4-gate pipeline |

---

## 🔐 Critical Security Checklist

- [ ] Never commit `.env` files (protected by `.gitignore`)
- [ ] Use unique API keys per environment (dev/staging/prod)
- [ ] Rotate `GEMINI_API_KEY` annually
- [ ] Store sensitive values in secret manager (not Git)
- [ ] All variables from secure sources only
- [ ] CORS_ORIGIN matches actual frontend domain

---

## 🧪 Verification After Setup

### Test Backend Startup
```bash
cd backend
python main.py
# Should show "Running on http://0.0.0.0:8000"
# Should NOT show "Missing required variable" errors
```

### Test Frontend Build
```bash
cd frontend
npm run build
# Should complete without errors
# `.next/` folder created with optimized build
```

### Test Mobile
```bash
cd frontend/mobile
npm run start
# Should open Expo CLI
# Connect device/emulator to test
```

---

## 📞 Deployment Troubleshooting

### Database Errors
| Error | Fix |
|-------|-----|
| "permission denied" | Check logged in as project owner |
| "table already exists" | Normal — script uses `IF NOT EXISTS` |
| "policy already exists" | Also normal — safe to re-run |

### Backend Won't Start
| Error | Fix |
|-------|-----|
| Missing GEMINI_API_KEY | Add to `backend/.env` |
| Missing SUPABASE_URL | Add to `backend/.env` |
| Connection refused (Supabase) | Check SUPABASE_URL is correct URL |

### Frontend Won't Build
| Error | Fix |
|-------|-----|
| Unknown variable `NEXT_PUBLIC_*` | Create `frontend/.env.local` |
| Build timeout | Clear `.next/`: `rm -rf .next/` |

---

## 💡 What to Expect

### After Step 1 (Database): ✅
- ✅ `batch_jobs` table created in Supabase
- ✅ RLS policies on 4 tables fixed
- ✅ Backend can now create batch jobs and log audits

### After Step 2: ✅ (Already Done)
- ✅ Backend folder has all 31 files
- ✅ main.py is 147 KB (full implementation)
- ✅ New modules: rate_limiter, request_logger, test suite

### After Step 3: ✅ (Already Done)
- ✅ Frontend has src/middleware.ts (session refresh)
- ✅ Mobile has updated api.ts (no hardcoded IP)
- ✅ Generate-rubric endpoint is auth-guarded

### After Step 4: 
- ✅ Backend starts without missing var errors
- ✅ Frontend builds with env vars included
- ✅ Mobile connects to correct backend
- ✅ CORS allows frontend to call backend

---

## 📚 Full Documentation

| Document | Purpose |
|----------|---------|
| [DEPLOYMENT_COMPLETE.md](./DEPLOYMENT_COMPLETE.md) | Complete deployment checklist & summary |
| [DEPLOYMENT_STEP_1_DATABASE.md](./DEPLOYMENT_STEP_1_DATABASE.md) | Detailed SQL migration guide |
| [DEPLOYMENT_STEP_4_ENVIRONMENT_VARIABLES.md](./DEPLOYMENT_STEP_4_ENVIRONMENT_VARIABLES.md) | Complete env var reference |
| [backend/.env.example](./backend/.env.example) | Backend config template |
| [frontend/mobile/.env.example](./frontend/mobile/.env.example) | Mobile config template |
| [PHASE_B_C_COMPLETION_REPORT.md](./PHASE_B_C_COMPLETION_REPORT.md) | What was implemented |

---

## 🎯 Summary

**Status:** Production-ready zips deployed ✅

**Files Deployed:** 31 backend + 6 frontend root files + all subdirectories  
**CI Pipelines:** Backend (9 KB) + Frontend (5 KB) ready  
**Remaining:** Run 2 SQL scripts + configure 3 env files

**Time to Complete:** ~20 minutes (5 min DB + 15 min config)  
**Risk Level:** Low (migrations use `IF NOT EXISTS`, env setup is standard)

---

**Next:** Open [DEPLOYMENT_STEP_1_DATABASE.md](./DEPLOYMENT_STEP_1_DATABASE.md) and run the SQL migrations.

Then configure environment variables in [DEPLOYMENT_STEP_4_ENVIRONMENT_VARIABLES.md](./DEPLOYMENT_STEP_4_ENVIRONMENT_VARIABLES.md).

Done! 🚀
