// QA only. Run against an isolated --demo server; no send/task-write endpoint is allowed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {chromium} = require('playwright');

const base = process.env.YUNYOUBAO_TEST_URL || 'http://127.0.0.1:8131';
const root = path.resolve(__dirname, '../..');
const output = path.resolve(__dirname, '../artifacts/browser');
const fixtures = path.join(output, 'product-fixtures');
const C = {
  name: '\u59d3\u540d', attachment: '\u4e2d\u6587\u9644\u4ef6\u6d4b\u8bd5',
  subject: '\u754c\u9762\u9a8c\u6536', old: '\u65e7\u8349\u7a3f',
};
const report = {url: base, playwright: require('playwright/package.json').version,
  results: [], dimensions: [], page_errors: [], unexpected_http: [], blocked_requests: [],
  selection_requests: [], screenshots: [], tasks_before: null, tasks_after: null};
let browser, child, persisted, helperError = '';
let resolveExit;
const helperExit = new Promise(resolve => { resolveExit = resolve; });

async function startFixtures() {
  const local = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const python = process.env.YUNYOUBAO_TEST_PYTHON || (fs.existsSync(local) ? local :
    process.platform === 'win32' ? 'python' : 'python3');
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Fixture service startup timed out: ' + helperError)), 30000);
    child = spawn(python, [path.join(__dirname, 'product-fixtures.py'), '--output', fixtures],
      {cwd: root, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
        env: {...process.env, PYTHONDONTWRITEBYTECODE: '1'}});
    let pending = '';
    child.stderr.on('data', data => { helperError += data; });
    child.stdout.on('data', data => {
      pending += data;
      const lines = pending.split(/\r?\n/);
      pending = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const item = JSON.parse(line);
          if (item.kind === 'ready') { clearTimeout(timeout); resolve(item.url); }
          if (item.kind === 'persisted') persisted = item.data;
        } catch (error) { helperError += line + '\n'; }
      }
    });
    child.on('error', error => { clearTimeout(timeout); reject(error); resolveExit(-1); });
    child.on('exit', code => {
      clearTimeout(timeout); resolveExit(code);
      if (!persisted) reject(new Error('Fixture service exited: ' + code + ' ' + helperError));
    });
  });
}

async function stopFixtures() {
  if (!child || child.exitCode !== null) return;
  child.stdin.end('\n');
  let timer;
  const result = await Promise.race([helperExit, new Promise(resolve => {
    timer = setTimeout(() => { child.kill(); resolve('timeout'); }, 15000);
  })]);
  clearTimeout(timer);
  if (result === 'timeout') await helperExit;
  assert.equal(result, 0, 'Fixture service must shut down cleanly: ' + helperError);
}

async function contextFor(url, isolated = false, mobile = false) {
  const context = await browser.newContext({viewport: mobile ? {width: 390, height: 844} :
    {width: 1440, height: 1000}, isMobile: mobile, hasTouch: mobile, reducedMotion: 'reduce'});
  context.on('page', page => {
    page.setDefaultTimeout(6000);
    page.on('pageerror', error => report.page_errors.push({url, message: error.message}));
    page.on('dialog', dialog => dialog.accept());
  });
  const origin = new URL(url).origin;
  await context.route('**/*', async route => {
    const request = route.request();
    const parsed = new URL(request.url());
    if (['data:', 'blob:', 'about:'].includes(parsed.protocol)) return route.continue();
    const pathname = parsed.pathname;
    const method = request.method();
    const api = pathname.startsWith('/api/');
    const mode = request.headers()['x-yunyoubao-mode'];
    const safeWrite = (method === 'POST' && ['/api/attachments', '/api/drafts', '/api/preview-email'].includes(pathname)) ||
      (method === 'POST' && /^\/api\/imports\/[^/]+\/preview$/.test(pathname)) ||
      (method === 'PUT' && pathname === '/api/account-selection') ||
      (method === 'DELETE' && /^\/api\/drafts\/[^/]+$/.test(pathname)) ||
      (isolated && method === 'POST' && pathname === '/api/accounts');
    if (parsed.origin !== origin || (api && (!['GET', 'HEAD'].includes(method) && !safeWrite)) ||
        (api && mode !== 'demo' && !(isolated && mode === 'live'))) {
      report.blocked_requests.push({url: request.url(), method, mode});
      return route.abort('blockedbyclient');
    }
    if (pathname === '/api/account-selection') {
      report.selection_requests.push({origin, method, mode,
        ...(method === 'PUT' ? {body: request.postDataJSON()} : {})});
    }
    await route.continue();
  });
  context.on('response', response => {
    if (response.status() >= 400) report.unexpected_http.push({url: response.url(), status: response.status()});
  });
  const page = await context.newPage();
  await page.goto(url, {waitUntil: 'networkidle'});
  assert.equal(await page.evaluate(() => window.YUNYOUBAO.initial_mode), 'demo', 'Require --demo server');
  await page.locator('#demo-banner').waitFor({state: 'visible'});
  await page.locator('.ql-editor').waitFor({state: 'attached'});
  return {context, page};
}

async function api(page, endpoint, method = 'GET', body, mode = 'demo') {
  return page.evaluate(async ({endpoint, method, body, mode}) => {
    const response = await fetch('/api' + endpoint, {method, headers: {
      Authorization: 'Bearer ' + window.YUNYOUBAO.token, 'X-Yunyoubao-Mode': mode,
      ...(body === undefined ? {} : {'Content-Type': 'application/json'})},
      ...(body === undefined ? {} : {body: JSON.stringify(body)})});
    if (!response.ok) throw new Error(endpoint + ': HTTP ' + response.status + ' ' + await response.text());
    return response.json();
  }, {endpoint, method, body, mode});
}

async function check(name, page, action) {
  const started = Date.now();
  try {
    const evidence = await action();
    report.results.push({name, status: 'pass', ms: Date.now() - started, ...(evidence ? {evidence} : {})});
    console.log('PASS ' + name);
  } catch (error) {
    const screenshot = 'product-failure-' + report.results.length + '.png';
    if (page && !page.isClosed()) await page.screenshot({path: path.join(output, screenshot), fullPage: true}).catch(() => {});
    report.results.push({name, status: 'fail', ms: Date.now() - started, message: error.message,
      stack: error.stack, screenshot});
    console.error('FAIL ' + name + ': ' + error.message);
  }
}

async function shot(page, name) {
  await page.locator('#toast').waitFor({state: 'hidden', timeout: 10000});
  await page.screenshot({path: path.join(output, name), fullPage: true});
  report.screenshots.push(name);
}

async function step(page, number) {
  await page.click('[data-view="workspace"]');
  await page.click('[data-step="' + number + '"]');
}

async function quillState(page) {
  return page.evaluate(() => {
    const q = document.querySelector('#editor').__quill;
    return {text: q.getText(), html: q.root.innerHTML, delta: q.getContents(),
      selection: q.getSelection(), format: q.getFormat(0, 5)};
  });
}

async function selectAlpha(page) {
  await page.locator('.ql-editor').click();
  await page.keyboard.press('Control+Home');
  for (let index = 0; index < 5; index++) await page.keyboard.press('Shift+ArrowRight');
  assert.deepEqual((await quillState(page)).selection, {index: 0, length: 5});
}

async function savedDraft(page) {
  const pending = page.waitForResponse(r => new URL(r.url()).pathname === '/api/drafts' && r.request().method() === 'POST');
  await page.click('#draft-save');
  const response = await pending;
  assert.equal(response.status(), 200);
  const item = await response.json();
  await page.waitForFunction(() => document.querySelector('#draft-state').textContent === '\u8349\u7a3f\u5df2\u4fdd\u5b58');
  return item.draft || item;
}

async function openDraft(page, id) {
  await page.click('#draft-open');
  await page.locator('[data-draft-load="' + id + '"]').click();
  await page.locator('#modal').waitFor({state: 'hidden'});
  await step(page, 2);
}

async function wrapperCount(page, html) {
  return page.evaluate(value => {
    const element = document.createElement('div'); element.innerHTML = value;
    return element.querySelectorAll('[data-yunmailbao-body]').length;
  }, html);
}

async function layout(page, label) {
  const evidence = await page.evaluate(() => {
    const visible = element => !!(element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden');
    const outside = [...document.querySelectorAll('button, select, input:not([type="file"]), .help-node-detail, .editor-shell')]
      .filter(visible).map(element => ({id: element.id || element.className,
        x: element.getBoundingClientRect().left, right: element.getBoundingClientRect().right}))
      .filter(item => item.x < -1 || item.right > innerWidth + 1);
    return {width: innerWidth, document: document.documentElement.scrollWidth,
      body: document.body.scrollWidth, outside};
  });
  report.dimensions.push({label, ...evidence});
  assert(evidence.document <= evidence.width && evidence.body <= evidence.width, JSON.stringify(evidence));
  assert.deepEqual(evidence.outside, [], 'Visible controls outside viewport: ' + JSON.stringify(evidence.outside));
}

async function main() {
  fs.mkdirSync(output, {recursive: true});
  const fixtureUrl = await startFixtures();
  report.isolated_url = fixtureUrl;
  browser = await chromium.launch({headless: true,
    ...(process.env.BROWSER_EXECUTABLE ? {executablePath: process.env.BROWSER_EXECUTABLE} : {})});
  const {context, page} = await contextFor(base);
  const createdDrafts = [];
  try {
    report.tasks_before = (await api(page, '/tasks')).tasks.map(task => task.id).sort();
    await step(page, 2);
    await check('editor: initially empty and default native controls', page, async () => {
      const state = await quillState(page);
      assert.equal(state.text, '\n');
      assert.equal(await page.inputValue('#subject'), '');
      for (const [selector, value] of [['#editor-font', 'Source Han Sans SC'], ['#editor-size', '14px']]) {
        const control = page.locator(selector);
        assert(await control.isVisible(), selector + ' must be visible');
        assert.equal(await control.evaluate(el => el.tagName), 'SELECT');
        assert.equal(await control.inputValue(), value);
        const box = await control.boundingBox(); assert(box.width >= 40 && box.height >= 24);
      }
      assert.equal(await page.locator('#editor-toolbar .ql-picker').count(), 0);
      const computed = await page.locator('.ql-editor').evaluate(el => ({font: getComputedStyle(el).fontFamily,
        size: getComputedStyle(el).fontSize}));
      assert.match(computed.font, /^"?Source Han Sans SC/); assert.equal(computed.size, '14px');
      return computed;
    });
    await check('editor: Source Han font actually loaded', page, async () => {
      await page.evaluate(() => document.fonts.ready);
      const faces = await page.evaluate(() => [...document.fonts].filter(face =>
        face.family.replace(/["']/g, '') === 'Source Han Sans SC').map(face => ({family: face.family, status: face.status})));
      assert(faces.length > 0 && faces.every(face => face.status === 'loaded'), JSON.stringify(faces));
      assert(await page.evaluate(() => document.fonts.check('14px "Source Han Sans SC"', '\u4e2d\u6587')));
      return faces;
    });
    await check('editor: attachment top-left and thin lucide icons', page, async () => {
      const command = await page.locator('.editor-command-row').boundingBox();
      const attachment = await page.locator('#attachment-upload').boundingBox();
      const format = await page.locator('.editor-format-row').boundingBox();
      assert(attachment.x - command.x <= 12 && attachment.y < format.y);
      assert.equal(await page.locator('i[data-lucide]').count(), 0, 'Unrendered icon placeholders');
      const icons = await page.locator('#editor-toolbar button svg').evaluateAll(elements => elements.map(el =>
        ({name: el.parentElement.id || el.parentElement.className, lucide: el.classList.contains('lucide'),
          stroke: getComputedStyle(el).strokeWidth, fill: getComputedStyle(el).fill})));
      assert(icons.length >= 15, JSON.stringify(icons));
      assert(icons.every(icon => icon.lucide && parseFloat(icon.stroke) <= 1.8 && icon.fill === 'none'), JSON.stringify(icons));
      return {attachment, icon_count: icons.length};
    });
    await page.fill('#subject', C.subject + ' ' + Date.now());
    await page.locator('.ql-editor').fill('Alpha Beta Gamma');
    await selectAlpha(page);
    await page.waitForTimeout(1100); // Quill history groups changes within its configured 1000ms delay.
    await check('editor: bold preserves selected range', page, async () => {
      await page.click('.ql-bold');
      const state = await quillState(page); assert.equal(state.format.bold, true);
      assert.deepEqual(state.selection, {index: 0, length: 5});
    });
    await page.waitForTimeout(1100);
    await check('editor: native size applies only selected text', page, async () => {
      await selectAlpha(page);
      await page.selectOption('#editor-size', '24px');
      const state = await quillState(page);
      assert.equal(state.format.size, '24px'); assert.equal(state.format.bold, true);
      assert.deepEqual(state.selection, {index: 0, length: 5});
      assert(state.delta.ops.some(op => String(op.insert).includes('Beta') && !op.attributes?.size), JSON.stringify(state.delta));
    });
    await check('editor: undo formatting preserves selected range', page, async () => {
      await page.click('#editor-undo');
      const state = await quillState(page);
      assert.equal(state.format.size, undefined); assert.equal(state.format.bold, true);
      assert.deepEqual(state.selection, {index: 0, length: 5}, 'Undo must preserve selection');
    });
    await check('editor: redo formatting preserves selected range', page, async () => {
      await selectAlpha(page);
      await page.click('#editor-redo');
      const state = await quillState(page);
      assert.equal(state.format.size, '24px'); assert.equal(state.format.bold, true);
      assert.deepEqual(state.selection, {index: 0, length: 5}, 'Redo must preserve selection');
    });
    await shot(page, '07-editor.png');
    await check('draft: repeated save/reopen keeps exactly one body wrapper', page, async () => {
      const expected = (await quillState(page)).delta;
      for (let round = 0; round < 3; round++) {
        const draft = await savedDraft(page);
        if (!createdDrafts.includes(draft.id)) createdDrafts.push(draft.id);
        assert.equal(await wrapperCount(page, draft.config.html_content), 1);
        await openDraft(page, draft.id);
        assert.equal(await page.locator('.ql-editor [data-yunmailbao-body]').count(), 0);
        assert.deepEqual((await quillState(page)).delta, expected);
      }
    });
    await check('draft: legacy name token translates on UI open and next save', page, async () => {
      const legacy = await api(page, '/drafts', 'POST', {title: C.old, config: {name_column: C.name,
        subject: C.old + ' <\u4eba\u540d>', html_content: '<p>&lt;\u4eba\u540d&gt; / <\u4eba\u540d></p>'}});
      createdDrafts.push(legacy.id);
      await openDraft(page, legacy.id);
      const variable = '{{' + C.name + '}}';
      assert.equal(await page.inputValue('#subject'), C.old + ' ' + variable);
      assert.equal((await quillState(page)).text.trim(), variable + ' / ' + variable);
      const updated = await savedDraft(page);
      assert(!/<\u4eba\u540d>|&lt;\u4eba\u540d&gt;/.test(updated.config.html_content));
    });
    for (const extension of ['pdf', 'docx', 'xlsx', 'pptx']) {
      await check('attachment: UI upload original Chinese name/size/remove ' + extension, page, async () => {
        const filename = C.attachment + '.' + extension;
        const buffer = fs.readFileSync(path.join(fixtures, 'attachment.' + extension));
        const chooser = page.waitForEvent('filechooser');
        await page.click('#attachment-upload');
        const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/attachments' && r.request().method() === 'POST');
        await (await chooser).setFiles({name: filename, mimeType: {
          pdf: 'application/pdf', docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation'}[extension], buffer});
        const uploaded = await response; assert.equal(uploaded.status(), 200, await uploaded.text());
        const item = await uploaded.json(); assert.equal(item.filename, filename); assert.equal(item.size, buffer.length);
        await page.waitForFunction(name => document.querySelector('#attachment-label').textContent.includes(name), filename);
        assert(await page.locator('#attachment-chip').isVisible());
        assert.equal(await page.locator('#attachment-label').innerText(), filename + ' \u00b7 ' + buffer.length + ' B');
        await page.click('#attachment-remove'); assert(await page.locator('#attachment-chip').isHidden());
        return {filename, size: item.size};
      });
    }
    await check('mail options: no obsolete entry and commercial forces unsubscribe/AD preview', page, async () => {
      await page.locator('#send-options > summary').click();
      assert.equal(await page.locator('#send-options #source-note, #send-options #purpose, #send-options [id*="legacy"]').count(), 0);
      const text = await page.locator('#send-options').innerText();
      assert(!/\u6765\u6e90\u5907\u6ce8|\u90ae\u4ef6\u7528\u9014|\u65e7\u7248/.test(text), text);
      await page.locator('#unsubscribe').uncheck();
      await page.locator('#commercial').check();
      assert(await page.locator('#unsubscribe').isChecked()); assert(await page.locator('#unsubscribe').isDisabled());
      await page.click('#demo-load');
      await page.waitForFunction(() => document.querySelector('#import-counts').textContent.includes('32'));
      await step(page, 2);
      const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/preview-email');
      await page.click('#editor-preview');
      const previewResponse = await response; assert.equal(previewResponse.status(), 200);
      const preview = await previewResponse.json(); assert.match(preview.subject, /\bAD\b/);
      await page.waitForFunction(() => document.querySelector('#preview-subject')?.textContent.includes('AD'));
      assert.match(await page.frameLocator('#preview-frame').locator('body').innerText(), /\u9000\u8ba2/);
      await page.click('#preview-done');
      await page.locator('#commercial').uncheck(); assert(await page.locator('#unsubscribe').isEnabled());
      return {preview_subject: preview.subject};
    });
    await check('account: new QQ defaults hide advanced, custom shows advanced', page, async () => {
      await step(page, 3); await page.click('#account-add');
      assert.equal(await page.inputValue('#account-preset'), 'qq');
      assert.equal(await page.locator('#account-advanced').evaluate(el => el.open), false);
      assert(await page.locator('#account-host').isHidden());
      assert.equal(await page.inputValue('#account-host'), 'smtp.qq.com');
      assert.equal(await page.inputValue('#account-port'), '465');
      assert.equal(await page.inputValue('#account-minute'), '6');
      assert.equal(await page.inputValue('#account-daily'), '200');
      await shot(page, '08-account-simple.png');
      await page.selectOption('#account-preset', 'custom');
      assert(await page.locator('#account-host').isVisible());
      assert.equal(await page.locator('#account-advanced').evaluate(el => el.open), true);
      await page.click('#account-cancel');
    });
    if (await page.locator('#modal').isVisible()) await page.click('#modal-close');
    await helpChecks(page);
    await responsiveChecks(page);
    await mobileChecks();
    report.tasks_after = (await api(page, '/tasks')).tasks.map(task => task.id).sort();
    await check('safety: target task set unchanged', page, () => assert.deepEqual(report.tasks_after, report.tasks_before));
  } finally {
    if (await page.locator('#modal').isVisible()) await page.click('#modal-close');
    for (const id of createdDrafts) await api(page, '/drafts/' + encodeURIComponent(id), 'DELETE');
    await context.close();
  }
  await persistenceChecks(fixtureUrl);
}

async function helpChecks(page) {
  await page.click('[data-view="help"]');
  await check('help: hover opens and leaving flow closes unpinned detail', page, async () => {
    const node = page.locator('[data-help-node="content"]');
    await page.locator('#help-search').focus(); await node.hover();
    await page.locator('#help-node-detail').waitFor({state: 'visible'});
    assert(await page.locator('#help-node-detail').isVisible(), 'Hover opens detail');
    assert.match(await page.locator('#help-node-detail').innerText(), /\{\{\u59d3\u540d\}\}/);
    await page.mouse.move(8, 8);
    await page.locator('#help-node-detail').waitFor({state: 'hidden'});
    assert(await page.locator('#help-node-detail').isHidden(), 'Leaving flow closes unpinned detail');
  });
  await check('help: keyboard focus opens and blur closes unpinned detail', page, async () => {
    const node = page.locator('[data-help-node="content"]');
    await node.focus(); await page.locator('#help-node-detail').waitFor({state: 'visible'});
    assert(await page.locator('#help-node-detail').isVisible(), 'Focus opens detail');
    await page.locator('#help-search').focus(); await page.locator('#help-node-detail').waitFor({state: 'hidden'});
    assert(await page.locator('#help-node-detail').isHidden(), 'Leaving focus closes unpinned detail');
  });
  await check('help: click pins detail, other hover does not replace, Escape closes', page, async () => {
    await page.click('[data-help-node="uncertain"]');
    await page.locator('#help-search').focus(); await page.locator('[data-help-node="failed"]').hover();
    assert.match(await page.locator('#help-node-detail h3').innerText(), /\u5f85\u786e\u8ba4/);
    assert.equal(await page.getAttribute('[data-help-node="uncertain"]', 'aria-expanded'), 'true');
    await page.mouse.move(8, 8); await page.keyboard.press('Escape');
    assert(await page.locator('#help-node-detail').isHidden());
    assert.equal(await page.getAttribute('[data-help-node="uncertain"]', 'aria-expanded'), 'false');
  });
  await check('help: click toggles and close button returns focus', page, async () => {
    await page.click('[data-help-node="account"]'); await page.click('[data-help-node="account"]');
    assert(await page.locator('#help-node-detail').isHidden());
    await page.click('[data-help-node="account"]'); await page.click('#help-detail-close');
    assert(await page.locator('#help-node-detail').isHidden());
    assert.equal(await page.locator('[data-help-node="account"]').evaluate(el => el === document.activeElement), true);
    await page.locator('#help-search').focus();
  });
  await check('help: detail links navigate to correct workspace step and history', page, async () => {
    for (const [id, target] of [['content', '#step-2'], ['account', '#step-3'], ['accepted', '#history']]) {
      await page.click('[data-view="help"]'); await page.click('[data-help-node="' + id + '"]');
      await page.click('#help-go'); assert(await page.locator(target).isVisible());
    }
  });
  await page.click('[data-view="help"]');
  await check('help: search matches node detail and article paragraph, not only title', page, async () => {
    await page.fill('#help-search', '\u53d1\u4ef6\u7bb1');
    const matches = page.locator('[data-help-node]:visible'); assert.equal(await matches.count(), 1);
    assert.equal(await matches.first().getAttribute('data-help-node'), 'uncertain');
    await matches.click(); assert.match(await page.locator('#help-node-detail p').innerText(), /\u53d1\u4ef6\u7bb1/);
    await page.fill('#help-search', '20 MiB');
    assert.equal(await page.locator('.help-article').count(), 1);
    assert.equal(await page.locator('#help-mail').evaluate(el => el.open), true);
    assert.match(await page.locator('#help-mail').innerText(), /20 MiB/);
    await page.fill('#help-search', 'QA-NO-SUCH-ARTICLE');
    assert.equal(await page.locator('[data-help-node]:visible').count(), 0);
    assert.equal(await page.locator('.help-article').count(), 0);
    await page.fill('#help-search', '');
    await page.locator('#help-directory a[href="#help-smtp"]').click();
    assert.equal(await page.locator('#help-smtp').evaluate(el => el.open), true);
  });
  await page.fill('#help-search', ''); await page.evaluate(() => window.scrollTo(0, 0));
  await page.click('[data-help-node="uncertain"]'); await page.mouse.move(8, 8);
  await shot(page, '09-help-detail.png');
}

async function responsiveChecks(page) {
  for (const theme of ['light', 'dark']) {
    const current = await page.locator('html').getAttribute('data-theme');
    if (current !== theme) await page.click('#theme');
    for (const [width, height] of [[1440, 1000], [1024, 768], [390, 844]]) {
      await page.setViewportSize({width, height});
      for (const view of ['editor', 'account', 'help']) {
        await check('layout: ' + theme + ' ' + width + ' ' + view + ' no overflow/reduced motion', page, async () => {
          if (await page.locator('#modal').isVisible()) await page.click('#modal-close');
          if (view === 'help') {
            await page.click('[data-view="help"]'); await page.fill('#help-search', '');
            await page.click('[data-help-node="uncertain"]');
          } else {
            await step(page, view === 'editor' ? 2 : 3);
            if (view === 'account') { await page.click('#account-add'); await page.selectOption('#account-preset', 'custom'); }
          }
          await layout(page, theme + '-' + width + '-' + view);
          const moving = await page.evaluate(() => [...document.querySelectorAll('body *')]
            .filter(el => el.getClientRects().length).filter(el => {
              const style = getComputedStyle(el);
              return style.animationName !== 'none' || style.transitionDuration.split(',').some(value => parseFloat(value) > 0);
            }).map(el => el.id || el.className));
          assert.deepEqual(moving, [], 'Animations/transitions under reduced-motion');
        });
      }
    }
  }
  if (await page.locator('#modal').isVisible()) await page.click('#modal-close');
}

async function mobileChecks() {
  const {context, page} = await contextFor(base, false, true);
  try {
    await check('help: real touch mobile tap pins and navigates', page, async () => {
      await page.locator('[data-view="help"]').tap();
      await page.locator('[data-help-node="uncertain"]').tap();
      assert(await page.locator('#help-node-detail').isVisible());
      await page.locator('#help-search').tap();
      assert(await page.locator('#help-node-detail').isVisible(), 'Detail remains pinned after outside tap');
      await page.locator('#help-detail-close').tap(); assert(await page.locator('#help-node-detail').isHidden());
      await page.locator('[data-help-node="content"]').tap(); await page.locator('#help-go').tap();
      assert(await page.locator('#step-2').isVisible());
      await page.locator('[data-view="help"]').tap();
      await page.fill('#help-search', '\u53d1\u4ef6\u7bb1');
      await page.locator('[data-help-node="uncertain"]').tap();
      assert.match(await page.locator('#help-node-detail p').innerText(), /\u53d1\u4ef6\u7bb1/);
      await page.fill('#help-search', ''); await page.locator('[data-help-node="uncertain"]').tap();
      await layout(page, 'touch-help-390');
    });
    await shot(page, '10-help-mobile.png');
  } finally { await context.close(); }
}

async function persistenceChecks(url) {
  const {context, page} = await contextFor(url, true);
  try {
    await check('selection: fresh GET configured=false, demo import restores first usable account', page, async () => {
      assert.deepEqual(await api(page, '/account-selection'), {account_ids: [], configured: false});
      await page.click('#demo-load');
      await page.waitForFunction(() => document.querySelector('#import-counts').textContent.includes('32'));
      await step(page, 3);
      assert.equal(await page.locator('[data-account-select]').count(), 1);
      assert(await page.locator('[data-account-select]').isChecked());
      const id = await page.locator('[data-account-select]').getAttribute('data-account-select');
      assert.deepEqual(await api(page, '/account-selection'), {account_ids: [id], configured: true});
    });
    await check('selection: checkbox persists selected and explicit empty across reload/import', page, async () => {
      const input = page.locator('[data-account-select]').first();
      const id = await input.getAttribute('data-account-select');
      for (const selected of [false, true, false]) {
        const pending = page.waitForResponse(r => new URL(r.url()).pathname === '/api/account-selection' && r.request().method() === 'PUT');
        await input.setChecked(selected); assert.equal((await pending).status(), 200);
        assert.deepEqual(await api(page, '/account-selection'), {account_ids: selected ? [id] : [], configured: true});
        await page.reload({waitUntil: 'networkidle'}); await step(page, 3);
        assert.equal(await input.isChecked(), selected, 'Explicit empty must not auto-select');
      }
      await page.click('#demo-load');
      await page.waitForFunction(() => document.querySelector('#import-counts').textContent.includes('32'));
      await step(page, 3); assert.equal(await input.isChecked(), false, 'Import must respect explicit empty');
    });
    await check('account: edit old custom/QQ settings unchanged when password left blank', page, async () => {
      for (const settings of [
        {email: 'old-custom@example.com', smtp_host: 'smtp.invalid', smtp_port: 2525, security: 'starttls', per_minute: 17, daily_limit: 987},
        {email: 'old-qq@example.com', smtp_host: 'smtp.qq.com', smtp_port: 465, security: 'ssl', per_minute: 9, daily_limit: 432}]) {
        const account = await api(page, '/accounts', 'POST', {...settings, password: 'QA-MEMORY-ONLY', remember: false, name: C.old});
        await page.reload({waitUntil: 'networkidle'}); await step(page, 3);
        await page.click('[data-account-edit="' + account.id + '"]');
        assert.equal(await page.inputValue('#account-password'), '');
        assert.equal(await page.locator('#account-advanced').evaluate(el => el.open), settings.security === 'starttls');
        for (const [selector, value] of [['#account-host', settings.smtp_host], ['#account-port', settings.smtp_port],
          ['#account-security', settings.security], ['#account-minute', settings.per_minute], ['#account-daily', settings.daily_limit]])
          assert.equal(await page.inputValue(selector), String(value));
        const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/accounts' && r.request().method() === 'POST');
        await page.click('#account-submit'); assert.equal((await response).status(), 200);
        await page.locator('#modal').waitFor({state: 'hidden'});
        const saved = (await api(page, '/accounts')).accounts.find(item => item.id === account.id);
        for (const [key, value] of Object.entries(settings)) assert.equal(saved[key], value);
        assert.equal(saved.has_secret, true); assert.equal(saved.remember, false);
        assert.equal('password' in saved, false);
      }
    });
    await check('selection: independent live/demo preferences and UI reload', page, async () => {
      await step(page, 3);
      const demo = page.locator('[data-account-select]').first();
      const demoId = await demo.getAttribute('data-account-select');
      const write = page.waitForResponse(r => new URL(r.url()).pathname === '/api/account-selection' && r.request().method() === 'PUT');
      await demo.check(); assert.equal((await write).status(), 200);
      assert.deepEqual(await api(page, '/account-selection', 'GET', undefined, 'live'), {account_ids: [], configured: true});
      await page.click('[data-mode="live"]');
      await page.locator('#modal .modal-actions button.primary').click();
      await page.locator('#demo-banner').waitFor({state: 'hidden'}); await step(page, 3);
      const live = page.locator('[data-account-select]'); assert.equal(await live.count(), 1); assert.equal(await live.isChecked(), false);
      const liveId = await live.getAttribute('data-account-select');
      const liveWrite = page.waitForResponse(r => new URL(r.url()).pathname === '/api/account-selection' && r.request().method() === 'PUT');
      await live.check(); assert.equal((await liveWrite).status(), 200);
      assert.deepEqual(await api(page, '/account-selection', 'GET', undefined, 'demo'), {account_ids: [demoId], configured: true});
      await page.click('[data-mode="demo"]'); await page.locator('#modal .modal-actions button.primary').click();
      await page.locator('#demo-banner').waitFor({state: 'visible'}); await step(page, 3);
      assert.equal(await page.locator('[data-account-select="' + demoId + '"]').isChecked(), true);
      await page.reload({waitUntil: 'networkidle'}); await step(page, 3);
      assert(await page.locator('[data-account-select="' + demoId + '"]').isChecked());
      assert.deepEqual(await api(page, '/account-selection', 'GET', undefined, 'live'), {account_ids: [liveId], configured: true});
      const storage = await page.evaluate(() => ({local: {...localStorage}, session: {...sessionStorage}}));
      assert(!/password|QA-MEMORY-ONLY/i.test(JSON.stringify(storage)), 'No credential in browser storage');
    });
  } finally { await context.close(); }
}

(async () => {
  try { await main(); }
  catch (error) { report.results.push({name: 'suite setup/cleanup', status: 'fail', message: error.stack}); console.error(error); }
  finally {
    if (browser) await browser.close();
    await check('fixture: clean shutdown and persisted preference contains IDs only', null, async () => {
      await stopFixtures(); assert(persisted, helperError || 'No persisted snapshot');
      for (const [mode, snapshot] of Object.entries(persisted)) {
        assert.equal(snapshot.task_count, 0, mode + ' has unexpected tasks');
        const preference = snapshot.preferences.find(item => item.key === 'account_selection');
        assert(preference, mode + ' missing persisted selection');
        const ids = JSON.parse(preference.payload); assert(Array.isArray(ids));
        assert(ids.every(id => typeof id === 'string' && snapshot.accounts.some(account => account.id === id)));
        assert(!/password|QA-MEMORY-ONLY/i.test(preference.payload));
        assert(snapshot.accounts.every(account => !('password' in account)));
      }
      return {modes: Object.keys(persisted), task_counts: [persisted.demo.task_count, persisted.live.task_count]};
    });
    await check('safety: zero forbidden requests, zero JS/HTTP errors, all requested screenshots', null, () => {
      assert.deepEqual(report.blocked_requests, []); assert.deepEqual(report.page_errors, []);
      assert.deepEqual(report.unexpected_http, []);
      for (const item of report.selection_requests.filter(item => item.method === 'PUT')) {
        assert.deepEqual(Object.keys(item.body), ['account_ids']); assert(Array.isArray(item.body.account_ids));
      }
      for (const name of ['07-editor.png', '08-account-simple.png', '09-help-detail.png', '10-help-mobile.png'])
        assert(report.screenshots.includes(name), name + ' not captured this run');
    });
    report.summary = {passed: report.results.filter(item => item.status === 'pass').length,
      failed: report.results.filter(item => item.status === 'fail').length};
    fs.writeFileSync(path.join(output, 'product-ui-report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report.summary));
    process.exitCode = report.summary.failed ? 1 : 0;
  }
})();
