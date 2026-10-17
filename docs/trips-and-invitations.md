# Sprint 1: trips, membership and invitations

## Implemented behavior

- The signed-in home is now **My trips**, using the login screen's white/coral visual style. It shows only trips the caller belongs to, with real empty/loading/error states.
- Create a named trip with an optional description. Creation atomically adds the signed-in creator as a participating administrator.
- Open a trip to see its name, description and member display names/roles. Emails and private profile rows are not exposed to other members. Display names are deliberately shared within a trip.
- Only the administrator can create, replace, inspect the status of, or revoke the trip's invitation.
- Each invitation is reusable for seven days. Creating a new link invalidates the previous link. Revocation blocks new joins without removing existing members.
- Join with a link or its code. Repeated joins return the existing membership.
- Invitation links use `/#invite=...`, keeping the token out of HTTP access-log URLs. The pending code is temporarily kept in session storage through sign-in, then removed after joining or cancelling. Authentication callback fragments remain owned by Supabase.
- The invitation panel displays the raw link only immediately after issuing it. After a reload, the administrator can replace it to obtain a new copy; raw tokens are not recoverable from storage.
- The existing private-profile account view is accessible through **Your account**. Developer connection checks remain available at `/setup` without requiring an account or Supabase configuration.

Private inputs and Essential/Flexible options have subsequently been added in the [member preferences milestone](member-preferences.md), with a separate migration. Readiness, shared dates, trip editing/deletion, member withdrawal and administrator transfer remain outside this trip/invitation milestone. No fake readiness statuses or group travel dates are shown.

## Database and access design

Migration: `supabase/migrations/20261016000100_trips_and_invitations.sql`, after the existing account profile migration.

| Table | Purpose | Access |
| --- | --- | --- |
| `trips` | Title, description, creator and creation time | Members can read; writes use guarded functions |
| `trip_members` | Unique membership per user and trip | Members can read the roster; direct writes are denied |
| `trip_invitations` | One token hash/expiry/revocation record per trip | No direct client access, including for administrators |

The administrator is derived from the trip creator; callers cannot submit a role or owner. There are no broad insert/update/delete grants that let a caller bypass FastAPI by using the Data API directly. Each exposed RPC checks the current Auth identity. Anonymous Supabase Auth accounts are rejected as well as unauthenticated requests.

Ordinary reads use RLS. Narrow `SECURITY DEFINER` functions are needed for atomic writes, invitation lookup before membership, and roster names without granting access to other users' private profile rows. They fix an empty search path, qualify application tables and check membership/administrator ownership explicitly. A helper in the unexposed `rihla_private` schema avoids recursive membership policies.

Invitation secrets contain 244 random bits from two cryptographically generated UUIDs. Only a SHA-256 hash is stored. Join, replace and revoke acquire the trip lock before the invitation lock, and joining rechecks expiry/revocation after acquiring the lock. A unique membership key prevents duplicates. This lock design is present; the single-engine test suite does not simulate concurrent independent PostgreSQL connections.

FastAPI still verifies each token through Supabase Auth, then calls the RPC with the publishable key plus that same user's token. No service-role key or browser-supplied user ID is used. API responses are marked `Cache-Control: no-store`.

Official references: [Supabase database functions](https://supabase.com/docs/guides/database/functions), [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security).

## Apply the reviewed development migration

The new trip migration has **not been applied to the hosted project**. Until it is applied, the new screens report that trip storage is unavailable. Existing authentication and profiles continue to work.

1. Confirm the account migration already exists; the user reported successful live profile saving.
2. Review the new trip migration and run local checks below.
3. In the intended **development** Supabase project, open **SQL Editor**, paste the exact contents of `20261016000100_trips_and_invitations.sql` and run it **once**. Do not rerun the earlier profile migration.
4. Keep the public schema available through the Data API, with RLS enabled. The migration grants the required RPC/table privileges explicitly even if automatic exposure of new tables is disabled.
5. Restart the backend if necessary, refresh `http://localhost:5173`, and sign in. Try creating a trip, generating an invitation, and joining as a second user in another browser profile.
6. Verify that an ordinary member has no invitation controls, replacement invalidates the older link, and revocation blocks a new user. Rejoining must keep the membership count unchanged.

No hosted tables, accounts, policies or records were changed during implementation. If using the CLI later, reconcile manual migration history before applying already-run SQL again.

## Run checks on Windows

From the repository root:

```powershell
Set-Location .\supabase
npm.cmd ci --ignore-scripts
npm.cmd test
Set-Location ..\backend
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
Set-Location ..\frontend
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
Set-Location ..
```

`supabase/package-lock.json` pins PGlite, an in-memory PostgreSQL engine. The test fixture emulates only Supabase's Auth user table, roles and JWT claim helpers, then applies the actual migration files and tests PostgreSQL RLS, grants, functions, constraints and rollback behavior. It does not validate hosted Supabase configuration, the real Auth service, PostgREST implementation details, or concurrent independent sessions. Existing pgTAP tests remain available for a full local Supabase setup. GitHub Actions now also runs the in-memory database suite without cloud credentials.

Backend HTTP tests mock Supabase responses. Browser smoke checks used the actual React app and FastAPI with a test-only local Auth/RPC facade over the in-memory database, including creation, joining, repeated joins, replacement, revocation and role-specific controls. No real signup emails were sent. Screenshots under ignored `.artifacts/trips-review/` contain fictional local data.

## Optional isolated browser preview

`supabase/tests/preview-server.mjs` is a **test-only** loopback server with fictional users and a disposable in-memory database. It is never imported by the application or included in its build. Use three separate PowerShell terminals after installing dependencies:

```powershell
# Terminal 1, from supabase/:
node tests/preview-server.mjs
```

```powershell
# Terminal 2, from backend/. These variables affect this terminal only.
$env:SUPABASE_URL='http://127.0.0.1:54329'
$env:SUPABASE_PUBLISHABLE_KEY='sb_publishable_local_preview'
$env:CORS_ORIGINS='["http://localhost:5174"]'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8101
```

```powershell
# Terminal 3, from frontend/. These variables affect this terminal only.
$env:VITE_API_BASE_URL='http://127.0.0.1:8101'
$env:VITE_SUPABASE_URL='http://127.0.0.1:54329'
$env:VITE_SUPABASE_PUBLISHABLE_KEY='sb_publishable_local_preview'
npm.cmd run dev -- --port 5174
```

Open `http://localhost:5174`. Fictional accounts are `alice@example.test`, `bob@example.test` and `carol@example.test`, all with the fixture-only password `PreviewOnly123!`. The facade does not support real registration or email. Stop all three processes with Ctrl+C and close these terminals after testing so preview variables cannot accidentally be reused for normal startup. Closing the server discards every fixture record. Use the normal project configuration and ports 5173/8001 for your real development project.
