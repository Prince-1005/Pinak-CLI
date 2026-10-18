# Verification record — 18 October 2026

## Delivered

- Astro/Starlight static site with 15 generated pages: homepage, installation, showcase, about, changelog, 404, and nine documentation pages.
- Three real screenshots and two full-length desktop playback recordings imported from the supplied directory. Original source files remain outside this checkout and were not replaced.
- Prepared videos are 11,357,849 and 14,217,441 bytes, both below the 40 MiB preparation budget. Preparation compares source/output duration.
- Generated media is about 24.7 MiB; complete static output is about 26.3 MiB.
- Automatic discovery, optional metadata, media preparation, caching, stale removal, responsive variants, covers, native playback, image zoom, search/filter/pagination, and WebVTT/transcript references.
- Shared light/dark preferences, reduced motion, and opt-in original browser-synthesized ambient audio.
- GitHub Pages workflow, repository-aware paths, social preview, sitemap, and maintenance/phase guides.

## Checks executed

- `npm test`: **11/11 passed**. Includes portrait/landscape, Unicode/nested names, metadata/attachment cache changes, removed files, unsupported/corrupt inputs, oversize source rejection, audio/video output, source-preserving import, animated GIF frames, identical bytes at different paths, and phone-photo EXIF orientation.
- `npm run check`: **0 errors, 0 warnings, 0 hints** on the application and test files.
- `npm run build`: successful root-path and repository-subpath (`example/Pinak-CLI`) builds; **330 local references validated** in each. Root build restored for local preview.
- Playwright: **32/32 passed**, covering desktop Chromium, Firefox, WebKit, and mobile Chromium. Tests include installation tabs/clipboard, gallery filtering/search/zoom/Escape/focus return, future 29-item gallery pagination, theme continuity through docs/mobile menus, sound consent/fallback, reduced motion, automated accessibility, live Pagefind search, and MP4 playback where the browser exposes a decoder.
- Axe: no tested WCAG A/AA violations on homepage and installation in the browser suite.
- Mobile Lighthouse, local production preview: homepage **100 performance / 100 accessibility / 100 best practices / 100 SEO**; installation **99 / 100 / 100 / 100**.
- Browser resource inspection: **246,882 initial resource bytes** on the measured homepage load; no full MP4/MP3 requests before interaction; no page errors in the visual inspection.
- Desktop, mobile, light/dark, installation, and showcase screenshots captured under ignored `.cache/visual-qa` and inspected.
- Built `pinak_cli-1.4.3-py3-none-any.whl`: inspected all **98 wheel entries**; no website directory or website media/font assets included.
- `git diff --check`: passed for tracked edits. Existing unrelated `Capture/` and project-analysis files were left alone.

## Limits and deployment status

Lighthouse scores are measurements of a local build, not guarantees for every network/device. Automated WebKit on Windows is not a physical Safari/iPhone test. The sound test exercises a graceful unavailable-audio path when the browser runtime does not expose Web Audio. Physical audio devices and installation commands on macOS/Linux were not manually tested here.

The initial verification above was completed before deployment. The Website workflow later deployed successfully from the repository's default branch, and Pages now uses **GitHub Actions** as its publishing source. Optional custom-domain settings are documented in the website README.

Local reports and screenshots are generated/ignored, not required tracked assets. Reproduce Lighthouse with `node scripts/lighthouse.mjs` and visual/resource inspection with `node scripts/inspect.mjs` while a root-path production preview runs at `http://127.0.0.1:4322`.
