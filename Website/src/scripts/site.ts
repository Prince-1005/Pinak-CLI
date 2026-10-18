const announce = (message: string) => { const el = document.querySelector('#announcement'); if (el) el.textContent = message; };
const readPreference = (key: string) => { try { return localStorage.getItem(key); } catch { return null; } };
const savePreference = (key: string, value: string) => { try { localStorage.setItem(key, value); } catch { /* Private browsing still works. */ } };
const themeButton = document.querySelector<HTMLButtonElement>('#theme-toggle');
function updateThemeLabel() { themeButton?.setAttribute('aria-label', `Switch to ${document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'} theme`); }
updateThemeLabel();
themeButton?.addEventListener('click', () => { const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = theme; savePreference('pinak-theme', theme); updateThemeLabel(); });
const menu = document.querySelector<HTMLButtonElement>('.menu-toggle');
menu?.addEventListener('click', () => { const expanded = menu.getAttribute('aria-expanded') !== 'true'; menu.setAttribute('aria-expanded', String(expanded)); document.querySelector('#main-nav')?.classList.toggle('open', expanded); });
document.querySelectorAll('#main-nav a').forEach(a => a.addEventListener('click', () => { menu?.setAttribute('aria-expanded', 'false'); document.querySelector('#main-nav')?.classList.remove('open'); }));
document.addEventListener('keydown', event => { if (event.key === 'Escape' && menu?.getAttribute('aria-expanded') === 'true') { menu.click(); menu.focus(); } });
document.querySelectorAll<HTMLButtonElement>('[data-copy]').forEach(button => {
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(button.dataset.copy || '');
      button.textContent = 'Copied ✓'; announce('Command copied to clipboard.'); cue();
      setTimeout(() => { button.textContent = 'Copy ⧉'; }, 2200);
    } catch { announce('Clipboard unavailable. Select and copy the command text.'); button.textContent = 'Select text'; }
  });
});
document.querySelectorAll<HTMLElement>('[role=tablist]').forEach(tablist => {
  const tabs = [...tablist.querySelectorAll<HTMLButtonElement>('[role=tab]')];
  function activate(tab: HTMLButtonElement) {
    for (const other of tabs) {
      const selected = other === tab;
      other.setAttribute('aria-selected', String(selected)); other.tabIndex = selected ? 0 : -1;
      const panel = document.getElementById(other.getAttribute('aria-controls') || ''); if (panel) panel.hidden = !selected;
    }
  }
  // All instructions remain visible without JavaScript; progressively enhance to tabs.
  if (tabs[0]) activate(tabs[0]);
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => activate(tab));
    tab.addEventListener('keydown', event => {
      let next = index;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = tabs.length - 1;
      else return;
      event.preventDefault(); activate(tabs[next]); tabs[next].focus();
    });
  });
});
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
if (!reducedMotion.matches && 'IntersectionObserver' in window) {
  document.documentElement.classList.add('motion-ready');
  const observer = new IntersectionObserver(entries => { entries.forEach(entry => { if (entry.isIntersecting) { entry.target.classList.remove('pending'); observer.unobserve(entry.target); } }); }, { threshold: .08 });
  document.querySelectorAll('.reveal').forEach(el => { el.classList.add('pending'); observer.observe(el); });
  reducedMotion.addEventListener('change', () => { if (reducedMotion.matches) { observer.disconnect(); document.querySelectorAll('.pending').forEach(el => el.classList.remove('pending')); } });
}

// Original ambient composition: four slow chords, sine harmonics, gentle attack/release.
// Nothing is initialized until the visitor explicitly enables sound.
let context: AudioContext | undefined;
let ambient: GainNode | undefined;
let cues: GainNode | undefined;
let soundOn = false;
let timer: ReturnType<typeof setInterval> | undefined;
let chordIndex = 0;
const chords = [[130.81, 164.81, 196], [110, 130.81, 164.81], [87.31, 130.81, 174.61], [98, 146.83, 196]];
const soundButton = document.querySelector<HTMLButtonElement>('#sound-toggle');
const volumeControl = document.querySelector<HTMLInputElement>('#ambient-volume');
let volume = Math.min(100, Math.max(0, Number(readPreference('pinak-volume') ?? 20))) / 100;
if (volumeControl) volumeControl.value = String(volume * 100);
if (readPreference('pinak-sound') === 'on') {
  const label = document.querySelector('#sound-label'); if (label) label.textContent = 'Resume sound';
}
function mediaPlaying() { return [...document.querySelectorAll<HTMLMediaElement>('video:not([aria-hidden=true]),audio')].some(el => !el.paused && !el.ended); }
function playChord() {
  if (!context || !ambient || !soundOn || document.hidden || mediaPlaying()) return;
  const now = context.currentTime;
  chords[chordIndex++ % chords.length].forEach((frequency, i) => {
    const oscillator = context!.createOscillator(); const envelope = context!.createGain();
    oscillator.type = 'sine'; oscillator.frequency.value = frequency; oscillator.detune.value = i * 3;
    envelope.gain.setValueAtTime(0, now); envelope.gain.linearRampToValueAtTime(.07, now + 1.5); envelope.gain.linearRampToValueAtTime(0, now + 6.5);
    oscillator.connect(envelope).connect(ambient!); oscillator.start(now); oscillator.stop(now + 7);
  });
}
function updateAmbient() {
  if (!context || !ambient) return;
  const active = soundOn && !document.hidden && !mediaPlaying();
  ambient.gain.cancelScheduledValues(context.currentTime);
  ambient.gain.setTargetAtTime(active ? volume * .3 : 0, context.currentTime, .2);
  if (active && context.state === 'suspended') void context.resume().catch(() => {});
}
function cue() {
  if (!soundOn || !context || !cues || document.hidden || mediaPlaying()) return;
  const oscillator = context.createOscillator(), gain = context.createGain(), now = context.currentTime;
  oscillator.frequency.setValueAtTime(660, now); oscillator.frequency.exponentialRampToValueAtTime(880, now + .05);
  gain.gain.setValueAtTime(.025 * volume, now); gain.gain.exponentialRampToValueAtTime(.0001, now + .1);
  oscillator.connect(gain).connect(cues); oscillator.start(); oscillator.stop(now + .12);
}
soundButton?.addEventListener('click', () => {
  try {
    if (!context) {
      const AudioEngine = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioEngine) throw new Error('Web Audio unavailable');
      context = new AudioEngine(); ambient = context.createGain(); ambient.gain.value = 0; ambient.connect(context.destination); cues = context.createGain(); cues.connect(context.destination);
    }
    // Reflect the explicit preference immediately; some browsers defer resume
    // while the window is in the background. A pending resume must not trap mute.
    void context.resume().catch(() => {
      soundOn = false; if (timer) clearInterval(timer); updateAmbient();
      soundButton.setAttribute('aria-pressed', 'false');
      const label = document.querySelector('#sound-label'); if (label) label.textContent = 'Sound off';
      savePreference('pinak-sound', 'off');
      announce('Audio is unavailable in this browser. The website remains fully usable.');
    });
    soundOn = !soundOn;
    soundButton.setAttribute('aria-pressed', String(soundOn));
    const label = document.querySelector('#sound-label'); if (label) label.textContent = soundOn ? 'Sound on' : 'Sound off';
    savePreference('pinak-sound', soundOn ? 'on' : 'off');
    if (timer) clearInterval(timer);
    updateAmbient();
    if (soundOn) { playChord(); timer = setInterval(playChord, 6000); cue(); }
    announce(soundOn ? 'Ambient sound enabled.' : 'Ambient sound muted.');
  } catch { announce('Audio is unavailable in this browser. The website remains fully usable.'); }
});
volumeControl?.addEventListener('input', () => { volume = Number(volumeControl.value) / 100; savePreference('pinak-volume', volumeControl.value); updateAmbient(); });
document.addEventListener('visibilitychange', () => { updateAmbient(); if (document.hidden && context) setTimeout(() => { if (document.hidden) void context?.suspend(); }, 1000); else playChord(); });
for (const name of ['play', 'pause', 'ended', 'emptied']) document.addEventListener(name, updateAmbient, true);
document.addEventListener('play', event => {
  if (!(event.target instanceof HTMLMediaElement) || event.target.getAttribute('aria-hidden') === 'true') return;
  document.querySelectorAll<HTMLMediaElement>('video,audio').forEach(el => { if (el !== event.target) el.pause(); });
  updateAmbient();
}, true);
window.addEventListener('pagehide', () => { if (timer) clearInterval(timer); void context?.close(); });
