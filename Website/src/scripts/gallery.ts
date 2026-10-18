import type { MediaItem } from '../lib/media';
const manifest: MediaItem[] = JSON.parse(document.querySelector('#media-manifest')?.textContent || '[]');
const dialog = document.querySelector<HTMLDialogElement>('#media-viewer');
const viewer = document.querySelector<HTMLElement>('#viewer-content');
const title = document.querySelector('#viewer-title');
const description = document.querySelector('#viewer-description');
const status = document.querySelector('#viewer-status');
const transcript = document.querySelector<HTMLAnchorElement>('#viewer-transcript');
const zoom = document.querySelector<HTMLButtonElement>('#viewer-zoom');
let opener: HTMLButtonElement | null = null;
document.querySelectorAll<HTMLButtonElement>('[data-media-id]').forEach(button => {
  button.addEventListener('click', () => {
    const item = manifest.find(i => i.id === button.dataset.mediaId);
    if (!item || !dialog || !viewer) return;
    opener = button; viewer.replaceChildren(); viewer.classList.remove('zoomed');
    if (title) title.textContent = item.title;
    if (description) description.textContent = item.description;
    if (status) status.textContent = '';
    if (zoom) { zoom.hidden = item.type !== 'image'; zoom.textContent = 'Zoom image'; zoom.setAttribute('aria-pressed', 'false'); }
    if (transcript) { transcript.hidden = !item.transcript; if (item.transcript) transcript.href = item.transcript; }
    if (item.type === 'image') {
      const image = new Image(); image.src = item.src; image.alt = item.alt; viewer.append(image);
      image.addEventListener('error', () => { if (status) status.textContent = 'This image could not load. Please try again.'; });
    } else {
      const player = document.createElement(item.type === 'video' ? 'video' : 'audio');
      player.controls = true; player.preload = 'metadata'; player.src = item.src;
      player.setAttribute('aria-label', item.title);
      if (player instanceof HTMLVideoElement) { player.poster = item.poster; player.playsInline = true; }
      if (item.captions) { const track = document.createElement('track'); track.src = item.captions; track.kind = 'captions'; track.label = 'Captions'; track.default = true; player.append(track); }
      if (item.type === 'audio') { const group = document.createElement('div'); group.className = 'audio-player'; const cover = new Image(); cover.src = item.poster; cover.alt = `${item.title} cover`; group.append(cover, player); viewer.append(group); }
      else viewer.append(player);
      player.addEventListener('waiting', () => { if (status) status.textContent = 'Loading media…'; });
      player.addEventListener('canplay', () => { if (status) status.textContent = ''; });
      player.addEventListener('error', () => { if (status) status.textContent = 'Playback is unavailable. Try another browser or reload this page.'; });
    }
    document.body.style.overflow = 'hidden'; dialog.showModal();
  });
});
const close = () => dialog?.close();
document.querySelector('#viewer-close')?.addEventListener('click', close);
dialog?.addEventListener('click', event => { if (event.target === dialog) { const box = dialog.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) close(); } });
dialog?.addEventListener('close', () => { viewer?.querySelectorAll<HTMLMediaElement>('video,audio').forEach(p => { p.pause(); p.removeAttribute('src'); p.load(); }); viewer?.replaceChildren(); document.body.style.overflow = ''; opener?.focus(); });
zoom?.addEventListener('click', () => { const expanded = viewer?.classList.toggle('zoomed'); zoom.textContent = expanded ? 'Fit image' : 'Zoom image'; zoom.setAttribute('aria-pressed', String(expanded)); });
let filter = 'all', term = '', page = 1;
const cards = [...document.querySelectorAll<HTMLElement>('[data-media-card]')];
const filters = [...document.querySelectorAll<HTMLButtonElement>('[data-filter]')];
const search = document.querySelector<HTMLInputElement>('#gallery-search');
const previous = document.querySelector<HTMLButtonElement>('#gallery-previous');
const next = document.querySelector<HTMLButtonElement>('#gallery-next');
function render() {
  const matches = cards.filter(c => (filter === 'all' || c.dataset.type === filter) && c.dataset.search?.includes(term));
  const total = Math.max(1, Math.ceil(matches.length / 24)); page = Math.min(page, total);
  cards.forEach(c => { const index = matches.indexOf(c); c.hidden = index < (page - 1) * 24 || index >= page * 24; });
  filters.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.filter === filter)));
  const summary = document.querySelector('#gallery-count'); if (summary) summary.textContent = `${matches.length} ${matches.length === 1 ? 'item' : 'items'} · ${filter === 'all' ? 'All media' : filter === 'image' ? 'Screenshots' : filter === 'video' ? 'Videos' : 'Audio'}`;
  const label = document.querySelector('#gallery-page'); if (label) label.textContent = `Page ${page} of ${total}`;
  const empty = document.querySelector<HTMLElement>('#gallery-empty'); if (empty) empty.hidden = matches.length > 0;
  if (previous) previous.disabled = page === 1; if (next) next.disabled = page === total;
}
filters.forEach(b => b.addEventListener('click', () => { filter = b.dataset.filter || 'all'; page = 1; render(); if (!matchMedia('(prefers-reduced-motion: reduce)').matches) cards.filter(c => !c.hidden).forEach(c => c.animate([{ opacity: .3, transform: 'translateY(5px)' }, { opacity: 1, transform: 'none' }], { duration: 200 })); }));
search?.addEventListener('input', () => { term = search.value.trim().toLowerCase(); page = 1; render(); });
previous?.addEventListener('click', () => { page--; render(); document.querySelector('#gallery-results')?.scrollIntoView({ block: 'start' }); });
next?.addEventListener('click', () => { page++; render(); document.querySelector('#gallery-results')?.scrollIntoView({ block: 'start' }); });
if (search) render();
document.querySelectorAll<HTMLVideoElement>('.media-preview').forEach(preview => {
  const parent = preview.closest('button');
  parent?.addEventListener('mouseenter', () => { if (!matchMedia('(prefers-reduced-motion: reduce)').matches && !dialog?.open) void preview.play().then(() => preview.dataset.playing = 'true').catch(() => {}); });
  parent?.addEventListener('mouseleave', () => { preview.pause(); delete preview.dataset.playing; });
});
matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', event => {
  if (event.matches) document.querySelectorAll<HTMLVideoElement>('.media-preview').forEach(preview => { preview.pause(); delete preview.dataset.playing; });
});
