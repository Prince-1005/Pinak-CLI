# Phase 6 — Verification and deployment

## Inputs and dependencies

Completed pages/media pipeline; Node tests, Astro check/build, Playwright/axe, and GitHub Pages Actions permissions.

## Tasks and outputs

- Run media regressions, type checks, root/subpath builds, generated-reference validation, and browser scenarios.
- Inspect desktop, tablet, and mobile screenshots in dark/light modes.
- Check keyboard navigation, dialog Escape/focus return, captions, sound consent, reduced motion, and accessibility.
- Check no full media request on homepage load, initial transfer budget, and mobile Lighthouse where tooling permits.
- Build/list the Python wheel to confirm website exclusion.
- Configure a separate workflow with locked dependencies, media conversion cache, PR validation, and default-branch Pages deployment.

## Commands

`npm test`, `npm run media:build`, `npm run check`, `npm run build`, `npx playwright install chromium firefox webkit`, `npm run test:browser`.

For a repository-path build, set `BASE_PATH=/Pinak-CLI`, then build. Clear it before root-path browser tests.

## Acceptance

All required checks pass, and remaining platform/tooling limits are recorded honestly. The deploy job depends on successful verification. Failures retain the last deployed site. No release workflow for the Python package is replaced.

## Completion notes

Pages needs the destination repository configured to use GitHub Actions. This cannot be inferred from local files. See the verification record for what was actually executed and whether a public deployment was made.
