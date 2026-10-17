# Rihla

Group travel planning project for SWE 444, King Saud University.

The agreed Sprint 1 flows are implemented: accounts, trips, invitations, private preferences, Essential/Flexible options, automatic readiness, shared dates and administrator readiness monitoring. The **My trips** workspace follows the new login screen's visual style. Rihla's backend login endpoint enforces the agreed Free-plan failed-attempt limit. Developer checks at `/setup` and `/health` still work without credentials. See [activation, verification and remaining team acceptance](docs/sprint-1-verification.md); local checks do not establish hosted completion.

## What works now

- React, Vite, and TypeScript frontend with a responsive setup page.
- Backend status check with separate checking, connected, and unavailable states and a retry action.
- FastAPI `GET /health`, environment settings, and explicit local-development CORS origins.
- A Supabase browser client module that handles absent or invalid configuration without crashing the page.
- Email/password registration, confirmation feedback, login/logout, and session restoration through Supabase Auth.
- Protected `/api/me` and `/api/profile` endpoints. FastAPI verifies tokens with Supabase Auth and forwards each user's token to the Data API so RLS applies.
- A private profile migration with explicit grants/RLS; the user reported successful live profile saving.
- Protected trip creation, trip lists/details, membership and administrator-only invitation controls, with a matching responsive frontend.
- Private per-trip preferences: departure city, SAR budget, available dates and optional Essential/Flexible inputs, including saved drafts. Apply the separate [preferences migration](docs/member-preferences.md) to enable storage in your development project.
- Automatic Ready/Incomplete with own missing-field explanations, shared-date intersection/duration, and administrator-only status monitoring. Apply the new readiness migration after preferences; see the [Sprint 1 guide](docs/sprint-1-verification.md).
- Backend-mediated password sign-in with five invalid attempts in 15 minutes triggering a 15-minute endpoint cooldown. Supabase still verifies passwords and manages sessions. This accepted Free-plan protection does not cover direct Supabase Auth requests.
- An atomic trips/invitations migration, prepared but **not applied** to the hosted project. Apply it before trying those operations with real accounts; see [the trip setup guide](docs/trips-and-invitations.md).
- In-memory PostgreSQL checks applying the actual migrations and testing RLS, grants, expiry, replacement, revocation, duplicate joins and failure rollback without cloud credentials.
- Dependency lockfiles, automated checks, and a GitHub Actions workflow requiring no Supabase credentials.

The connection card reports configuration only. The account section separately checks backend identity and profile access. `/health` only checks FastAPI. Application HTTP tests mock Supabase; database tests use real PostgreSQL in memory with emulated Auth claims. Trip browser checks used fictional local data, not the hosted project. Hosted trip verification is still pending migration application.

## Project structure

```text
Rihla/
  frontend/
    src/
      components/        Reusable interface pieces
      pages/             Page-level components
      lib/               API and Supabase client helpers
      types/             Shared frontend type definitions
      App.tsx            Frontend entry component
    .env.example         Public frontend configuration examples
    package.json         Commands and dependency declarations
    package-lock.json    Exact resolved frontend dependencies
  backend/
    app/
      api/routes/        Public health and protected account/profile/trip endpoints
      core/              Environment settings and verified account identity
      schemas/           Request/response models
      services/          Request-scoped Supabase HTTP integration
      main.py            FastAPI application creation and CORS
    tests/               Backend checks
    .env.example         Backend configuration examples
    pyproject.toml       Python package, dependencies, and check settings
    uv.lock              Exact resolved backend dependencies
  supabase/
    migrations/          Account, trip and invitation schema, constraints, grants, RLS
    tests/               In-memory PostgreSQL checks, full-Supabase pgTAP checks
    package-lock.json    Locked local database test dependency
    README.md            Supabase concepts and migration conventions
  docs/
    architecture.md      Current structure and intended authentication/data flow
    authentication.md    Dashboard setup, migration review and account test steps
    trips-and-invitations.md  Trip migration, API/security design and checks
    sprint-1-decisions.md Approved product rules, including privacy
  .github/workflows/
    ci.yml               Frontend, backend and in-memory database checks
```

## Prerequisites

- Git.
- Node.js **24.13.1**, recorded in `.node-version`, with npm. Development was checked with npm **11.8.0**.
- Python **3.12.14**, recorded in `backend/.python-version`; uv can download this version for you.
- **uv 0.13.1**, which installs the locked Python dependencies into `backend/.venv`.

Install Node.js using the [official downloads](https://nodejs.org/en/download). If uv is not installed, install it from Windows PowerShell:

```powershell
winget install --id=astral-sh.uv -e
```

Open a new terminal afterward and check `node --version`, `npm.cmd --version`, and `uv --version`. The backend lockfile is managed with uv 0.13.1; newer compatible uv releases may also work. See the [official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/) for alternative installation methods.

Docker and the Supabase CLI are needed for the optional full local Supabase/pgTAP workflow. The in-memory PostgreSQL checks in `supabase/` need only Node/npm, as do the frontend checks.

## First-time installation on Windows

Open PowerShell in the repository root. On this computer, the checkout is located here:

```powershell
Set-Location 'C:\Users\Ibrah\OneDrive\Desktop\Rihla\Rihla-dev\Rihla'
```

On another computer, use the folder where you cloned this repository.

Install the frontend dependencies and copy its configuration example:

```powershell
Set-Location .\frontend
npm.cmd ci
Copy-Item .env.example .env.local
Set-Location ..
```

Install Python and the backend dependencies, then copy its configuration example:

```powershell
Set-Location .\backend
uv python install 3.12.14
uv sync --locked --dev
Copy-Item .env.example .env
Set-Location ..
```

Install the local database test dependency from its separate lockfile:

```powershell
Set-Location .\supabase
npm.cmd ci --ignore-scripts
npm.cmd test
Set-Location ..
```

Copy each example only the first time; keep your existing local configuration on subsequent installs. The Supabase fields can remain empty. No database setup is needed to run the foundation.

`npm.cmd` works in PowerShell even when execution policy prevents running `npm.ps1`. The commands below use the Python executable inside the virtual environment, so activating it is unnecessary.

## Start the applications

Use two PowerShell terminals and keep them open.

**Terminal 1 - backend:**

```powershell
Set-Location 'C:\Users\Ibrah\OneDrive\Desktop\Rihla\Rihla-dev\Rihla\backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

**Terminal 2 - frontend:**

```powershell
Set-Location 'C:\Users\Ibrah\OneDrive\Desktop\Rihla\Rihla-dev\Rihla\frontend'
npm.cmd run dev
```

Open **http://localhost:5173** for the login screen or signed-in trips workspace. Developer connection checks are at **http://localhost:5173/setup**. Missing Supabase configuration produces a setup explanation; trip storage requires its migration before use. Press `Ctrl+C` in each terminal to stop its server.

Backend API documentation is available at **http://localhost:8001/docs** while the backend is running. Port 8001 is used because Windows blocked port 8000 on this computer. Set `VITE_API_BASE_URL=http://localhost:8001` in the frontend environment file.

## Configuration

Frontend values go in `frontend/.env.local`:

| Variable | Purpose | Where to get it |
| --- | --- | --- |
| `VITE_API_BASE_URL` | FastAPI address; use `http://localhost:8001` here | Your local backend address |
| `VITE_SUPABASE_URL` | Supabase project API URL; optional now | The project's Connect dialog |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Public application key; optional now | Connect dialog or project API Keys settings |

Backend values go in `backend/.env`:

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | Environment name; development by default |
| `CORS_ORIGINS` | JSON list of permitted browser origins; defaults include `http://localhost:5173` and `http://127.0.0.1:5173` |
| `SUPABASE_URL` | Same project URL as the frontend; required for account endpoints |
| `SUPABASE_PUBLISHABLE_KEY` | Same public application key as the frontend; required for account endpoints |

For example, `CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]`. Restart the relevant server after changing its environment file.

All `VITE_` variables are visible in browser code. Only the project URL and **publishable** key belong there. Never put a Supabase secret key, legacy `service_role` key, database password, or future AI-provider key in frontend configuration. Local environment files are ignored by Git; the examples contain no credentials. [Supabase key types](https://supabase.com/docs/guides/getting-started/api-keys)

## Verify the setup

From PowerShell, with the backend running:

```powershell
Invoke-RestMethod http://localhost:8001/health
```

Expected response:

```json
{"status":"ok","service":"rihla-api"}
```

Open `/setup`, confirm the connected state, stop the backend and use the retry action. It should change to unavailable. Restart the backend and retry to confirm recovery. Without Supabase settings, the login and setup screens stay usable and explain missing configuration.

Run the checks from the repository root:

```powershell
Set-Location .\frontend
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
Set-Location ..\backend
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
Set-Location ..\supabase
npm.cmd ci --ignore-scripts
npm.cmd test
Set-Location ..
```

GitHub Actions runs these checks on pushes and pull requests after the workflow is committed and pushed. It has not been run remotely as part of this local setup.

Commit both npm lockfiles and `backend/uv.lock` with dependency changes. Use `npm ci` and `uv sync --locked` for reproducible installs; do not hand-edit the lockfiles.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `uv` is not recognized | Install uv, reopen PowerShell, then check `uv --version`. |
| `python` opens the Microsoft Store | Use uv to install Python, then run the explicit `.venv\Scripts\python.exe` command above. |
| VS Code reports `No module named pip` while refreshing packages | From `backend`, run `uv sync --locked --dev`, then refresh the Python Environments package view or reload the VS Code window. Pip is included as a development dependency for that view; keep using uv to manage the project lockfile. |
| Backend unavailable | Confirm the backend terminal is running, open `/health`, and check `VITE_API_BASE_URL`. |
| `/health` works in a browser but the page cannot connect | Check the browser console for CORS errors. The page's exact origin, including port, must be in `CORS_ORIGINS`. Restart the backend after changes. |
| A port is already in use | Stop the other process or choose a new port. Update the API URL or CORS origins to match. |
| Frontend environment changes do not appear | Restart Vite after editing `.env.local`. |
| Supabase says unconfigured or invalid | Check the URL and publishable key together. Empty configuration is expected before you create a project. |
| Supabase says configured | This confirms local settings only. Sign in through the account section for separate backend identity and profile checks. |
| Profile storage unavailable | Apply the reviewed profile migration; see the account setup guide. Keep RLS enabled. |
| Dependency installation fails | Check internet access and registry/proxy settings, then retry the locked installation. |

## Connect and verify the development Supabase project

1. Create or select the team's development project in the Supabase dashboard and arrange individual team access.
2. Put its project URL and publishable key in both local environment files and configure email confirmation/redirects.
3. Review and locally test the profile migration before applying it to the development project.
4. Restart both servers. Register with your own test email, confirm, sign in, and save/reload a private profile.
5. Follow [docs/authentication.md](docs/authentication.md) for exact dashboard settings, migration commands, and verification steps.
6. Apply any unapplied trip, preferences and readiness migrations in order, then follow the [Sprint 1 activation and acceptance checklist](docs/sprint-1-verification.md). Do not rerun migrations already applied. The domain rules and accepted endpoint-only login limit are recorded in [Sprint 1 decisions](docs/sprint-1-decisions.md).

Read [the architecture](docs/architecture.md) for the implemented request flow and [the Supabase guide](supabase/README.md) for beginner terminology and migration conventions. No remote schema, test accounts, deployments, commits, or pushes were created by this implementation.
