# Agreed Sprint 1 rules

Recorded 16 October 2026 from the user's decisions in the project conversation. These decisions supersede conflicting Sprint 0 wording for the remaining Sprint 1 work. They describe intended behavior, not completed implementation.

## Accounts and trip roles

- Users authenticate through Supabase Auth; FastAPI verifies their access tokens.
- The creator becomes both the trip administrator and a participating member.
- Administrator permissions belong to one trip, not to a global platform role.
- Protected trip information requires authenticated membership.

## Member inputs and readiness

- Required inputs: departure city, an individual maximum budget in SAR, and one start/end availability range.
- SAR is the only supported currency in Sprint 1.
- Destinations, interests, flight preferences and accommodation preferences are optional. Empty optional preferences do not block readiness.
- Departure city, budget cap and availability are firm limits.
- Optional preferences may be Essential or Flexible, with no extra flexibility levels. Essential requirements must be respected; adjustments to Flexible preferences need an explanation when proposals are introduced.
- There is no manual Ready button. Valid required inputs determine Ready/Incomplete automatically.
- Members can edit their own inputs throughout planning. Removing required information makes them Incomplete again.

## Shared dates and duration

- Count both endpoints of each date range as calendar days.
- Calculate the intersection of all participating members' ranges, including the administrator's.
- Shared start = latest member start; shared end = earliest member end.
- An intersection exists when shared start is on or before shared end. Duration = shared end minus shared start plus one day.
- There is no separate preferred-duration field and no Essential/Flexible duration setting.
- If required date inputs are missing, show that the calculation is waiting for members; do not invent shared dates.
- If every member has provided valid dates but they do not overlap, report a group date conflict.
- Individual readiness and group date feasibility are separate: all members can be Ready while their dates conflict.
- Recalculate after relevant saves and new joins. A new member without dates makes the full-group calculation pending again.

## Invitations

- One reusable invitation per trip, available as a full link and six-digit code, valid for seven days.
- Only the trip administrator can revoke or replace it. Replacement invalidates the previous link.
- Joining requires a signed-in user and an active invitation.
- Joining twice never creates duplicate membership.

## Privacy

- Members can read and edit their own detailed preferences and budget.
- The administrator sees **only each member's Ready/Incomplete status** for readiness monitoring: no missing-field names, detailed preferences, budgets or individual availability ranges belonging to others.
- Members can see their own missing-field explanations.
- Everyone in the trip can see the group shared-date result. This remains separate from individual readiness monitoring.
- These boundaries must be enforced in API responses and database access, not just by hiding interface controls. Aggregation must not expose the underlying private rows.

## Changes from the submission

- Departure city is confirmed as required.
- Shared dates determine duration, replacing separate preferred-duration input.
- Currency is SAR only.
- Essential/Flexible applies to optional preferences, without additional levels.
- Administrator readiness monitoring exposes status only; the later user correction explicitly removed missing-field names.

## Remaining milestones and limits

The account flow and private profile have been implemented, and the user reported successful live profile saving. The first login/registration design review has also been implemented. This does not establish completion of trip features or all security acceptance criteria.

Trip/membership/invitation storage, private preferences, Essential/Flexible inputs, automatic readiness, administrator status monitoring and shared-date intersection/duration are implemented and tested locally. The new migrations are prepared, not applied remotely by this implementation. Hosted verification remains outstanding in our records. See [Sprint 1 activation and verification](sprint-1-verification.md). AI proposals remain in Sprint 2.

## Accepted login-protection scope (16 October 2026)

The user explicitly chose **Keep Free: limit Rihla's backend login endpoint** after being told that Supabase's provider-wide Password Verification Attempt hook requires Teams/Enterprise and that an endpoint limit cannot prevent direct Supabase Auth calls. Sign-in now goes through FastAPI before Supabase verifies the password; the browser SDK still manages sessions. The backend counts five invalid credential attempts within a rolling fifteen-minute window and then blocks its login endpoint for fifteen minutes. Successful requests do not erase failures in that rolling window. Persistence, concurrent attempts, expiry and provider outages are tested. This is the accepted endpoint-only protection, not a claim of provider-wide account lockout.

No remote migration application, deployment or push is authorized by this document. The earlier constraint against modifying the remote database remains in effect.
