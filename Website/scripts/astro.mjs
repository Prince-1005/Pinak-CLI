import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const cli = fileURLToPath(new URL('../node_modules/astro/astro.js', import.meta.url));
const child = spawn(process.execPath, [cli, ...process.argv.slice(2)], { stdio: 'inherit', env: { ...process.env, ASTRO_TELEMETRY_DISABLED: '1' }, windowsHide: true });
child.on('error', error => { console.error(error); process.exitCode = 1; });
child.on('exit', code => { process.exitCode = code ?? 1; });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
