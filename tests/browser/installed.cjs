const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {chromium} = require('playwright');

async function stopNative(window) {
  if (!window) return;
  if (window.browser) await window.browser.close().catch(() => {});
  if (window.child.exitCode === null && window.child.pid) {
    window.child.kill();
    await Promise.race([new Promise(resolve => window.child.once('exit', resolve)),
      new Promise(resolve => setTimeout(resolve, 5000))]);
  }
  assert.notEqual(window.child.exitCode, null, 'Owned application did not exit');
}

async function startNative(executable, root, demo) {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  const child = spawn(executable, demo ? ['--demo'] : [], {cwd: path.dirname(executable),
    windowsHide: true, stdio: 'ignore', env: {...process.env,
      YUNYOUBAO_DATA_DIR: root,
      WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: '--remote-debugging-port=' + port}});
  let spawnError;
  child.on('error', error => { spawnError = error; });
  const window = {child, browser: null, page: null};
  try {
    const deadline = Date.now() + 45000;
    while (Date.now() < deadline) {
      if (spawnError) throw spawnError;
      assert.equal(child.exitCode, null, 'Installed application exited before opening its window');
      try {
        const response = await fetch('http://127.0.0.1:' + port + '/json/version');
        if (response.ok) {
          window.browser = await chromium.connectOverCDP('http://127.0.0.1:' + port);
          break;
        }
      } catch { /* WebView2 is still starting. */ }
      await new Promise(resolve => setTimeout(resolve, 250));
    }
    assert(window.browser, 'Installed WebView2 did not start within 45 seconds');
    let page;
    while (Date.now() < deadline) {
      page = window.browser.contexts().flatMap(context => context.pages()).find(item => /127\.0\.0\.1/.test(item.url()));
      if (page) break;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert(page, 'Installed application did not load its local workbench');
    window.page = page;
    return window;
  } catch (error) {
    await stopNative(window);
    throw error;
  }
}

// Exercise the installed executable twice, using only synthetic, isolated data.
async function run() {
  assert.equal(process.platform, 'win32', 'Windows and WebView2 are required');
  const executable = path.resolve(process.argv[2] || '');
  const manifest = JSON.parse(fs.readFileSync(path.resolve(process.argv[3] || ''), 'utf8'));
  assert(fs.statSync(executable).isFile());
  for (const file of manifest.candidate_files) {
    const installed = path.join(path.dirname(executable), ...file.path.split('/'));
    assert(fs.existsSync(installed), 'Missing installed dependency: ' + file.path);
    const content = fs.readFileSync(installed);
    assert.equal(content.length, file.size, 'Installed size mismatch: ' + file.path);
    assert.equal(crypto.createHash('sha256').update(content).digest('hex'), file.sha256,
      'Installed hash mismatch: ' + file.path);
  }
  const output = path.resolve(__dirname, '../artifacts/installed');
  fs.mkdirSync(output, {recursive: true});
  const ownsRoot = !process.env.YUNYOUBAO_SMOKE_DATA_DIR;
  const root = ownsRoot ? fs.mkdtempSync(path.join(os.tmpdir(), 'YunYouBao-installed-')) : path.resolve(process.env.YUNYOUBAO_SMOKE_DATA_DIR);
  let window;
  const api = async (page, endpoint, body, method = 'POST') => page.evaluate(async ({endpoint, body, method}) => {
    const response = await fetch('/api/' + endpoint, {method, headers: {
      Authorization: 'Bearer ' + window.YUNYOUBAO.token, 'X-Yunyoubao-Mode': 'live',
      'Content-Type': 'application/json'}, ...(body === undefined ? {} : {body: JSON.stringify(body)})});
    if (!response.ok) throw new Error('Native fixture API failed: ' + endpoint + ' (' + response.status + ')');
    return response.json();
  }, {endpoint, body, method});
  const sends = [];
  const observe = page => page.on('request', request => {
    if (/\/api\/(test-send|tasks\/[^/]+\/(start|resume|retry))/.test(request.url())) sends.push(request.url());
  });
  try {
    window = await startNative(executable, root, true);
    const page = window.page;
    observe(page);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.waitForFunction(() => window.Quill && window.pywebview?.api.save_export && document.querySelector('.ql-editor'));
    const state = await page.evaluate(() => ({version: window.YUNYOUBAO.version,
      desktop: window.YUNYOUBAO.desktop, mode: window.YUNYOUBAO.initial_mode,
      editor: document.querySelector('.ql-editor').textContent.trim(),
      logo_width: document.querySelector('.brand img').naturalWidth,
      bridge: Object.keys(window.pywebview.api).sort()}));
    assert.equal(state.version, manifest.app_version);
    assert.equal(state.desktop, true);
    assert.equal(state.mode, 'demo');
    assert.equal(state.editor, '', 'Fresh editor must be blank');
    assert(state.logo_width > 0);
    assert.deepEqual(state.bridge, ['import_legacy', 'open_data_folder', 'save_export']);
    const font = await page.evaluate(async () => {
      await document.fonts.load('14px "Source Han Sans SC"');
      return [...document.fonts].some(face => face.family.includes('Source Han Sans SC') && face.status === 'loaded');
    });
    assert(font, 'Bundled Source Han Sans must load in installed WebView2');
    await page.click('#demo-load');
    await page.waitForFunction(() => document.querySelector('#import-counts').textContent.includes('32'));
    await page.mouse.move(8, 8);
    await page.screenshot({path: path.join(output, 'installed-workbench.png')});
    await page.click('[data-step="2"]');
    assert(await page.locator('.ql-editor').isVisible());
    await page.locator('.ql-editor').fill('Installed rich text editor check');
    assert.equal(await page.locator('.ql-editor').innerText(), 'Installed rich text editor check');
    await page.screenshot({path: path.join(output, 'installed-editor.png')});
    assert.deepEqual(errors, []);
    const saved = await api(page, 'accounts', {id: 'native-restart-fixture', email: 'native-restart@example.test',
      name: 'Native restart fixture', smtp_host: 'smtp.example.test', smtp_port: 465,
      security: 'ssl', password: 'FAKE-NATIVE-SECRET', remember: true, per_minute: 6, daily_limit: 200});
    await api(page, 'account-selection', {account_ids: [saved.id]}, 'PUT');
    const firstOrigin = new URL(page.url()).origin;
    await stopNative(window);
    window = await startNative(executable, root, false);
    observe(window.page);
    await window.page.waitForFunction(() => window.Quill && document.querySelector('.ql-editor'));
    await window.page.click('[data-step="3"]');
    const selected = window.page.locator('[data-account-select="native-restart-fixture"]');
    await selected.waitFor();
    assert(await selected.isChecked(), 'Saved account selection must survive a private WebView2 restart');
    const accounts = await api(window.page, 'accounts', undefined, 'GET');
    const restored = accounts.accounts.find(account => account.id === saved.id);
    assert(restored && restored.has_secret && restored.remember);
    assert(!Object.hasOwn(restored, 'password'));
    assert.deepEqual(sends, [], 'Native smoke must never request any send');
    const report = {executable, verified_files: manifest.candidate_files.length,
      ...state, demonstration_rows: 32, page_errors: errors, font_loaded: font,
      account_restart: true, origins: [firstOrigin, new URL(window.page.url()).origin],
      smtp: 'no send requested; synthetic data only'};
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  } finally {
    await stopNative(window);
    if (ownsRoot) fs.rmSync(root, {recursive: true, force: true});
  }
}

run().catch(error => { console.error(error); process.exitCode = 1; });
