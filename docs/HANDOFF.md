# 云邮宝 YunMailBao 0.2.1 阶段交接

更新日期：2026-10-12。先读本文，再读 `docs/PRODUCT.md`。用户最新指定版本 **0.2.1**，取代此前计划的 0.3.0。

## 当前检查点

**源码、完整候选构建、本机隔离升级/卸载与原生 WebView2 验收通过。未覆盖用户安装，未创建正式 Release。**

- 工作目录 `D:\New_Project\auto_email` 不改名。仓库已更名为 https://github.com/OrionPace/yunmailbao，origin 正确，不重复改名。
- 分支 master。前期提交 f294bf6、d239ace；本轮版本/预览修复 **d15efd6**。后续验收文档提交以 git log 为准。
- 工件 `release/0.2.1/云邮宝-0.2.1-setup.exe`，清单及 SHA256SUMS 同目录；旧 `release/0.2.0/` 保留。
- 候选来源提交 d15efd6，manifest 如实记录 dirty（用户原有删除）。其后仅调整验收脚本与文档，不改候选应用代码。
- 安装器 SHA256：`6a20caee2b76fd1a8a07395bdf3c6359b14bade653fa65a8d709cd4d70a62147`。
- manifest SHA256：`68e1818d2d2f45206d3fd6942ea819c9fcf8e95c79bde313e6177371c1367ac4`。
- 用户正式安装仍是 0.2.0；升级测试确认实际 EXE 哈希未变，不读取真实名单或授权码。
- 临时源码服务 8132 已关闭（当时 PID 32016，不能按旧 PID 盲目杀进程）。原生窗口和隔离升级进程全部结束。
- 推送/Checks 的实际结果由本文末尾记录补充，不沿用旧 CI 成功结论。

## 已实现与设计红线

- 保留简洁浅/深主题、工作台/任务记录/帮助、四步工作流；README 只讲谁用、用途和使用。
- Quill 1.3.6，初始空白、思源黑体 14px、两排薄 Lucide 工具栏、附件左上角；不加 AI、新框架或表格编辑器。
- 单附件 PDF/DOCX/XLSX/PPTX，原名进入 MIME；检查 Office 包格式、路径、展开体积、宏和 XML，不声称病毒扫描。
- 删除 UI 中的 <人名> 入口；旧草稿打开转当前变量，旧冻结任务快照和内部兼容保留。
- QQ/163 新默认 SSL/465，参数折叠；自定义和旧非标准配置可编辑。编辑留空授权码保留凭据。
- 商业广告开关映射 purpose，开启后 AD + 强制退订；旧 source_note 仅内部兼容，不必填。
- 默认 6/min、200 次/日是软件尝试预算，不是邮箱官方额度或防垃圾箱证明。全任务均匀节奏，不用多账号规避限流。
- 普通连续可重试 4xx 全任务 30/120 秒退避，第三次暂停；认证/策略拒绝暂停，不自动换账号。
- 明确 4.7.28 保存 600 秒账号等待期限，重开/新任务仍约束；未知提交不自动重试。
- EXE `YunYouBao.exe`、正式 AppId `{A3859DE6-BCF4-4CCE-9D4C-816A51BF2648}`、安装 `%LOCALAPPDATA%\Programs\YunYouBao`、数据 `%LOCALAPPDATA%\YunYouBao` 均不变。
- 不真实发信，不读取/公布真实凭据，不删除旧 dist、dist_release、.env 或用户库，不改写 Git 历史。

关键位置：static/index.html/script.js/style.css（UI）、core/service.py（偏好/附件/预览）、core/store.py（additive preferences）、core/email_sender.py（MIME）、core/engine.py（节奏状态）、main.py（版本/API）。

账号选择只存 IDs，live/demo 独立：
```text
GET /api/account-selection -> {account_ids: [...], configured: false|true}
PUT /api/account-selection {account_ids: [...]} -> {account_ids: [...], configured: true}
```
未配置和明确 [] 不同；仅未配置且唯一可用账号才自动选。桌面隐私模式和动态端口保留，不用 localStorage 或固定端口解决重开保存。

**预览字体修复完成。** loadPreviewFont() 只读本地 WOFF2，缓存 data URL；srcdoc 使用 @font-face 和 font-src data:。空 sandbox、禁脚本/表单/外部请求保留，不加 allow-same-origin。读失败可重试，不将字体嵌入发出的邮件。

字体为 Adobe tag 2.005R 原始完整简体子集，未修改/裁剪：
- static/fonts/SourceHanSansCN-VF.ttf.woff2，7,711,988 字节；SHA256 f971e3bff46f76b49e1d5510556c2297c618ec4b491a295a4e741cdd38257799。
- static/fonts/SourceHanSans-LICENSE.txt，4,463 字节；SHA256 fcac737e761ec63dbfbdce11030a1780161920d80315edba9c8beff1c2bac5a2。
- .gitattributes 保持原许可/字体 -text。第三方许可未决没有因此解除。

## 验收证据

全部虚构数据/替身，无实际投递。报告为忽略的本地产物，重跑会覆盖。

| 检查 | 实际结果 |
| --- | --- |
| 后端回归 | 92 项，21.627 秒，OK；DPAPI 两进程、旧备份、偏好、Office/MIME、预算退避。 |
| 浏览器流程 | 10 accepted、0 failed、0 uncertain；1440/1024/390 无溢出，page_errors=[]；tests/artifacts/browser/report.json。 |
| 专项 UI | 47/47，包含隔离 iframe 字体 loaded、字体族和 CSP 断言；product-ui-report.json。 |
| 源码 WebView2 | 0.2.1、空编辑器、logo、32 demo、errors=[]；桥仅 import_legacy/open_data_folder/save_export。 |
| 完整构建 | PyInstaller 6.19.0、Python 3.12.12 x64、Inno 7.1.0；916 文件；未用 PackageOnly。 |
| 冻结及隔离安装 WebView2 | 916 文件大小/哈希一致，编辑器与预览字体 loaded、账号两次私密窗口重开恢复；tests/artifacts/installed/report.json。 |
| 0.2.0 → 0.2.1 升级 | 账号/DPAPI、旧草稿、未启动冻结任务、自选目录保留；卸载留测试数据、实际安装未改；tests/artifacts/upgrade/report.json。 |
| 安装器 UI | 中文许可、可选目录；打开后取消，没有覆盖实际安装。 |

源码截图 docs/screenshots/07–10 保留；README 引用 07–09。

不要回退的细节：
- Snow 初始化前暂移出自定义 select，完成后还原，避免字体/字号控件消失。
- demo 首次加载后重新读取选择，仍尊重明确空选择。
- undo/redo 选区保存钳制；帮助用真实 focusout 事件。
- fake clock 的 quota 日期断言也用 fake clock，不取消预算保护。
- 升级 harness 的 httpx Headers.update 用字典，不支持关键字参数。
- Windows 子进程结束可能 signalCode 有值而 exitCode 为 null；两者判断，exit 监听先于 kill。
- 原生字体检查等待 iframe CSP meta 解析后再查 fonts，否则初始 about:blank 会误报。修复后冻结 EXE 与隔离安装分别通过。

## 下一步

1. 核对本轮推送与 Checks 状态；远端失败先修，不将本机成功当远端成功。
2. 干净 Windows 首装、缺失 WebView2、运行中升级拦截、本版原生保存对话框人工验收仍未完成。
3. 处理 THIRD_PARTY_NOTICES 未决：proxy-tools MIT/BSD 冲突、pydantic-core 编译/传递依赖清单、VC/UCRT 来源及分发授权。不能自动 tag/正式 Release。
4. 用户实际安装未覆盖；可体验候选 EXE。覆盖实际安装前说明并保留数据备份，不删除历史成品。
5. 不做真实 SMTP/收件箱实验，不将 accepted 等同于投递/主收件箱，不重启商业访谈或 SaaS 规划。

复跑入口：
```powershell
uv sync --locked
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q
$env:YUNYOUBAO_DATA_DIR = Join-Path $PWD '.runtime/validation-v021'
.\.venv\Scripts\python.exe -B main.py --headless --demo --port 8132
```
另一个终端：
```powershell
$env:YUNYOUBAO_TEST_URL = 'http://127.0.0.1:8132'
$env:BROWSER_EXECUTABLE = Join-Path $env:LOCALAPPDATA 'ms-playwright/chromium-1223/chrome-win64/chrome.exe'
node tests/browser/workflow.cjs
node tests/browser/product-ui.cjs
.\.venv\Scripts\python.exe -B tests/desktop_smoke.py
node tests/browser/installed.cjs .build/candidate/YunYouBao/YunYouBao.exe release/0.2.1/build-manifest.json
.\.venv\Scripts\python.exe -B tests/installer_upgrade.py
.\.venv\Scripts\python.exe -B tests/installer_ui_smoke.py release/0.2.1/云邮宝-0.2.1-setup.exe
```

升级测试要求独立 AppId 无注册且测试 installed 目录不存在。默认旧来源为真实 0.2.0 安装；若已覆盖需用 --old-candidate 指定真实旧原件，不能改 manifest 绕过校验。测试 data 保留，复跑复用虚构记录。完整重建用 scripts/build_release.ps1，同版本产物自动归档，不覆写旧版本。

## 工作树纪律

- 原有删除：.codex/skills/remotion-best-practices/**、根 AGENTS.md、旧 remotion/yunyoubao-tutorial/**；原有未跟踪 .agents/、skills-lock.json。不是本轮删除，不恢复、不提交。
- git add 明确列文件，不用 -A；不 reset、不 force push。编辑用 apply_patch；GitHub 优先 gh。
- .runtime/、tests/artifacts/、.build/、release/ 为忽略本地产物；不提交 .env、名单或库。
- 不依赖旧 subagent/session ID，从本文、Git 和实际文件核对。
