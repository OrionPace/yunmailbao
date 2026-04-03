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
const currentTheme = localStorage.getItem('theme') || 'dark';
if (currentTheme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
}

themeToggleBtn.addEventListener('click', () => {
    if (document.documentElement.getAttribute('data-theme') === 'light') {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('theme', 'dark');
    } else {
        document.documentElement.setAttribute('data-theme', 'light');
        localStorage.setItem('theme', 'light');
    }
});

// --- Quill RTE Custom Initialization ---
const Font = Quill.import('attributors/style/font');
Font.whitelist = ['microsoft-yahei', 'simsun', 'simhei', 'sans-serif'];
Quill.register(Font, true);

const Size = Quill.import('attributors/style/size');
Size.whitelist = ['12px', '14px', '16px', '18px', '20px', '24px', '32px'];
Quill.register(Size, true);

// Custom LineHeight format
const Parchment = Quill.import('parchment');
const lineHeightConfig = { scope: Parchment.Scope.BLOCK, whitelist: ['1', '1.25', '1.5', '2'] };
const LineHeightClass = new Parchment.Attributor.Style('line-height', 'line-height', lineHeightConfig);
Quill.register(LineHeightClass, true);

const toolbarOptions = [
    [{ 'font': ['sans-serif', 'microsoft-yahei', 'simsun', 'simhei'] }],
    [{ 'size': ['12px', '14px', '16px', '18px', '20px', '24px', '32px'] }],
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

// Add drop down list for custom line height to toolbar via DOM since Quill doesn't provide default UI for custom attributes easily:
const toolbarContainer = document.querySelector('.ql-toolbar');
if(toolbarContainer) {
    const formatBtnContainer = document.createElement('span');
    formatBtnContainer.className = 'ql-formats';
    formatBtnContainer.innerHTML = `
        <select class="ql-line-height" title="行距">
            <option selected>1.25 (默认)</option>
            <option value="1">1</option>
            <option value="1.5">1.5</option>
            <option value="2">2</option>
        </select>
    `;
    toolbarContainer.appendChild(formatBtnContainer);
}

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

let trackingInterval = null;
let uploadedPaths = { excel: null, attachment: null };

// File Upload Handlers (Visual & API)
excelDropzone.addEventListener('click', () => excelFile.click());
excelFile.addEventListener('change', async (e) => {
    if(e.target.files.length > 0) {
        const file = e.target.files[0];
        excelFileName.textContent = file.name;
        await uploadFile(file, 'excel');
    }
});

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

    const sendersText = document.getElementById('senderAccounts').value;
    if(!sendersText.trim()) {
        alert("请至少配置一个发件人账号池内容！");
        return;
    }
    
    const config = {
        excel_path: uploadedPaths.excel,
        attachment_path: uploadedPaths.attachment,
        subject: document.getElementById('emailSubject').value,
        html_content: quill.root.innerHTML,
        senders_text: sendersText,
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
    }
}).catch(e => {
    appendLog("无法连接到本地守护进程...");
});
