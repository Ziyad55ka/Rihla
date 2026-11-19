# Sprint 2 review and proposed Sprint 3 plan

Reviewed 17 November 2026 against `origin/main` at `2c2048b` and the local **Sprint 0 Submission - Rihla_3.pdf**, sections 2.4, 2.5, 8 and 9. This is a code review and planning proposal, not a claim that hosted acceptance has passed.

## Branch update

Fetched origin and fast-forwarded local `ibrahim` from `fa7b545` to `2c2048b`, preserving its history without conflicts. The team had already merged Ibrahim's earlier work through PR #1. No remote branch was pushed. Local `main` was not moved; the update used the latest `origin/main` directly.

## What Sprint 2 delivers

| Story | Implementation in main | Acceptance assessment |
| --- | --- | --- |
| US-09 Generate proposals | Readiness/conflict checks, up to three researched alternatives, fare-first generation, persistence, retries, progress and stale-input detection | Substantial implementation, but AC01 says generation starts automatically when ready; the UI currently requires an administrator's Generate action. Record team approval for a requirement change or finish the automatic trigger. |
| US-10 Proposal details | Destination, dates, ordered city stays, flights, hotels, transfers and status labels | Implemented in the detail page; verify live data and missing-data cases. |
| US-11 Activities and places | City/date research, attractions, activities, restaurants, descriptions, images, durations, costs and event-date checks | Implemented; hosted/provider acceptance remains to be established. |
| US-12 Activity choices | Private per-member saved choices, removal, version checks and personal/group cost integration | Implemented without requiring day/time assignment. Verify persistence with real test accounts. |
| US-13 Costs and assumptions | Itemized costs, personal/group totals, room scenarios, budget warnings, assumptions and incomplete-price handling | Implemented; estimates and unknown costs need acceptance coverage. Room scenario choice is currently a view, not a saved decision. |
| US-14 Sources and data status | Source links, retrieval times, price-age checks, estimated/unconfirmed labels and warnings | Implemented; source presence does not guarantee current price or availability. |
| US-15 Compatibility | Essential/Flexible checks, trade-offs, group average and least-satisfied-member fit with scoring explanation | Implemented in current code. Earlier handoff says no score, but the later `CompatibilitySection.tsx` now displays it. Some free-text Essential checks remain unverified. |

Additional work includes refreshed teal/sand branding, Arabic presentation, photos, flight price refresh/replacement, provider error handling and automated tests. These do not replace the remaining acceptance evidence.

Evidence entry points: `frontend/src/components/ProposalsPanel.tsx`, `frontend/src/pages/ProposalDetailPage.tsx`, `frontend/src/components/proposal-details/CompatibilitySection.tsx`, `backend/app/api/routes/proposals.py`, `backend/app/api/routes/activities.py`, `backend/app/services/proposal_generation.py`, `backend/app/services/proposal_costs.py`, `docs/activity-acceptance.md`, and `supabase/migrations/20261102*` through `20261106*`.

## Sprint 3 scope

The original roadmap assigns **5-18 November 2026** to **US-16, US-18 and US-19**, under SF-08/SF-09. Since this review is on 17 November, the original review date is tomorrow. Re-estimate remaining work and record any revised dates in Trello; do not claim a fresh full sprint fits before that deadline.

**Scope update confirmed by Ibrahim on 17 November 2026:** Include **US-17 and US-20** (SF-11) in Sprint 3. The current Sprint 3 scope is **US-16 through US-20**. These notification stories are committed scope for this plan, although the original roadmap classified them as optional Sprint 4 work. Record the scope change in Trello and reassess effort and dates.

**Goal:** Members compare the same proposal information; the administrator chooses one option and revises only that option, preserving the alternatives and its earlier versions. Active members receive email links when proposals become ready and when a revised version is saved.

### 1. US-16: Compare proposals

- Add a comparison view with the same categories for every available option: destination, dates/duration, city route, flights, accommodation, transport, itemized costs, group/per-person totals, compatibility and trade-offs.
- Reuse existing cost calculations, source labels and fit scores. Use consistent room assumptions across columns. Show partial/unknown totals explicitly.
- Keep flight visibility and private budgets/preferences consistent with existing member permissions.
- Support fewer than three generated options, stale results, mobile screens and Arabic.
- Acceptance: AC01/AC02 pass using the same dataset, including missing values. Current summary cards provide a starting point but not the full comparison categories.

### 2. US-18: Select one proposal

- Add a persisted selected-proposal reference scoped to its trip and generation, with administrator-only writes and member-readable selection status.
- Provide a Select action and selected badge. Returning or reloading preserves selection and leaves all other options available for reference (AC01).
- Validate membership, administrator role, proposal ownership and freshness on the server/database. Handle concurrent selection attempts atomically.
- Before implementation, agree whether switching the selected option is allowed and what regeneration does to an existing selection. Recommended: permit switching before finalization and require explicit reselection after regeneration.

### 3. US-19: Revise the selected proposal

- Add an administrator feedback form and revision endpoint tied to the selected option and expected current version.
- Reuse research and validation services while restricting the operation to that option. Full-set regeneration is not a substitute.
- Preserve immutable prior versions, feedback, version number, creation time and source/status information. Show the latest version with accessible history.
- Recheck dates, duration, budgets and Essential requirements. Reject or explain incompatible feedback; do not silently weaken Essential requirements.
- Save the new version and latest-version pointer atomically only after validation. On provider failure, keep the last valid version and offer a safe retry without duplicate versions.
- Define how saved activity choices are carried forward: retain only still-valid choices; explain removed/unavailable items and recalculate estimates.
- Acceptance: AC01-AC04 pass; the other options stay unchanged; earlier versions remain readable; non-admin and unrelated-user writes fail.

### 4. US-17: Email when proposals are ready

- After a successful proposal-generation save, notify each active member with one email containing a link to the trip (AC01). Failed generation must not send a ready notification.
- Use a backend email service with a configured sender and server-only credentials. Confirm the provider, sender verification and test recipients during setup.
- Save notification jobs with the successful generation transaction, then deliver asynchronously so an email outage does not lose or roll back proposals.
- Track each recipient and generation event with a unique delivery key; retry failed deliveries without recreating successful jobs. Use provider idempotency where available to prevent duplicate emails after ambiguous timeouts.
- Keep emails brief and free of private budgets/preferences; trip links still require sign-in and membership authorization.
- Define the ready event for partial results: recommended, notify once when the generation successfully finishes with usable saved proposals, including fewer than three, with a link to review the available options.

### 5. US-20: Email when the selected proposal is revised

- After a valid revised version is committed, send each active member an email linking to the trip (AC01). Rejected feedback or failed revisions must not trigger it.
- Reuse the US-17 notification queue and delivery tracking, keyed by proposal version and recipient.
- Opening the selected proposal shows the latest version first, with earlier versions still accessible (AC02); reuse the US-19 history view.
- Verify delivery to active members, retry behavior, duplicate protection, latest-version links and preservation of the plan during email failures.

## Suggested team allocation

Assignments below are proposals based on the Sprint Zero roles, not confirmed ownership.

| Owner | Work package |
| --- | --- |
| Ibrahim | Selection/version schema and protected APIs; transactional notification jobs and delivery tracking |
| Ziyad | Comparison UI, selection actions, revision/history views and Arabic/mobile behavior; confirm hosting readiness as required by D-04 |
| Ali | Feedback-driven revision pipeline, prompt restrictions, revalidation and provider retry behavior |
| Eyad | US-17/US-20 email service, templates, delivery worker and retries; activity-choice/cost integration checks |
| Abdulrahman | Acceptance scenarios, notification recipient/deduplication checks, role/privacy and failure tests, Trello tracking and sprint evidence |

Build order: agree selection/version and notification-event contracts and policy decisions; implement comparison and selection; integrate revision and history; connect generation/revision saves to email jobs; run end-to-end acceptance and fix defects. Comparison and email-service setup can proceed while storage/API contracts are implemented.

## Completion evidence

- Demonstrate Ready group -> proposals -> compare -> select -> feedback -> valid new version -> earlier version; reload to prove persistence.
- Demonstrate proposal-ready email delivery to every active member and revision email delivery after a valid new version is saved. Verify authenticated trip links and latest-first history.
- Simulate email failures and repeated job execution: saved proposals remain usable, successful deliveries are not resent, failed deliveries can retry, and failed generation/revision emits no ready/revised notification.
- Test all roles, stale/concurrent requests, invalid Essential changes, missing prices, provider timeout and failed database writes.
- Confirm the original two alternatives are unchanged and failed revisions leave the selected version usable.
- Run frontend, backend and database checks using locked dependencies; save actual outcomes rather than inferring success from existing tests.
- Verify applicable Sprint Zero NFR targets: revision resilience/time (90% within 10 minutes over at least 20 generation/revision requests), data integrity, revision traceability, standard-operation performance (95% within 2 seconds at 50 concurrent users), and 375-1440px/browser compatibility.
- Confirm required Sprint 2 migrations and backend-only provider credentials exist in the team's test environment. This local branch merge does not apply hosted migrations or verify live providers.

## Scope held for Sprint 4

US-23/US-24 finalization and saved final-plan access, full release testing and deployment. US-21/US-22 withdrawal/role transfer remain optional under the baseline. US-17/US-20 notifications have moved into the confirmed Sprint 3 scope above. Avoid expanding Sprint 3 into booking/payment work. The baseline also excludes fixed daily schedules; any suggested daily display must remain optional and must not make activity selection depend on time slots.

## Local verification on 17 November

- Database: `npm.cmd test` in `supabase` passed all 98 tests.
- Frontend: `npm.cmd test` passed 140 tests in 17 files; 11 suites could not load because the existing local dependency installation lacks `lucide-react` declared in the merged package/lockfile.
- Backend: pytest could not load its application fixture because the existing virtual environment lacks `openai`, declared in the merged Python dependency/lockfile.
- Dependencies were not synchronized during this review. Run the repository's locked install commands before treating these as application test failures. No live-provider or hosted acceptance result is implied.
