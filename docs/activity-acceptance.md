# US-11 / US-12 acceptance review — mock-backed implementation

Scope source: Sprint 0 Submission - Rihla (2).pdf, pages 13–14.
Reviewed locally; the user approved publishing this revision to Ziyad only. Do not merge into main or modify teammate branches.

| Criterion | Implementation | Verification |
| --- | --- | --- |
| US-11-AC01 | City suggestions explicitly carry activity, attraction or restaurant categories. Legacy suggestions default to activity. Each mock city contains all three. Category filters do not erase choices. | Schema category coverage tests; browser restaurant filter shows only the restaurant. |
| US-11-AC02 | Suggestion cards show description, location, approximate price, duration and image when supplied. | Card-rendering tests for all fields and a supplied image. |
| US-11-AC03 | Missing prices are labelled Not available, not free; missing or failed images show a placeholder. Explicit zero-price activities remain free. | Unknown/free calculation tests, placeholder checks and image failure handling. |
| US-11-AC04 | Fixed event dates must be valid calendar dates inside the city stay. The frontend also marks and disables unsuitable events if unvalidated data is received. | Backend rejects out-of-stay dates; frontend renders unsuitable label and rejects selection; mock includes an in-period dated event. |
| US-12-AC01 | Explicit save replaces the member's saved choices for this trip/proposal/version. Removing choices uses the same save flow. | Browser add, save, remove, reload; mock store tests; authenticated route tests; existing local PostgreSQL permission and persistence tests. |
| US-12-AC02 | Saving requires version and activity IDs only. There is no member-chosen day/time field. A displayed event date describes the event, not a scheduling requirement. | Request-schema and route tests save without day/time; UI has no scheduling controls. |
| US-12-AC03 | Saved known activity prices are included in the relevant per-person proposal estimate, not only a detached subtotal. The API returns the estimate on read/save; the mock returns the same contract. | 3000.00 base + 85.50 attraction + 65.00 restaurant = 3150.50; removing restaurant gives 3085.50; reload retains 3150.50 after re-adding. Backend and frontend tests cover removal, unknown prices, return costs and multi-city stays. |

## Cost integration boundary

`ActivitySelections.estimate` identifies the proposal and version and contains
base component amounts, saved activity amount and the updated total. It is
calculated from the authenticated caller's filtered proposal, not from request
prices. The write is performed only after the estimate can be calculated, and
the database still checks proposal/version/membership before saving.

The UI displays only the base proposal estimate, saved activity cost and resulting
total. This is the US-12 contribution to the estimate; it does not implement the
rest of US-13 (group totals, shared-room management, extra expenses) or US-23/24
(finalizing and accessing a saved final plan). The established baseline assumes
one room per person, uses full-route flight prices once, and per-person transfers.
Unknown prices produce a partial estimate; the original budget label is explicitly
marked as applying before chosen activities. No private budget is exposed.

## Validation result

- 382 backend tests passed; Ruff lint and formatting passed.
- 113 frontend tests passed; TypeScript, translation coverage and production build passed.
- Existing local database tests remain applicable; this revision adds no SQL migration.
- Browser verified category filtering, explicit save, removal, refresh persistence,
  updated proposal total and a 390px viewport without horizontal overflow.

Data generation and externally sourced details are deliberately mocked, as
requested. Cloud credentials and real Supabase deployment were not used. These
results establish the local implementation against the seven criteria; production
data/provider integration remains a separate end-to-end verification step.
