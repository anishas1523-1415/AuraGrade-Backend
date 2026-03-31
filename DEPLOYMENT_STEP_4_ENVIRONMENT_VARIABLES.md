# Step 4: Environment Variables Configuration (Production Setup)

## Critical Alert ⚠️

**The application will refuse to start if these required variables are missing:**
- Backend: `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_JWT_SECRET`
- Mobile: `EXPO_PUBLIC_SUPABASE_URL`, `EXPO_PUBLIC_SUPABASE_ANON_KEY`, `EXPO_PUBLIC_API_URL`

---

## File Locations

### Backend Environment File
**Location:** `backend/.env`
**Template:** `backend/.env.example` (already provided in deployment)

### Mobile Environment File  
**Location:** `frontend/mobile/.env`
**Template:** `frontend/mobile/.env.example` (already provided in deployment)

### Frontend Web Environment (Next.js)
**Location:** `frontend/.env.local`
**Note:** Next.js reads from environment + `.env.local` at build time

---

## Backend Configuration (`backend/.env`)

### Required Variables (Must be set before running)

#### Supabase Project Connection
```bash
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your_supabase_service_role_key
SUPABASE_JWT_SECRET=your_supabase_jwt_secret
```

**Where to find these:**
1. Log in to Supabase Dashboard
2. Select your project
3. Go to **Settings → API**
   - `Project URL` → `SUPABASE_URL`
   - `service_role secret` → `SUPABASE_KEY`
   - `JWT Secret` → `SUPABASE_JWT_SECRET`

⚠️ **Security Note:** `service_role_key` is extremely sensitive — treat like AWS access key. Never commit to git.

---

#### Gemini API Key
```bash
GEMINI_API_KEY=your_gemini_api_key
```

**How to get it:**
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create or copy your API key
3. Paste into `.env`

**Failover pool (optional):**
```bash
GEMINI_EXTRA_KEYS=key2,key3,key4
```
Comma-separated, no spaces. Backend will round-robin if primary key is rate-limited.

---

#### CORS Configuration
```bash
CORS_ORIGIN=https://your-frontend-domain.com
```

**What it does:** Restricts which domains can call backend API
- **Development:** `http://localhost:3000`
- **Production:** Your actual frontend domain (e.g., `https://auragrade.example.com`)
- **Multiple domains:** Comma-separated, no spaces
  ```bash
  CORS_ORIGIN=https://app.auragrade.com,https://admin.auragrade.com
  ```

---

### Optional Variables

#### Pinecone (Similarity Sentinel / RAG)
```bash
PINECONE_API_KEY=your_pinecone_api_key
```
Only needed if using vector embeddings for plagiarism detection.

#### Grading Tuning
```bash
HUMAN_REVIEW_CONFIDENCE_THRESHOLD=85
ALLOWED_SUBJECT_KEYWORDS=ai,data science,computer science,cs,python,sql,data structures,algorithms
```

---

## Mobile Configuration (`frontend/mobile/.env`)

### Required Variables

```bash
EXPO_PUBLIC_SUPABASE_URL=https://your-project-id.supabase.co
EXPO_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
EXPO_PUBLIC_API_URL=https://your-backend-domain
```

**Getting these values:**

| Variable | Source |
|----------|--------|
| `EXPO_PUBLIC_SUPABASE_URL` | Supabase Dashboard → Settings → API → Project URL |
| `EXPO_PUBLIC_SUPABASE_ANON_KEY` | Supabase Dashboard → Settings → API → `anon` public key |
| `EXPO_PUBLIC_API_URL` | Your backend server URL (e.g., `https://api.auragrade.com`) |

**Note:** These use `anon_key` (public key), not `service_role_key`. RLS policies control access.

---

## Frontend Web Configuration (`frontend/.env.local`)

### Development Setup
```bash
NEXT_PUBLIC_SUPABASE_URL=https://your-project-id.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Production Setup
```bash
NEXT_PUBLIC_SUPABASE_URL=https://your-project-id.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
NEXT_PUBLIC_API_URL=https://api.auragrade.com
```

**Important:** `NEXT_PUBLIC_*` variables are embedded in the frontend bundle — use only non-sensitive values (anon_key is OK).

---

## Required External Accounts & Keys

### 1. Supabase Project (Required)
- Create at [supabase.com](https://supabase.com)
- Create PostgreSQL database
- Get `Project URL`, `service_role_key`, `anon_key`, `JWT_SECRET`

### 2. Google Gemini API Key (Required)
- Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
- Create API key
- Enable in Gemini API quota

### 3. Domain Names (Production)
- Frontend domain (e.g., `app.auragrade.com`)
- Backend API domain (e.g., `api.auragrade.com`)
- Set `CORS_ORIGIN` in backend to match frontend domain

### 4. Pinecone (Optional)
- Only if using similarity sentinel / vector search
- Create at [pinecone.io](https://pinecone.io)

---

## Setup Checklist

### Backend (.env)

- [ ] `SUPABASE_URL` — from Supabase Settings → API
- [ ] `SUPABASE_KEY` — service_role key (sensitive!)
- [ ] `SUPABASE_JWT_SECRET` — from API settings
- [ ] `GEMINI_API_KEY` — from Google AI Studio
- [ ] `CORS_ORIGIN` — matches your frontend domain
- [ ] *(Optional)* `GEMINI_EXTRA_KEYS` — failover API keys
- [ ] *(Optional)* `PINECONE_API_KEY` — if using vector search

### Mobile (.env)

- [ ] `EXPO_PUBLIC_SUPABASE_URL` — from Supabase
- [ ] `EXPO_PUBLIC_SUPABASE_ANON_KEY` — public anon key
- [ ] `EXPO_PUBLIC_API_URL` — backend domain

### Frontend Web (.env.local)

- [ ] `NEXT_PUBLIC_SUPABASE_URL` — from Supabase  
- [ ] `NEXT_PUBLIC_SUPABASE_ANON_KEY` — public anon key
- [ ] `NEXT_PUBLIC_API_URL` — backend domain

---

## Security Best Practices

### Do NOT

- ❌ Commit `.env` files to git (already in `.gitignore`)
- ❌ Share `SUPABASE_KEY` (service_role_key) in messages or emails
- ❌ Expose `GEMINI_API_KEY` in client-side code
- ❌ Use same keys across dev/staging/production

### Do

- ✅ Rotate `GEMINI_API_KEY` annually
- ✅ Use separate Supabase projects for dev/staging/production
- ✅ Use environment-specific API URLs
- ✅ Store secrets in secure secret management (e.g., AWS Secrets Manager, Cloud Secret Manager)
- ✅ Regenerate keys if accidentally exposed

---

## Deployment Verification

### Test Backend Startup
```bash
cd backend
python main.py
```
Should start without "Missing required variable" errors.

### Test Mobile Expo
```bash
cd frontend/mobile
npm run start
```
Should connect to backend and Supabase without auth errors.

### Test Frontend Next.js Build
```bash
cd frontend
npm run build
```
Should complete without missing environment variable errors.

---

## Next Steps
✅ **Complete Step 4** → All environment variables configured

**You're ready to:**
1. Deploy backend to production environment
2. Build & deploy mobile app via Expo
3. Deploy frontend Next.js to production hosting

See `DEPLOYMENT_COMPLETE.md` for final checklist.
