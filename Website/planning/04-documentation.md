# Phase 4 — Installation and documentation

## Inputs and dependencies

Current CLI source/help, `cli/OPERATIONS.md`, package metadata, and maintained changelog. Historical plans are not authoritative.

## Tasks and outputs

- Publish accessible Windows/macOS/Linux installation tabs, pipx setup, venv/source alternatives, verification, and first-download commands.
- Separate required download tools from optional desktop/audio setup.
- Write command, download, REPL, playback/subtitle, settings/storage, troubleshooting, update, and contributor guides.
- Add searchable Starlight navigation and a route back to the homepage.
- Render the maintained package changelog and identify source versus published releases honestly.

## Commands

`npm run check`, `npm run build`, `npm run test:browser`.

## Acceptance

Copy buttons have visible/live feedback and an unavailable-clipboard fallback. Tabs work with arrows/Home/End and do not hide all instructions without JavaScript. Search returns actual guide pages in a production build. Commands match current source; all local links pass validation.

## Completion notes

Platform instructions are published, but not all OS installation procedures can be executed on a single Windows development machine. Maintain those instructions alongside the upstream operating guide and release changes.
