const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

const base = process.env.YUNYOUBAO_TEST_URL || 'http://127.0.0.1:8131';
const output = path.resolve(__dirname, '../artifacts/browser');
const shots = process.env.YUNYOUBAO_SCREENSHOTS_DIR;

async function run() {
  fs.mkdirSync(output, {recursive: true});
  const browser = await chromium.launch({headless: true,
    ...(process.env.BROWSER_EXECUTABLE ? {executablePath: process.env.BROWSER_EXECUTABLE} : {})});
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}, acceptDownloads: true,
    ...(process.env.YUNYOUBAO_RECORD_VIDEO ? {recordVideo: {dir: output, size: {width: 1440, height: 1000}}} : {})});
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const hold = async () => { if (process.env.YUNYOUBAO_RECORD_VIDEO) await page.waitForTimeout(3500); };
  const screenshot = async name => {
    await page.mouse.move(8, 8);
    await page.locator('#toast').waitFor({state: 'hidden', timeout: 10000});
    await page.waitForTimeout(100);
    await page.screenshot({path: path.join(output, name), fullPage: true});
    if (shots) {
      fs.mkdirSync(shots, {recursive: true});
      fs.copyFileSync(path.join(output, name), path.join(shots, name));
    }
  };
  const task = async id => page.evaluate(async identifier => {
    const response = await fetch('/api/tasks/' + identifier, {headers: {
      Authorization: 'Bearer ' + window.YUNYOUBAO.token, 'X-Yunyoubao-Mode': 'demo'}});
    if (!response.ok) throw new Error('Cannot inspect demonstration task');
    return response.json();
  }, id);
  const waitTask = async (id, accepted) => {
    let snapshot;
    const deadline = Date.now() + 15000;
    do {
      snapshot = await task(id);
      if (['completed', 'completed_with_issues'].includes(snapshot.status) && snapshot.counts.accepted === accepted) break;
      await page.waitForTimeout(250);
    } while (Date.now() < deadline);
    assert(['completed', 'completed_with_issues'].includes(snapshot.status), JSON.stringify(snapshot.counts));
    assert.equal(snapshot.counts.accepted, accepted);
    if (await page.locator('#monitor-refresh').isVisible()) await page.click('#monitor-refresh');
    else {
      await page.click('#history-refresh');
      await page.locator('[data-task-id="' + id + '"]').click();
    }
  };
  try {
    await page.goto(base, {waitUntil: 'networkidle'});
    assert.equal(await page.locator('.ql-editor').count(), 1);
    assert.equal(await page.evaluate(() => window.YUNYOUBAO.initial_mode), 'demo', 'Use an isolated --demo server');
    assert(await page.locator('#demo-banner').isVisible());
    await hold();
    await page.click('#demo-load');
    await page.waitForFunction(() => document.querySelector('#import-counts').textContent.includes('32'));
    await page.click('#division-filter');
    await page.locator('[data-filter-index="0"][value="工作人员 A"]').check();
    await page.waitForFunction(() => document.querySelector('#selection-summary').textContent.includes('10'));
    const numbers = await page.locator('#import-counts strong').allTextContents();
    assert.deepEqual(numbers, ['32', '12', '1', '1', '0', '0', '10']);
    await screenshot('01-console.png');
    await hold();
    await page.click('[data-step="2"]');
    await page.click('#template-open');
    await page.locator('[data-template="training"]').click();
    await page.fill('#subject', '培训通知 · {{姓名}}');
    await hold();
    await page.click('#preview-open');
    await page.waitForFunction(() => document.querySelector('#preview-subject')?.textContent.includes('示例学员01'));
    await screenshot('04-preview.png');
    await hold();
    await page.click('#preview-done');
    await page.click('#test-open');
    await page.fill('#test-email', 'review@example.com');
    await page.click('#test-submit');
    await page.waitForFunction(() => document.querySelector('#test-result')?.textContent.includes('服务器已接收'));
    await hold();
    await page.click('#test-cancel');
    await page.click('#draft-save');
    await page.click('[data-step="3"]');
    await hold();
    await page.click('[data-step="4"]');
    await page.fill('#task-title', '秋季培训通知 · 分工 A');
    await page.locator('#send-consent').check();
    const createdResponse = page.waitForResponse(response => response.url().endsWith('/api/tasks') && response.request().method() === 'POST');
    await page.click('#task-create');
    const created = await (await createdResponse).json();
    assert.equal(created.counts.total, 10);
    await page.waitForSelector('#monitor-content [data-task-action="start"]');
    await hold();
    await page.click('#monitor-content [data-task-action="start"]');
    await page.getByRole('button', {name: '明确启动', exact: true}).click();
    await page.waitForSelector('#monitor-content [data-task-action="pause"]');
    await page.click('#monitor-content [data-task-action="pause"]');
    await page.waitForSelector('#monitor-content [data-task-action="resume"]');
    assert.equal((await task(created.id)).status, 'paused');
    await hold();
    await page.click('#monitor-content [data-task-action="resume"]');
    await page.getByRole('button', {name: '继续任务', exact: true}).last().click();
    await waitTask(created.id, 8);
    let state = await task(created.id);
    assert.equal(state.counts.failed, 1);
    assert.equal(state.counts.uncertain, 1);
    await page.click('[data-view="history"]');
    await page.waitForSelector('#task-detail .task-recipient-check');
    await screenshot('03-resume-banner.png');
    await hold();
    const downloadPromise = page.waitForEvent('download');
    await page.click('#task-detail [data-task-export="failed"]');
    const download = await downloadPromise;
    await download.saveAs(path.join(output, download.suggestedFilename()));
    await page.locator('#task-detail tbody tr').filter({hasText: '发送失败'}).locator('input').check();
    await page.click('#task-detail [data-retry="failed"]');
    await page.getByRole('button', {name: '确认重发', exact: true}).click();
    await waitTask(created.id, 9);
    await page.locator('#task-detail tbody tr').filter({hasText: '待确认'}).locator('input').check();
    await page.click('#task-detail [data-retry="uncertain"]');
    await hold();
    await page.getByRole('button', {name: '确认重发', exact: true}).click();
    await waitTask(created.id, 10);
    assert.equal((await task(created.id)).status, 'completed');
    await page.click('[data-view="help"]');
    await screenshot('02-doc.png');
    await hold();
    await page.click('#theme');
    await screenshot('05-dark-help.png');
    await page.click('[data-view="workspace"]');
    assert(await page.locator('#workspace').isVisible());
    await screenshot('06-dark-workspace.png');
    const dimensions = [];
    for (const [width, height] of [[1440,1000],[1024,768],[390,844]]) {
      await page.setViewportSize({width, height});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Horizontal page overflow');
      dimensions.push({width, height, overflow: false});
      await page.screenshot({path:path.join(output, 'viewport-' + width + '.png'),fullPage:true});
    }
    assert.deepEqual(errors, []);
    const report = {task_id: created.id, counts: (await task(created.id)).counts, dimensions, page_errors: errors,
                    smtp: 'simulated only', exported: download.suggestedFilename()};
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  } finally {
    await context.close();
    await browser.close();
  }
}

run().catch(error => { console.error(error); process.exitCode = 1; });
