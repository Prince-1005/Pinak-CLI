import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import sitemap from '@astrojs/sitemap';

const repository = process.env.GITHUB_REPOSITORY;
const [owner, name] = (repository || 'Prince-1005/Pinak-CLI').split('/');
const customSite = process.env.SITE_URL;
const site = customSite || `https://${owner.toLowerCase()}.github.io`;
const base = process.env.BASE_PATH || (repository && !customSite && name.toLowerCase() !== `${owner}.github.io`.toLowerCase() ? `/${name}` : '/');

export default defineConfig({
  site, base, trailingSlash: 'always', output: 'static',
  integrations: [
    sitemap(),
    starlight({
      disable404Route: true,
      title: 'Pinak / Docs',
      description: 'The local media toolkit. Installation, commands, playback, and troubleshooting.',
      social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/Prince-1005/Pinak-CLI' }],
      customCss: ['./src/styles/docs.css'],
      components: { SiteTitle: './src/components/DocsTitle.astro', ThemeProvider: './src/components/DocsThemeProvider.astro', ThemeSelect: './src/components/DocsThemeSelect.astro' },
      sidebar: [
        { label: 'Start here', items: [{ label: 'Overview', slug: 'docs' }, { label: 'Installation', slug: 'docs/installation' }] },
        { label: 'Download', items: [{ label: 'Commands & options', slug: 'docs/commands' }, { label: 'Audio, quality & batches', slug: 'docs/downloads' }] },
        { label: 'Your workspace', items: [{ label: 'Interactive shell', slug: 'docs/interactive' }, { label: 'Playback & subtitles', slug: 'docs/playback' }, { label: 'Configuration & storage', slug: 'docs/configuration' }] },
        { label: 'AI connections', items: [{ label: 'Choose Local or Cloud', slug: 'docs/mcp' }, { label: 'Local MCP setup', slug: 'docs/mcp-local' }, { label: 'Host Cloud MCP', slug: 'docs/mcp-cloud' }] },
        { label: 'Keep it working', items: [{ label: 'Diagnostics & troubleshooting', slug: 'docs/troubleshooting' }, { label: 'Updating & contributing', slug: 'docs/contributing' }] }
      ]
    })
  ]
});
