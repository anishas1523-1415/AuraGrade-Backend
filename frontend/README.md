# AuraGrade Frontend

Next.js 16 + Expo React Native — Phases A+B+C hardened and production-ready.

## Web app quick start

```bash
cp .env.local.example .env.local   # fill in real values
npm install
npm run dev
```

## Mobile app quick start

```bash
cd mobile
cp .env.example .env               # fill in real values
npm install
npx expo start
```

## Required environment variables

### Web (`src/.env.local`)
```
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
NEXT_PUBLIC_API_URL=https://your-backend-domain.com
GEMINI_API_KEY=your_gemini_key     # server-side only, for /api/generate-rubric
```

### Mobile (`mobile/.env`)
```
EXPO_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
EXPO_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
EXPO_PUBLIC_API_URL=https://your-backend-domain.com
```

## Key fixes applied (Phase A–C)

- `src/middleware.ts` — correctly exports `middleware` (previous `proxy.ts` was silently ignored by Next.js)
- `src/app/api/generate-rubric/route.ts` — requires authenticated Supabase session
- `mobile/lib/api.ts` — throws on missing `EXPO_PUBLIC_API_URL` (removed hardcoded IP fallback)

## CI gates

GitHub Actions runs on every push to `main`:
1. TypeScript typecheck (`tsc --noEmit`, strict mode)
2. Next.js lint
3. Production build (`next build`)
4. Middleware export name verification
