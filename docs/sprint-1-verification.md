# Sprint 1 implementation and verification

The agreed Sprint 1 application flows are implemented: accounts, trips, invitations, member preferences, Essential/Flexible options, automatic readiness, shared-date intersection and administrator readiness monitoring. This is a local implementation/test result, not a declaration that the hosted project or course acceptance exercises have been completed.

## Readiness and dates

Open a trip to see the planning stage, shared dates and member cards. **Enter/Edit preferences** opens a separate private page. See [the 17 October redesign](frontend-redesign.md) for page routes, trip card statuses and candidate-date warnings. Readiness is derived from current saved inputs, with no manual Ready button or writable readiness column. A member is Ready when departure city, a positive SAR budget and both valid availability dates are present. Blank optional preferences never prevent readiness. Clearing required information changes the member back to Incomplete after saving.

The shared period includes every member, including the administrator. It is the latest start date through the earliest end date. Both endpoints count, so 10–15 November is six days and touching endpoints give one day. There is no separate duration preference.

- **Waiting for dates:** at least one member has not saved both dates. No partial overlap or other members' ranges are returned.
- **No shared dates:** all dates are saved but do not overlap. Individual members may still all be Ready.
- **Shared dates found:** return only the intersection and its inclusive duration.

`GET /api/trips/{trip_id}/planning` calls `rihla_get_planning_status` using the verified user's token. The narrow database function checks membership before aggregating private rows. The response contains the caller's own missing-field names, the group's date result, and an administrator-only list of `{user_id, status}`. Ordinary members receive `member_readiness: null`. No other user's budget, preferences, individual availability or missing-field names are returned. Direct table access remains owner-only under RLS.

Results recalculate on every database query. The frontend refreshes immediately after a preference save and checks for changes every 15 seconds while the trip page is visible, plus on focus or **Refresh group / Refresh planning**. Background refreshes do not reset preference drafts. Unsaved edits do not change the saved readiness result.

## Free-plan login protection

The user explicitly chose to keep the Supabase Free plan and limit **Rihla's backend login endpoint**, acknowledging that it cannot prevent direct requests to Supabase Auth. Supabase documents its provider-wide Password Verification Attempt hook as Teams/Enterprise only: [Auth Hooks availability](https://supabase.com/docs/guides/auth/auth-hooks).

The sign-in screen now sends credentials to `POST /api/auth/login`. FastAPI applies the limit and immediately forwards credentials to Supabase Auth for verification. It returns only the issued access/refresh tokens; the browser installs them with `supabase.auth.setSession`. Supabase still manages password hashing, sessions, refresh and sign-out. Registration/confirmation still use the Supabase browser SDK. Passwords and sessions are never stored by Rihla's limiter or written to logs.

The limit is per normalized email address (trimmed/lowercase for the limiter). It counts invalid-credential responses in a **rolling 15-minute window**. The fifth failure starts a **15-minute cooldown** and returns HTTP 429. Further requests, including a correct password, are rejected before calling Supabase until the cooldown expires. Successful requests and provider outages do not add failures; success does not erase failures still in the rolling window. Errors include `Retry-After`. No session is installed when login is refused, and there is no frontend fallback around the limiter.

The limiter stores SHA-256 email hashes and timing metadata in ignored `backend/.local/login-limits.sqlite3`; it stores no plaintext emails, passwords or tokens. `LOGIN_LIMIT_DB` can override the path. Short SQLite transactions serialize updates across local workers; a 60-second per-account reservation prevents concurrent requests bypassing the counter without holding a database lock during the network request. An abandoned reservation expires, and an expired attempt cannot overwrite a new attempt. Inactive metadata is pruned after a day on subsequent login requests.

No new dependency or secret is required. Keep the file on a local persistent disk and keep it out of Git. Separate backend hosts each have their own limit unless given a shared implementation; local SQLite is not a distributed deployment solution. The accepted endpoint-only protection does **not** lock Supabase accounts, existing sessions, refresh tokens, or direct Supabase Auth requests. Do not describe it as provider-wide account lockout. Supabase's own limits continue to apply separately: [provider rate limits](https://supabase.com/docs/guides/auth/rate-limits).

## Enable the development project

No hosted database or Auth settings were modified by this implementation. No deployment or push was performed.

Apply only migrations that have **not already run**, in order, in your development project's Supabase SQL Editor:

1. `20261014000100_account_profiles.sql`
2. `20261016000100_trips_and_invitations.sql`
3. `20261016000200_member_preferences.sql`
4. `20261016000300_readiness_and_shared_dates.sql`
5. **`20261017000100_planning_overview.sql`** — group readiness, own saved flag and read-only candidate-date checks for the redesign.
6. **`20261017000200_invitation_codes.sql`** — hashed six-digit invitation codes alongside the existing full invitation links.

Do not rerun earlier migrations that already succeeded. The readiness migration needs preferences and trips to exist first. It adds functions/grants only; existing preferences are evaluated automatically. No manual Ready flags or data backfill is needed.

Restart FastAPI if it is not running with `--reload`, refresh Vite, sign in and open a trip. Sign-in now needs FastAPI running, as well as Supabase configuration. If planning is unavailable, check that the readiness migration succeeded. If login protection is unavailable, check that the backend can write to its configured local metadata path; do not disable protection to work around a storage failure.

Normal PowerShell startup remains:

```powershell
# Backend terminal, from the repository root:
Set-Location .\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

```powershell
# A separate frontend terminal, from the repository root:
Set-Location .\frontend
npm.cmd run dev
```

## Verification evidence and limits

Automated checks cover real PostgreSQL functions/policies in disposable PGlite with emulated Auth claims, backend HTTP behavior with mocked upstream responses, and frontend helpers. They do not establish hosted Supabase Auth/PostgREST behavior. The backend login tests use isolated temporary SQLite files and verify rolling-window boundaries, cooldown expiry, persistence, account independence, concurrent reservation exclusion, abandoned attempts, outages and storage failure. Planning checks include pending/conflict/available states, leap days, single-day intersection, changed inputs, new/duplicate joins, privacy and rollback.

The 17 October 2026 local run passed **140 backend tests, 78 frontend tests and 46 database tests (264 total)**, Ruff lint/format checks, ESLint, TypeScript/build checks and a production build. The hosted service and separate full-Supabase pgTAP suite were not run.

Browser checks use real React and FastAPI with the existing fictional local Auth/RPC facade. They verified backend-mediated sign-in, creation, invitation link/code generation, joining with the six-digit code, invitation handoff through sign-in, automatic Ready, conflict, resolving an overlap to four days, reverting to Incomplete, administrator statuses, ordinary-member privacy and the fifth failed login message. Screenshots are in ignored `.artifacts/sprint1-review/` and `.artifacts/redesign-review/`. Layout checks at 375px and 1440px showed no horizontal overflow in the tested in-app Chromium browser. Real email confirmation and the hosted project were not exercised in these checks.

Use the frontend/backend/database check commands from the README or `docs/trips-and-invitations.md`. Existing GitHub Actions jobs run the new tests without real credentials.

## Team acceptance checklist

| Story | Implementation | Remaining team verification |
| --- | --- | --- |
| US-01 accounts | Registration, confirmation feedback, sign-in/out, session restoration, agreed endpoint login limit | Actual email delivery, two real confirmed accounts, restart/cooldown test |
| US-02 create/invite | Atomic trip+administrator membership, seven-day links and six-digit codes, replace/revoke | Apply migrations and exercise hosted permissions |
| US-03 join | Signed-in join by code or link, invitation handoff, duplicate-safe membership | Friend joins with their own account using both methods |
| US-04 preferences | Private draft/save/edit form, SAR budget and one date range | Save/reopen with both hosted accounts |
| US-05 importance | Optional Essential/Flexible flags | Confirm saved values persist; enforcement in proposals is Sprint 2 |
| US-06 shared dates | Pending, conflict and inclusive overlap/duration | Check agreed example ranges with the group |
| US-07 readiness | Derived Ready/Incomplete, reverses after required inputs are cleared | Verify real-account edits and new joins refresh correctly |
| US-08 administrator | Status-only member readiness view | Member has no readiness roster or access to others' private inputs |

The course's five-representative-user usability exercise and Chrome/Edge/Safari checks still need human/team evidence; automated tests are not substitutes. Record each acceptance result, screenshots without credentials, tester/browser/date and defects before declaring Sprint 1 accepted. AI proposals, comparison, revisions, final plans, payments, withdrawal and administrator transfer remain outside this Sprint 1 implementation.
