# Activity acceptance checks

| Criterion | Implementation / verification |
| --- | --- |
| US-11-AC01 | City/date-based live research; activities, attractions and restaurants; shared persisted suggestions |
| US-11-AC02 | Cited description, location, duration and price; image when supplied |
| US-11-AC03 | Missing image placeholder, unknown prices, partial totals |
| US-11-AC04 | ISO event dates validated against each city's stay; invalid events discarded |
| US-12-AC01 | Authenticated Supabase save; per-member choices, reload, removal, stale-version rejection |
| US-12-AC02 | No day/time assignment fields or requirement |
| US-12-AC03 | Saved selection included in the existing personal estimate; group sum uses actual member choices |

Automated tests cover source verification, fabricated values, free/unknown prices,
service errors, cache behavior, verified identity, selection persistence, database
permissions, research leases, regeneration and personal/group cost integration.

The live provider/database walkthrough has **not** been performed: the user does
not have the team's environment files. See `activities.md` for prerequisites.
