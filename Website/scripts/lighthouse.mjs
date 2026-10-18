import fs from 'node:fs/promises';
import path from 'node:path';
import lighthouse from 'lighthouse';
import { launch } from 'chrome-launcher';
import { chromium } from '@playwright/test';
import { root } from './media.mjs';
const directory = path.join(root, '.cache/lighthouse'); await fs.mkdir(directory, { recursive: true });
await fs.mkdir(path.join(directory, 'chrome-profile'), { recursive: true });
const chrome = await launch({ chromePath: chromium.executablePath(), port: 9225, userDataDir: path.join(directory, 'chrome-profile'), chromeFlags: ['--headless', '--no-sandbox'], logLevel: 'silent' });
try {
  for (const [name, route] of [['home', '/'], ['install', '/install/']]) {
    const result = await lighthouse(`http://127.0.0.1:4322${route}`, { port: chrome.port, output: 'json', logLevel: 'error', onlyCategories: ['performance', 'accessibility', 'best-practices', 'seo'] });
    await fs.writeFile(path.join(directory, `${name}.json`), result.report);
    console.log(name, JSON.stringify(Object.fromEntries(Object.entries(result.lhr.categories).map(([key, value]) => [key, Math.round(value.score * 100)]))));
    const failures = Object.values(result.lhr.audits).filter(a => a.score !== null && a.score < .9 && a.scoreDisplayMode !== 'informative');
    console.log('Review:', failures.map(a => `${a.id}: ${a.displayValue || a.title}`).join('; '));
  }
} finally { chrome.kill(); }
