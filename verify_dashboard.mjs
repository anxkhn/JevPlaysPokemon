import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
const require = createRequire(import.meta.url);
let chromium;
try {
  ({ chromium } = require('playwright-core'));
} catch {
  throw new Error('Install playwright-core to run dashboard browser checks: npm install -D playwright-core');
}
const server = spawn('./emulator.sh', ['--port', '8766'], { stdio: ['ignore', 'pipe', 'pipe'] });
server.stdout.on('data', data => process.stdout.write(data));
server.stderr.on('data', data => process.stderr.write(data));
let browser;
try {
  const base = 'http://127.0.0.1:8766';
  for (let i = 0; i < 100; i++) {
    if (await fetch(base + '/api/status').then(r => r.ok).catch(() => false)) break;
    if (server.exitCode !== null) throw new Error('Dashboard server exited');
    await new Promise(r => setTimeout(r, 200));
  }
  assert.equal((await fetch(base + '/api/catalog')).status, 200);
  const catalog = await fetch(base + '/api/catalog').then(r => r.json());
  assert.ok(catalog.species.some(p => p.name === 'Jolteon'));
  browser = await chromium.launch({ channel: 'chrome', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#start-button')?.disabled === false || document.body.innerText.includes('Ready to play'));
  await page.waitForTimeout(1500);
  await mkdir('emulator-data/checks', { recursive: true });
  await page.screenshot({ path: 'emulator-data/checks/dashboard.png', fullPage: true });
  await page.locator('#battle-setup').evaluate(el => el.open = true);
  await page.getByRole('button', { name: 'Edit party', exact: true }).click();
  assert.ok(await page.locator('#editor').isVisible());
  await page.screenshot({ path: 'emulator-data/checks/editor.png' });
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByRole('button', { name: 'Replays', exact: true }).click();
  await page.locator('.recording').filter({ hasText: 'Won' }).first().getByRole('button', { name: 'Watch replay' }).click();
  await page.waitForFunction(() => document.querySelector('#replay-video').readyState >= 1);
  await page.locator('#replay-jump').selectOption('0');
  await page.waitForTimeout(500);
  assert.ok((await page.locator('#chosen-action').textContent()).length > 0);
  assert.ok((await page.locator('#probabilities').innerText()).includes('%'));
  await page.screenshot({ path: 'emulator-data/checks/replay.png', fullPage: true });
  await page.locator('#raw-details').evaluate(el => el.open = true);
  await page.waitForTimeout(100);
  assert.ok((await page.locator('#raw-request').innerText()).includes('questions'));
  assert.ok((await page.locator('#raw-response').innerText()).includes('probabilities'));
  await page.getByRole('button', { name: 'Live view', exact: true }).click();
  if (process.env.LIVE_TEST === '1') {
  await page.locator('#speed-select').selectOption('4');
  await page.getByRole('button', { name: 'Start battle', exact: true }).click();
  await page.waitForFunction(() => Number(document.querySelector('#decision-count').textContent) > 0, null, { timeout: 60000 });
  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  await page.waitForTimeout(1200);
  assert.ok((await fetch(base + '/api/status').then(r => r.json())).paused);
  await page.screenshot({ path: 'emulator-data/checks/live.png', fullPage: true });
  await page.locator('#pause-button').click();
  let finished;
  for (let i = 0; i < 180; i++) {
    finished = await fetch(base + '/api/status').then(r => r.json());
    if (['finished', 'error', 'stopped'].includes(finished.phase)) break;
    await new Promise(r => setTimeout(r, 1000));
  }
  assert.equal(finished.phase, 'finished', finished.message);
  assert.ok(['Won', 'Lost', 'Draw'].includes(finished.outcome));
  console.log(`Live UI battle result ${finished.outcome}: ${finished.run}, ${finished.decisions} real decisions.`);
  await page.screenshot({ path: 'emulator-data/checks/win.png', fullPage: true });
  }
  assert.deepEqual(errors, []);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: 'emulator-data/checks/mobile.png', fullPage: true });
  console.log('Dashboard boot, catalog, browser errors and mobile overflow checks passed.');
} finally {
  await browser?.close();
  server.kill('SIGINT');
  await new Promise(resolve => server.once('exit', resolve));
}
