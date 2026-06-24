// --- Tab Switching Logic ---
const tabs = document.querySelectorAll('.tab-btn');
const contents = document.querySelectorAll('.tab-content');

tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        contents.forEach(c => c.classList.remove('active'));
        
        tab.classList.add('active');
        document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
    });
});

// --- Theme Toggling ---
const themeToggleBtn = document.getElementById('themeToggle');
const currentTheme = localStorage.getItem('theme') || 'light';
if (currentTheme === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
}

themeToggleBtn.addEventListener('click', () => {
    if (document.documentElement.getAttribute('data-theme') === 'dark') {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('theme', 'light');
    } else {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('theme', 'dark');
    }
});

// --- Quill RTE Custom Initialization ---
const Font = Quill.import('attributors/style/font');
Font.whitelist = ['Microsoft YaHei', 'SimSun', 'SimHei', 'sans-serif'];
Quill.register(Font, true);

const Size = Quill.import('attributors/style/size');
Size.whitelist = ['9px', '10px', '11px', '12px', '14px', '16px', '18px', '20px', '22px', '24px', '26px', '29px', '32px', '34px', '36px', '48px', '56px', '72px'];
Quill.register(Size, true);

// Custom LineHeight format
const Parchment = Quill.import('parchment');
const lineHeightConfig = { scope: Parchment.Scope.BLOCK, whitelist: ['1', '1.25', '1.5', '2'] };
const LineHeightClass = new Parchment.Attributor.Style('line-height', 'line-height', lineHeightConfig);
Quill.register(LineHeightClass, true);

const toolbarOptions = [
    [{ 'font': ['sans-serif', 'Microsoft YaHei', 'SimSun', 'SimHei'] }],
    [{ 'size': Size.whitelist }],
    ['bold', 'italic', 'underline', 'strike'],
    [{ 'color': [] }, { 'background': [] }],
    [{ 'list': 'ordered'}, { 'list': 'bullet' }],
    [{ 'align': [] }],
    [{ 'line-height': ['1', '1.25', '1.5', '2'] }], // Custom
    ['image', 'clean']
];

const quill = new Quill('#editor', {
    theme: 'snow',
    modules: {
        toolbar: { 
            container: toolbarOptions,
            handlers: {
                // Ensure Line-height button exists conceptually, handled mostly via CSS though standard Quill drops it without custom modules UI.
                // We will rely on standard formatting for native, or users can use default align/etc.
                'line-height': function(value) {
                    this.quill.format('line-height', value);
                }
            }
        }
    }
});

const toolbarContainer = document.querySelector('.ql-toolbar');
if(toolbarContainer) {
    const formatBtnContainer = document.createElement('span');
    formatBtnContainer.className = 'ql-formats';
    formatBtnContainer.innerHTML = `
        <select class="ql-line-height" title="行距">
            <option value="1.25" selected>1.25 (默认)</option>
            <option value="1">1</option>
            <option value="1.5">1.5</option>
            <option value="2">2</option>
        </select>
    `;
    toolbarContainer.appendChild(formatBtnContainer);

    const lhSelect = formatBtnContainer.querySelector('.ql-line-height');
    lhSelect.addEventListener('change', (e) => {
        quill.format('line-height', e.target.value);
    });
}

// Intercept paste event for base64 image support
quill.root.addEventListener('paste', function(e) {
    if (e.clipboardData && e.clipboardData.items) {
        for (let i = 0; i < e.clipboardData.items.length; i++) {
            let item = e.clipboardData.items[i];
            if (item.type.indexOf('image') !== -1) {
                e.preventDefault();
                let file = item.getAsFile();
                let reader = new FileReader();
                reader.onload = function(e) {
                    let range = quill.getSelection(true);
                    if (!range) range = { index: quill.getLength() };
                    quill.insertEmbed(range.index, 'image', e.target.result);
                };
                reader.readAsDataURL(file);
            }
        }
    }
});

// --- UI Elements ---
const excelFile = document.getElementById('excelFile');
const excelDropzone = document.getElementById('excelDropzone');
const excelFileName = document.getElementById('excelFileName');
const attachmentFile = document.getElementById('attachmentFile');

const valTotal = document.getElementById('valTotal');
const valSent = document.getElementById('valSent');
const valFailed = document.getElementById('valFailed');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');

const logContainer = document.getElementById('logContainer');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');

const btnStart = document.getElementById('startBtn');
const btnStop = document.getElementById('stopBtn');
const addAccountBtn = document.getElementById('addAccountBtn');
const senderAccountsContainer = document.getElementById('senderAccountsContainer');
const exportFailedBtn = document.getElementById('exportFailedBtn');
const failedCountBadge = document.getElementById('failedCountBadge');

// Export failed recipients handler
exportFailedBtn.addEventListener('click', async () => {
    try {
        const res = await fetch('/api/export-failed');
        const contentType = res.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            const data = await res.json();
            alert(data.message || '导出失败');
            return;
        }
        // Download the file
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `failed_recipients_${new Date().toISOString().slice(0,10)}.xlsx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        appendLog('[✓] 失败记录已导出为 Excel 文件');
    } catch (e) {
        appendLog(`[✗] 导出失败: ${e.message}`);
    }
});

addAccountBtn.addEventListener('click', () => {
    const row = document.createElement('div');
    row.className = 'form-row account-row';
    row.style.marginBottom = '8px';
    row.innerHTML = `
        <input type="text" class="account-name" placeholder="发件人别名(如:培训组)" style="width: 120px; flex: none;">
        <input type="text" class="account-email flex-1" placeholder="example@163.com">
        <input type="text" class="account-smtp flex-1" placeholder="SMTP授权码(非密码)">
    `;
    senderAccountsContainer.appendChild(row);
});

let trackingInterval = null;
let uploadedPaths = { excel: null, attachment: null };

// File Upload Handlers (Visual & API)
// NOTE: Do NOT add a click handler on excelDropzone — the <input> already covers
// the entire area via CSS absolute positioning. Adding excelFile.click() here would
// trigger DOUBLE native file dialogs in pywebview, causing a crash/flash.
excelFile.addEventListener('change', async (e) => {
    if(e.target.files.length > 0) {
        const file = e.target.files[0];
        excelFileName.textContent = file.name;
        await uploadFile(file, 'excel');
        // After successful upload, fetch column headers
        if (uploadedPaths.excel) {
            await fetchExcelColumns(uploadedPaths.excel);
        }
    }
});

async function fetchExcelColumns(filePath) {
    try {
        const res = await fetch(`/api/excel-columns?file_path=${encodeURIComponent(filePath)}`);
        const data = await res.json();
        if (data.status === 'success' && data.columns.length > 0) {
            const nameSelect = document.getElementById('nameColumn');
            const emailSelect = document.getElementById('emailColumn');
            
            // Use proper DOM manipulation instead of innerHTML+= to avoid reparse issues
            nameSelect.length = 0;
            emailSelect.length = 0;
            data.columns.forEach(col => {
                nameSelect.add(new Option(col, col));
                emailSelect.add(new Option(col, col));
            });
            
            // Smart auto-select: try to guess which column is name/email
            const cols = data.columns.map(c => c.toLowerCase());
            const nameGuess = cols.findIndex(c => c.includes('姓名') || c.includes('名字') || c.includes('name'));
            const emailGuess = cols.findIndex(c => c.includes('邮箱') || c.includes('email') || c.includes('mail'));
            if (nameGuess >= 0) nameSelect.selectedIndex = nameGuess;
            if (emailGuess >= 0) emailSelect.selectedIndex = emailGuess;
            document.getElementById('columnMappingRow').style.display = 'flex';
            appendLog(`[✓] 检测到 ${data.columns.length} 列: ${data.columns.join(', ')}`);
        }
    } catch (e) {
        appendLog(`[✗] 读取 Excel 列头失败: ${e.message}`);
    }
}

attachmentFile.addEventListener('change', async (e) => {
    if(e.target.files.length > 0) {
        await uploadFile(e.target.files[0], 'attachment');
    }
});

async function uploadFile(file, type) {
    const formData = new FormData();
    formData.append('file', file);
    try {
        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if(data.status === 'success') {
            uploadedPaths[type] = data.file_path;
            appendLog(`[✓] 成功上传载入: ${file.name}`);
        } else {
            appendLog(`[✗] 上传失败: ${data.message}`);
        }
    } catch (e) {
        appendLog(`[✗] 上传错误: ${e.message}`);
    }
}

// Appending Live Logs
function appendLog(msg) {
    const div = document.createElement('div');
    div.className = 'log-line';
    
    // colorize based on content
    if(msg.includes('✅') || msg.includes('[✓]')) div.style.color = 'var(--accent-emerald)';
    else if(msg.includes('❌') || msg.includes('[✗]')) div.style.color = 'var(--danger)';
    
    div.textContent = msg;
    logContainer.appendChild(div);
    logContainer.scrollTop = logContainer.scrollHeight;
}

// Start Campaign
btnStart.addEventListener('click', async () => {
    if(!uploadedPaths.excel) {
        alert("请先上传目标受众 Excel 文件！");
        return;
    }

    const accountRows = document.querySelectorAll('.account-row');
    let sendersList = [];
    accountRows.forEach(row => {
        const name = (row.querySelector('.account-name')?.value || '').trim();
        const email = row.querySelector('.account-email').value.trim();
        const smtp = row.querySelector('.account-smtp').value.trim();
        if (email && smtp) {
            sendersList.push(`${name}||||${email}----${smtp}`);
        }
    });
    const sendersText = sendersList.join('\n');
    
    if(!sendersText.trim()) {
        alert("请至少配置一个完整的发件人账号和SMTP授权码！");
        return;
    }
    
    const config = {
        mode: "new",
        excel_path: uploadedPaths.excel,
        attachment_path: uploadedPaths.attachment,
        subject: document.getElementById('emailSubject').value,
        html_content: quill.root.innerHTML,
        senders_text: sendersText,
        name_column: document.getElementById('nameColumn').value,
        email_column: document.getElementById('emailColumn').value,
        batch_size: parseInt(document.getElementById('batchSize').value) || 1,
        start_time: document.getElementById('startTime').value,
        end_time: document.getElementById('endTime').value,
        min_interval: document.getElementById('minInterval').value,
        max_interval: document.getElementById('maxInterval').value
    };

    try {
        const res = await fetch('/api/start', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(config)
        });
        const data = await res.json();
        
        if(data.status === 'success') {
            btnStart.disabled = true;
            btnStop.disabled = false;
            statusDot.className = 'dot active';
            statusText.textContent = '营销引擎运行中...';
            startTracking();
        } else {
            alert(data.message);
        }
    } catch (e) {
        appendLog(`[系统错误] ${e.message}`);
    }
});

// Stop Campaign
btnStop.addEventListener('click', async () => {
    try {
        await fetch('/api/stop', { method: 'POST' });
        btnStop.disabled = true;
    } catch(e) {
        appendLog(`[系统错误] ${e.message}`);
    }
});

let lastLogCount = 0;
// Track Status Function
function startTracking() {
    if(trackingInterval) clearInterval(trackingInterval);
    
    trackingInterval = setInterval(async () => {
        try {
            const res = await fetch('/api/status');
            const data = await res.json();
            
            // Update metrics
            const p = data.progress;
            valTotal.textContent = p.total;
            valSent.textContent = p.sent;
            valFailed.textContent = p.failed;
            
            // Progress Bar
            if(p.total > 0) {
                const percent = Math.floor((p.current / p.total) * 100);
                progressBar.style.width = `${percent}%`;
                progressText.textContent = `${percent}%`;
            }

            // Show/update export button when there are failures
            if (data.failed_count > 0) {
                exportFailedBtn.style.display = 'inline-flex';
                failedCountBadge.textContent = data.failed_count;
            }

            // Sync Logs
            if(data.logs.length > lastLogCount) {
                const newLogs = data.logs.slice(lastLogCount);
                newLogs.forEach(lg => appendLog(lg));
                lastLogCount = data.logs.length;
            }

            // Detect Engine Stop
            if(!data.is_running && btnStart.disabled) {
                clearInterval(trackingInterval);
                btnStart.disabled = false;
                btnStop.disabled = true;
                statusDot.className = 'dot online';
                statusText.textContent = '队列结束或中止';
            }
        } catch(e) {
            console.error("Status fetch error");
        }
    }, 1500);
}

// --- Resume (断点续传) banner wiring ---
const resumeBanner = document.getElementById('resumeBanner');
const resumeBannerDetail = document.getElementById('resumeBannerDetail');
const resumeBtn = document.getElementById('resumeBtn');
const discardBtn = document.getElementById('discardBtn');

function hideResumeBanner() {
    if (resumeBanner) resumeBanner.style.display = 'none';
}

async function checkResumableTask() {
    try {
        const res = await fetch('/api/checkpoint');
        const cp = await res.json();
        if (cp.resumable) {
            const subjectPart = cp.subject ? `「${cp.subject}」` : '';
            resumeBannerDetail.textContent =
                `任务${subjectPart}：已发送 ${cp.sent} / ${cp.total}，失败 ${cp.failed}，更新于 ${cp.updated_at}`;
            resumeBanner.style.display = 'flex';
            // Reflect restored progress on the dashboard right away
            valTotal.textContent = cp.total;
            valSent.textContent = cp.sent;
            valFailed.textContent = cp.failed;
            if (cp.total > 0) {
                const percent = Math.floor((cp.sent / cp.total) * 100);
                progressBar.style.width = `${percent}%`;
                progressText.textContent = `${percent}%`;
            }
        }
    } catch (e) {
        // No checkpoint endpoint / no task — ignore silently
    }
}

if (resumeBtn) {
    resumeBtn.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ mode: 'resume' })
            });
            const data = await res.json();
            if (data.status === 'success') {
                hideResumeBanner();
                btnStart.disabled = true;
                btnStop.disabled = false;
                statusDot.className = 'dot active';
                statusText.textContent = '营销引擎运行中（续传）...';
                lastLogCount = 0;
                startTracking();
            } else {
                alert(data.message);
            }
        } catch (e) {
            appendLog(`[系统错误] ${e.message}`);
        }
    });
}

if (discardBtn) {
    discardBtn.addEventListener('click', async () => {
        if (!confirm('确定放弃上次未完成的任务吗？已发送的进度记录将被清除（已投递的邮件不受影响）。')) return;
        try {
            await fetch('/api/clear-checkpoint', { method: 'POST' });
            hideResumeBanner();
            valTotal.textContent = 0;
            valSent.textContent = 0;
            valFailed.textContent = 0;
            progressBar.style.width = '0%';
            progressText.textContent = '0%';
        } catch (e) {
            appendLog(`[系统错误] ${e.message}`);
        }
    });
}

// Initial status check
fetch('/api/status').then(res => res.json()).then(data => {
    if(data.is_running) {
        btnStart.disabled = true;
        btnStop.disabled = false;
        statusDot.className = 'dot active';
        statusText.textContent = '营销引擎运行中...';
        startTracking();
    } else {
        statusDot.className = 'dot online';
        // Only offer resume when nothing is currently running
        checkResumableTask();
    }
}).catch(e => {
    appendLog("无法连接到本地守护进程...");
});
