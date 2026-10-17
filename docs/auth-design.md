# First account-screen design review

Historical review: the user replaced this visual direction on 17 October 2026. See [the current cream/forest design](frontend-redesign.md). The original image and its provenance below are preserved.

Reference: [Karate template by Dhileep Kumar GM](https://21st.dev/@dhileepkumargm/templates/karate), viewed through its [live Framer preview](https://karateacadamy.framer.website/).

This implementation translates the reference's oversized black typography, white space, coral accent and rounded action buttons into Rihla's travel identity. The layout, copy, compass mark and travel image are adapted for Rihla; no Framer package or template source was imported.

## Scope

- Signed-out login and registration only. Review this direction before extending it to other pages.
- `AuthPage.tsx` supplies the screen layout. `AuthForm.tsx` reuses the existing `submitCredentials` helper and its Supabase confirmation/error handling.
- Signing in still returns to the existing workspace and private-profile checks. Sign-out remains available there.
- `auth.css` scopes the screen's palette and layout. Existing workspace styles remain in `styles.css`.
- On narrow screens, the photograph is hidden and the form uses a single-column layout with 16px inputs. Password visibility controls, keyboard focus, busy states, validation feedback and confirmation feedback are included.
- No account recovery, social login, trip screens, or new backend/database functionality was added.

## Review locally

Open `http://localhost:5173`. If already signed in, sign out from the existing account panel. Switch between **Sign in** and **Create an account** to review both states.

The existing Supabase configuration and application server remain in use. Browser layout checks do not create test accounts or submit real credentials.

Validation: frontend lint, TypeScript checking, all 37 existing frontend tests and production build passed. Browser checks covered 375px mobile, 768px tablet and 1440px desktop widths without horizontal overflow, plus mode switching, password visibility and mismatched-password validation. Live signup/sign-in was not repeated during the visual redesign. Local review screenshots are in the ignored `.artifacts/auth-review/` directory.

## Image provenance

Final asset: `frontend/public/images/rihla-travel-friends.jpg` (1536 × 1024, approximately 408 KB). Generated using the built-in image generation tool and encoded as JPEG for the web; the original PNG remains in the tool's generated-image output directory. It is decorative imagery, not a real booking, destination recommendation, or customer photo.

Final generation prompt:

> Use case: photorealistic-natural. Asset type: decorative travel photograph for a premium group travel web app login screen. Generate a horizontal editorial photograph, 3:2 landscape. Three young adult friends, a Middle Eastern man, a woman with dark hair wearing a pale linen shirt, and a man in muted coral overshirt, seen mostly from behind sitting casually on a rough cream limestone coastal overlook, small travel backpacks beside them, enjoying a turquoise Mediterranean sea and a distant dramatic mountainous coastline. Authentic candid friendship, sophisticated travel magazine photography, natural warm midday light, tactile 35mm film grain, muted warm neutrals with rich teal water, relaxed aspirational moment. Place people in lower center, landscape and horizon above. Natural real anatomy. NO text, NO logos, NO typography, NO watermark, NO website or UI mockup. This is a photographic asset only, not a screenshot or design. High-quality final asset suitable for cropping to a wide rectangle.
