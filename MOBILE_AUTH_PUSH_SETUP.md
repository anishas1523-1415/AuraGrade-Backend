# AuraGrade Mobile: JWT Auth + Push Notifications

## Overview

This document covers the implementation of two critical features deployed to the mobile app (Expo React Native) and backend (FastAPI):

1. **Real JWT Authentication** — Replaces fake prefix-based login with Supabase email/password auth + secure token persistence
2. **Push Notifications & Live Result Updates** — Automatically notifies students when grades/appeals are published, and refreshes their results screen

---

## 1. Real JWT Authentication Flow

### Mobile Changes

#### New Dependencies Added
- `@supabase/supabase-js` — Supabase client for auth + JWT + session mgmt
- `expo-secure-store` — Native secured token storage (iOS Keychain, Android Keystore)
- `react-native-url-polyfill` — URL support in React Native

**File: `mobile/lib/supabase.ts`** (NEW)
- Initializes Supabase client with secure persistent storage
- Thread-safe token refresh via `autoRefreshToken` flag
- Env vars: `EXPO_PUBLIC_SUPABASE_URL`, `EXPO_PUBLIC_SUPABASE_ANON_KEY`

**File: `mobile/lib/api.ts`** (NEW)
- Authenticated fetch wrapper: `authFetch(path, init)`
- Automatically injects `Authorization: Bearer <JWT>` header
- All backend API calls must use `authFetch` instead of raw `fetch`

**File: `mobile/screens/LoginScreen.tsx`** (REPLACED)
- Old: Prefix-based fake login (`AIDS-... | PROF-...`)
- New: Real email/password Supabase auth
- Input: college email + password
- On success: Calls `onLoginSuccess()` callback triggering session hydration

**File: `mobile/App.tsx`** (UPDATED)
- New: `hydrateFromBackend()` async function
  - Checks Supabase session on app launch
  - Calls `/api/auth/me` (new backend endpoint) to resolve role + student reg_no
  - Sets role to `PROFESSOR` if user has evaluator role, else `STUDENT`
  - Registers push token on hydration success
  - Triggers on auth state changes (auto re-hydrate on logout)
- Displays loading state during hydration

**File: `mobile/screens/StudentDashboard.tsx`** & **`mobile/screens/StaffDashboard.tsx`** (UPDATED)
- All network calls now use `authFetch()` instead of hardcoded `API_BASE`
- No `resolved_by` or other identity fields — backend resolves from JWT

### Backend Changes

**File: `backend/main.py`** (UPDATED)

New endpoint: `GET /api/auth/me`
```python
@app.get("/api/auth/me")
async def auth_me(current_user=Depends(require_auth)):
    # Verify token, resolve role from profiles table
    # Lookup student record by email
    # Return: { user: {...role}, student: {...reg_no} }
```

Existing auth already in place:
- `require_auth` — validates Supabase JWT, returns user + profile
- `require_role(*roles)` — enforces RBAC on protected endpoints

Updated endpoints now enforce auth:
- `@app.get("/api/staff/appeals/pending")` — now requires `require_role("ADMIN_COE", "HOD_AUDITOR", "EVALUATOR")`
- `@app.put("/api/staff/appeals/{id}/resolve")` — now requires role, uses `current_user` identity instead of `resolved_by` body param

### Environment Setup (Mobile)

In Expo's `.env` or `eas.json` build environment:
```
EXPO_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
EXPO_PUBLIC_SUPABASE_ANON_KEY=<YOUR_ANON_KEY>
EXPO_PUBLIC_API_URL=https://backend.deployed.url
```

Test account setup in Supabase:
1. Create auth user with email + password
2. Create profile record: `{ id: <user_id>, role: "EVALUATOR" }`
3. For students: Create student record with matching email, link profile

---

## 2. Push Notifications & Live Result Updates

### Mobile Changes

**File: `mobile/lib/notifications.ts`** (NEW)
- `registerForPushNotifications()` — Requests permission, returns Expo push token
  - Handles Android notification channel setup
  - Returns `null` on simulators/non-devices
- `registerPushTokenOnBackend(token, role, regNo)` — Calls new backend registration endpoint

**File: `mobile/App.tsx`** (UPDATED)
- After successful hydration, calls `registerForPushNotifications()`
- If token obtained, calls `registerPushTokenOnBackend(token, appRole, regNo)`
- Backend stores token in `device_push_tokens` table for later push dispatch

**File: `mobile/screens/StudentDashboard.tsx`** (UPDATED)
- Added notification listeners using `Notifications.add...Listener()`
- On `RESULT_PUBLISHED` or `APPEAL_RESOLVED` notification received:
  - Automatically calls `fetchResults()` to refresh from backend
  - User sees updated score without manual refresh
- Cleanup: Remove listeners on unmount

### Backend Changes

**File: `backend/schema.sql`** (UPDATED)
- New table: `device_push_tokens`
  ```sql
  CREATE TABLE device_push_tokens (
      push_token TEXT UNIQUE NOT NULL,
      user_id UUID REFERENCES auth.users(id),
      email TEXT,
      role TEXT,       -- 'STUDENT' or 'PROFESSOR'
      reg_no TEXT,
      platform TEXT,   -- 'android' or 'ios'
      is_active BOOLEAN DEFAULT true,
      updated_at TIMESTAMPTZ
  );
  ```
- RLS policies allow users to manage own tokens, admins to read all

**File: `backend/main.py`** (NEW)

Helper functions:
- `_send_expo_push(tokens, title, body, data)` — HTTP POST to `https://exp.host/--/api/v2/push/send`
  - Sends multimodal Expo notification batch
  - Graceful failure (logs warning, doesn't crash)
- `_get_student_push_tokens(student_reg_no)` — Queries `device_push_tokens`, returns active tokens for STUDENT role
- `notify_result_published(reg_no, score, assessment_id)` — Triggers push with type `RESULT_PUBLISHED`
- `notify_appeal_resolved(reg_no, new_score, grade_id)` — Triggers push with type `APPEAL_RESOLVED`

New endpoint: `POST /api/notifications/register-device`
```python
@app.post("/api/notifications/register-device")
async def register_device_token(body: RegisterDeviceTokenBody, current_user=Depends(require_auth)):
    # Extract push_token, platform, role from body
    # Lookup reg_no from student table if not provided
    # Upsert row in device_push_tokens
```

Updated endpoints to trigger push:
- `save_grade_to_db()` — After grade is persisted, calls `notify_result_published()`
- `resolve_pending_appeal()` — After appeal score override, calls `notify_appeal_resolved()`

### Push Notification Payload

When a result is published or appeal resolved, students receive:
- Title: "AuraGrade Result Published" or "AuraGrade Appeal Updated"
- Body: "Your score is now available: 12.5" (or similar)
- Data:
  ```json
  {
    "type": "RESULT_PUBLISHED",  // or "APPEAL_RESOLVED"
    "reg_no": "AD011",
    "assessment_id": "...",
    "grade_id": "..."
  }
  ```

Mobile app detects `type` and auto-refreshes UI without user action.

---

## Testing Checklist

### Mobile Testing
- [ ] Create test Supabase account (email + password)
- [ ] Set env vars in eas.json preview/development profiles
- [ ] Run `npm run android` or `eas build --platform android --profile preview`
- [ ] Log in with test account → expect /api/auth/me to succeed
- [ ] Grant notification permission → verify push token registered to backend
- [ ] On separate device/window, grade a paper → receive push notification → notice automatic result refresh

### Backend Testing
- [ ] Deploy schema.sql to Supabase (run in SQL console)
- [ ] Verify `device_push_tokens` table exists with RLS policies
- [ ] Test `/api/notifications/register-device` with curl:
  ```bash
  curl -X POST http://localhost:8000/api/notifications/register-device \
    -H "Authorization: Bearer <JWT>" \
    -H "Content-Type: application/json" \
    -d '{ "push_token": "ExponentPushToken[...]", "role": "STUDENT", "reg_no": "AD011" }'
  ```
- [ ] Verify row inserted in `device_push_tokens`
- [ ] Grade a paper for that student → check Expo push logs for delivery

### Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| `Cannot find module '@supabase/supabase-js'` | Dependencies not installed | `npm install` in mobile/ |
| `SUPABASE_URL or SUPABASE_ANON_KEY not set` | Missing env vars | Set in `.env`, `eas.json`, or build settings |
| `Notification permission denied` | iOS/Android permission not granted | Prompt user, allow in system settings |
| `Push token not registering` | Backend unreachable or token not passed | Verify `API_URL` env, check network logs |
| `Results not auto-refreshing` | Notification not received or type mismatch | Check Expo dashboard logs, verify data.type in push payload |
| `JWT token expired` | Token older than Supabase session TTL | App will auto-refresh via `autoRefreshToken` or trigger re-login |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         MOBILE APP (Expo)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  LoginScreen ──[email/password]──> Supabase Auth              │
│       ↓                                  ↓                     │
│  (success) ──────────────────────────> JWT Token              │
│       ↓                                (secure store)          │
│  App hydrates via /api/auth/me         ↓                      │
│       ↓                          [validate + role]            │
│  Push register call                    ↓                      │
│       ↓                          StudentDashboard/            │
│  [authFetch injects Bearer]           StaffDashboard          │
│       ↓                                                        │
│  listen(RESULT_PUBLISHED)                                     │
│  listen(APPEAL_RESOLVED) ───────────────────────────────────> │
│                                 (auto-refresh on push)        │
└─────────────────────────────────────────────────────────────────┘
                              ↕ (via authFetch)
┌─────────────────────────────────────────────────────────────────┐
│                      BACKEND (FastAPI)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  POST /api/auth/me                                             │
│  ├─ require_auth (validate JWT)                               │
│  └─ resolve role + student from profiles/students             │
│                                                                 │
│  POST /api/notifications/register-device                       │
│  ├─ require_auth                                              │
│  ├─ upsert device_push_tokens row                             │
│  └─ ✅ ok (token now stored for push dispatch)               │
│                                                                 │
│  (on grade save or appeal resolve)                            │
│  ├─ _get_student_push_tokens(reg_no)                         │
│  ├─ _send_expo_push(tokens, title, body, data)              │
│  └─ [HTTP POST to Expo push service]                         │
│          ↓                                                     │
│         [Expo service routes to FCM/APNs]                     │
│          ↓                                                     │
│      [Device receives notification]                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Configuration Checklist

### Supabase Setup
- [ ] Create new Supabase project (or use existing)
- [ ] Enable Supabase Auth (email provider)
- [ ] Run [schema.sql](backend/schema.sql) in SQL console
- [ ] Create test users in Auth > Users tab
- [ ] Create matching profiles with roles (EVALUATOR, ADMIN_COE, etc.)
- [ ] Copy Supabase URL + Anon Key to mobile `.env` / `eas.json`

### Mobile Build Configuration
- [ ] Set `EXPO_PUBLIC_SUPABASE_URL` in eas.json `[build.preview.env]`
- [ ] Set `EXPO_PUBLIC_SUPABASE_ANON_KEY` in eas.json
- [ ] Set `EXPO_PUBLIC_API_URL` (backend domain)
- [ ] Run `eas build --platform android --profile preview` to build APK
- [ ] Or `npm run android` for dev Expo Go testing

### Backend Deployment
- [ ] Deploy FastAPI (uvicorn or cloud run)
- [ ] Set env vars: `SUPABASE_URL`, `SUPABASE_KEY`, `GEMINI_API_KEY`
- [ ] Ensure CORS allows mobile origin
- [ ] Test `/api/system/readiness` returns 200 OK

---

## Future Enhancements

1. **Refresh Token Rotation** — Supabase auto-handles, but consider explicit rotation for enterprise
2. **Push Analytics** — Log which students have active tokens, delivery rates
3. **Silent Push** — Send data-only pushes for instant data sync (no notification badge)
4. **Offline Mode** — Queue requests when network unavailable, sync on reconnect
5. **Multi-Device Push** — Support per user pushing to all active devices
6. **Custom Notification Sounds** — iOS/Android custom audio per event type

---

## References

- [Supabase JavaScript Client](https://supabase.com/docs/reference/javascript)
- [Expo Secure Store](https://docs.expo.dev/versions/latest/sdk/securestore/)
- [Expo Notifications](https://docs.expo.dev/versions/latest/sdk/notifications/)
- [Expo Push Notifications](https://docs.expo.dev/push-notifications/overview/)
- [FastAPI Dependency Injection](https://fastapi.tiangolo.com/tutorial/dependencies/)
