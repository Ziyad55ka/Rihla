# Shared member dates and required saves

The 21 October 2026 rules supersede earlier draft-saving and private-availability wording. All authenticated members of a trip can see each member's saved availability dates on their card. Budgets, departure cities and optional preferences remain owner-only. Individual readiness remains visible only to the administrator. Unsaved edits are not shared.

`GET /api/trips/{id}/planning` now includes `member_dates`, a roster of `{user_id, available_start, available_end}`. The database function checks authenticated membership before returning this explicit projection; private-table RLS is unchanged. Missing dates remain null and are displayed as not entered. The normal trip refresh updates these cards after saves and edits.

Every preference save requires a nonblank departure city, a valid positive maximum budget in SAR and both valid travel dates. Empty optional preferences remain allowed. Equal dates are valid; reversed dates and invalid amounts are rejected. A group overlap conflict still warns without preventing an otherwise complete save. Invalid submissions preserve the last saved values and keep the user's edits in the form.

The frontend uses required fields plus validation; FastAPI uses a separate required-input submission schema while reads still accept new/legacy incomplete forms. A PostgreSQL check constraint also rejects incomplete inserts and updates through the RPC or direct Data API. The constraint is added `NOT VALID` so existing incomplete rows remain readable; this does not disable enforcement for new writes. Existing drafts must be completed on their next save. No existing data is deleted or filled with invented values.

## Activate in your development project

1. Confirm all migrations through `20261017000200_invitation_codes.sql` have already been applied. Do not rerun previously applied migrations.
2. Review and run the contents of `supabase/migrations/20261021000100_shared_member_dates_and_required_preferences.sql` once in your development project's Supabase SQL Editor.
3. Restart FastAPI if not using `--reload`, refresh the frontend, and open a trip with two accounts. Save distinct date ranges and verify that both accounts see both ranges on the member cards. An account outside the trip must have no access.
4. Try submitting with each required field missing or only whitespace in the city. Saving must be blocked; optional fields may remain blank. Check that editing dates updates their card and the shared interval after saving.

No remote database changes were made by this implementation. Without this migration, the updated backend rejects the old planning response as unavailable instead of reporting missing dates as verified. Run the existing frontend, backend and local PostgreSQL checks; these do not verify a hosted Supabase connection.
