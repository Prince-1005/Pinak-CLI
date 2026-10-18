import fs from 'node:fs/promises';
import path from 'node:path';
import { root, walk } from './media.mjs';

const dist = path.join(root, 'dist');
const repo = process.env.GITHUB_REPOSITORY?.split('/');
const base = (process.env.BASE_PATH || (repo && !process.env.SITE_URL && repo[1].toLowerCase() !== `${repo[0]}.github.io`.toLowerCase() ? `/${repo[1]}` : '')).replace(/\/$/, '');
const errors = [];
let checked = 0;
for (const file of (await walk(dist)).filter(f => f.endsWith('.html'))) {
  const html = await fs.readFile(file, 'utf8');
  if (!/<title>[^<]+<\/title>/.test(html)) errors.push(`${file}: missing title`);
  if (!/name="description"/.test(html)) errors.push(`${file}: missing description`);
  for (const match of html.matchAll(/\b(?:href|src|poster)="([^"#]+)(?:#[^"]*)?"/g)) {
    const link = match[1].replaceAll('&amp;', '&');
    if (/^(https?:|mailto:|data:|tel:|javascript:)/i.test(link)) continue;
    const pathname = decodeURIComponent(link.split(/[?#]/)[0]);
    if (!pathname) continue;
    let target;
    if (pathname.startsWith('/')) {
      if (base && pathname !== base && !pathname.startsWith(base + '/')) { errors.push(`${path.relative(dist, file)}: misses repository base: ${pathname}`); continue; }
      target = path.join(dist, base ? pathname.slice(base.length) : pathname);
    } else target = path.resolve(path.dirname(file), pathname);
    if (!target.startsWith(dist + path.sep) && target !== dist) { errors.push(`${file}: link escapes site: ${link}`); continue; }
    const stat = await fs.stat(target).catch(() => null);
    if (!stat) errors.push(`${path.relative(dist, file)}: missing ${link}`);
    else if (stat.isDirectory() && !(await fs.stat(path.join(target, 'index.html')).catch(() => null))) errors.push(`${file}: directory without index ${link}`);
    checked++;
  }
}
const bytes = (await Promise.all((await walk(dist)).map(f => fs.stat(f)))).reduce((sum, s) => sum + s.size, 0);
if (bytes >= 1024 ** 3) errors.push('Published output exceeds GitHub Pages’ 1 GiB limit.');
if (errors.length) { console.error(errors.join('\n')); process.exitCode = 1; }
else console.log(`Validated ${checked} local references. Static output: ${(bytes / 1024 ** 2).toFixed(1)} MiB.`);
