# Supabase in Rihla

Supabase supplies Auth and PostgreSQL storage. The `/setup` page and health endpoint work without credentials. Accounts/private profiles are implemented and the user reported successful hosted profile saving. Trip creation, membership and seven-day invitations are implemented in a second migration, which is not yet applied remotely. Follow [the trip guide](../docs/trips-and-invitations.md) for that migration and its access model.

`npm ci --ignore-scripts` and `npm test` in this folder run in-memory PostgreSQL test cases without Docker or cloud credentials. The actual migrations are applied, with a small fixture emulating Supabase Auth claims/roles. The existing pgTAP file is separate and still requires a full local Supabase environment; it is not what the npm suite executes.

## Terms for a first-time user

| Term | Meaning |
| --- | --- |
| Project | One Supabase environment containing services such as Auth and a database |
| PostgreSQL | The database engine Supabase uses |
| Table and row | A collection of one kind of record, and one record within it |
| Primary key | A unique identifier for a row |
| Foreign key | A database-enforced link to a row in another table |
| Auth user | An account managed by Supabase Auth; application profile fields are separate from credentials |
| Session / access token | A signed-in session includes a short-lived token identifying the user to protected services |
| Publishable key | Identifies the application; does not by itself identify a signed-in user |
| RLS | Row Level Security: SQL policies determining which rows a database user can access |
| Migration | A versioned SQL file describing a database change |
| Seed data | Fictional sample records for repeatable local development and testing |

Supabase's [database overview](https://supabase.com/docs/guides/database/overview) introduces its PostgreSQL tools. [Password authentication](https://supabase.com/docs/guides/auth/passwords) explains how Auth manages accounts; do not create an application password column.

## Connect a development project

No cloud actions are part of this setup. When the team is ready:

1. Create or select the team's development project in Supabase. Keep development and test data separate from any future production environment.
2. Open the project's **Connect** dialog or **Settings > API Keys**. Obtain its project URL and **publishable** key. A database password, signing secret, or secret/service-role key is not the frontend key. See [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys).
3. From the repository root, copy examples if local files do not already exist:

   ```powershell
   if (-not (Test-Path -LiteralPath .\frontend\.env.local)) {
       Copy-Item -LiteralPath .\frontend\.env.example -Destination .\frontend\.env.local
   }
   if (-not (Test-Path -LiteralPath .\backend\.env)) {
       Copy-Item -LiteralPath .\backend\.env.example -Destination .\backend\.env
   }
   ```

4. Edit `frontend/.env.local` with your own project values:

   ```dotenv
   VITE_API_BASE_URL=http://localhost:8001
   VITE_SUPABASE_URL=https://your-project-ref.supabase.co
   VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_your_project_key
   ```

   The last two values above are placeholders. Do not paste them literally. For the present setup, leaving them blank is valid.

5. Set `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` to the same project values in `backend/.env`. These are required for account endpoints, while `/health` stays usable without them.
6. Configure email confirmation and local redirect URLs, review/test the profile migration, and restart both applications. The connection card confirms configuration only; signing in triggers separate checks of backend identity and profile access. See [the account guide](../docs/authentication.md).

All `VITE_` variables are public to the browser. Secret keys and legacy `service_role` keys bypass RLS and must stay out of the frontend, repository, screenshots, and logs. The normal Rihla data path uses the publishable key plus the user's access token, including from FastAPI. See [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys).

Email signup retains confirmation; configure your local frontend as the allowed site/redirect URL. Supabase's built-in email delivery is intended for restricted testing; review [custom SMTP](https://supabase.com/docs/guides/auth/auth-smtp) before inviting the whole team. Use individual fictional test accounts and keep their passwords out of Git.

## Plan access before creating tables

The profile migration restricts read/insert/update to the owning Auth UUID. Anonymous users have no grants, creation timestamps cannot be written, and no direct delete is granted. The trip migration adds member-only reads and guarded administrator/join functions; see [the access design](../docs/trips-and-invitations.md).

PostgreSQL grants authorize operations on a table; RLS policies then restrict rows. Enable RLS on every application table exposed through the Data API and deliberately grant only the required operations. Policies and grants belong in the same migration. Add allow-and-deny tests, including protection against changing ownership or a member's trip role. Test `SELECT`, `INSERT`, `UPDATE`, and `DELETE` as applicable. See [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security).

Do not assume that running a backend or hiding buttons secures the Data API. Tests should cover anonymous callers and unrelated users; future trip tests must also cover members and trip administrators. The implemented FastAPI profile path passes the user's verified token so PostgreSQL sees that user's identity.

## Migration conventions

`migrations/20261014000100_account_profiles.sql` creates account profiles; `20261016000100_trips_and_invitations.sql` adds trips/memberships/invitations; `20261016000200_member_preferences.sql` adds owner-only member inputs and invoker RPCs; `20261016000300_readiness_and_shared_dates.sql` adds derived readiness and a protected group-date/status aggregation function. `20261017000100_planning_overview.sql` extends that status with a group readiness boolean, the caller's saved-preferences indicator and a read-only candidate-date check. `20261017000200_invitation_codes.sql` adds hashed six-digit invitation codes alongside the existing full links. Apply only migrations that have not already run, in filename order. This implementation has not applied migrations remotely; see [Sprint 1 activation](../docs/sprint-1-verification.md). `tests/database.test.mjs` rebuilds all migrations in memory and checks access, atomicity, expiry, replacement, code/link joins, private input persistence, readiness, shared dates and integrity. `tests/profiles.test.sql` is the separate full-Supabase pgTAP suite.

The date-check RPC compares an unsaved range with the complete saved ranges of all other members and returns only `available`, `conflict`, or `pending`. A known conflict is reported even when another member has not entered dates. It does not return another person's dates or save the candidate. Planning status still gives administrators only each member's readiness; ordinary members receive no readiness roster.

For subsequent changes:

1. Write a focused migration named `YYYYMMDDHHMMSS_short_description.sql` in `supabase/migrations/`.
2. Include the necessary table constraints, indexes, least-privilege grants, and RLS policies together. Document the feature and access rules it implements.
3. Add matching permission and integrity checks under `supabase/tests/`. Use fictional data and distinct users/trips so an accidentally broad policy fails a test.
4. Run and review the migration and tests in an isolated local/test environment before merging. Verify rebuilding from the migration history.
5. After a migration is shared/applied, add a new migration for a change rather than rewriting shared history. Avoid dashboard-only structural edits; capture any such change in reviewed migration history.

The naming and history workflow follow [Supabase migrations](https://supabase.com/docs/guides/local-development/database-migrations). Database tests can use pgTAP through the CLI; see [Supabase testing](https://supabase.com/docs/guides/local-development/testing/overview).

## Optional local database workflow

Application checks require neither Docker nor Supabase CLI. To execute the actual SQL tests, add a pinned team CLI version and a Docker-compatible runtime, initialize local configuration, review the generated files, start local services and use the existing migration/test directories. Follow [Supabase local development](https://supabase.com/docs/guides/local-development/cli-workflows).

In that local environment, `supabase db reset` rebuilds the database from migration history and replaces local records. Use it only with disposable local data. `supabase test db` runs the SQL tests after local configuration and services are initialized. Remote linking, migration pushes and production changes require a separately agreed deployment workflow.

If seed data is later useful, keep fictional sample data separate from schema statements and never include real account credentials. See [Supabase seed data](https://supabase.com/docs/guides/local-development/seeding-your-database).
