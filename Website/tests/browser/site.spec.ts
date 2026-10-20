import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('home shows real captures and loads no full media before interaction', async ({ page }) => {
  const media: string[] = [];
  page.on('request', req => { if (/\.(mp4|mp3)(?:\?|$)/.test(req.url())) media.push(req.url()); });
  await page.goto('/'); await expect(page.locator('h1')).toContainText('Keep it local.');
  await expect(page.locator('.hero-image-button img')).toBeVisible();
  await expect(page.locator('#sound-toggle')).toHaveAttribute('aria-pressed', 'false');
  expect(media).toEqual([]);
});
test('installation tabs, keyboard navigation and copied command feedback', async ({ page }) => {
  await page.goto('/install/');
  await expect(page.locator('#panel-windows')).toBeVisible(); await expect(page.locator('#panel-linux')).toBeHidden();
  await page.getByRole('tab', { name: 'macOS' }).click(); await expect(page.locator('#panel-macos')).toBeVisible();
  await page.getByRole('tab', { name: 'macOS' }).press('ArrowRight'); await expect(page.locator('#panel-linux')).toBeVisible();
  await page.evaluate(() => { Object.defineProperty(navigator, 'clipboard', { value: { writeText: async (value: string) => { (window as unknown as { copied: string }).copied = value; } }, configurable: true }); });
  await page.locator('#panel-linux [data-copy="pipx install pinak-cli"]').click();
  await expect(page.locator('#announcement')).toHaveText('Command copied to clipboard.');
  expect(await page.evaluate(() => (window as unknown as { copied: string }).copied)).toBe('pipx install pinak-cli');
});
test('gallery filtering, search, dialog escape, zoom and focus restoration', async ({ page }) => {
  await page.goto('/showcase/'); await expect(page.locator('[data-media-card]:visible')).toHaveCount(5);
  await page.getByRole('button', { name: 'Videos', exact: true }).click(); await expect(page.locator('[data-media-card]:visible')).toHaveCount(2);
  await page.locator('#gallery-search').fill('soundtrack'); await expect(page.locator('[data-media-card]:visible')).toHaveCount(1);
  await page.locator('[data-media-card]:visible button').click(); await expect(page.locator('#media-viewer')).toBeVisible();
  await expect(page.locator('#viewer-content video')).toHaveAttribute('controls', '');
  await page.keyboard.press('Escape'); await expect(page.locator('#media-viewer')).not.toBeVisible();
  await expect(page.locator('[data-media-card]:visible button')).toBeFocused();
  await page.locator('#gallery-search').clear(); await page.getByRole('button', { name: 'Screenshots', exact: true }).click();
  await page.locator('[data-media-card]:visible button').first().click(); await page.locator('#viewer-zoom').click();
  await expect(page.locator('#viewer-content')).toHaveClass(/zoomed/); await page.locator('#viewer-close').click();
});
test('sound requires consent and theme preference survives navigation', async ({ page }) => {
  await page.goto('/');
  await page.bringToFront();
  await expect(page.locator('#sound-toggle')).toHaveAttribute('aria-pressed', 'false');
  const supported = await page.evaluate(() => Boolean(window.AudioContext || (window as unknown as { webkitAudioContext?: unknown }).webkitAudioContext));
  await page.locator('#sound-toggle').click();
  if (supported) {
    await expect(page.locator('#sound-toggle')).toHaveAttribute('aria-pressed', 'true');
    await page.locator('#sound-toggle').click(); await expect(page.locator('#sound-toggle')).toHaveAttribute('aria-pressed', 'false');
  } else {
    await expect(page.locator('#announcement')).toContainText('Audio is unavailable');
    await expect(page.locator('#sound-toggle')).toHaveAttribute('aria-pressed', 'false');
  }
  await page.locator('#theme-toggle').click(); await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await page.goto('/install/'); await expect(page.locator('html')).toHaveAttribute('data-theme', 'light'); await expect(page.locator('#sound-toggle')).toHaveCount(0);
  await page.goto('/docs/'); await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  if (!(await page.getByRole('combobox', { name: 'Select theme' }).isVisible())) await page.getByRole('button', { name: 'Menu', exact: true }).click();
  await page.getByRole('combobox', { name: 'Select theme' }).selectOption('dark');
  await page.goto('/'); await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
});
test('reduced motion, layout and accessibility', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' }); await page.goto('/');
  expect(await page.locator('.cursor').evaluate(el => getComputedStyle(el).animationName)).toBe('none');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze(); expect(results.violations).toEqual([]);
  await page.goto('/install/'); const install = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze(); expect(install.violations).toEqual([]);
});
test('documentation search is built and navigation works', async ({ page }) => {
  await page.goto('/docs/'); await expect(page.locator('h1')).toContainText('Your terminal');
  await page.getByRole('button', { name: /Search/ }).first().click();
  await page.getByRole('textbox', { name: 'Search', exact: true }).fill('subtitles');
  await expect(page.locator('.pagefind-ui__result').first()).toBeVisible();
});

test('MCP editions lead to correct setup guides and remain accessible', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await page.getByRole('link', { name: 'Explore Local & Cloud MCP' }).click();
  await expect(page.locator('h1')).toContainText('Keep the controls.');
  await expect(page.locator('#local')).toContainText('pinak-mcp-install');
  await expect(page.locator('#cloud')).toContainText('pinak-mcp-cloud-install');
  await expect(page.locator('#cloud')).toContainText('your server');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  for (const theme of ['dark', 'light']) {
    await page.evaluate(value => { document.documentElement.dataset.theme = value; }, theme);
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(results.violations).toEqual([]);
  }
  await page.getByRole('link', { name: 'Set up Local MCP' }).click();
  await expect(page).toHaveURL(/\/docs\/mcp-local\/$/);
  await expect(page.locator('main')).toContainText('pinak.mcp_server configure');
  await page.goto('/mcp/');
  await page.getByRole('link', { name: 'Host your Cloud MCP' }).click();
  await expect(page).toHaveURL(/\/docs\/mcp-cloud\/$/);
  await expect(page.locator('main')).toContainText('docker compose exec app python -m pinak.mcp_cloud users add alice');
  await expect(page.locator('main')).toContainText('Live VPS and Render account deployment remains unverified');
});

test('MCP setup documentation is discoverable through search', async ({ page }) => {
  await page.goto('/docs/');
  await page.getByRole('button', { name: /Search/ }).first().click();
  await page.getByRole('textbox', { name: 'Search', exact: true }).fill('bearer');
  await expect(page.locator('.pagefind-ui__result').first()).toBeVisible();
  await expect(page.locator('.pagefind-ui__results')).toContainText('Cloud');
});

test('Library and queue examples link to the expanded MCP guidance', async ({ page }) => {
  await page.goto('/docs/commands/');
  await expect(page.locator('main')).toContainText('pinak queue show 1');
  await expect(page.locator('main')).toContainText('pinak library scan');
  await page.goto('/docs/library/');
  await expect(page.locator('main')).toContainText('pinak library bookmark add');
  await page.goto('/mcp/');
  await expect(page.locator('#local')).toContainText('Library');
  await expect(page.locator('#cloud')).toContainText('Library');
  await page.goto('/docs/mcp/');
  await expect(page.locator('main')).toContainText('history_show');
  await expect(page.locator('main')).toContainText('library_scan');
});

test('future gallery growth paginates at 24 and handles no matches', async ({ page }) => {
  await page.route('**/showcase/', async route => {
    const response = await route.fetch(); const html = await response.text();
    const card = html.match(/<article\b[^>]*data-media-card[\s\S]*?<\/article>/)?.[0];
    expect(card).toBeTruthy();
    await route.fulfill({ response, body: html.replace(card!, card!.repeat(25)) });
  });
  await page.goto('/showcase/'); await expect(page.locator('[data-media-card]:visible')).toHaveCount(24);
  await page.locator('#gallery-next').click(); await expect(page.locator('[data-media-card]:visible')).toHaveCount(5);
  await expect(page.locator('#gallery-page')).toHaveText('Page 2 of 2');
  await page.locator('#gallery-search').fill('nothing-matches-this'); await expect(page.locator('#gallery-empty')).toBeVisible();
});

test('video starts in browsers with an MP4 decoder and stops on close', async ({ page }) => {
  await page.goto('/showcase/'); await page.bringToFront();
  await page.getByRole('button', { name: 'Videos', exact: true }).click();
  await page.locator('[data-media-card]:visible button').first().click();
  const supported = await page.locator('#viewer-content video').evaluate((element: HTMLVideoElement) => Boolean(element.canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"')));
  if (supported) {
    await page.locator('#viewer-content video').evaluate(async (element: HTMLVideoElement) => { element.muted = true; await element.play(); });
    await expect.poll(() => page.locator('#viewer-content video').evaluate((element: HTMLVideoElement) => element.currentTime)).toBeGreaterThan(0);
  } else {
    await page.locator('#viewer-content video').dispatchEvent('error'); await expect(page.locator('#viewer-status')).toContainText('Playback is unavailable');
  }
  await page.locator('#viewer-close').click(); await expect(page.locator('#viewer-content video')).toHaveCount(0);
});
