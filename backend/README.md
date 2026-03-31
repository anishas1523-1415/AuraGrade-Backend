# AuraGrade Backend

FastAPI-based AI grading engine. Phases A+B+C hardened and production-ready.

## Quick start

```bash
cp .env.example .env   # fill in real values
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Required environment variables

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Gemini AI grading |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase service role key |
| `SUPABASE_JWT_SECRET` | JWT verification secret |
| `CORS_ORIGIN` | Frontend URL(s), comma-separated |

App will **refuse to start** if any of the above are missing.

## Database setup

Run in Supabase SQL Editor, in order:

1. `schema.sql` — base tables + RLS
2. `rls_gap_remediation.sql` — fixes 3 RLS policy gaps found in Phase C audit
3. `batch_jobs_migration.sql` — persistent batch job tracking table

## Security hardening (Phase A–C)

- All 62 endpoints require authentication
- AI endpoints rate-limited per user (JWT sub)
- Structured JSON logging with `X-Request-ID` per request
- Startup fail-fast on missing critical env vars
- Student data isolation enforced at API layer

## Running tests

```bash
pip install pytest httpx
export TEST_STUDENT_TOKEN=...   # Supabase JWT for STUDENT role user
export TEST_STAFF_TOKEN=...     # Supabase JWT for EVALUATOR role user
export TEST_ADMIN_TOKEN=...     # Supabase JWT for ADMIN_COE role user
export TEST_STUDENT_REG_NO=...
export TEST_GRADE_ID=...
export TEST_ASSESSMENT_ID=...
export BACKEND_URL=http://localhost:8000

uvicorn main:app --port 8000 &
pytest test_auth_matrix.py -v
```

## Rate limits (per user per minute)

| Endpoint | Limit | Override env var |
|----------|-------|-----------------|
| `/api/evaluate` | 10 | `RL_EVALUATE` |
| `/api/grade/stream` | 20 | `RL_GRADE_STREAM` |
| `/api/grade` | 20 | `RL_GRADE` |
| `/api/evaluate_script` | 10 | `RL_EVALUATE_SCRIPT` |
| `/api/voice-to-rubric` | 20 | `RL_VOICE_RUBRIC` |
| `/api/evaluate-batch` | 3 | `RL_EVALUATE_BATCH` |
| `/api/rubric/upload-pdf` | 10 | `RL_RUBRIC_UPLOAD` |

For multi-worker deployments, set `RATE_LIMIT_STORAGE_URI=redis://...`
