import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import sharp from 'sharp';

export const root = fileURLToPath(new URL('../', import.meta.url));
const require = createRequire(import.meta.url);
const images = new Set(['.png', '.jpg', '.jpeg', '.webp', '.avif', '.gif']);
const videos = new Set(['.mp4', '.webm', '.mov', '.mkv', '.avi']);
const audios = new Set(['.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.opus']);
export const kind = (filename) => images.has(path.extname(filename).toLowerCase()) ? 'image' : videos.has(path.extname(filename).toLowerCase()) ? 'video' : audios.has(path.extname(filename).toLowerCase()) ? 'audio' : null;
export const cleanTitle = (filename) => path.basename(filename, path.extname(filename)).replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
export const stableId = (filename) => createHash('sha256').update(filename.split(path.sep).join('/')).digest('hex').slice(0, 16);
export function safeRelative(filename) {
  if (typeof filename !== 'string' || path.isAbsolute(filename) || filename.split(/[\\/]/).some(p => p === '..') || /^[a-z]+:/i.test(filename)) throw new Error(`Expected a relative media path: ${filename}`);
  return filename.replaceAll('\\', '/');
}
export async function walk(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true }).catch(e => { if (e.code === 'ENOENT') return []; throw e; });
  const files = [];
  for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name, 'en'))) {
    if (entry.isSymbolicLink() || entry.name.startsWith('.')) continue;
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) files.push(...await walk(file));
    else if (entry.isFile()) files.push(file);
  }
  return files;
}
const ffmpeg = () => process.env.FFMPEG_PATH || require('ffmpeg-static');
const ffprobe = () => process.env.FFPROBE_PATH || require('ffprobe-static').path;
async function run(exe, args) {
  return new Promise((resolve, reject) => {
    const proc = spawn(exe, args, { windowsHide: true });
    let out = '', err = '';
    proc.stdout.on('data', b => { out += b; });
    proc.stderr.on('data', b => { err = (err + b).slice(-12000); });
    proc.on('error', reject);
    proc.on('close', code => code === 0 ? resolve(out) : reject(new Error(`${path.basename(exe)} exited ${code}: ${err}`)));
  });
}
export async function probe(file) {
  const data = JSON.parse(await run(ffprobe(), ['-v', 'error', '-show_format', '-show_streams', '-of', 'json', file]));
  const video = data.streams.find(s => s.codec_type === 'video' && !s.disposition?.attached_pic);
  const audio = data.streams.find(s => s.codec_type === 'audio');
  return { duration: Number(data.format.duration) || 0, width: video?.width, height: video?.height, video, audio, streams: data.streams };
}
async function hashFile(file) { return createHash('sha256').update(await fs.readFile(file)).digest('hex'); }
async function encodeVideo(source, destination, info, budget = 40 * 1024 ** 2) {
  if (!info.video || !info.duration) throw new Error('No valid video stream/duration. Re-export as MP4 and retry.');
  const scale = "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2";
  const common = ['-y', '-i', source, '-map', '0:v:0', '-map', '0:a:0?', '-vf', scale, '-c:v', 'libx264', '-preset', 'fast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k', '-movflags', '+faststart', '-map_metadata', '-1'];
  await run(ffmpeg(), [...common, '-crf', '23', destination]);
  if ((await fs.stat(destination)).size > budget) {
    const bitrate = Math.floor(budget * 8 * 0.94 / info.duration - (info.audio ? 96000 : 0));
    if (bitrate < 350000) throw new Error('40 MiB budget would require unreadable quality. Supply a shorter editorial version or adjust the budget deliberately.');
    const log = `${destination}.pass`;
    await run(ffmpeg(), [...common, '-b:v', String(bitrate), '-pass', '1', '-passlogfile', log, '-an', '-f', 'null', process.platform === 'win32' ? 'NUL' : '/dev/null']);
    await run(ffmpeg(), [...common, '-b:v', String(bitrate), '-pass', '2', '-passlogfile', log, destination]);
    for (const suffix of ['-0.log', '-0.log.mbtree']) await fs.rm(log + suffix, { force: true });
  }
  const result = await probe(destination);
  if (Math.abs(result.duration - info.duration) > Math.max(1, info.duration * .01)) throw new Error('Encoded duration differs from original; refusing to publish a truncated file.');
  if ((await fs.stat(destination)).size > budget) throw new Error('Encoded video exceeds the 40 MiB budget; provide an editorial version.');
}
export async function prepare(sourceDir, targetDir = path.join(root, 'Media')) {
  const from = path.resolve(sourceDir), target = path.resolve(targetDir);
  if (from === target) throw new Error('Use a separate source folder; originals must remain untouched.');
  const all = await walk(from);
  if (!all.length) throw new Error(`No source files found in ${from}`);
  for (const source of all) {
    const relative = path.relative(from, source);
    const type = kind(source);
    if (!type && !['.vtt', '.txt', '.md'].includes(path.extname(source).toLowerCase())) continue;
    const destRelative = type === 'video' ? relative.replace(/\.[^.]+$/, '.mp4') : relative;
    const destination = path.join(target, destRelative);
    await fs.mkdir(path.dirname(destination), { recursive: true });
    try { await fs.access(destination); throw new Error(`Refusing to overwrite ${destination}; choose another name or remove it explicitly.`); } catch (error) { if (error.code !== 'ENOENT') throw error; }
    const temp = destination.replace(/(\.[^.]+)$/, '.preparing$1');
    try {
      if (type === 'video') await encodeVideo(source, temp, await probe(source));
      else await fs.copyFile(source, temp);
      if ((await fs.stat(temp)).size >= 100 * 1024 ** 2) throw new Error('File exceeds GitHub’s 100 MiB limit.');
      await fs.rename(temp, destination);
      console.log(`Prepared ${destRelative}`);
    } finally { await fs.rm(temp, { force: true }); }
  }
}
function validateMeta(meta, filename) {
  if (!meta || typeof meta !== 'object' || Array.isArray(meta)) throw new Error(`Metadata for ${filename} must be an object.`);
  for (const key of ['title', 'description', 'alt', 'poster', 'cover', 'captions', 'transcript', 'focalPoint']) if (meta[key] !== undefined && typeof meta[key] !== 'string') throw new Error(`${filename}: ${key} must be text.`);
  if (meta.tags !== undefined && (!Array.isArray(meta.tags) || meta.tags.some(x => typeof x !== 'string'))) throw new Error(`${filename}: tags must be strings.`);
  if (meta.featured !== undefined && typeof meta.featured !== 'boolean') throw new Error(`${filename}: featured must be boolean.`);
  if (meta.order !== undefined && !Number.isFinite(meta.order)) throw new Error(`${filename}: order must be a number.`);
  if (meta.previewRange !== undefined && (!Array.isArray(meta.previewRange) || meta.previewRange.length !== 2 || meta.previewRange.some(x => !Number.isFinite(x)) || meta.previewRange[0] < 0 || meta.previewRange[1] <= meta.previewRange[0] || meta.previewRange[1] - meta.previewRange[0] > 12)) throw new Error(`${filename}: previewRange is [startSeconds, endSeconds], up to 12 seconds.`);
}
export async function buildMedia(options = {}) {
  const mediaDir = options.mediaDir || path.join(root, 'Media');
  const outputDir = options.outputDir || path.join(root, 'public/generated');
  const cacheDir = options.cacheDir || path.join(root, '.cache/media');
  const metadata = options.metadata || JSON.parse(await fs.readFile(path.join(root, 'media.json'), 'utf8'));
  await fs.mkdir(outputDir, { recursive: true });
  const expected = new Set(); const items = []; const warnings = [];
  const files = await walk(mediaDir);
  const supported = files.filter(kind);
  const fileNames = new Set(files.map(f => path.relative(mediaDir, f).replaceAll('\\', '/')));
  for (const key of Object.keys(metadata)) if (!fileNames.has(key)) warnings.push(`Unused metadata: ${key}`);
  for (const file of files) if (!kind(file) && !['.vtt', '.txt', '.md'].includes(path.extname(file).toLowerCase())) warnings.push(`Unsupported: ${path.relative(mediaDir, file)}`);
  for (const source of supported) {
    const relative = path.relative(mediaDir, source).replaceAll('\\', '/');
    try {
      if ((await fs.stat(source)).size >= 100 * 1024 ** 2) throw new Error('Over 100 MiB. Use npm run media:prepare -- --from <external-folder> before committing.');
      const meta = metadata[relative] || {}; validateMeta(meta, relative);
      const attachments = {};
      for (const field of ['poster', 'cover', 'captions', 'transcript']) if (meta[field]) {
        const ref = safeRelative(meta[field]);
        const full = path.join(mediaDir, ref);
        attachments[field] = { path: full, hash: await hashFile(full) };
      }
      const key = createHash('sha256').update(relative).update(await hashFile(source)).update(JSON.stringify(meta)).update(JSON.stringify(attachments)).update(JSON.stringify(sharp.versions)).update('pipeline-v4').digest('hex').slice(0, 20);
      const cache = path.join(cacheDir, key); const dataFile = path.join(cache, 'item.json');
      let item;
      try { item = JSON.parse(await fs.readFile(dataFile, 'utf8')); } catch { /* Generate on cache miss. */ }
      if (!item) {
        await fs.mkdir(cache, { recursive: true });
        const type = kind(source);
        item = { id: stableId(relative), original: relative, type, title: meta.title || cleanTitle(relative), description: meta.description || '', alt: meta.alt || meta.description || cleanTitle(relative), tags: meta.tags || [], featured: meta.featured || false, order: meta.order ?? 100, variants: [], focalPoint: meta.focalPoint };
        if (type === 'image') {
          const imageInfo = await sharp(source, { animated: true, limitInputPixels: 80000000 }).metadata();
          const rotated = [5, 6, 7, 8].includes(imageInfo.orientation);
          item.width = rotated ? imageInfo.pageHeight || imageInfo.height : imageInfo.width;
          item.height = rotated ? imageInfo.width : imageInfo.pageHeight || imageInfo.height;
          for (const width of [...new Set([480, 960, 1600, Math.min(item.width, 2400)].filter(w => w <= item.width))]) {
            const filename = `image-${width}.webp`;
            await sharp(source, { animated: true, limitInputPixels: 80000000 }).rotate().resize({ width, withoutEnlargement: true }).webp({ quality: 84 }).toFile(path.join(cache, filename));
            item.variants.push({ width, src: filename });
          }
          item.src = item.variants.at(-1).src;
          item.poster = item.variants.find(v => v.width >= 960)?.src || item.src;
          const customCover = attachments.poster || attachments.cover;
          if (customCover) { item.poster = 'cover.webp'; await sharp(customCover.path).rotate().resize({ width: 960, withoutEnlargement: true }).webp().toFile(path.join(cache, item.poster)); }
        } else {
          const info = await probe(source);
          if (type === 'video') {
            await encodeVideo(source, path.join(cache, 'video.mp4'), info);
            item.src = 'video.mp4'; item.width = info.width; item.height = info.height;
            if (!attachments.poster && !attachments.cover) await run(ffmpeg(), ['-y', '-ss', String(Math.min(info.duration * .2, 5)), '-i', source, '-frames:v', '1', '-vf', 'scale=min(960\\,iw):-2', path.join(cache, 'poster.jpg')]);
            item.poster = 'poster.jpg';
            if (meta.featured && meta.previewRange) {
              const [start, end] = meta.previewRange;
              if (end > info.duration) throw new Error('Preview range exceeds media duration.');
              await run(ffmpeg(), ['-y', '-ss', String(start), '-i', source, '-t', String(end - start), '-an', '-vf', 'scale=min(640\\,iw):-2', '-c:v', 'libx264', '-crf', '28', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', path.join(cache, 'preview.mp4')]);
              item.preview = 'preview.mp4';
            }
          } else {
            if (!info.audio) throw new Error('No audio stream.');
            await run(ffmpeg(), ['-y', '-i', source, '-vn', '-c:a', 'libmp3lame', '-b:a', '128k', '-map_metadata', '-1', path.join(cache, 'audio.mp3')]);
            item.src = 'audio.mp3'; item.poster = 'poster.webp';
            const art = info.streams.find(s => s.disposition?.attached_pic);
            if (art && !attachments.cover && !attachments.poster) {
              await run(ffmpeg(), ['-y', '-i', source, '-map', `0:${art.index}`, '-frames:v', '1', path.join(cache, 'art.png')]);
              await sharp(path.join(cache, 'art.png')).resize(640, 640, { fit: 'inside' }).webp().toFile(path.join(cache, item.poster));
            } else if (!attachments.cover && !attachments.poster) {
              await sharp(Buffer.from('<svg width="640" height="640" xmlns="http://www.w3.org/2000/svg"><rect width="640" height="640" fill="#101b25"/><circle cx="320" cy="300" r="150" fill="none" stroke="#6be0ef" stroke-width="2"/><circle cx="320" cy="300" r="100" fill="none" stroke="#6be0ef" stroke-width="2"/><circle cx="320" cy="300" r="18" fill="#efb96c"/><path d="M70 540H570" stroke="#6be0ef" stroke-width="2"/></svg>')).webp().toFile(path.join(cache, item.poster));
            }
          }
          item.duration = info.duration;
          const customPoster = attachments.poster || attachments.cover;
          if (customPoster) { item.poster = 'poster.webp'; await sharp(customPoster.path).rotate().resize({ width: 960, withoutEnlargement: true }).webp().toFile(path.join(cache, item.poster)); }
        }
        if (attachments.captions) {
          const text = await fs.readFile(attachments.captions.path, 'utf8');
          if (!text.startsWith('WEBVTT')) throw new Error('Captions must be WebVTT (.vtt), beginning WEBVTT.');
          await fs.copyFile(attachments.captions.path, path.join(cache, 'captions.vtt')); item.captions = 'captions.vtt';
        }
        if (attachments.transcript) { await fs.copyFile(attachments.transcript.path, path.join(cache, 'transcript.txt')); item.transcript = 'transcript.txt'; }
        await fs.writeFile(dataFile, JSON.stringify(item));
      }
      expected.add(key);
      await fs.cp(cache, path.join(outputDir, key), { recursive: true });
      await fs.rm(path.join(outputDir, key, 'item.json'), { force: true });
      await fs.rm(path.join(outputDir, key, 'art.png'), { force: true });
      const asset = p => `/generated/${key}/${p}`;
      items.push({ ...item, src: asset(item.src), poster: asset(item.poster), variants: item.variants.map(v => ({ ...v, src: asset(v.src) })), ...(item.captions ? { captions: asset(item.captions) } : {}), ...(item.transcript ? { transcript: asset(item.transcript) } : {}), ...(item.preview ? { preview: asset(item.preview) } : {}) });
      if (!item.description) warnings.push(`Add a description for ${relative}`);
    } catch (error) { throw new Error(`Media validation failed: ${relative}\n${error.message}\nRe-export or replace this file and retry.`, { cause: error }); }
  }
  for (const entry of await fs.readdir(outputDir, { withFileTypes: true })) if (entry.isDirectory() && !expected.has(entry.name)) await fs.rm(path.join(outputDir, entry.name), { recursive: true });
  const bytes = (await Promise.all((await walk(outputDir)).map(f => fs.stat(f)))).reduce((n, s) => n + s.size, 0);
  if (bytes > 900 * 1024 ** 2) throw new Error('Media output exceeds the 900 MiB site safety budget. Reduce media before deploying.');
  items.sort((a, b) => a.order - b.order || a.original.localeCompare(b.original, 'en'));
  return { items, warnings, bytes };
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    if (process.argv.includes('--prepare')) {
      const index = process.argv.indexOf('--from');
      if (index < 0 || !process.argv[index + 1]) throw new Error('Usage: npm run media:prepare -- --from <external-folder>');
      await prepare(process.argv[index + 1]);
    } else {
      const report = await buildMedia();
      await fs.mkdir(path.join(root, 'src/generated'), { recursive: true });
      await fs.writeFile(path.join(root, 'src/generated/media.json'), JSON.stringify(report.items, null, 2));
      await fs.mkdir(path.join(root, '.cache'), { recursive: true });
      await fs.writeFile(path.join(root, '.cache/media-report.json'), JSON.stringify(report, null, 2));
      console.log(`Media: ${report.items.length} items, ${(report.bytes / 1024 ** 2).toFixed(1)} MiB generated.`);
      report.warnings.forEach(w => console.warn(w));
    }
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
