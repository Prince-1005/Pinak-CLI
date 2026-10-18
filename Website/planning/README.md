# Website delivery phases

This tracked directory records the end-to-end implementation and maintenance plan. The root `phases` folder is intentionally avoided because repository ignore rules exclude it.

1. [Foundation](01-foundation.md)
2. [Media system](02-media-system.md)
3. [Product presentation](03-presentation.md)
4. [Installation and documentation](04-documentation.md)
5. [Motion and audio](05-motion-and-audio.md)
6. [Verification and deployment](06-verification-and-deployment.md)

For recurring updates, use [media maintenance](media-maintenance.md). For exact checks performed in this implementation session, read [verification record](verification.md).

## Product contract

The site introduces the real Python CLI, explains installation, and displays local supplied assets. It accepts no media URLs for downloading, creates no accounts, and runs no backend. Do not add claims about unreleased GUI, mobile, or MCP products as current capabilities.

## Build order

Install locked dependencies → discover/validate/transform media → typecheck → build Astro/Starlight and Pagefind → validate references and size → test the production site in browsers → deploy the verified repository-path artifact.

## Source boundaries

Website code lives under `Website`. The Python application remains under `cli`. Website source version and changelog are read at build time from the package, not fetched on every visit. Remote links point to canonical package/release resources; deployment host/base derive from the actual GitHub repository.
