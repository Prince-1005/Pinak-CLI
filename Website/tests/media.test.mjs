import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { root, kind, cleanTitle, stableId, safeRelative, buildMedia, prepare } from '../scripts/media.mjs';
const loadDependency = createRequire(import.meta.url);
sharp.cache(false); // Release file handles before Windows fixture cleanup.
async function fixture(t) {
  await fs.mkdir(path.join(root, '.cache/test-fixtures'), { recursive: true });
  const dir = await fs.mkdtemp(path.join(root, '.cache/test-fixtures', 'pinak-media-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 }));
  const options = { mediaDir: path.join(dir, 'Media'), outputDir: path.join(dir, 'output'), cacheDir: path.join(dir, 'cache'), metadata: {} };
  await fs.mkdir(options.mediaDir);
  return options;
}
async function picture(file, width = 320, height = 600) { await sharp({ create: { width, height, channels: 3, background: '#173a44' } }).png().toFile(file); }
test('classification, stable identity, titles, and path boundaries', () => {
  assert.equal(kind('A.MP4'), 'video'); assert.equal(kind('music.opus'), 'audio'); assert.equal(kind('secret.exe'), null);
  assert.equal(cleanTitle('screen_capture-one.png'), 'screen capture one'); assert.equal(stableId('folder/a.mp4'), stableId('folder/a.mp4'));
  assert.notEqual(stableId('folder/a.mp4'), stableId('other/a.mp4'));
  for (const bad of ['../x', '/x', 'C:\\secret', 'https://example.com']) assert.throws(() => safeRelative(bad));
});
test('portrait, landscape, spaces and Unicode import without upscaling', async t => {
  const options = await fixture(t); await fs.mkdir(path.join(options.mediaDir, 'nested'));
  await picture(path.join(options.mediaDir, 'nested', '你好 capture.png'));
  await picture(path.join(options.mediaDir, 'landscape.png'), 1100, 400);
  const report = await buildMedia(options);
  assert.equal(report.items.length, 2);
  const portrait = report.items.find(i => i.width === 320);
  assert.equal(portrait.height, 600); assert.equal(portrait.variants.length, 1); assert.equal(portrait.variants[0].width, 320);
  assert.equal(report.warnings.filter(w => w.includes('description')).length, 2);
});
test('metadata and cache invalidate when caption or source changes', async t => {
  const options = await fixture(t); await picture(path.join(options.mediaDir, 'screen.png'));
  await fs.writeFile(path.join(options.mediaDir, 'captions.vtt'), 'WEBVTT\n\n00:00.000 --> 00:01.000\nFirst\n');
  options.metadata = { 'screen.png': { title: 'A title', description: 'A capture', captions: 'captions.vtt', featured: true, tags: ['test'] } };
  const first = await buildMedia(options); const again = await buildMedia(options);
  assert.equal(first.items[0].src, again.items[0].src); assert.equal(first.items[0].title, 'A title');
  await fs.appendFile(path.join(options.mediaDir, 'captions.vtt'), '\nChanged\n');
  const changed = await buildMedia(options); assert.notEqual(first.items[0].src, changed.items[0].src); assert.equal(first.items[0].id, changed.items[0].id);
});
test('unsupported files report and deleted media removes stale output', async t => {
  const options = await fixture(t); const source = path.join(options.mediaDir, 'image.png'); await picture(source);
  await fs.writeFile(path.join(options.mediaDir, 'file.xyz'), 'unsupported');
  const first = await buildMedia(options); assert.equal(first.items.length, 1); assert.match(first.warnings.join(' '), /Unsupported/);
  await fs.unlink(source); const after = await buildMedia(options); assert.equal(after.items.length, 0); assert.deepEqual(await fs.readdir(options.outputDir), []);
});
test('corrupt media names its file and invalid metadata fails clearly', async t => {
  const options = await fixture(t); await fs.writeFile(path.join(options.mediaDir, 'broken.png'), 'not an image');
  await assert.rejects(buildMedia(options), /broken.png/);
  await picture(path.join(options.mediaDir, 'broken.png'));
  options.metadata = { 'broken.png': { tags: 'not-array' } }; await assert.rejects(buildMedia(options), /tags must/);
  options.metadata = { 'broken.png': { cover: '../outside.png' } }; await assert.rejects(buildMedia(options), /relative media path/);
});
test('100 MiB source preflight prevents an unpublishable source', async t => {
  const options = await fixture(t); const file = await fs.open(path.join(options.mediaDir, 'large.mp4'), 'w'); await file.truncate(100 * 1024 ** 2); await file.close();
  await assert.rejects(buildMedia(options), /media:prepare/);
});
test('audio and video get browser-playable outputs, duration and covers', async t => {
  const options = await fixture(t); const binary = loadDependency('ffmpeg-static');
  for (const [name, args] of [
    ['clip.mp4', ['-f', 'lavfi', '-i', 'color=c=blue:s=320x180:d=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p']],
    ['tone.wav', ['-f', 'lavfi', '-i', 'sine=frequency=440:duration=1']]
  ]) { const result = spawnSync(binary, ['-y', ...args, path.join(options.mediaDir, name)], { windowsHide: true }); assert.equal(result.status, 0, result.stderr?.toString()); }
  const report = await buildMedia(options); assert.equal(report.items.length, 2);
  for (const item of report.items) { assert.ok(item.duration >= .9); assert.ok(item.poster); await fs.access(path.join(options.outputDir, item.src.replace('/generated/', ''))); }
  assert.ok(report.items.find(i => i.type === 'video').src.endsWith('.mp4'));
  assert.ok(report.items.find(i => i.type === 'audio').src.endsWith('.mp3'));
});
test('preparation preserves source bytes and refuses overwrites', async t => {
  const options = await fixture(t); const source = path.join(options.mediaDir, 'source.png'); await picture(source);
  const bytes = await fs.readFile(source); const target = path.join(options.cacheDir, 'prepared');
  await prepare(options.mediaDir, target); assert.deepEqual(await fs.readFile(source), bytes);
  await assert.rejects(prepare(options.mediaDir, target), /overwrite/);
});
test('animated GIF retains frames in web renditions', async t => {
  const options = await fixture(t);
  const source = path.join(options.mediaDir, 'animated.gif');
  const result = spawnSync(loadDependency('ffmpeg-static'), ['-y', '-f', 'lavfi', '-i', 'testsrc=size=64x32:rate=5:duration=0.4', source], { windowsHide: true });
  assert.equal(result.status, 0, result.stderr?.toString());
  const report = await buildMedia(options);
  const output = path.join(options.outputDir, report.items[0].src.replace('/generated/', ''));
  const metadata = await sharp(output, { animated: true }).metadata();
  assert.equal(metadata.pages, 2); assert.equal(report.items[0].height, 32);
});
test('identical bytes at different paths keep separate gallery identities', async t => {
  const options = await fixture(t);
  await picture(path.join(options.mediaDir, 'first.png'));
  await fs.copyFile(path.join(options.mediaDir, 'first.png'), path.join(options.mediaDir, 'second.png'));
  const report = await buildMedia(options);
  assert.equal(report.items.length, 2); assert.notEqual(report.items[0].id, report.items[1].id);
  assert.notEqual(report.items[0].title, report.items[1].title);
});
test('phone-photo EXIF orientation produces correct portrait dimensions', async t => {
  const options = await fixture(t);
  await sharp({ create: { width: 400, height: 200, channels: 3, background: '#21494c' } }).jpeg().withMetadata({ orientation: 6 }).toFile(path.join(options.mediaDir, 'phone.jpg'));
  const report = await buildMedia(options);
  assert.equal(report.items[0].width, 200); assert.equal(report.items[0].height, 400);
  const rendition = await sharp(path.join(options.outputDir, report.items[0].src.replace('/generated/', ''))).metadata();
  assert.equal(rendition.width, 200); assert.equal(rendition.height, 400);
});
