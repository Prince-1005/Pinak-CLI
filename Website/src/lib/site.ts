import metadata from '../../../cli/pyproject.toml?raw';
export const version = metadata.match(/^version\s*=\s*"([^"]+)"/m)?.[1] ?? 'unknown';
export const repository = 'https://github.com/Prince-1005/Pinak-CLI';
export const base = import.meta.env.BASE_URL.replace(/\/$/, '');
export const url = (path = '/') => `${base}/${path.replace(/^\//, '')}`;
