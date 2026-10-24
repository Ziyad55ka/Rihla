# Rihla landing and planning design

Updated 17 October 2026. This supersedes the earlier Karate visual direction.

The user selected the [Fintech SaaS template by Kedhareswer Naidu](https://21st.dev/@kedhareswer/templates/fintech-saas-landing-page-template). Rihla adapts its warm cream, forest green, large regular typography, fine route lines, soft card shadows and rectangular buttons to group travel. The illustrations use local SVG/CSS; the earlier generated photograph remains in the repository but is no longer the hero image. No template installation, external font request or additional runtime dependency is needed.

The later navbar reference uses a floating white capsule, left wordmark, centered links and a dark rounded action. `navbar.css` shares that style across public, account and trip headers. On narrow screens the navigation links wrap into a second row inside the rounded header; all navigation remains available.

## Pages and navigation

- `/`: public landing page with the slogan “Good company. Great journeys.”, Login/Sign up, Create/Join actions and an About section. A restored signed-in session opens the trips workspace.
- `/login`, `/signup`: account screens. Existing Supabase registration/confirmation and backend-mediated sign-in are retained.
- `/trips`: cards for the caller's trips, showing title, role, member display names and current planning stage.
- `/trips/new`, `/trips/join`: protected create/join pages. An anonymous visitor signs in first and continues the intended action. Invitation codes remain in the fragment/session storage rather than the server URL. Pending actions use an allowlist of internal routes.
- `/trips/{id}`: shared dates, group stage and a card for each member. Only administrators receive/display individual Ready/Incomplete statuses. Enter/Edit preferences appears above the member cards. Invitation controls remain administrator-only.
- `/trips/{id}/preferences`: separate private form. Saving stays on the form with confirmation; Back returns to the refreshed trip. Direct URLs, refresh and browser Back/Forward work through a small History API helper.
- `/account`, `/setup`: account settings and developer connection checks.

Vite handles local page refreshes. A future static deployment must rewrite application URLs to `index.html`; no hosting configuration was changed here.

## Planning stages

The cards and detail screen derive their display from current saved data:

1. **Dates do not overlap** when the saved group date result conflicts.
2. **Waiting for your preferences** when the caller's required inputs are incomplete.
3. **Waiting for members’ preferences** when the caller is Ready but other required inputs or dates remain incomplete.
4. **Waiting for AI generation** only when every member is Ready and group dates overlap. The adjacent copy explains that AI planning arrives in Sprint 2; no generation is performed.

The user defined **Trip finished** as an AI-generated plan approved by the group. It cannot occur in Sprint 1 and no fabricated completion state is displayed or stored.

## Date checks and activation

After both candidate dates are valid, the form debounces a read-only `POST /api/trips/{id}/date-check`. FastAPI verifies identity and calls `rihla_check_trip_dates` with the user's token. It checks the candidate against complete saved ranges of other members, excluding the caller's stored range. Only `available`, `conflict` or `pending` is returned by this endpoint. A conflict warns without blocking a complete save. Obsolete requests are aborted and results are tied to the candidate range. Save retries the check. Shared dates and readiness always use saved values. As of 21 October, member cards also show individual saved ranges, and incomplete saves are blocked; see [the updated rules and migration](shared-member-dates.md).

Apply **`supabase/migrations/20261017000100_planning_overview.sql`** once in the development project's SQL Editor, after the previous four migrations. It adds the date-check function and extends planning status with `all_members_ready` and the caller's `has_saved_preferences`. Existing records, private RLS policies and status-only administrator access are retained. This implementation did not modify a hosted database. Without the migration, the backend reports planning unavailable instead of inventing a stage. Restart FastAPI if it does not use `--reload`.

Startup from two PowerShell terminals, starting at the repository root:

```powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

```powershell
Set-Location .\frontend
npm.cmd run dev
```

Open `http://localhost:5173`. If a saved session opens My trips, sign out to review the public landing page. Real email confirmation and hosted integration remain separate team checks.

## Verification

Local checks passed: 140 backend tests, 78 frontend tests and 46 PostgreSQL tests, plus Ruff, ESLint, TypeScript and production build checks. Browser checks used real React/FastAPI with the disposable fictional Auth/PostgreSQL facade, including create through login, invitation link and six-digit code generation, joining by code, save/edit, reload, browser Back, candidate conflict before save, saved conflict, resolving an overlap to four days and role-specific member cards. Tested layouts at 375px and 1440px had no horizontal overflow. Screenshots with fictional accounts are in ignored `.artifacts/redesign-review/`. These checks do not establish live Supabase connectivity or multi-browser course acceptance.
