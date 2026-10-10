'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icon = name => '<i data-lucide="' + name + '"></i>';
  const boot = window.YUNYOUBAO || {};
  const state = {
    mode: boot.initial_mode === 'demo' ? 'demo' : 'live', epoch: 0, step: 1, view: 'workspace',
    import: null, columns: [], filters: [], preview: null, revision: null, offset: 0, limit: 20,
    generation: 0, preflightSequence: 0, accounts: [], accountIds: [], attachment: null,
    tasks: [], task: null, taskOffset: 0, taskLimit: 20, selectedRecipients: new Set(),
    draftId: null, dirty: false, variableTarget: 'body', previewIndex: 0, poll: null, taskSequence: 0,
    actionBusy: false, uploading: false, mailRevision: 0, testResult: null
  };
  const labels = {
    ready:'待启动', starting:'正在启动', running:'运行中', stopping:'正在暂停', paused:'已暂停',
    completed:'已完成', completed_with_issues:'完成但有问题', pending:'等待发送', sending:'发送中',
    accepted:'服务器已接收', failed:'发送失败', uncertain:'待确认', invalid:'地址无效', legacy:'旧版只读',
    duplicate:'重复地址', duplicates:'重复地址', excluded:'已排除', conflict:'信息冲突',
    conflicts:'信息冲突', sendable:'可发送', valid:'可发送', selected:'已选中', skipped:'已跳过'
  };
  const activeStatuses = new Set(['starting','running','stopping']);
  const isLegacy = task => !!task.legacy || task.status === 'legacy';
  const pauseText = reason => ({
    manual:'已按请求安全暂停', window:'当前不在发送窗口内，等待窗口开放',
    account_error:'账号认证或服务商限制，请检查账号并测试',
    quota:'账号预算已用尽，请检查额度或稍后继续',
    error:'发送异常，请检查任务日志', storage_error:'数据保存异常，请检查磁盘与权限',
    retry:'所选记录已进入人工重发队列'
  }[reason] || reason);
  let quill, preflightTimer, toastTimer, drawerFocus, modalFocus;
  const icons = () => window.lucide && window.lucide.createIcons();
  function badge(status) {
    const tone = ['accepted','sendable','valid','completed'].includes(status) ? 'good' :
      ['failed','invalid','conflict','conflicts'].includes(status) ? 'bad' :
      ['uncertain','paused','completed_with_issues','duplicate','duplicates','excluded'].includes(status) ? 'warn' : '';
    return '<span class="badge ' + tone + '">' + esc(labels[status] || status || '未知状态') + '</span>';
  }
  function toast(message) {
    $('toast').textContent = message;
    $('toast').hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { $('toast').hidden = true; }, 6000);
  }
  function safeError(error) {
    if (error.name === 'AbortError') return '';
    return error.message || '请求失败，请检查服务连接。';
  }
  function authHeaders(mode = state.mode) {
    if (!boot.token) throw new Error('缺少桌面会话令牌，请从云邮宝桌面窗口打开页面。');
    return {Authorization: 'Bearer ' + boot.token, 'X-Yunyoubao-Mode': mode};
  }
  async function api(path, options = {}) {
    const epoch = state.epoch, mode = state.mode;
    const headers = authHeaders(mode);
    const init = {method: options.method || 'GET', headers, signal: options.signal};
    if (options.body !== undefined) {
      if (options.body instanceof FormData) init.body = options.body;
      else { headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(options.body); }
    }
    let response;
    try { response = await fetch('/api' + path, init); }
    catch (_) { throw new Error('无法连接云邮宝服务，请检查桌面应用是否仍在运行。'); }
    if (epoch !== state.epoch) throw new DOMException('模式已切换', 'AbortError');
    let data;
    try { data = await response.json(); }
    catch (_) { throw new Error('服务返回了非 JSON 响应（HTTP ' + response.status + '）。'); }
    if (epoch !== state.epoch) throw new DOMException('模式已切换', 'AbortError');
    if (!response.ok) {
      const detail = data.detail;
      let message = typeof detail === 'string' ? detail : Array.isArray(detail) ?
        detail.map(x => x.msg || '参数不正确').join('；') : detail?.message || data.message || '操作失败';
      if (boot.token) message = message.split(boot.token).join('[已隐藏]');
      if (options.body?.password) message = message.split(options.body.password).join('[已隐藏]');
      throw new Error(message + '（HTTP ' + response.status + '）');
    }
    return data;
  }
  const taskResult = data => data.task || data;
  const accountResult = data => data.account || data;
  const pathId = id => encodeURIComponent(String(id));
  function on(id, event, action) {
    $(id).addEventListener(event, async e => {
      try { await action(e); }
      catch (error) { const message = safeError(error); if (message) toast(message); }
    });
  }
  async function busy(button, action) {
    if (button.disabled) return;
    button.disabled = true;
    try { return await action(); }
    finally { if (button.isConnected) button.disabled = false; }
  }
  function openModal(title, content) {
    modalFocus = document.activeElement;
    $('modal-title').textContent = title;
    $('modal-content').innerHTML = content;
    if (!$('modal').open) $('modal').showModal();
    icons();
  }
  function closeModal() { $('modal').close(); }
  function modalError(message) {
    let element = $('modal-error');
    if (!element) {
      element = document.createElement('p'); element.id = 'modal-error'; element.className = 'modal-error';
      element.setAttribute('role','alert'); $('modal-content').append(element);
    }
    element.textContent = message;
  }
  function confirmAction(title, message, label = '确认') {
    return new Promise(resolve => {
      openModal(title, '<p>' + esc(message) + '</p><div class="modal-actions"><button id="confirm-cancel">取消</button><button id="confirm-yes" class="primary">' + esc(label) + '</button></div>');
      let answered = false;
      const done = value => { if (answered) return; answered = true; $('modal').removeEventListener('close', cancel); closeModal(); resolve(value); };
      const cancel = () => done(false);
      $('modal').addEventListener('close', cancel);
      $('confirm-cancel').onclick = () => done(false);
      $('confirm-yes').onclick = () => done(true);
    });
  }
  function markDirty(listChanged = false) {
    state.dirty = true;
    state.mailRevision++;
    $('draft-state').textContent = '有未保存更改';
    $('send-consent').checked = false;
    if (listChanged) {
      state.generation++; state.revision = null; state.offset = 0; state.preview = null;
      $('preflight-state').textContent = '名单已变更，等待重新预检';
      $('selection-summary').textContent = '名单已变更，需重新预检';
      clearTimeout(preflightTimer);
      if (state.import) preflightTimer = setTimeout(() => runPreflight().catch(error => { const message = safeError(error); if (message) toast(message); }), 260);
    }
    renderReview();
    renderContentIssues();
    renderPreparation();
  }
  function config() {
    return {
      title: $('task-title').value.trim(), import_id: state.import?.import_id || null,
      sheet: $('sheet').value, name_column: $('name-column').value, email_column: $('email-column').value,
      filters: state.filters.filter(f => f.values.length).map(f => ({column:f.column,values:[...f.values]})),
      revision: state.revision, subject: $('subject').value.trim(),
      html_content: quill && (quill.getText().trim() || quill.root.querySelector('img')) ? quill.root.innerHTML : '',
      attachment_id: state.attachment?.attachment_id || null, account_ids: [...state.accountIds],
      start_time: $('start-time').value, end_time: $('end-time').value,
      add_unsubscribe: $('unsubscribe').checked, purpose: $('purpose').value, source_note: $('source-note').value.trim()
    };
  }
  function navigate(view) {
    state.view = view;
    ['workspace','history','help'].forEach(id => { $(id).hidden = id !== view; });
    document.querySelectorAll('[data-view]').forEach(b => { b.classList.toggle('active',b.dataset.view === view); b.setAttribute('aria-current',b.dataset.view === view ? 'page' : 'false'); });
    $('action-bar').hidden = view !== 'workspace';
    document.body.classList.remove('focus-edit');
    if (view === 'history') loadTasks().catch(error => toast(safeError(error)));
    icons();
  }
  function setStep(step) {
    state.step = Math.max(1, Math.min(4, Number(step)));
    document.querySelectorAll('.step').forEach(e => { e.hidden = e.id !== 'step-' + state.step; });
    document.querySelectorAll('[data-step]').forEach(b => { b.classList.toggle('active',Number(b.dataset.step) === state.step); b.setAttribute('aria-current',Number(b.dataset.step) === state.step ? 'step' : 'false'); });
    $('step-back').disabled = state.step === 1; $('step-next').disabled = state.step === 4;
    $('step-position').textContent = '0' + state.step + ' / 04';
    document.body.classList.remove('focus-edit');
    if (state.step === 4) renderReview();
  }
  function fillSelect(element, values, selected, emptyLabel) {
    element.innerHTML = (emptyLabel !== undefined ? '<option value="">' + esc(emptyLabel) + '</option>' : '') +
      values.map(v => '<option value="' + esc(v) + '">' + esc(v) + '</option>').join('');
    if (values.includes(selected)) element.value = selected;
  }
  function sheetNames(sheets) {
    return (sheets || []).map(s => typeof s === 'string' ? s : s.name || s.sheet || s.title).filter(Boolean);
  }
  function setColumns(columns, preferred = {}) {
    state.columns = (columns || []).map(c => typeof c === 'string' ? c : c.name || c.column).filter(Boolean);
    const oldName = preferred.name !== undefined ? preferred.name : $('name-column').value;
    const oldEmail = preferred.email !== undefined ? preferred.email : $('email-column').value;
    const name = state.columns.includes(oldName) ? oldName : state.columns.find(c => /姓名|人名|联系人|^name$/i.test(c)) || '';
    const email = state.columns.includes(oldEmail) ? oldEmail : state.columns.find(c => /邮箱|邮件|email|e-mail/i.test(c)) || '';
    fillSelect($('name-column'),state.columns,name,'选择姓名列');
    fillSelect($('email-column'),state.columns,email,'选择邮箱列');
    fillSelect($('variable-column'),state.columns,$('variable-column').value,'选择名单列');
  }
  function setImport(data) {
    if (!data.import_id) throw new Error('导入响应缺少 import_id。');
    state.import = data; state.filters = []; state.offset = 0;
    const names = sheetNames(data.sheets);
    fillSelect($('sheet'), names.length ? names : [data.default_sheet || 'Sheet1'], data.default_sheet);
    setColumns(data.sheet_columns?.[$('sheet').value] || data.columns, {name:'',email:''});
    $('import-name').textContent = data.filename || '已导入名单';
    $('import-empty').hidden = true; $('import-content').hidden = false;
    renderFilters(); markDirty(true);
  }
  async function importFile(file) {
    if (!file) return;
    if (!/\.(xlsx|csv)$/i.test(file.name)) throw new Error('请选择 .xlsx 或 .csv 文件。');
    if (state.uploading) return;
    state.uploading = true; $('import-trigger').disabled = true;
    try {
      const form = new FormData(); form.append('file',file);
      const data = await api('/imports',{method:'POST',body:form});
      setImport(data); await runPreflight(); toast('名单已导入并预检');
    } finally { state.uploading = false; $('import-trigger').disabled = false; $('import-file').value = ''; }
  }
  async function runPreflight() {
    clearTimeout(preflightTimer);
    if (!state.import) throw new Error('请先导入收件名单。');
    const sequence = ++state.preflightSequence, generation = state.generation;
    const c = config();
    if (!c.sheet || !c.email_column || !c.name_column) {
      state.revision = null; $('preflight-state').textContent = '请选择工作表、姓名列和邮箱列'; renderReview();
      throw new Error('请完成姓名列与邮箱列映射。');
    }
    $('preflight-state').textContent = '正在预检…';
    let result;
    try {
      result = await api('/imports/' + pathId(c.import_id) + '/preview', {
        method:'POST', body:{sheet:c.sheet,name_column:c.name_column,email_column:c.email_column,filters:c.filters,offset:state.offset,limit:state.limit}
      });
      if (sequence !== state.preflightSequence || generation !== state.generation) throw new DOMException('名单已变更', 'AbortError');
      if (result.mapping_required) {
        if (result.columns) setColumns(result.columns,{name:c.name_column,email:c.email_column});
        throw new Error('请完成此工作表的姓名列与邮箱列映射后重新预检。');
      }
      if (result.revision === undefined || result.revision === null) throw new Error('预检响应缺少 revision，不能创建或启动任务。');
    } catch (error) {
      if (sequence === state.preflightSequence && generation === state.generation && error.name !== 'AbortError') {
        state.revision = null; $('preflight-state').textContent = '预检失败：' + safeError(error);
        renderReview();
        renderPreparation();
      }
      throw error;
    }
    state.preview = result; state.revision = result.revision;
    if (result.columns) setColumns(result.columns,{name:c.name_column,email:c.email_column});
    $('preflight-state').textContent = '预检完成';
    renderImport(); renderFilters(); renderReview(); renderContentIssues(); renderPreparation();
    return result;
  }
  function renderImport() {
    const p = state.preview;
    if (!p) return;
    const items = [['total','总行数'],['selected','选中'],['invalid','无效'],['duplicates','重复'],['excluded','排除'],['conflicts','冲突'],['sendable','可发送']];
    $('import-counts').innerHTML = items.map(([key,label]) => '<div class="' + (key === 'sendable' ? 'positive' : ['invalid','conflicts'].includes(key) ? 'warning' : '') + '"><span>' + label + '</span><strong>' + Number(p.counts?.[key] || 0) + '</strong></div>').join('');
    const cols = state.columns;
    $('recipients-table').querySelector('thead').innerHTML = '<tr><th>行号</th>' + cols.map(c => '<th>' + esc(c) + '</th>').join('') + '<th>预检状态</th><th>原因</th></tr>';
    const rows = (p.rows || []).filter(r => !$('problem-only').checked || !['sendable','valid','selected'].includes(r.status));
    $('recipients-table').querySelector('tbody').innerHTML = rows.length ? rows.map(r => '<tr><td class="row-number">' + Number(r.row_number) + '</td>' +
      cols.map((c,i) => '<td>' + esc(Array.isArray(r.values) ? r.values[i] : r.values?.[c]) + '</td>').join('') +
      '<td>' + badge(r.status) + '</td><td>' + esc(r.reason || '') + '</td></tr>').join('') : '<tr><td colspan="' + (cols.length + 3) + '">' + ($('problem-only').checked ? '本页没有问题行' : '此筛选范围没有记录') + '</td></tr>';
    const total = Number(p.counts?.selected || 0), length = (p.rows || []).length;
    $('import-page-label').textContent = (length ? state.offset + 1 : 0) + '–' + (state.offset + length) + ' / ' + total + ($('problem-only').checked ? ' · 问题行限本页' : '');
    $('import-prev').disabled = state.offset === 0;
    $('import-next').disabled = length < state.limit || state.offset + length >= total;
    $('selection-summary').textContent = '可发送 ' + Number(p.counts?.sendable || 0) + ' / 选中 ' + total;
    icons();
  }
  function renderFilters() {
    $('filters').innerHTML = state.filters.map((filter,i) => {
      const values = state.preview?.filter_values?.[filter.column] || [];
      const choices = [...values];
      filter.values.forEach(value => { if (!choices.some(v => String(v.value ?? '') === value)) choices.push({value,count:0}); });
      return '<div class="filter-row"><select data-filter-column="' + i + '" aria-label="筛选列">' +
        state.columns.map(c => '<option value="' + esc(c) + '"' + (c === filter.column ? ' selected' : '') + '>' + esc(c) + '</option>').join('') +
        '</select><div class="filter-values">' + (choices.length ? choices.map(v => '<label><input type="checkbox" data-filter-index="' + i + '" value="' + esc(v.value ?? '') + '"' +
          (filter.values.includes(String(v.value ?? '')) ? ' checked' : '') + '><span>' + esc(v.value === '' ? '（空值）' : v.value) + '</span><small>' + Number(v.count || 0) + '</small></label>').join('') : '<span class="muted">等待可选值，先完成列映射并预检</span>') +
        '</div><button data-filter-remove="' + i + '" class="icon" title="删除条件" aria-label="删除条件">' + icon('x') + '</button></div>';
    }).join('');
    icons();
  }
  function addFilter(column) {
    if (!state.columns.length) throw new Error('请先导入名单。');
    const selected = column || state.columns.find(c => !state.filters.some(f => f.column === c));
    if (!selected) throw new Error('每列只能添加一组条件，同列所选值采用 OR。');
    if (state.filters.some(f => f.column === selected)) {
      toast('此列已有筛选条件'); return;
    }
    state.filters.push({column:selected,values:[]}); renderFilters();
  }
  function contentIssues() {
    const c = config(), issues = [];
    if (!c.subject) issues.push('请填写邮件主题');
    if (!c.html_content) issues.push('请填写邮件正文');
    const text = c.subject + ' ' + (quill?.getText() || '');
    const variables = [...text.matchAll(/\{\{([^{}]+)\}\}/g)].map(m => m[1].trim());
    [...new Set(variables)].forEach(v => {
      if (!state.columns.includes(v)) issues.push('名单中不存在变量列：' + v);
    });
    if (/\{\{|\}\}/.test(text.replace(/\{\{[^{}]+\}\}/g,''))) issues.push('变量括号不完整');
    if (text.includes('<人名>') && !$('name-column').value) issues.push('兼容姓名变量需要选择姓名列');
    return issues;
  }
  function renderContentIssues() {
    if (!quill) return;
    $('content-issues').textContent = contentIssues().join('；');
  }
  function checks() {
    const c = config(), counts = state.preview?.counts || {};
    return [
      {ok:!!c.import_id && c.revision !== null, text:c.import_id ? '名单预检版本' : '导入收件名单', detail:c.revision !== null ? '已获取有效预检版本' : '需要重新预检'},
      {ok:Number(counts.sendable) > 0,text:'可发送收件人',detail:Number(counts.sendable || 0) + ' 位；无效、重复、排除与冲突记录以预检结果为准'},
      {ok:Number(counts.conflicts || 0) === 0,text:'姓名冲突',detail:Number(counts.conflicts || 0) ? '存在同邮箱不同姓名，请调整名单或筛选后再发送' : '未发现姓名冲突'},
      {ok:contentIssues().length === 0,text:'邮件内容与变量',detail:contentIssues().join('；') || '主题、正文和变量列完整'},
      {ok:c.account_ids.length > 0 && state.accounts.filter(a => c.account_ids.includes(a.id)).every(a => a.has_secret !== false),text:'发件账号',detail:c.account_ids.length + ' 个已选账号；缺失授权码需重新填写'},
      {ok:/^\d{2}:\d{2}$/.test(c.start_time) && /^\d{2}:\d{2}$/.test(c.end_time),text:'发送窗口',detail:c.start_time === c.end_time ? '全天发送窗口' : c.start_time + '–' + c.end_time + (c.start_time > c.end_time ? '（跨日）' : '')},
      {ok:c.purpose !== 'promotion' || (!!c.source_note && c.add_unsubscribe),text:'授权与退订',detail:c.purpose === 'promotion' ? '推广邮件须填写名单来源并添加退订信息' : '事务通知'}
    ];
  }
  function renderReview() {
    if (!quill) return;
    const c = config();
    $('review-summary').innerHTML = '<dt>运行模式</dt><dd>' + (state.mode === 'demo' ? '演示（不会真实投递）' : '正式（会真实投递）') +
      '</dd><dt>名单</dt><dd>' + esc(state.import?.filename || '未导入') + ' / ' + esc(c.sheet || '未选择') +
      '</dd><dt>主题</dt><dd>' + esc(c.subject || '未填写') + '</dd><dt>附件</dt><dd>' + esc(state.attachment?.filename || '无') +
      '</dd><dt>发件账号</dt><dd>' + esc(state.accounts.filter(a => state.accountIds.includes(a.id)).map(a => a.email).join('、') || '未选择') + '</dd>';
    $('review-checks').innerHTML = checks().map(check => '<div class="check-item ' + (check.ok ? '' : 'invalid') + '">' + icon(check.ok ? 'circle-check' : 'circle-alert') + '<div><strong>' + esc(check.text) + '</strong><div class="muted">' + esc(check.detail) + '</div></div></div>').join('');
    icons();
  }
  function insertVariable(value) {
    if (state.variableTarget === 'subject') {
      const el = $('subject'); const start = el.selectionStart ?? el.value.length, end = el.selectionEnd ?? start;
      el.value = el.value.slice(0,start) + value + el.value.slice(end);
      el.focus(); el.setSelectionRange(start + value.length,start + value.length); markDirty();
    } else {
      const range = quill.getSelection(true) || {index:quill.getLength() - 1,length:0};
      if (range.length) quill.deleteText(range.index,range.length,'user');
      quill.insertText(range.index,value,'user'); quill.setSelection(range.index + value.length,0);
    }
  }
  async function loadAccounts() {
    const data = await api('/accounts');
    state.accounts = (data.accounts || []).map(a => {
      const {password, token, ...safe} = a;
      return safe;
    });
    state.accountIds = state.accountIds.filter(id => state.accounts.some(a => a.id === id));
    renderAccounts(); renderReview();
  }
  function renderAccounts() {
    $('accounts').innerHTML = state.accounts.length ? state.accounts.map(a =>
      '<div class="account-row"><input type="checkbox" data-account-select="' + esc(a.id) + '" aria-label="选择 ' + esc(a.email) + '"' +
      (state.accountIds.includes(a.id) ? ' checked' : '') + '><div><strong>' + esc(a.name || a.email) +
      '</strong><div class="muted">' + esc(a.email) + ' · ' + esc(a.smtp_host) + ':' + Number(a.smtp_port) + ' · ' + esc(a.security) +
      '</div><div class="muted">每分钟 ' + Number(a.per_minute ?? 6) + ' 封 / 每日 ' + Number(a.daily_limit ?? 200) + ' 封' +
      (a.remember === false ? ' · 不记住授权码' : '') + (a.has_secret === false ? ' · 授权码缺失' : '') + '</div></div><div class="inline"><button data-account-edit="' + esc(a.id) +
      '" class="icon" title="编辑账号" aria-label="编辑账号">' + icon('pencil') + '</button><button data-account-delete="' + esc(a.id) +
      '" class="icon danger" title="删除账号" aria-label="删除账号">' + icon('trash-2') + '</button></div></div>').join('') :
      '<div class="empty">' + icon('at-sign') + '<strong>还没有发件账号</strong><span>添加账号后选择本次任务的发件人</span></div>';
    icons();
    renderPreparation();
  }
  function accountEditor(account) {
    const a = account || {email:'',name:'',smtp_host:'smtp.qq.com',smtp_port:465,security:'ssl',remember:true,per_minute:6,daily_limit:200};
    const preset = a.smtp_host === 'smtp.qq.com' ? 'qq' : a.smtp_host === 'smtp.163.com' ? '163' : 'custom';
    openModal(account ? '编辑发件账号' : '新增发件账号', '<form id="account-form">' +
      '<div class="fields two"><label>邮箱服务<select id="account-preset"><option value="qq">QQ 邮箱</option><option value="163">163 邮箱</option><option value="custom">自定义 SMTP</option></select></label><label>发件人名称<input id="account-name" value="' + esc(a.name) + '" maxlength="100"></label></div>' +
      '<label>邮箱地址<input id="account-email" type="email" required value="' + esc(a.email) + '" autocomplete="off"' + (account ? ' readonly title="修改邮箱请新增账号"' : '') + '></label>' +
      '<label class="separated">SMTP 授权码' + (account ? '（留空保留现有授权码）' : '') + '<div class="password-field"><input id="account-password" type="password" autocomplete="new-password"' +
      (account ? '' : ' required') + '><button type="button" id="password-toggle" class="icon" title="显示授权码" aria-label="显示授权码">' + icon('eye') + '</button></div></label>' +
      '<div class="fields three separated"><label>SMTP 主机<input id="account-host" required value="' + esc(a.smtp_host) + '"></label><label>端口<input id="account-port" type="number" min="1" max="65535" required value="' +
      Number(a.smtp_port) + '"></label><label>连接安全<select id="account-security"><option value="ssl">SSL / TLS</option><option value="starttls">STARTTLS</option></select></label></div>' +
      '<div class="fields two"><label>每分钟上限<input id="account-minute" type="number" min="1" max="120" required value="' + Number(a.per_minute ?? 6) +
      '"></label><label>每日上限<input id="account-daily" type="number" min="1" max="100000" required value="' + Number(a.daily_limit ?? 200) + '"></label></div>' +
      '<label class="check"><input id="account-remember" type="checkbox"' + (a.remember !== false ? ' checked' : '') +
      '>记住授权码</label><div class="modal-actions"><button type="button" id="account-cancel">取消</button><button type="submit" id="account-submit" class="primary">' + icon('save') + '保存账号</button></div></form>');
    $('account-preset').value = preset; $('account-security').value = a.security || 'ssl';
    $('account-preset').onchange = () => {
      const v = $('account-preset').value;
      if (v === 'qq' || v === '163') {
        $('account-host').value = 'smtp.' + (v === 'qq' ? 'qq.com' : '163.com');
        $('account-port').value = '465'; $('account-security').value = 'ssl';
      }
    };
    $('password-toggle').onclick = () => {
      const show = $('account-password').type === 'password'; $('account-password').type = show ? 'text' : 'password';
      $('password-toggle').title = show ? '隐藏授权码' : '显示授权码';
      $('password-toggle').setAttribute('aria-label',$('password-toggle').title);
      $('password-toggle').innerHTML = icon(show ? 'eye-off' : 'eye'); icons();
    };
    $('account-cancel').onclick = closeModal;
    $('account-form').onsubmit = async e => {
      e.preventDefault();
      const body = {
        ...(account ? {id:account.id} : {}), email:$('account-email').value.trim(),name:$('account-name').value.trim(),
        smtp_host:$('account-host').value.trim(),smtp_port:Number($('account-port').value),security:$('account-security').value,
        remember:$('account-remember').checked,per_minute:Number($('account-minute').value),daily_limit:Number($('account-daily').value)
      };
      if ($('account-password').value) body.password = $('account-password').value;
      try {
        await busy($('account-submit'),async () => {
          const result = accountResult(await api('/accounts',{method:'POST',body}));
          $('account-password').value = '';
          if (!account && result.id !== undefined) state.accountIds.push(result.id);
          closeModal(); await loadAccounts(); markDirty(); toast('账号已保存');
        });
      } catch (error) { modalError(safeError(error)); }
      finally { delete body.password; }
    };
  }
  async function saveDraft(button = $('draft-save')) {
    await busy(button,async () => {
      const c = config();
      const revision = state.mailRevision;
      const title = c.title || c.subject || '未命名草稿';
      const data = await api('/drafts',{method:'POST',body:{...(state.draftId ? {id:state.draftId} : {}),title,config:{
        ...c, _ui:{import:state.import,attachment:state.attachment}
      }}});
      state.draftId = (data.draft || data).id;
      state.dirty = revision !== state.mailRevision;
      $('draft-state').textContent = state.dirty ? '草稿已保存，仍有新更改' : '草稿已保存';
      toast(state.dirty ? '保存完成；保存期间的新更改尚未保存' : '草稿已保存');
    });
  }
  async function openDrafts() {
    const data = await api('/drafts');
    const drafts = data.drafts || [];
    openModal('任务草稿', drafts.length ? '<div class="modal-list">' + drafts.map(d =>
      '<div><div><strong>' + esc(d.title || '未命名草稿') + '</strong><div class="muted">' + esc(d.config?.subject || '无主题') +
      '</div></div><div class="inline"><button data-draft-load="' + esc(d.id) + '">打开</button><button data-draft-delete="' + esc(d.id) +
      '" class="icon danger" title="删除草稿" aria-label="删除草稿">' + icon('trash-2') + '</button></div></div>').join('') + '</div>' :
      '<div class="empty">' + icon('notebook-pen') + '<strong>还没有草稿</strong></div>');
    $('modal-content').onclick = async e => {
      const load = e.target.closest('[data-draft-load]'), remove = e.target.closest('[data-draft-delete]');
      try {
        if (load) {
          const d = drafts.find(x => String(x.id) === load.dataset.draftLoad);
          if (state.dirty && !window.confirm('打开草稿会替换当前未保存的配置，继续吗？')) return;
          applyDraft(d); closeModal();
          if (state.import) await runPreflight();
          toast('草稿已打开；请重新核对账号和名单');
        }
        if (remove && window.confirm('删除此草稿？')) {
          await api('/drafts/' + pathId(remove.dataset.draftDelete),{method:'DELETE'});
          if (String(state.draftId) === remove.dataset.draftDelete) { state.draftId = null; $('draft-state').textContent = '未保存草稿'; }
          await openDrafts();
        }
      } catch (error) { modalError(safeError(error)); }
    };
  }
  function applyDraft(draft) {
    const c = draft.config || {};
    state.draftId = draft.id; state.attachment = c._ui?.attachment || (c.attachment_id ? {attachment_id:c.attachment_id,filename:c.attachment_name || '草稿附件'} : null);
    state.accountIds = (c.account_ids || []).filter(id => state.accounts.some(a => a.id === id));
    state.import = c._ui?.import || (c.import_id ? {import_id:c.import_id,filename:'草稿名单',sheets:[c.sheet],default_sheet:c.sheet,columns:[c.name_column,c.email_column].filter(Boolean)} : null);
    state.filters = (c.filters || []).map(f => ({column:f.column,values:[...f.values]}));
    state.offset = 0; state.revision = null; state.preview = null; state.generation++; state.preflightSequence++;
    $('import-empty').hidden = !!state.import; $('import-content').hidden = !state.import;
    $('import-name').textContent = state.import?.filename || '尚未导入名单';
    fillSelect($('sheet'),sheetNames(state.import?.sheets),c.sheet);
    setColumns(state.import?.columns || [],{name:c.name_column,email:c.email_column});
    $('task-title').value = c.title || draft.title || ''; $('subject').value = c.subject || '';
    quill.clipboard.dangerouslyPasteHTML(c.html_content || '', 'silent');
    $('start-time').value = c.start_time || '08:00'; $('end-time').value = c.end_time || '21:40';
    $('purpose').value = c.purpose || 'notification'; $('source-note').value = c.source_note || '';
    $('unsubscribe').checked = c.add_unsubscribe !== false;
    $('send-consent').checked = false; state.dirty = false; state.mailRevision++;
    $('draft-state').textContent = '草稿已载入'; $('selection-summary').textContent = state.import ? '草稿名单需重新预检' : '尚未导入名单';
    renderAccounts(); renderFilters(); renderAttachment(); renderReview(); renderContentIssues();
    navigate('workspace'); setStep(1);
  }
  async function openTemplates() {
    const data = await api('/templates'), templates = data.templates || [];
    openModal('邮件模板',templates.length ? '<div class="modal-list">' + templates.map(t => '<div><div><strong>' + esc(t.title) +
      '</strong><div class="muted">' + esc(t.subject) + '</div></div><button data-template="' + esc(t.id) + '">使用</button></div>').join('') + '</div>' :
      '<div class="empty">' + icon('files') + '<strong>暂无可用模板</strong></div>');
    $('modal-content').onclick = e => {
      const b = e.target.closest('[data-template]'); if (!b) return;
      if (config().html_content && !window.confirm('使用模板会替换当前邮件内容，继续吗？')) return;
      const t = templates.find(x => String(x.id) === b.dataset.template);
      $('subject').value = t.subject || ''; quill.clipboard.dangerouslyPasteHTML(t.html_content || '', 'silent');
      markDirty(); closeModal();
    };
  }
  function renderAttachment() {
    $('attachment-label').textContent = state.attachment ? state.attachment.filename + ' · ' + formatSize(state.attachment.size) : '未添加附件';
    $('attachment-remove').hidden = !state.attachment;
    renderPreparation();
  }
  function formatSize(bytes) {
    if (bytes === undefined) return '';
    const n = Number(bytes) || 0;
    return n < 1024 ? n + ' B' : n < 1024 * 1024 ? (n / 1024).toFixed(1) + ' KB' : (n / 1024 / 1024).toFixed(1) + ' MB';
  }
  async function uploadAttachment(file) {
    if (!file) return;
    if (!/\.pdf$/i.test(file.name)) throw new Error('当前版本仅支持 PDF 公共附件。');
    if (file.size > 20 * 1024 * 1024) throw new Error('公共附件最大 20 MiB。');
    const form = new FormData(); form.append('file',file);
    await busy($('attachment-upload'),async () => {
      const data = await api('/attachments',{method:'POST',body:form});
      if (!data.attachment_id) throw new Error('附件响应缺少 attachment_id。');
      state.attachment = data; renderAttachment(); markDirty(); toast('公共附件已上传');
    });
    $('attachment-file').value = '';
  }
  async function openPreview() {
    if (!config().html_content) throw new Error('请先填写邮件正文。');
    await runPreflight();
    const max = Number(state.preview?.counts?.sendable || 0);
    if (!max) throw new Error('当前名单没有可发送的预览样例。');
    state.previewIndex = Math.min(state.previewIndex,max - 1);
    openModal('邮件预览', '<div class="fields two"><label>样例序号<input id="preview-index" type="number" min="1" max="' + max +
      '" value="' + (state.previewIndex + 1) + '"></label><div class="inline"><button id="preview-update">' + icon('refresh-cw') +
      '刷新预览</button><span class="muted">共 ' + max + ' 个可发送样例</span></div></div><h3 id="preview-subject"></h3><p id="preview-meta" class="preview-meta"></p><iframe id="preview-frame" class="preview-frame" sandbox="" referrerpolicy="no-referrer" title="邮件正文预览"></iframe><div class="modal-actions"><button id="preview-done">关闭</button></div>');
    $('preview-done').onclick = closeModal;
    let sequence = 0;
    const update = async () => {
      const current = ++sequence;
      const index = Number($('preview-index').value) - 1;
      if (!Number.isInteger(index) || index < 0 || index >= max) { modalError('请选择有效样例序号。'); return; }
      try {
        await busy($('preview-update'),async () => {
          const result = await api('/preview-email',{method:'POST',body:{...config(),recipient_index:index}});
          if (current !== sequence || !$('preview-frame')) return;
          state.previewIndex = index;
          $('preview-subject').textContent = result.subject || '';
          const recipient = typeof result.recipient === 'string' ? result.recipient : [result.recipient?.name,result.recipient?.email].filter(Boolean).join(' · ');
          $('preview-meta').textContent = recipient + (result.attachment_name ? ' | 附件：' + result.attachment_name : '');
          $('preview-frame').srcdoc = '<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; font-src \'none\'; form-action \'none\'; base-uri \'none\'"><style>body{font:14px/1.8 Arial,sans-serif;padding:18px;color:#202429;overflow-wrap:anywhere}img{max-width:100%}table{max-width:100%}</style></head><body>' + (result.html_content || esc(result.text_content || '')) + '</body></html>';
          const unresolved = (result.subject || '') + ' ' + (result.html_content || '');
          if (/\{\{[^{}]+\}\}|&lt;人名&gt;|<人名>/.test(unresolved)) modalError('样例含未解析变量，请核对变量列与空值。');
        });
      } catch (error) { modalError(safeError(error)); }
    };
    $('preview-update').onclick = update;
    $('preview-index').onchange = update;
    await update();
  }
  async function openTest() {
    if (!state.accounts.length) throw new Error('请先添加发件账号。');
    if (state.import) await runPreflight();
    const samples = (state.preview?.rows || []).filter(r => ['valid','sendable'].includes(r.status));
    openModal(state.mode === 'demo' ? '模拟测试发送' : '测试发送（真实邮件）', '<form id="test-form"><label>测试账号<select id="test-account">' +
      state.accounts.map(a => '<option value="' + esc(a.id) + '">' + esc(a.name || a.email) + ' · ' + esc(a.email) + '</option>').join('') +
      '</select></label><div class="fields two separated"><label>测试收件邮箱<input id="test-email" type="email" required placeholder="你的邮箱"></label><label>测试姓名<input id="test-name" value="测试收件人" required></label></div>' +
      (samples.length ? '<label>变量样例（当前名单页）<select id="test-sample">' + samples.map((r,i) => '<option value="' + i + '">第 ' + Number(r.row_number) + ' 行 · ' + esc(r.name) + ' · ' + esc(r.email) + '</option>').join('') + '</select></label>' : '') +
      '<p class="muted">' + (state.mode === 'live' ? '将发送一封真实邮件。仅填写你有权测试的收件地址。' : '演示模式仅模拟，不会投递真实邮件。') +
      '</p><div class="modal-actions"><button type="button" id="test-cancel">取消</button><button id="test-submit" type="submit" class="primary">' + icon('send-horizontal') + '发送测试邮件</button></div><p id="test-result" class="preview-meta" aria-live="polite"></p></form>');
    if (state.accountIds.length) $('test-account').value = String(state.accountIds[0]);
    let previousStatus = null;
    $('test-cancel').onclick = closeModal;
    $('test-form').onsubmit = async e => {
      e.preventDefault();
      let testStarted = false;
      try {
        await busy($('test-submit'),async () => {
          const issues = contentIssues();
          if (issues.length) throw new Error(issues.join('；'));
          if (previousStatus === 'uncertain' && !window.confirm('上一封测试邮件状态待确认，可能已经投递。再次测试有重复投递风险，确认继续？')) return;
          const c = config();
          const text = c.subject + ' ' + quill.getText();
          const sample = samples[Number($('test-sample')?.value || 0)];
          if (/\{\{[^{}]+\}\}/.test(text) && !sample) throw new Error('当前页没有有效变量样例，请在名单中翻页到有效记录后测试。');
          const values = {...(sample?.values || {})};
          if (c.name_column) values[c.name_column] = $('test-name').value.trim();
          if (Object.hasOwn(values,'姓名')) values['姓名'] = $('test-name').value.trim();
          const account = state.accounts.find(a => String(a.id) === $('test-account').value);
          const testRevision = state.mailRevision;
          testStarted = true;
          state.testResult = {status:'testing',revision:testRevision};
          renderPreparation();
          const result = await api('/test-send',{method:'POST',body:{account_id:account.id,test_email:$('test-email').value.trim(),
            test_name:$('test-name').value.trim(),subject:c.subject,html_content:c.html_content,attachment_id:c.attachment_id,
            add_unsubscribe:c.add_unsubscribe,purpose:c.purpose,values}});
          const status = result.status;
          if (!['accepted','failed','uncertain'].includes(status)) throw new Error('服务未返回明确的测试结果，请先检查收件箱，不要盲目重复测试。');
          previousStatus = status;
          state.testResult = {status,revision:testRevision};
          renderPreparation();
          if (!$('test-result')) return;
          $('test-result').textContent = (labels[status] || status) + (result.detail ? '：' + safeLog(result.detail) : '');
          if (status === 'uncertain') $('test-result').textContent += '。请检查收件箱，重复测试可能重复投递。';
        });
      } catch (error) {
        if (testStarted && state.testResult?.status === 'testing') {
          state.testResult.status = 'error'; renderPreparation();
        }
        modalError(safeError(error));
      }
    };
  }
  async function createTask() {
    if (state.actionBusy) return;
    state.actionBusy = true;
    try {
      await busy($('task-create'),async () => {
        navigate('workspace'); setStep(4);
        const wasConsented = $('send-consent').checked;
        await runPreflight();
        const invalid = checks().filter(c => !c.ok);
        if (invalid.length) throw new Error(invalid.map(c => c.text + '：' + c.detail).join('；'));
        if (!wasConsented || !$('send-consent').checked) throw new Error('请勾选核对确认后创建任务。');
        const c = config(); c.title = c.title || c.subject || '邮件任务';
        const task = taskResult(await api('/tasks',{method:'POST',body:c}));
        if (!task.id) throw new Error('任务响应缺少 id。');
        $('send-consent').checked = false;
        state.taskOffset = 0; state.selectedRecipients.clear();
        await selectTask(task.id);
        await loadTasks();
        toast('任务已创建，尚未发送。请在监控中明确启动。');
      });
    } finally { state.actionBusy = false; }
  }
  function stopPolling() { clearTimeout(state.poll); state.poll = null; }
  function schedulePolling() {
    stopPolling();
    if (!state.task || !activeStatuses.has(state.task.status)) return;
    state.poll = setTimeout(async () => {
      try { await refreshTask(); }
      catch (error) {
        if (safeError(error)) {
          $('connection').hidden = false; $('connection').textContent = '任务状态暂时无法刷新，请勿重复启动或重发。' + safeError(error);
        }
        schedulePolling();
      }
    }, 1200);
  }
  async function loadTasks() {
    const data = await api('/tasks'); state.tasks = data.tasks || [];
    renderTaskList();
    if (!state.task && state.tasks.length) {
      const candidate = state.tasks.find(t => activeStatuses.has(t.status) || t.status === 'paused') || state.tasks[0];
      await selectTask(candidate.id);
    } else if (!state.tasks.length && !state.task) renderMonitor();
  }
  async function selectTask(id) {
    stopPolling();
    state.taskOffset = 0; state.selectedRecipients.clear();
    const sequence = ++state.taskSequence;
    const data = taskResult(await api('/tasks/' + pathId(id) + '?offset=0&limit=' + state.taskLimit));
    if (sequence !== state.taskSequence) return;
    state.task = data; renderMonitor(); renderTaskDetail(); schedulePolling();
  }
  async function refreshTask() {
    if (!state.task) { await loadTasks(); return; }
    const id = state.task.id, sequence = ++state.taskSequence;
    const data = taskResult(await api('/tasks/' + pathId(id) + '?offset=' + state.taskOffset + '&limit=' + state.taskLimit));
    if (sequence !== state.taskSequence || id !== state.task?.id) return;
    state.task = data;
    const index = state.tasks.findIndex(t => t.id === id);
    if (index >= 0) state.tasks[index] = data;
    if ($('connection').textContent.startsWith('任务状态')) $('connection').hidden = true;
    renderMonitor(); renderTaskDetail(); renderTaskList(); schedulePolling();
  }
  function taskMetrics(task) {
    const c = task.counts || {};
    return '<div class="metrics">' + [['total','收件总数'],['pending','等待发送'],['sending','发送中'],['accepted','服务器已接收'],['failed','发送失败'],['uncertain','待确认']].map(([key,title]) =>
      '<div class="' + key + '"><span>' + title + '</span><strong>' + Number(c[key] || 0) + '</strong></div>').join('') + '</div>';
  }
  function taskButtons(task, full = false) {
    let buttons = '';
    if (task.status === 'ready' && !isLegacy(task)) buttons += '<button data-task-action="start" class="primary">' + icon('play') + '启动任务</button>';
    if (['starting','running'].includes(task.status) && !isLegacy(task)) buttons += '<button data-task-action="pause">' + icon('pause') + '安全暂停</button>';
    if (task.status === 'paused' && !isLegacy(task) && Number(task.counts?.pending) > 0) buttons += '<button data-task-action="resume" class="primary">' + icon('play') + '继续任务</button>';
    if (task.status === 'stopping') buttons += '<button disabled>' + icon('loader-circle') + '等待状态确认</button>';
    if (full) {
      if (task.config?.import_id && !isLegacy(task)) buttons += '<button data-task-copy>' + icon('copy') + '载入为新任务</button>';
      buttons += '<button data-task-export="all">' + icon('download') + '导出全部</button><button data-task-export="failed">' + icon('file-down') + '导出问题记录</button>';
    } else {
      buttons += '<button data-task-detail>' + icon('list') + '查看明细</button>';
    }
    return '<div class="task-actions">' + buttons + '</div>';
  }
  function readableTime(value) {
    if (!value) return '';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN',{hour12:false});
  }
  function safeLog(message) {
    let text = String(message || '');
    if (boot.token) text = text.split(boot.token).join('[已隐藏]');
    return text.replace(/(Authorization\s*[:=]\s*|Bearer\s+)[^\s,;]+/gi,'$1[已隐藏]')
      .replace(/((?:password|smtp_password|授权码|密码|token)\s*[:=]\s*)[^\s,;]+/gi,'$1[已隐藏]');
  }
  function renderPreparation() {
    if (state.task) return;
    const checked = state.preview && state.revision !== null;
    const recipientText = checked ? Number(state.preview.counts?.sendable || 0) + ' 人' : state.import ? '待预检' : '未导入';
    const accountCount = state.accountIds.filter(id => state.accounts.some(a => a.id === id)).length;
    const accountText = accountCount ? accountCount + ' 个已选' : state.accounts.length ? '未选择' : '未添加';
    const result = state.testResult;
    const current = result && result.revision === state.mailRevision;
    const testText = !result ? '未测试' : !current ? '配置已变更，需重新测试' :
      result.status === 'testing' ? '测试中' : result.status === 'error' ? '测试未完成' :
      (state.mode === 'demo' ? '模拟 · ' : '') + (labels[result.status] || result.status);
    const testTone = current && result.status === 'accepted' ? 'good' :
      current && result.status === 'uncertain' ? 'warn' : current && result.status === 'failed' ? 'bad' : '';
    $('monitor-content').innerHTML = '<div class="preparation"><h3>准备摘要</h3><dl>' +
      '<div><dt>' + icon('users') + '可发送人数</dt><dd>' + esc(recipientText) + '</dd></div>' +
      '<div><dt>' + icon('at-sign') + '发件账号</dt><dd>' + esc(accountText) + '</dd></div>' +
      '<div><dt>' + icon('paperclip') + '公共附件</dt><dd>' + esc(state.attachment?.filename || '无附件') + '</dd></div>' +
      '<div><dt>' + icon('send-horizontal') + '测试结果</dt><dd class="' + testTone + '">' + esc(testText) + '</dd></div>' +
      '</dl></div>';
    icons();
  }
  function renderMonitor() {
    const task = state.task;
    if (!task) {
      renderPreparation(); return;
    }
    const c = task.counts || {}, settled = Number(c.accepted || 0) + Number(c.failed || 0) + Number(c.uncertain || 0);
    const total = Number(c.total || 0);
    $('monitor-content').innerHTML = badge(task.status) + '<h3 class="monitor-title">' + esc(task.title || '邮件任务') +
      '</h3><div class="muted">' + esc(readableTime(task.created_at)) + '</div>' + taskMetrics(task) +
      '<progress max="' + Math.max(total,1) + '" value="' + settled + '" aria-label="任务处理进度"></progress><div class="muted">' +
      settled + ' / ' + total + ' 已处理（待确认不算成功）</div>' +
      (task.pause_reason ? '<div class="notice">' + icon('circle-alert') + '<span>' + esc(pauseText(task.pause_reason)) + '</span></div>' : '') +
      (isLegacy(task) ? '<div class="notice">' + icon('archive') + '<span>旧版任务仅供审阅和导出，不自动继续发送。</span></div>' : '') +
      taskButtons(task) + '<div class="task-events"><h3>最近活动</h3>' +
      ((task.logs || []).slice(-4).reverse().map(log => '<div class="event"><time>' + esc(readableTime(log.time).split(' ').pop()) +
      '</time><span>' + esc(safeLog(log.message)) + '</span></div>').join('') || '<p class="muted">暂无活动记录</p>') + '</div>';
    icons();
  }
  function renderTaskList() {
    const q = $('task-search').value.trim().toLowerCase(), status = $('task-status').value;
    const tasks = state.tasks.filter(t => (!q || (t.title || '').toLowerCase().includes(q)) && (!status || t.status === status));
    $('task-list').innerHTML = tasks.length ? tasks.map(t => '<div class="task-list-row"><div><h3>' + esc(t.title || '邮件任务') +
      '</h3><span class="muted">' + Number(t.counts?.total || 0) + ' 位收件人' + (isLegacy(t) ? ' · 旧版记录' : '') +
      '</span></div>' + badge(t.status) + '<span class="muted task-date">' + esc(readableTime(t.created_at)) +
      '</span><button data-task-id="' + esc(t.id) + '" class="icon" title="查看任务" aria-label="查看任务">' + icon('arrow-up-right') + '</button></div>').join('') :
      '<div class="empty">' + icon('list-checks') + '<strong>' + (state.tasks.length ? '没有符合条件的任务' : '还没有任务记录') + '</strong></div>';
    icons();
  }
  function renderTaskDetail() {
    const task = state.task;
    $('task-detail').hidden = !task;
    if (!task) return;
    const rows = task.recipients || [], total = Number(task.counts?.total || 0);
    state.selectedRecipients.forEach(id => { if (!rows.some(r => r.id === id && ['failed','uncertain'].includes(r.status))) state.selectedRecipients.delete(id); });
    const locked = activeStatuses.has(task.status) || isLegacy(task);
    $('task-detail').innerHTML = '<div class="section-head"><div><h2>' + esc(task.title || '邮件任务') + '</h2><div class="muted">' +
      esc(task.config?.subject || '') + '</div></div>' + badge(task.status) + '</div>' + taskMetrics(task) +
      (task.pause_reason ? '<div class="notice">' + icon('circle-alert') + '<span>' + esc(pauseText(task.pause_reason)) + '</span></div>' : '') +
      taskButtons(task,true) + '<div class="section-head compact"><h3>收件结果</h3><div class="inline"><button data-retry="failed"' +
      (locked ? ' disabled' : '') + '>' + icon('rotate-cw') + '重发失败</button><button data-retry="uncertain"' +
      (locked ? ' disabled' : '') + '>' + icon('triangle-alert') + '人工重发待确认</button></div></div><div class="table-wrap"><table><thead><tr><th>选择</th><th>姓名</th><th>邮箱</th><th>状态</th><th>详情</th></tr></thead><tbody>' +
      (rows.length ? rows.map(r => '<tr><td>' + (['failed','uncertain'].includes(r.status) ? '<input class="task-recipient-check" type="checkbox" data-recipient-id="' +
        esc(r.id) + '" aria-label="选择 ' + esc(r.email) + '"' + (state.selectedRecipients.has(r.id) ? ' checked' : '') + (locked ? ' disabled' : '') + '>' : '') +
        '</td><td>' + esc(r.name) + '</td><td>' + esc(r.email) + '</td><td>' + badge(r.status) + '</td><td>' + esc(safeLog(r.detail)) +
        '</td></tr>').join('') : '<tr><td colspan="5">暂无收件记录</td></tr>') +
      '</tbody></table></div><div class="pagination"><span>' + (rows.length ? state.taskOffset + 1 : 0) + '–' + (state.taskOffset + rows.length) +
      ' / ' + total + ' · 重发范围限本页所选记录</span><div class="inline"><button data-task-page="-1" class="icon" title="上一页" aria-label="上一页"' +
      (state.taskOffset === 0 ? ' disabled' : '') + '>' + icon('chevron-left') + '</button><button data-task-page="1" class="icon" title="下一页" aria-label="下一页"' +
      (rows.length < state.taskLimit || state.taskOffset + rows.length >= total ? ' disabled' : '') + '>' + icon('chevron-right') +
      '</button></div></div><details class="log-section"><summary>任务日志（' + (task.logs || []).length + '）</summary>' +
      (task.logs || []).map(log => '<div class="event"><time>' + esc(readableTime(log.time)) + '</time><span>' + esc(safeLog(log.message)) +
      '</span></div>').join('') + '</details>';
    icons();
  }
  async function taskAction(action, button) {
    if (state.actionBusy || !state.task) return;
    let task = state.task;
    if (isLegacy(task)) throw new Error('旧版任务只能查看和导出。');
    state.actionBusy = true;
    try {
      if (action === 'start') {
        task = taskResult(await api('/tasks/' + pathId(task.id) + '?offset=' + state.taskOffset + '&limit=' + state.taskLimit));
        state.task = task; renderMonitor(); renderTaskDetail();
        if (isLegacy(task) || task.status !== 'ready') throw new Error('任务状态已变化，请刷新并检查，当前不能直接启动。');
        const c = task.config || {}, counts = task.counts || {};
        if (!Number(counts.pending)) throw new Error('冻结任务中没有待发送收件人。');
        const savedFilters = (c.filters || []).map(f => String(f.column) + '：' + (f.values || []).join('、')).join('；') || '未筛选';
        const confirmed = await confirmAction(state.mode === 'live' ? '启动真实发送' : '启动模拟发送',
          '启动已冻结任务「' + (task.title || '邮件任务') + '」：' + (c.subject || '') +
          '。保存工作表：' + (c.sheet || '未指定') + '；保存筛选：' + savedFilters +
          '。冻结名单共 ' + Number(counts.total || 0) + ' 位，当前待发 ' + Number(counts.pending) +
          ' 位。发送使用任务保存的配置，后台逐封复查排除名单。' +
          (state.mode === 'live' ? '将投递真实邮件。' : '不会投递真实邮件。'),'明确启动');
        if (!confirmed) return;
      } else if (action === 'resume') {
        if (!await confirmAction('继续任务','继续仅处理任务中尚未发送的记录；请先核对暂停原因。','继续任务')) return;
      }
      await busy(button,async () => {
        await api('/tasks/' + pathId(task.id) + '/' + action,{method:'POST'});
        await refreshTask(); await loadTasks();
        toast(action === 'pause' ? '暂停请求已提交，正在检查任务状态' : '任务请求已提交');
      });
    } finally { state.actionBusy = false; }
  }
  async function retryRecipients(kind, button) {
    const task = state.task;
    if (!task || state.actionBusy || activeStatuses.has(task.status) || isLegacy(task)) return;
    const rows = (task.recipients || []).filter(r => r.status === kind && state.selectedRecipients.has(r.id));
    if (!rows.length) throw new Error('请先选择本页的' + (kind === 'uncertain' ? '待确认' : '失败') + '收件记录。');
    const uncertain = kind === 'uncertain';
    if (!await confirmAction(uncertain ? '待确认记录重复投递风险' : '重发失败记录',
      uncertain ? '这 ' + rows.length + ' 条记录可能已被服务器接收。请先人工检查收件箱或服务商记录；继续可能导致重复邮件。确认承担重复投递风险并重发？' :
      '重新发送所选 ' + rows.length + ' 条明确失败记录，不包含待确认记录。','确认重发')) return;
    state.actionBusy = true;
    try {
      await busy(button,async () => {
        await api('/tasks/' + pathId(task.id) + '/retry',{method:'POST',body:{recipient_ids:rows.map(r => r.id),include_uncertain:uncertain}});
        state.selectedRecipients.clear(); await refreshTask(); await loadTasks();
        toast('重发请求已提交，请检查任务状态');
      });
    } finally { state.actionBusy = false; }
  }
  async function downloadExport(data) {
    if (!data.export_id) throw new Error('导出响应缺少 export_id。');
    const mode = state.mode, epoch = state.epoch;
    if (boot.desktop && window.pywebview?.api?.save_export) {
      const result = await window.pywebview.api.save_export(data.export_id,mode);
      if (result?.error || result?.ok === false || result?.success === false || result?.status === 'error') throw new Error(result.error || result.message || result.detail || '原生保存失败');
      toast(result === false || result?.cancelled || result?.status === 'cancelled' ? '已取消保存' : '保存操作已完成');
      return;
    }
    const response = await fetch('/api/exports/' + pathId(data.export_id),{headers:authHeaders(mode)});
    if (epoch !== state.epoch) throw new DOMException('模式已切换','AbortError');
    if (!response.ok) throw new Error('导出下载失败（HTTP ' + response.status + '）');
    const url = URL.createObjectURL(await response.blob());
    const a = document.createElement('a'); a.href = url; a.download = data.filename || 'yunyoubao-export';
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url),30000);
    toast('已开始下载导出文件');
  }
  async function exportTask(scope, button) {
    if (!state.task) return;
    await busy(button,async () => {
      const data = await api('/tasks/' + pathId(state.task.id) + '/export',{method:'POST',body:{scope}});
      await downloadExport(data);
    });
  }
  async function handleTaskClick(e) {
    const action = e.target.closest('[data-task-action]'), detail = e.target.closest('[data-task-detail]');
    const exportButton = e.target.closest('[data-task-export]'), retry = e.target.closest('[data-retry]'), page = e.target.closest('[data-task-page]');
    const copy = e.target.closest('[data-task-copy]');
    if (copy && state.task && !state.actionBusy) {
      if (state.dirty && !window.confirm('载入任务配置会替换未保存的工作台更改，继续吗？')) return;
      const task = state.task, c = {...task.config};
      if (state.import?.import_id === c.import_id) c._ui = {import:state.import,attachment:state.attachment?.attachment_id === c.attachment_id ? state.attachment : null};
      applyDraft({id:null,title:task.title,config:c});
      state.dirty = true; $('draft-state').textContent = '任务配置已载入，尚未保存';
      await runPreflight();
      toast('任务配置已载入，新任务需重新核对并创建');
    }
    if (action && !action.disabled) await taskAction(action.dataset.taskAction,action);
    if (detail) { navigate('history'); $('task-detail').scrollIntoView({behavior:'smooth',block:'start'}); }
    if (exportButton) await exportTask(exportButton.dataset.taskExport,exportButton);
    if (retry && !retry.disabled) await retryRecipients(retry.dataset.retry,retry);
    if (page && !page.disabled) {
      state.taskOffset = Math.max(0,state.taskOffset + Number(page.dataset.taskPage) * state.taskLimit);
      state.selectedRecipients.clear(); await refreshTask();
    }
  }
  const help = [
    {id:'import',title:'名单导入与筛选',paragraphs:[
      '导入 .xlsx 或 .csv 后，选择工作表并指定姓名列、邮箱列。名单中的其他列可作为筛选条件，也可用作邮件变量。',
      '每个筛选列可勾选多个值：同列值采用 OR，不同列条件采用 AND。未勾选值的条件不限制范围。「按分工筛选」会寻找分工、部门、岗位或角色列。',
      '预检显示选中、无效、重复、排除、冲突和可发送计数。问题行开关仅筛选当前页，上一页和下一页可继续核查其他行。修改工作表、映射、筛选或排除名单后必须重新预检。']},
    {id:'mail',title:'正文、变量与附件',paragraphs:[
      '主题与正文初始为空。可插入 {{列名}} 变量；旧版 <人名> 使用已映射的姓名列。列名须与名单一致，不存在的变量会阻止创建任务。',
      '预览使用名单样例逐条渲染，请检查姓名、空值、主题和附件。邮件正文在隔离窗口中显示；外部图片不会在预览中联网加载，建议上传或粘贴图片。',
      '公共附件由任务中所有收件人共享，优先使用 PDF。上传成功后核对文件名；移除附件仅移除当前配置关联。',
      '模板会替换主题与正文，草稿保存四步全部配置，无需先添加账号。打开草稿后需要重新预检并核对授权范围。']},
    {id:'smtp',title:'账号与 SMTP 授权码',paragraphs:[
      'QQ 与 163 预设使用各自 SMTP 主机和 465 SSL / TLS 端口。自定义账号请填写服务商提供的 SMTP 主机、端口与连接安全方式。',
      '授权码不是邮箱登录密码。请在邮箱服务商的账号设置中开启 SMTP，并生成专用授权码。编辑账号时留空保留原授权码；默认记住授权码。',
      '默认每分钟 6 封、每日 200 封，按账号分别限制。额度、发送窗口和服务商限制会影响任务进度，请参考任务暂停原因。']},
    {id:'send',title:'测试与正式发送',paragraphs:[
      '正式模式会投递真实邮件；演示模式使用隔离数据和模拟发送。演示横幅始终标识当前模式。切换模式不代表暂停另一模式中已经启动的任务。',
      '先选择测试账号并发送到你有权使用的测试地址，再核对主题、排版和附件。测试 {{列名}} 使用所选名单样例的其他列，姓名使用测试姓名。',
      '核对发送页检查通过且人工确认后，可创建待启动任务。任务创建后不自动发送，必须明确启动。任务使用创建时保存的配置，而非工作台当前未保存内容。']},
    {id:'status',title:'任务状态与重发',paragraphs:[
      '服务器已接收仅表示 SMTP 服务端接收邮件，不保证最终送达。请勿把此计数当作收件箱送达率。',
      '安全暂停先提交暂停请求，再等待任务状态变为已暂停；正在暂停时不可继续或重复启动。已暂停任务可检查原因后继续。',
      '失败表示明确的发送失败；待确认表示投递结果未知，不能算成功。重发失败只处理所选明确失败记录。待确认须先人工检查，再单独确认重复投递风险。',
      '完成但有问题的任务仍须检查失败和待确认。任务明细可导出全部或问题记录，旧版任务只供审阅与导出。']},
    {id:'troubleshoot',title:'排错清单',paragraphs:[
      '认证失败：核对邮箱地址、SMTP 授权码、SMTP 开关和服务商安全限制，不要使用登录密码替代授权码。',
      '连接失败：核对主机、端口、SSL / TLS 或 STARTTLS、防火墙和网络代理。修改账号后先测试，不要直接重试全量任务。',
      '没有可发送记录：检查工作表与邮箱列映射、筛选条件、重复地址、冲突记录和排除名单。',
      '创建新任务前应重新预检当前配置。已冻结任务按保存的名单、筛选与人数启动，后台逐封复查排除名单。',
      '状态刷新失败：保持任务现场，不要重复启动或盲目重发；恢复服务连接后刷新任务查看真实状态。']},
    {id:'data',title:'数据、备份与迁移',paragraphs:[
      '设置中可查看当前模式的数据路径、备份数据、恢复备份、导入旧版数据和维护排除名单。正式与演示数据分别管理。',
      '备份和导出在桌面中优先使用原生保存窗口；普通浏览器使用鉴权下载。打开数据目录和导入旧版数据需要桌面桥接。',
      '恢复备份可能覆盖当前数据，请先备份，并确保没有运行任务。清理仅针对所选历史日志和未使用的导入文件。不要清理尚需追查的日志。',
      '授权码不写入草稿，也不展示在任务日志；当前备份不含授权码，恢复后需重新填写。备份仍包含名单与发送记录，请妥善保存。']}
  ];
  function renderHelp() {
    const query = $('help-search').value.trim().toLowerCase();
    const articles = help.filter(a => (a.title + a.paragraphs.join('')).toLowerCase().includes(query));
    $('help-directory').innerHTML = articles.map(a => '<a href="#help-' + a.id + '">' + esc(a.title) + '</a>').join('');
    $('help-articles').innerHTML = articles.length ? articles.map(a => '<section class="help-article" id="help-' + a.id +
      '"><h2>' + esc(a.title) + '</h2>' + a.paragraphs.map(p => '<p>' + esc(p) + '</p>').join('') + '</section>').join('') :
      '<div class="empty">' + icon('search-x') + '<strong>没有匹配的帮助</strong></div>';
    icons();
  }
  async function loadSettings() {
    const [data,suppressions] = await Promise.all([api('/data'),api('/suppressions')]);
    $('data-info').innerHTML = '<dt>当前模式</dt><dd>' + (state.mode === 'live' ? '正式' : '演示') + '</dd><dt>数据路径</dt><dd>' +
      esc(data.path) + '</dd><dt>占用</dt><dd>' + formatSize(data.size) + '</dd><dt>版本</dt><dd>' + esc(data.version || boot.version) + '</dd>';
    $('suppressions').value = suppressions.content || '';
    updateNativeControls();
  }
  function updateNativeControls() {
    const native = boot.desktop && window.pywebview?.api;
    $('data-folder').disabled = !native?.open_data_folder;
    $('data-folder').title = native?.open_data_folder ? '打开当前模式数据目录' : '需要桌面窗口的原生接口';
    $('data-legacy').disabled = !native?.import_legacy;
    $('data-legacy').title = native?.import_legacy ? '从旧版数据目录导入' : '需要桌面窗口的原生接口';
  }
  function setDrawer(open) {
    if (open) drawerFocus = document.activeElement;
    $('settings').hidden = !open; $('drawer-backdrop').hidden = !open;
    document.querySelectorAll('.app-header,main,.action-bar').forEach(e => { e.inert = open; });
    if (open) { $('settings-close').focus(); loadSettings().catch(error => toast(safeError(error))); }
    else drawerFocus?.focus();
  }
  async function nativeCall(method) {
    const mode = state.mode, epoch = state.epoch;
    if (!boot.desktop || !window.pywebview?.api?.[method]) throw new Error('此操作需要桌面应用的原生接口。');
    const result = await window.pywebview.api[method](mode);
    if (epoch !== state.epoch) throw new DOMException('模式已切换','AbortError');
    if (result?.error || result?.success === false || result?.ok === false || result?.status === 'error') throw new Error(result.error || result.message || result.detail || '原生操作失败');
    return result;
  }
  async function restoreFile(file) {
    if (!file) return;
    if (state.tasks.some(t => activeStatuses.has(t.status))) throw new Error('请先安全暂停所有运行任务，再恢复备份。');
    if (!window.confirm('恢复备份可能覆盖当前' + (state.mode === 'live' ? '正式' : '演示') + '数据。已备份当前数据并确认继续？')) return;
    const form = new FormData(); form.append('file',file);
    await busy($('data-restore'),async () => {
      await api('/data/restore',{method:'POST',body:form});
      resetComposer(); state.task = null; state.tasks = []; stopPolling();
      await initializeData(); await loadSettings(); toast('备份已恢复，请重新核对账号与任务');
    });
    $('restore-file').value = '';
  }
  function applyModeUI() {
    document.querySelectorAll('[data-mode]').forEach(b => {
      b.classList.toggle('active',b.dataset.mode === state.mode);
      b.setAttribute('aria-pressed',String(b.dataset.mode === state.mode));
    });
    $('demo-banner').hidden = state.mode !== 'demo';
    $('mode-label').textContent = state.mode === 'demo' ? '演示模式' : '正式模式';
    $('mode-label').classList.toggle('demo',state.mode === 'demo');
    $('test-open').innerHTML = icon('send-horizontal') + (state.mode === 'demo' ? '模拟测试' : '测试发送');
    icons();
  }
  function resetComposer() {
    clearTimeout(preflightTimer);
    state.import = null; state.columns = []; state.filters = []; state.preview = null; state.revision = null;
    state.accountIds = []; state.attachment = null; state.draftId = null; state.dirty = false;
    state.generation++; state.preflightSequence++; state.mailRevision++; state.offset = 0;
    state.previewIndex = 0; state.selectedRecipients.clear();
    state.testResult = null;
    ['subject','task-title','source-note','suppressions'].forEach(id => { $(id).value = ''; });
    $('purpose').value = 'notification'; $('unsubscribe').checked = true; $('send-consent').checked = false;
    $('start-time').value = '08:00'; $('end-time').value = '21:40'; $('problem-only').checked = false;
    $('import-empty').hidden = false; $('import-content').hidden = true;
    $('import-name').textContent = '尚未导入名单'; $('selection-summary').textContent = '尚未导入名单';
    $('draft-state').textContent = '未保存草稿';
    fillSelect($('sheet'),[]); setColumns([]); quill.setText('','silent');
    renderAttachment(); renderReview(); renderContentIssues(); setStep(1);
  }
  async function switchMode(mode) {
    if (mode === state.mode) return;
    if (state.actionBusy || state.uploading) throw new Error('请等待当前操作完成后再切换模式。');
    if (state.mode === 'live' && mode === 'demo') {
      await loadTasks();
      if (state.tasks.some(t => activeStatuses.has(t.status)) || (state.task && activeStatuses.has(state.task.status))) {
        throw new Error('正式任务仍在启动、运行或停止中。请先安全暂停并等待已暂停状态，再切换演示模式。');
      }
    }
    if (!await confirmAction('切换至' + (mode === 'demo' ? '演示模式' : '正式模式'),
      (state.dirty ? '当前未保存配置将被清空。' : '') +
      '两种模式数据隔离，切换不会暂停另一模式已启动的任务。' + (mode === 'live' ? '正式模式会发送真实邮件。' : '演示模式不会投递真实邮件。'),'切换模式')) return;
    stopPolling(); state.epoch++; state.taskSequence++; state.mode = mode;
    state.task = null; state.tasks = []; state.accounts = [];
    resetComposer(); applyModeUI(); renderAccounts(); renderMonitor(); renderTaskList();
    $('connection').hidden = true;
    await initializeData();
  }
  async function initializeData() {
    if (!boot.token) {
      $('connection').hidden = false;
      $('connection').textContent = '缺少会话令牌，请由后端注入 window.YUNYOUBAO 并从桌面应用打开。';
      return;
    }
    const results = await Promise.allSettled([loadAccounts(),loadTasks()]);
    const errors = results.filter(r => r.status === 'rejected' && r.reason?.name !== 'AbortError');
    if (errors.length) {
      $('connection').hidden = false; $('connection').textContent = errors.map(r => safeError(r.reason)).join('；');
    } else $('connection').hidden = true;
    renderAccounts(); renderMonitor(); renderTaskList(); renderReview();
  }
  function initializeEditor() {
    if (!window.Quill || Quill.version !== '1.3.6') throw new Error('本地 Quill 1.3.6 加载失败，请检查 static/vendor。');
    const Font = Quill.import('attributors/style/font'); Font.whitelist = ['Microsoft YaHei','SimSun','Georgia','monospace']; Quill.register(Font,true);
    const Size = Quill.import('attributors/style/size'); Size.whitelist = ['12px','14px','16px','18px','24px','32px']; Quill.register(Size,true);
    const Parchment = Quill.import('parchment');
    Quill.register(new Parchment.Attributor.Style('lineheight','line-height',{scope:Parchment.Scope.BLOCK,whitelist:['1.25','1.5','1.8','2']}),true);
    quill = new Quill('#editor',{theme:'snow',placeholder:'',modules:{toolbar:{
      container:[[{font:[false,...Font.whitelist]}],[{size:[false,...Size.whitelist]}],
        ['bold','italic','underline','strike'],[{color:[]},{background:[]}],[{header:[1,2,3,false]}],
        [{list:'ordered'},{list:'bullet'}],[{align:[]}],['link','image','clean']],
      handlers:{image:function() {
        const input = document.createElement('input'); input.type = 'file'; input.accept = 'image/*';
        input.onchange = () => {
          const file = input.files[0]; if (!file) return;
          if (!/^image\/(png|jpeg|gif|webp)$/.test(file.type)) { toast('正文图片支持 PNG、JPEG、GIF 和 WebP'); return; }
          if (file.size > 5 * 1024 * 1024) { toast('正文图片请控制在 5 MB 以内'); return; }
          const reader = new FileReader(); const index = quill.getSelection(true)?.index ?? quill.getLength() - 1;
          reader.onload = () => quill.insertEmbed(index,'image',reader.result,'user');
          reader.onerror = () => toast('图片读取失败'); reader.readAsDataURL(file);
        }; input.click();
      }}
    }}});
    const toolbar = document.querySelector('.ql-toolbar');
    const spacing = document.createElement('select'); spacing.setAttribute('aria-label','行距'); spacing.title = '行距';
    spacing.className = 'lineheight-select';
    spacing.innerHTML = '<option value="1.25">行距 1.25</option><option value="1.5">行距 1.5</option><option value="1.8" selected>行距 1.8</option><option value="2">行距 2</option>';
    spacing.onchange = () => quill.format('lineheight',spacing.value,'user'); toolbar.append(spacing);
    const titles = {bold:'加粗',italic:'斜体',underline:'下划线',strike:'删除线',link:'链接',image:'插入图片',clean:'清除格式',list:'列表',align:'对齐',font:'字体',size:'字号',header:'标题',color:'文字颜色',background:'背景颜色'};
    toolbar.querySelectorAll('button,select').forEach(el => {
      const cls = [...el.classList].find(c => c.startsWith('ql-')); const label = titles[cls?.slice(3)];
      if (label) { el.title = label; el.setAttribute('aria-label',label); }
    });
    quill.root.setAttribute('aria-label','邮件正文'); quill.root.setAttribute('role','textbox');
    quill.root.setAttribute('aria-multiline','true');
    quill.on('text-change',(_delta,_old,source) => { if (source !== 'silent') markDirty(); });
    quill.root.addEventListener('paste',e => {
      const images = [...(e.clipboardData?.items || [])].filter(item => item.type.startsWith('image/'));
      if (!images.length) return; e.preventDefault();
      images.forEach(item => {
        const file = item.getAsFile(); if (!file) return;
        if (!/^image\/(png|jpeg|gif|webp)$/.test(file.type)) { toast('正文图片支持 PNG、JPEG、GIF 和 WebP'); return; }
        if (file.size > 5 * 1024 * 1024) { toast('正文图片请控制在 5 MB 以内'); return; }
        const reader = new FileReader();
        reader.onload = () => { const index = quill.getSelection(true)?.index ?? quill.getLength() - 1; quill.insertEmbed(index,'image',reader.result,'user'); };
        reader.readAsDataURL(file);
      });
    });
  }
  function bindEvents() {
    document.querySelectorAll('[data-view]').forEach(b => b.onclick = () => navigate(b.dataset.view));
    document.querySelectorAll('[data-step]').forEach(b => b.onclick = () => setStep(b.dataset.step));
    document.querySelectorAll('[data-mode]').forEach(b => b.onclick = () => busy(b,() => switchMode(b.dataset.mode)).catch(error => { const message = safeError(error); if (message) toast(message); }));
    document.querySelectorAll('[data-variable-target]').forEach(b => b.onclick = () => {
      state.variableTarget = b.dataset.variableTarget;
      document.querySelectorAll('[data-variable-target]').forEach(x => x.classList.toggle('active',x === b));
    });
    document.querySelector('.brand').onclick = e => { e.preventDefault(); navigate('workspace'); };
    on('step-back','click',() => setStep(state.step - 1)); on('step-next','click',() => setStep(state.step + 1));
    on('theme','click',() => {
      const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = theme;
      try { localStorage.setItem('yunyoubao-theme',theme); } catch (_) {}
    });
    on('settings-open','click',() => setDrawer(true)); on('settings-close','click',() => setDrawer(false));
    on('drawer-backdrop','click',() => setDrawer(false));
    on('modal-close','click',closeModal);
    $('modal').addEventListener('close',() => { $('modal-content').onclick = null; $('modal-content').innerHTML = ''; modalFocus?.focus(); });
    $('modal').addEventListener('click',e => {
      if (e.target === $('modal')) {
        const rect = $('modal').getBoundingClientRect();
        if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) closeModal();
      }
    });
    document.addEventListener('keydown',e => {
      if (e.key === 'Escape' && !$('settings').hidden) setDrawer(false);
      if (e.key === 'Escape' && document.body.classList.contains('focus-edit')) document.body.classList.remove('focus-edit');
      if (e.key === 'Tab' && !$('settings').hidden) {
        const focusable = [...$('settings').querySelectorAll('button:not(:disabled),input:not([hidden]),select,textarea')];
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    });
    on('import-trigger','click',() => $('import-file').click());
    on('import-empty','click',() => $('import-file').click());
    on('import-empty','keydown',e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('import-file').click(); } });
    on('import-file','change',e => importFile(e.target.files[0]));
    const drop = $('import-empty');
    drop.addEventListener('dragover',e => { e.preventDefault(); drop.classList.add('over'); });
    drop.addEventListener('dragleave',() => drop.classList.remove('over'));
    on('import-empty','drop',e => { e.preventDefault(); drop.classList.remove('over'); return importFile(e.dataTransfer.files[0]); });
    on('demo-load','click',e => busy(e.currentTarget,async () => {
      if (state.mode !== 'demo') return;
      if (state.import && !window.confirm('演示名单将替换当前名单，继续吗？')) return;
      const data = await api('/demo/import'); setImport(data); await loadAccounts();
      state.accountIds = state.accounts.map(a => a.id); renderAccounts(); await runPreflight(); toast('虚构演示名单已载入');
    }));
    on('sheet','change',async () => {
      const oldName = $('name-column').value, oldEmail = $('email-column').value;
      state.filters = []; markDirty(true);
      clearTimeout(preflightTimer);
      const sheet = $('sheet').value, generation = state.generation;
      const metadata = (state.import.sheets || []).find(s => typeof s === 'object' && (s.name || s.sheet || s.title) === sheet);
      const sheetColumns = state.import.sheet_columns?.[sheet] || metadata?.columns;
      let result;
      if (sheetColumns) result = {columns:sheetColumns};
      else {
        try {
          result = await api('/imports/' + pathId(state.import.import_id) + '/preview',{method:'POST',body:{
            sheet,name_column:'',email_column:'',filters:[],offset:0,limit:state.limit
          }});
        } catch (error) {
          if (error.name === 'AbortError') throw error;
          result = await api('/imports/' + pathId(state.import.import_id) + '/preview',{method:'POST',body:{
            sheet,name_column:oldName,email_column:oldEmail,filters:[],offset:0,limit:state.limit
          }});
        }
      }
      if (generation !== state.generation) return;
      if (result.columns) state.import.sheet_columns = {...(state.import.sheet_columns || {}),[sheet]:result.columns};
      if (result.mapping_required) { state.preview = result; state.revision = null; }
      setColumns(result.columns || [],{name:oldName,email:oldEmail}); renderFilters();
      if ($('name-column').value && $('email-column').value) await runPreflight();
      else $('preflight-state').textContent = '请选择此工作表的姓名列与邮箱列';
    });
    on('name-column','change',() => markDirty(true)); on('email-column','change',() => markDirty(true));
    on('filter-add','click',() => addFilter());
    on('division-filter','click',() => {
      const col = state.columns.find(c => /分工|部门|岗位|角色|division|department|role/i.test(c));
      if (!col) throw new Error('名单中未找到分工、部门、岗位或角色列，请使用添加条件。');
      addFilter(col);
    });
    on('filter-clear','click',() => { state.filters = []; renderFilters(); markDirty(true); });
    on('filters','change',e => {
      if (e.target.dataset.filterColumn !== undefined) {
        const i = Number(e.target.dataset.filterColumn), column = e.target.value;
        if (state.filters.some((f,j) => j !== i && f.column === column)) { renderFilters(); throw new Error('同列不能重复添加条件，请在现有条件中勾选多个值。'); }
        state.filters[i] = {column,values:[]}; markDirty(true); renderFilters();
      } else if (e.target.dataset.filterIndex !== undefined) {
        const f = state.filters[Number(e.target.dataset.filterIndex)], value = e.target.value;
        f.values = e.target.checked ? [...new Set([...f.values,value])] : f.values.filter(v => v !== value);
        markDirty(true);
      }
    });
    on('filters','click',e => {
      const b = e.target.closest('[data-filter-remove]'); if (!b) return;
      state.filters.splice(Number(b.dataset.filterRemove),1); renderFilters(); markDirty(true);
    });
    on('problem-only','change',renderImport);
    on('preflight-refresh','click',e => busy(e.currentTarget,runPreflight));
    on('review-refresh','click',e => busy(e.currentTarget,runPreflight));
    on('import-prev','click',async () => { state.offset = Math.max(0,state.offset - state.limit); await runPreflight(); });
    on('import-next','click',async () => { state.offset += state.limit; await runPreflight(); });
    on('import-page-size','change',async e => { state.limit = Number(e.target.value); state.offset = 0; await runPreflight(); });
    ['subject','task-title','source-note','start-time','end-time'].forEach(id => on(id,'input',() => markDirty()));
    ['purpose','unsubscribe'].forEach(id => on(id,'change',() => markDirty()));
    on('variable-insert','click',() => { const col = $('variable-column').value; if (!col) throw new Error('请选择要插入的名单列。'); insertVariable('{{' + col + '}}'); });
    on('legacy-name','click',() => insertVariable('<人名>'));
    on('focus-editor','click',() => {
      document.body.classList.toggle('focus-edit');
      $('focus-editor').title = document.body.classList.contains('focus-edit') ? '退出专注编辑' : '专注编辑';
      $('focus-editor').setAttribute('aria-label',$('focus-editor').title);
    });
    on('attachment-upload','click',() => $('attachment-file').click());
    on('attachment-file','change',e => uploadAttachment(e.target.files[0]));
    on('attachment-remove','click',() => { state.attachment = null; renderAttachment(); markDirty(); });
    on('account-add','click',() => accountEditor());
    on('accounts','change',e => {
      if (!e.target.matches('[data-account-select]')) return;
      const a = state.accounts.find(a => String(a.id) === e.target.dataset.accountSelect);
      state.accountIds = e.target.checked ? [...new Set([...state.accountIds,a.id])] : state.accountIds.filter(id => id !== a.id);
      markDirty();
    });
    on('accounts','click',async e => {
      const edit = e.target.closest('[data-account-edit]'), remove = e.target.closest('[data-account-delete]');
      if (edit) accountEditor(state.accounts.find(a => String(a.id) === edit.dataset.accountEdit));
      if (remove) {
        const a = state.accounts.find(a => String(a.id) === remove.dataset.accountDelete);
        if (!await confirmAction('删除发件账号','删除 ' + a.email + '？已保存任务可能引用此账号，请先核查。','删除')) return;
        await api('/accounts/' + pathId(a.id),{method:'DELETE'}); await loadAccounts(); markDirty(); toast('账号已删除');
      }
    });
    on('draft-save','click',() => saveDraft()); on('draft-open','click',openDrafts); on('template-open','click',openTemplates);
    on('preview-open','click',e => busy(e.currentTarget,openPreview)); on('test-open','click',openTest);
    on('task-create','click',createTask); on('monitor-refresh','click',e => busy(e.currentTarget,refreshTask));
    on('history-refresh','click',e => busy(e.currentTarget,async () => { await loadTasks(); if (state.task) await refreshTask(); }));
    on('monitor-content','click',handleTaskClick); on('task-detail','click',handleTaskClick);
    on('task-detail','change',e => {
      const el = e.target.closest('[data-recipient-id]'); if (!el) return;
      const r = state.task?.recipients?.find(r => String(r.id) === el.dataset.recipientId);
      if (!r) return; if (el.checked) state.selectedRecipients.add(r.id); else state.selectedRecipients.delete(r.id);
    });
    on('task-list','click',async e => {
      const b = e.target.closest('[data-task-id]'); if (!b) return;
      await selectTask(b.dataset.taskId); $('task-detail').scrollIntoView({behavior:'smooth',block:'start'});
    });
    on('task-search','input',renderTaskList); on('task-status','change',renderTaskList); on('help-search','input',renderHelp);
    on('data-folder','click',() => nativeCall('open_data_folder'));
    on('data-backup','click',e => busy(e.currentTarget,async () => downloadExport(await api('/data/backup',{method:'POST'}))));
    on('data-restore','click',() => $('restore-file').click()); on('restore-file','change',e => restoreFile(e.target.files[0]));
    on('data-legacy','click',e => busy(e.currentTarget,async () => {
      if (!window.confirm('导入旧版数据到当前模式？请先备份现有数据。')) return;
      const result = await nativeCall('import_legacy');
      if (result === false || result?.cancelled || result?.status === 'cancelled') { toast('已取消导入'); return; }
      await initializeData(); await loadSettings(); toast('旧版数据导入操作已完成');
    }));
    on('suppression-save','click',e => busy(e.currentTarget,async () => {
      await api('/suppressions',{method:'PUT',body:{content:$('suppressions').value}});
      markDirty(true); if (state.import) await runPreflight(); toast('排除名单已保存，名单已重新预检');
    }));
    on('data-cleanup','click',e => busy(e.currentTarget,async () => {
      const body = {logs:$('cleanup-logs').checked,unused_imports:$('cleanup-imports').checked};
      if (!body.logs && !body.unused_imports) throw new Error('请选择要清理的项目。');
      if (state.tasks.some(t => activeStatuses.has(t.status))) throw new Error('请先安全暂停运行任务，再清理数据。');
      if (!window.confirm('永久清理所选数据？此操作不能撤销。')) return;
      await api('/data/cleanup',{method:'POST',body}); await loadSettings(); await loadTasks();
      if (state.task) await refreshTask(); toast('所选数据已清理');
    }));
    window.addEventListener('pywebviewready',updateNativeControls);
    window.addEventListener('beforeunload',e => { if (state.dirty) { e.preventDefault(); e.returnValue = ''; } });
    window.addEventListener('pagehide',stopPolling);
  }
  try {
    try { document.documentElement.dataset.theme = localStorage.getItem('yunyoubao-theme') || localStorage.getItem('theme') || 'light'; } catch (_) {}
    $('version').textContent = boot.version ? 'v' + String(boot.version).replace(/^v/,'') : 'v0.2';
    initializeEditor(); bindEvents(); applyModeUI(); renderAccounts(); renderMonitor(); renderHelp(); renderReview();
    setStep(1); initializeData().catch(error => toast(safeError(error)));
  } catch (error) {
    $('connection').hidden = false; $('connection').textContent = safeError(error);
    document.querySelectorAll('button').forEach(b => { b.disabled = true; });
  }
})();
