# Revise one proposal (US-19)

Apply `supabase/migrations/20261118000100_proposal_feedback.sql` after the Sprint 2 migrations in the team's development database. The existing backend Supabase secret, AI provider and travel research settings are used. Demo mode cannot revise canned proposals.

On a proposal, the administrator opens **What do you want to change** (**وش تحتاج من تعديل**), describes one change and submits. The backend passes the itinerary and feedback to the planner, researches one replacement, checks it against the existing duration, shared dates, budget and requirements, and asks the model to check the result against the feedback. Provider or validation failure leaves the current proposal unchanged.

The revision keeps the proposal link and option number. The other options do not change. A successful save archives the previous itinerary and its activity selections in the same transaction. The new itinerary starts without activity selections; the old activities and their prices may no longer apply. Members can expand **Earlier versions** for an itinerary summary. The member history endpoint filters flight routes and sources for the signed-in member and does not return administrator feedback or other members' choices.

To verify with team accounts, request a specific route change from an administrator account, reopen the proposal, check its version and the other options, then open the same proposal as a member to verify read-only access. Live revision uses the team's provider quota.
