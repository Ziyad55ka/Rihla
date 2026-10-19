# Frontend languages and motion

The navbar switches between English and Arabic. Its AR/EN label names the language to switch to. The choice is stored locally as `rihla-language` and restored on reload. Arabic updates the document's language and direction to `ar` / `rtl`; the brand and account/language controls keep their physical navbar positions.

Use `useLanguage()` for application copy, including placeholders, accessible labels, statuses, errors and success notices. Add Arabic copy to `frontend/src/lib/translations.ts`. Store message keys in component state and translate when rendering, so messages also change when the language changes. Trip names, member names and preference values stay as their authors entered them.

For dynamic text use named placeholders: `t('Saved {date}', { date: formattedDate })`. Use the context's `locale` for dates and numbers. Arabic dates use the Gregorian calendar, matching the saved travel dates. Invitation links and codes remain left-to-right.

`npm.cmd run lint` includes translation coverage checks for JSX copy, labels and application messages, as well as matching interpolation placeholders. Frontend tests cover rendered landing, signup, join and trip copy in Arabic, English fallback, and preserved user-entered names.

`PageMotion` reveals sections/cards when they enter the viewport and observes content added by navigation. CSS adds gentle background movement, floating travel artwork, button feedback and dialog entry. Controls remain immediately usable. The user's `prefers-reduced-motion` setting disables these effects and reveals all content.

Browser review: English/Arabic landing and Arabic signup checked in local headless Edge at 1440px and 375px, including navbar adjacency, overflow, language persistence, scroll reveals and reduced-motion behavior. This review did not submit credentials or change hosted data.
