import { readFileSync } from 'node:fs';
const metadata = readFileSync(new URL('../../../cli/pyproject.toml', import.meta.url), 'utf8');
export const version = metadata.match(/^version\s*=\s*"([^"]+)"/m)?.[1] ?? 'unknown';
export const repository = 'https://github.com/Prince-1005/Pinak-CLI';
export const base = import.meta.env.BASE_URL.replace(/\/$/, '');
export const url = (path = '/') => `${base}/${path.replace(/^\//, '')}`;
