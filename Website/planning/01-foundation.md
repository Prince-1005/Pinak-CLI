# Phase 1 — Foundation

## Inputs and dependencies

- Current README, operating guide, pyproject, and canonical package repository.
- Existing screenshots/videos in the supplied Media directory.
- Node 24, npm, Astro, Starlight, TypeScript, and self-hosted fonts.

## Tasks and outputs

- Establish separate website package/lockfile and ignore generated output.
- Configure static routes, sitemap, Pagefind, repository-aware asset URLs, and custom-domain overrides.
- Implement shared header/footer, brand, dark/light tokens, mobile navigation, and skip links.
- Read source version at build time; never label it as the current PyPI version.
- Preserve originals outside the repository when preparing initial videos.

## Commands

`npm ci`, `npm run media:build`, `npm run check`, `npm run dev`.

## Acceptance

The root page and docs load on mobile/desktop; navigation and metadata are present; root and repository-path builds resolve assets; Python packaging has no website dependency.

## Completion notes

Implemented in the website package, shared layout, site helpers, CSS, and Astro configuration. No hosted application service is created. The deployment account/domain remains a repository setting, not a hardcoded workstation remote.
