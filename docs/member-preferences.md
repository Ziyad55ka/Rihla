# Sprint 1: private member preferences (US-04 / US-05)

Each participating member, including the administrator, has a **Your trip. Your preferences.** form inside a trip. It follows the existing white/coral design and stacks on mobile.

## What works

- Save and edit departure city, maximum individual budget in SAR, and one availability start/end range.
- Save incomplete drafts, including clearing previously entered required fields. Null budget/dates and a blank departure city deliberately represent incomplete input.
- Save optional destinations, interests, flight and accommodation preferences as short free text. Each category is Essential or Flexible; blank optional fields are allowed. Sprint 2 will interpret these inputs when proposals are built.
- Reject nonpositive budgets, more than two fractional digits, oversized inputs, invalid calendar dates, reversed ranges and unknown importance values. Equal dates are valid. Both range endpoints count as available days.
- Preserve edits after a failed save; show loading, retry, saving, unsaved and saved feedback. Saved values are loaded again when the trip is reopened.
- All amounts use SAR. The storage/API limit is below 10,000,000,000 SAR with at most two fractional digits (12 total decimal digits); this is a storage bound, not a recommended travel budget. There is no currency conversion.

## Request and privacy design

`GET /api/trips/{trip_id}/preferences` returns the current member's saved inputs or an empty draft. `PUT` replaces their inputs; omitted fields reset to their empty defaults. The UI always submits the complete editable object. Response metadata includes `currency: "SAR"` and `updated_at` (null before the first save). Budget responses use decimal strings to preserve money precision.

The request cannot specify a user ID, administrator role, currency or update timestamp. FastAPI verifies the Supabase access token and forwards that same token to the two `SECURITY INVOKER` RPCs. Normal reads and writes retain the caller's identity and RLS applies.

`public.member_preferences` has a composite trip/user primary key and a foreign key to existing membership. RLS allows only the owner of a row who belongs to its trip to select, insert or update it. No direct delete grant exists; clear a draft through the form. Anonymous requests and anonymous Auth accounts are denied. An administrator has no override to read another member's inputs. Constraints also reject invalid writes made directly through the Supabase Data API. See [Supabase's RLS documentation](https://supabase.com/docs/guides/database/postgres/row-level-security).

The optional JSON objects contain only `value` (up to 500 characters) and `importance` (`Essential` or `Flexible`). Departure city has a 100-character storage bound. Dates are calendar dates, not times or timestamps. The API accepts YYYY-MM-DD only. The database bounds dates to years 0001–9999.

## Enable in your development Supabase project

No hosted database changes were made during implementation.

1. Confirm the account and trips/invitations migrations have already been applied. If the trip screen works, do not rerun those files.
2. Open `supabase/migrations/20261016000200_member_preferences.sql`, review it, then run its exact contents **once** in the intended development project's SQL Editor.
3. Restart the backend if it is not running with `--reload`, refresh the frontend and open a trip. Select **Enter preferences** above the member cards to open the separate preferences page; after saving, the action becomes **Edit preferences**. See the [latest design and candidate-date checks](frontend-redesign.md) for the additional planning overview migration.
4. Save a draft, leave and reopen the trip, then check that the values persist. Test a second account in another browser profile. It must see its own blank inputs, not the first user's inputs, and cannot change the first user's row.

If the screen reports **Preference storage is unavailable**, check that the migration ran successfully after the earlier migrations and that the Data API still exposes the public schema. Do not remove RLS or use a service-role key to work around permissions.

Normal Windows startup commands remain in the repository README. No new dependencies or environment values are needed.

## Checks and remaining work

Backend tests mock upstream Supabase HTTP; database tests apply the actual SQL migrations in disposable PGlite PostgreSQL with emulated Auth roles/claims. They exercise persistence, updates/clearing, draft/single-day dates, invalid-save rollback, separate trips, anonymous/nonmember denial and administrator/member privacy through direct table access and RPCs. Frontend checks cover payload ownership, cancellation and budget/date validation. Run the existing frontend, backend and database check commands from `docs/trips-and-invitations.md`.

Browser checks use the real React/FastAPI apps with the existing local test-only Auth/RPC facade and fictional accounts. They do not verify hosted Supabase Auth, email delivery or PostgREST configuration. Review screenshots are stored in ignored `.artifacts/preferences-review/`.

Automatic Ready/Incomplete calculation, administrator readiness statuses, shared-date intersection/duration and the agreed backend endpoint login limit have since been implemented; see [Sprint 1 verification](sprint-1-verification.md). Readiness refreshes after a successful preference save. Hosted activation is still separate. Essential preference enforcement in proposals remains Sprint 2.
