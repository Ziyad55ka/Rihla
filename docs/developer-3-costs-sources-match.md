# Developer 3: US-13, US-14 and US-15

Branch `dev3/costs-compatibility`, based on `sprint-2/ai-proposals`. The three sections sit after activities on the proposal details page, in `CostsAndCompatibility.tsx`.

## Acceptance criteria

| Criterion | How it is met | Where |
| --- | --- | --- |
| US-13-AC01 | Flights, accommodation, travel between cities, selected activities and meals and other expenses, per person | `services/proposal_costs.py`, `CostsSection.tsx` |
| US-13-AC02 | Per person and group totals, with two room plans (one or two per room) and a written list of assumptions | Same |
| US-13-AC03 | Each member sees a warning when the proposal is over their own budget (with the gap) or when it cannot be confirmed. The group check stays `budget_status` | Same, plus `rihla_cost_context` |
| US-14-AC01 | A sources list with each source's site and check time (`ProposalSource.retrieved_at`). Flight and hotel prices keep their own age badges | `SourcesSection.tsx` |
| US-14-AC02 | Estimated prices say "About" and carry a badge. Totals take their weakest part's label | `values.tsx`, `CostsSection.tsx` |
| US-14-AC03 | A legend explains each of the four labels. Missing prices are never counted as free, and totals that need them say so | `SourcesSection.tsx`, `CostsSection.tsx` |
| US-15-AC01 | One row per topic: destinations, interests, flights, accommodation, dates and the group budget | `Proposal.compatibility`, `CompatibilitySection.tsx` |
| US-15-AC02 | Results are met, not verified or not met. An Essential that is not verified is named at the top | `compatibility_checks` in `proposal_generation.py` |
| US-15-AC03 | Trade-offs from `flexible_adjustments`. No score is shown, and the page says so | `CompatibilitySection.tsx` |

## Decisions to confirm with the team

1. **Meals** use a general daily allowance, `MEALS_PER_DAY_SAR` (default 150), always labelled Unconfirmed. Researching real meal prices is possible later.
2. **Activities** are listed but not counted until US-11/12 is merged. Then `proposal_costs.py` should add the saved activities, replacing the separate total in `activity_estimate.py`, so there is one calculation.
3. **Met vs not verified:** only destinations are checked in code, against the destination, country and city names in both languages. Interests, flights and accommodation are free text, so when the AI reports them met the page says "Not verified". This is deliberately cautious.
4. **Privacy:** budgets are shown only to their owner, as a label and the gap. The group total adds everyone's flights. The member count is already on the trip page, so the total reveals nothing new about budgets or cities.
5. **Removed earlier, now back:** the sources section and the trade-off text, because US-14-AC01 and US-15-AC03 require them. Only sources classified as booking or ideas are listed, never fare notes or unclassified entries. The four page tests that asserted their absence were updated.
6. The room choice is a view only and is not saved.

## Data changes

- `Proposal.compatibility` and `ProposalSource.retrieved_at`: optional, so saved proposals still load. Proposals generated before this show a note to regenerate.
- `StoredProposals.costs`: worked out on every read for the signed-in member, never saved.
- Migration `20261104000100_proposal_cost_context.sql`: `rihla_cost_context`, for the secret key only. **Apply it to Supabase after the AI proposals migration.** Without it, the page still shows the member's own costs, but no group total or budget check.
- `supabase/package.json` now runs `proposals.test.mjs` too. It was not run by `npm test` before.

## Checks

Backend: `uv run pytest`, `ruff check`, `ruff format --check`. Frontend: `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`. Database: `npm test` in `supabase`.
