# Pinak website

Static Astro + Starlight site for Pinak’s introduction, installation, documentation, and media showcase. This does not provide a cloud downloader. The Python package still builds independently from `cli/`.

## Develop

Use Node.js 24 LTS (minimum 22.23.4). From this directory:

```sh
npm ci
npm run media:build
npm run check
npm run dev
```

Open the printed localhost URL. Build-time FFmpeg/FFprobe and Sharp are installed as website dependencies. No visitor needs Node or these website tools. If npm reports that dependency setup scripts were blocked, review and approve only the pinned native packages listed in `package.json` with your npm version’s script approval commands, then `npm rebuild ffmpeg-static sharp`.

## Verify

```sh
npm test
npm audit --audit-level=moderate
npm run build
npx playwright install chromium firefox webkit
npm run test:browser
```

The build validates local links and generated assets. `npm run check` expects a generated manifest, so run `media:build` first in a fresh checkout. Playwright serves the production build and covers desktop Chromium/Firefox/WebKit plus mobile Chromium.

## Add media

Add supported files to `Media/`, optionally describe them in `media.json`, run `npm run build`, and push. The next website deployment discovers the files automatically. See [the maintenance guide](planning/media-maintenance.md).

For files over GitHub’s 100 MiB limit, preserve the originals outside the repository and import smaller copies:

```sh
npm run media:prepare -- --from "<external-source-folder>"
```

This does not overwrite existing destination files. Source originals remain untouched. Imported full-length video targets 40 MiB or less and validates duration. A bitrate threshold is a technical guard, not a guarantee of perceptual quality; review prepared videos before publishing.

## Deploy on GitHub Pages

The dedicated `Website` workflow validates relevant pushes/PRs, tests browsers, and deploys only the default branch. In the destination GitHub repository, select **Settings → Pages → Build and deployment → Source: GitHub Actions**. No website deployment changes the PyPI release process.

The repository host and base path derive from `GITHUB_REPOSITORY`; the source-code link intentionally continues pointing to the package’s canonical repository. Optional repository variables:

- `WEBSITE_SITE_URL`: full origin for a custom domain, such as `https://pinak.example`.
- `WEBSITE_BASE_PATH`: `/` for a custom-domain root, or a deliberate path override.

For local subpath verification set `GITHUB_REPOSITORY=owner/repo` before building, or use `BASE_PATH=/repo`. On PowerShell: `$env:BASE_PATH='/repo'; npm run build`. Clear the variable for a normal local root build. Configure custom-domain DNS and GitHub Pages domain separately; this project does not provision domains.

Build output and media caches are ignored. Commit source media that fit the file limit, metadata, source files, and `package-lock.json`. Never commit `node_modules`, `.cache`, or full local archives.

## Maintenance and handover

See [planning index](planning/README.md) for phase tasks and acceptance criteria. Build reports live in `.cache/media-report.json`. Current source version is read from `../cli/pyproject.toml`, and source release notes come from `../cli/CHANGELOG.md`; website documentation changes should accompany behavior changes in Pinak.

For each website update: compare installation commands with the current CLI and the published package, review new gallery media and descriptions, run `npm run check`, `npm test`, and `npm run build`, then check the Website workflow and the live install page after deployment. Keep package releases and website deployments independent.
