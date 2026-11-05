# US-11/US-12 integration

Integrated against main `0ac74999bc8869bb60cddd3e33b54c0d0c1c5bb5`.
No changes are made to main or teammates' branches.

## Flow

1. Open a real proposal from the trip workspace.
2. In its existing details page, choose **Find activity suggestions**.
3. The authenticated backend reads that proposal's stored cities and dates.
   Tavily searches public city/date information; Gemini extracts cited suggestions.
   No member budgets, preferences or departure cities enter activity search prompts.
4. Names, locations, durations, descriptions and dates must match a quoted source.
   Fabricated quotes and source ids are rejected. Prices require a stated amount
   and currency; converted prices are Estimated, missing prices stay unknown.
   Events outside the city's stay are omitted. Missing images use a placeholder.
5. Suggestions are saved once for the proposal. A database lease prevents duplicate
   paid searches, and cached results are shared across trip members. Failed jobs
   can retry after a short backoff; regenerated proposals invalidate old jobs.
6. Each member selects/removes activities and presses **Save activities**.
   No day or time assignment is required. Choices persist in Supabase per member.
7. Saving refreshes Developer 3's existing cost section. It adds that member's
   saved activities and uses the sum of each member's actual choices for the group.
   Unknown costs make totals partial; one member's choices are not multiplied by
   the group size. Other members' choices and budgets are not exposed.

The previous `/demo/activities` page and browser-localStorage mock adapter are
removed from the application. Synthetic activity examples exist only under test
fixtures. Developer 1's existing general proposal demo mode remains unchanged;
activity research itself never substitutes demo results.

## Deployment prerequisites

This checkout has **no live credentials**. Local tests stub external services;
passing them does not establish that production keys, quotas or cloud migrations
are configured. No migration has been applied to the shared cloud database here.

Use the team's normal `backend/.env` and `frontend/.env.local` files, keeping all
secret keys out of GitHub and out of the frontend. Required variables already
appear in the main branch's environment examples:

- Backend: `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`,
  `GEMINI_API_KEY`, `TAVILY_API_KEY`, and the team's `PROPOSALS_HASH_KEY`.
- Frontend: `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`,
  `VITE_SUPABASE_PUBLISHABLE_KEY`.

Activity search can reuse existing real proposals; regenerating the entire trip
is not required. Apply new activity migrations in order through the team's normal
deployment process, after their existing proposal migration:

1. `20261103000100_activity_selections.sql`
2. `20261105000100_activity_research.sql`
3. `20261105000200_activity_costs.sql`

The existing `20261104000100_proposal_cost_context.sql` is also needed for the
group total and private budget comparison. Do not reapply or edit teammates'
existing migrations to add these features.

## Live verification still required

With the team's setup: log in as two trip members, open the same real proposal,
research its cities, save different selections, reload, remove a selection and
save again. Confirm each member sees their own choices and that the shared total
adds both members' costs. Exercise a provider failure, missing prices, expired
events and regeneration. These live checks are pending credentials and deployment.

## Scope

Only activity browsing, selection persistence, and the US-12-AC03 cost integration
are added. Existing flights, bookings, rooms, compatibility and sources remain
Developer 1/3's implementations. The flight-price review findings on PR #2 were
not fixed by this change.

## Tourist-only suggestions matched to the group (3 November 2026)

Problem seen in testing: the single broad search ("attractions … events {dates}")
returned conferences and medical events, and nothing used the group's interests.

- **Interests, privately.** When proposals are generated, Gemini maps the group's
  Interests to up to 4 general tags (`Proposal.activity_focus`: landmarks,
  museums_history, culture_arts, food, nature_outdoors, beaches_water, shopping,
  family_fun, adventure_sports, wellness_spa, events_festivals). Members' own words
  are never stored. Older proposals fall back to landmarks and food.
- **Searches.** Two per city, run at the same time: things to do for tourists (with
  the tags as words) on travel guides (Tripadvisor, Lonely Planet, Time Out,
  GetYourGuide, Viator, Klook …), and restaurants on food guides. An empty guide
  search falls back once to the open web. About 2 Tavily credits per city.
- **Prompt.** Says what a tourist suggestion is, lists what to never return
  (conferences, trade shows, medical/academic/professional events, courses, job
  fairs, services for residents, hotels, list titles), asks for `tourist` and `fits`.
- **Code checks.** Off-topic words (English and Arabic) on the name and description,
  exact quotes, sources from that city, event dates inside the stay. Ranked by how
  many group interests match, then a fair mix per city: up to 6 attractions,
  4 activities, 4 restaurants (12 per city, 36 in total).
- **Page.** Each card shows "Matches the group's interests: …" when it does.
- **Log.** `activity_research_counts` holds counts, the tags and the model only.

A proposal whose activities were already found keeps them; regenerate the proposals
to get the new focus tags and search again.

## Live test feedback (5 November 2026)

- A third search per city finds popular experiences: water parks, theme parks, haunted
  houses, escape rooms, beach and boat activities, and newly opened places.
- When no source states a price, Gemini's usual price per person (`typical_price_sar`)
  is shown as "About X · Rough estimate, may change with the season" (`Unconfirmed`).
- Cards are grouped as Top sights, Things to do and Where to eat, with the ones that
  match the group's interests first, plus a "Picked for your group" filter.
- US-11-AC02 photos: sights and activities get the free Wikipedia photo of the page
  with that exact name, with its artist and licence (`Activity.image`, added when
  proposals are read and never saved). Restaurants are not looked up. Lookups run six
  at a time with a 5-second limit and are cached, so photos fill in on a later read.
