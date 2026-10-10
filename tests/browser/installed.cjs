const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {chromium} = require('playwright');

// Exercise the installed executable, not the source Python environment.
async function run() {
  assert.equal(process.platform, 'win32', 'Windows and WebView2 are required');
  const executable = path.resolve(process.argv[2] || '');
  const manifestPath = path.resolve(process.argv[3] || '');
  assert(fs.statSync(executable).isFile());
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
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
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'YunYouBao-installed-'));
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  const child = spawn(executable, ['--demo'], {cwd: path.dirname(executable),
    windowsHide: true, stdio: 'ignore', env: {...process.env,
      YUNYOUBAO_DATA_DIR: root,
      WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: '--remote-debugging-port=' + port}});
  let spawnError;
  child.on('error', error => { spawnError = error; });
  let browser;
  try {
    const deadline = Date.now() + 45000;
    while (Date.now() < deadline) {
      if (spawnError) throw spawnError;
      assert.equal(child.exitCode, null, 'Installed application exited before opening its window');
      try {
        const response = await fetch('http://127.0.0.1:' + port + '/json/version');
        if (response.ok) {
          browser = await chromium.connectOverCDP('http://127.0.0.1:' + port);
          break;
        }
      } catch { /* WebView2 is still starting. */ }
      await new Promise(resolve => setTimeout(resolve, 250));
    }
    assert(browser, 'Installed WebView2 did not start within 45 seconds');
    let page;
    while (Date.now() < deadline) {
      page = browser.contexts().flatMap(context => context.pages()).find(item => /127\.0\.0\.1/.test(item.url()));
      if (page) break;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert(page, 'Installed application did not load its local workbench');
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
    const report = {executable, verified_files: manifest.candidate_files.length,
      ...state, demonstration_rows: 32, page_errors: errors, smtp: 'no send requested; demo only'};
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  } finally {
    // Disconnect CDP; terminate only the application this check started.
    if (browser) await browser.close();
    if (child.exitCode === null && child.pid) {
      child.kill();
      await Promise.race([new Promise(resolve => child.once('exit', resolve)),
        new Promise(resolve => setTimeout(resolve, 5000))]);
    }
    if (child.exitCode !== null) fs.rmSync(root, {recursive: true, force: true});
  }
}

run().catch(error => { console.error(error); process.exitCode = 1; });
