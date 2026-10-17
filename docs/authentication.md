# Accounts and private profiles (Sprint 1, US-01)

## What is implemented

- The account section supports email/password registration, email-confirmation feedback, sign-in, local-session sign-out, and session restoration/refresh through Supabase Auth.
- Registration uses Supabase Auth directly. Sign-in now passes through FastAPI's `/api/auth/login` to enforce the user-approved Free-plan endpoint limit, then Supabase verifies the password. Rihla never stores passwords or implements password hashing. See [the current login flow and limitations](sprint-1-verification.md).
- `GET /api/me` requires a Bearer access token. FastAPI calls the configured project's `GET /auth/v1/user` to validate it authoritatively, rather than trusting a browser ID or decoded JWT. This supports the project's signing method without a signing secret in Rihla.
- `GET /api/profile` returns the verified user's private profile or `null` if none has been saved. `PUT /api/profile` creates/updates the name. Requests to PostgREST include the publishable key and the same verified user access token.
- `20261014000100_account_profiles.sql` creates the profile table, constraints, explicit grants and RLS policies. It does not change `auth.users` or introduce trip tables.
- The UI distinguishes a signed-in browser session, backend-verified identity, and successful profile database access. A backend health check alone proves neither identity nor database access.

All network tests in the normal application checks use fictional users and mocked Supabase responses. They test authorization decisions and request construction, not the hosted project's policies. The SQL tests need an isolated Supabase/PostgreSQL environment. No remote migration or test-account creation has been performed by this implementation.

## One-time dashboard configuration

1. Open your **development** project in Supabase.
2. Under **Authentication**, open the email provider configuration. Enable email/password sign-in and keep **Confirm email** enabled. Set the project password minimum to at least eight characters; the UI uses eight as a minimum for registration. Supabase remains the authority on additional password rules.
3. Under **Authentication → URL Configuration**, use `http://localhost:5173` as Site URL. Add explicit redirect URLs for the frontend origins you use: `http://localhost:5173`, `http://127.0.0.1:5173`, and, if needed, `http://localhost:5174`. The signup call uses the page's current origin as `emailRedirectTo`.
4. Copy the **project URL** and **publishable key** into both local environment files. No database password, JWT signing secret, secret API key, or legacy service-role key is needed.

Frontend (`frontend/.env.local`):

```dotenv
VITE_API_BASE_URL=http://localhost:8001
VITE_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_YOUR_PUBLIC_KEY
```

Backend (`backend/.env`):

```dotenv
APP_ENV=development
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_YOUR_PUBLIC_KEY
```

If the frontend runs on 5174, add its exact origin to `CORS_ORIGINS` as well. Restart both servers after environment changes. On this computer the existing public Supabase values have been copied into the backend's ignored local environment file; real values are not in the examples.

These dashboard paths may move; the settings are described in [Supabase password authentication](https://supabase.com/docs/guides/auth/passwords) and [redirect URL configuration](https://supabase.com/docs/guides/auth/redirect-urls).

## Review and apply the account migration

The migration is **prepared, not applied**. Registration and token verification can work before it is applied, but profile checks/saves will report unavailable storage.

Preferred team workflow: use the [Supabase local-development tools](https://supabase.com/docs/guides/local-development/cli-workflows), a Docker-compatible runtime, and an agreed CLI version. From the repository root, after installing the CLI:

```powershell
# Once, if supabase/config.toml does not yet exist:
supabase init
supabase start

# Only on a disposable local database: reset replaces its records.
supabase db reset
supabase test db
```

Review the generated local configuration before sharing it. The migration and `supabase/tests/profiles.test.sql` will be picked up from the existing directories. The SQL tests roll back fixtures and check anonymous access, ownership isolation, forged owners, upsert behavior, column privileges and database name constraints. Do not run test fixtures against a shared project with real users.

After local review/testing, a team member can apply the migration to the development project using the team's reviewed migration workflow. For a first manual application, open **SQL Editor**, paste the exact contents of `supabase/migrations/20261014000100_account_profiles.sql`, review, and run it once on the development project. Preserve the migration file as the source of truth. Do not rerun it: it intentionally fails if the table already exists. If you later use CLI deployment, reconcile migration history before pushing changes. No command here automatically links or pushes to a remote project.

## Try the complete flow

Backend PowerShell terminal:

```powershell
Set-Location 'C:\Users\Ibrah\OneDrive\Desktop\Rihla\Rihla-dev\Rihla\backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Frontend PowerShell terminal:

```powershell
Set-Location 'C:\Users\Ibrah\OneDrive\Desktop\Rihla\Rihla-dev\Rihla\frontend'
npm.cmd run dev
```

1. Open `http://localhost:5173`, choose **Create an account**, and submit your own test email/password. The page handles confirmation-required responses without claiming a session exists.
2. Open the confirmation email and follow the link. Supabase may sign you in through that link; otherwise return and sign in. Reload to check session restoration.
3. **Backend identity verified** means `/api/me` accepted your session. **Profile database reachable** means the profile query also succeeded with your user token. An empty profile is a successful read, not proof that saving works.
4. Save a display name, then reload. A loaded saved name verifies a real write and subsequent read. Sign out, then sign in as a different fictional test user; the first user's profile must not appear.
5. Sign out. As a separate anonymous check, `Invoke-WebRequest http://localhost:8001/api/me` should return HTTP 401. `/health` stays public.

Do not copy access tokens or passwords into screenshots, logs, commits, or shared reports. Supabase's session SDK manages refresh tokens. Authenticated application requests send only access tokens; the login endpoint transiently forwards Supabase's issued access/refresh tokens to the browser without persisting them.

## Troubleshooting and limits

| Symptom | Meaning / action |
| --- | --- |
| Configured | Local URL/key are present, without proof of a live account/data operation. |
| Backend identity unverified | Check backend startup/CORS, its own environment file, and the current session. |
| Supabase is not configured on the backend | Put the same project URL/key in `backend/.env`, then restart Uvicorn. Frontend variables are not automatically backend variables. |
| Profile storage unavailable | Review/apply the profile migration and ensure the public schema is exposed through the Data API. Do not turn off RLS to fix this. |
| Profile access denied | Check explicit `authenticated` grants and ownership policies. The project setting that disables automatic table exposure is compatible with this migration's explicit grants. |
| Invalid or expired session | Sign out and sign in again. Auth errors return 401; upstream outages/configuration errors return 503. |
| Confirmation email missing | Check spam and the project's email provider settings/rate limits. Hosted development email delivery is restricted; configure SMTP before testing with a wider group. |
| Link opens wrong address | Fix Site URL and redirect allow-list, then request a fresh confirmation. |

Trips, permissions, invitations, preferences/readiness and shared dates have since been implemented. The user chose a Free-plan backend endpoint limit for **five failed logins within fifteen minutes**, with the direct Supabase Auth bypass explicitly acknowledged; see [current verification and limits](sprint-1-verification.md). Hosted verification and team acceptance remain separate. Password recovery is outside the agreed Sprint 1 slice. Local-session sign-out clears/revokes the session via Supabase; a previously copied JWT can remain usable until expiry, so do not describe this as immediate revocation of all access tokens.
