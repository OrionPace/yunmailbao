# 云邮宝 YunMailBao 0.2.1 阶段交接

更新日期：2026-10-12。接手时先读本文，再读 `docs/PRODUCT.md`。这是事实快照，不是新一轮需求讨论。

本轮接续：用户将候选版本从 0.3.0 改为 **0.2.1**，源码、锁文件、升级测试与发布路径已统一。预览已嵌入本地字体的 data URL，保留空 sandbox、禁止脚本/表单/外部网络；47 项 UI 检查现在包含 iframe 字体实际加载及 CSP 断言。92 项后端回归及源码 WebView2（版本 0.2.1）复验通过。以下构建/安装状态将在实际验收后更新。

## 当前停止点

**源码改动和本机回归已形成检查点；0.2.1 尚未构建、安装、推送或发布。** 用户要求先完成当前小阶段，再压缩上下文、读取交接后继续。因此本轮不启动安装验证，也不推送以免触发远端构建。

- 本地目录：`D:\New_Project\auto_email`，禁止改名或移动。
- 产品：中文“云邮宝”，英文 **YunMailBao**；下一版本 `0.2.1` 候选。
- 原 GitHub 仓库已直接改名为 `https://github.com/OrionPace/yunmailbao`，不是另建仓库。改名前后 ID 均为 `R_kgDOR4hCHA`，`origin` 已更新。
- 分支：`master`。本轮源码检查点：`f294bf69ad85fe2234856c0696df26c43ae430e5`。文档收尾会另有本地提交，以 `git log` 为准。
- 远端仍停在旧版已推送的 `9e214ec`；**0.2.1 的 GitHub CI 尚未运行**，不要沿用旧 CI 成功结论。
- `release/` 只有 `0.2.0/`，用户实际安装也仍是 0.2.0。本轮没有覆盖用户安装或数据。
- `.build/candidate` 可能仍是旧 0.2.0 缓存：下一轮必须完整重建，**不能用 `-PackageOnly` 拼一个标成 0.2.1 的旧程序**。
- 临时源码验收服务 `127.0.0.1:8132`、PID `20996` 已关闭。之前的 PID `28192` 也不再运行；PID 会复用，下一轮先核对命令行，不按旧 PID 盲目杀进程。

## 已批准的设计与红线

- 保留简洁浅色/深色、工作台/任务记录/使用帮助，以及四步邮件工作流。README 只讲目标用户、用途、使用，不放 AI 作品叙述、影响力目标或商业访谈。
- 编辑器空白、默认思源黑体 14px；附件入口左上角、统一薄 Lucide 图标。沿用 Quill 1.3.6，不升级框架、不新增 AI、表格编辑器或公网服务。
- 本轮单附件，支持 PDF/DOCX/XLSX/PPTX，不新增多附件或个性化附件。
- 删除 `<人名>` 的 UI 入口和新介绍；旧草稿打开时转现行变量，旧冻结任务保留原快照及内部兼容。
- QQ/163 默认隐藏 SMTP 参数，自定义显示高级参数；旧账号编辑留空授权码不丢凭据，不悄悄覆盖旧连接设置。
- 普通邮件不用先选“通知/推广”或填来源；更多选项中“邮件包含商业广告”映射现有 `purpose`，开启后 AD + 强制退订。旧 `source_note` 保留兼容但不必填、不在 UI 展示。
- 正常均匀发送，默认 6/min、200 次/日是软件预算，不是服务商额度或防垃圾箱证明。未知提交不自动重试，不轮换账号绕开限流。
- 主程序 `YunYouBao.exe`、正式 AppId `{A3859DE6-BCF4-4CCE-9D4C-816A51BF2648}`、默认安装目录 `%LOCALAPPDATA%\Programs\YunYouBao`、数据目录 `%LOCALAPPDATA%\YunYouBao` 均保持稳定。
- **不发送真实邮件，不读取/公布真实授权码，不删除旧 `dist/`、`dist_release/`、`.env` 或实际数据库，不强制重写 Git 历史。** 历史凭据风险由持有人轮换；此轮没有代为处理。

## 已实现的代码

| 子系统 | 实际实现与关键位置 |
| --- | --- |
| 编辑器 | `static/index.html/script.js/style.css`：两排工具栏、字体/字号原生控件、颜色、格式、列表/缩进、撤销重做、选区保持、附件 chip；默认 HTML 外层 `data-yunmailbao-body`，草稿重开不会重复套层。 |
| 帮助 | 同上：4 个主流程节点 + 3 个结果分支，摘要、悬停/聚焦详情、点击固定、Esc/关闭、操作跳转、搜索/折叠正文、触屏及减少动画适配。 |
| 账号 | `core/service.py`：QQ/163 新默认 SSL/465；现有 DPAPI 和非持久内存凭据保留。前端高级参数折叠、有效选择恢复、明确空选择不被自动勾上。 |
| 选择偏好 | `core/store.py` 新增 `preferences(key,payload)`，主库版本仍是 1，属于 additive 建表。只保存账号 IDs，不存密码；旧备份没有新表也可恢复，live/demo 按数据库隔离。 |
| 附件 | `core/service.py` 检查格式、Office 包/XML/宏/展开体积；`core/email_sender.py` 新可选 `attachment_filename` 传原名，按扩展名生成 MIME；任务创建、测试和正式发送均传原名。 |
| 节奏 | `core/engine.py`：全任务采用最慢所选账号的间隔；普通连续可重试 4xx 全任务 30/120 秒退避，第三次暂停；认证/策略错误也暂停，不自动换账号。等待写入 `recipients.next_attempt`。 |
| 明确长限流 | 返回 `4.7.28` 时立即暂停；`preferences` 的 `smtp_pause_until:<email_key>` 保存 600 秒期限，`reserve()` 和新任务/重开均遵守。demo 不拖慢等待，但保留相应模拟暂停。 |
| 版本/打包 | `main.py`、`pyproject.toml`、`uv.lock` 均是 0.2.1；`/api/data` 返回 main 的 VERSION，不再误报 0.2.0。安装标识/目录不变，publisher/link/manifest 使用新英文名；构建和 CI 要求字体及许可在包内。 |

新的偏好接口使用已有会话鉴权和模式头：

```text
GET /api/account-selection -> {account_ids: [...], configured: false|true}
PUT /api/account-selection  body {account_ids: [...]} -> {account_ids: [...], configured: true}
```

`account_selection()` 返回 None 表示从未配置，返回空数组表示用户明确未选；不能混淆。只有“未配置且唯一可用账号”才自动选。桌面保持隐私模式和动态端口，**不要改用 localStorage 或固定端口实现重开保存**。

字体是 Adobe 官方 tag `2.005R` 的完整简体子集 WOFF2，没有自行修改/再裁剪，也没加 FontTools：

- `static/fonts/SourceHanSansCN-VF.ttf.woff2`：7,711,988 字节，SHA256 `f971e3bff46f76b49e1d5510556c2297c618ec4b491a295a4e741cdd38257799`。
- `static/fonts/SourceHanSans-LICENSE.txt`：4,463 字节，SHA256 `fcac737e761ec63dbfbdce11030a1780161920d80315edba9c8beff1c2bac5a2`。
- `.gitattributes` 对字体/原许可使用 `-text`，不要让 Windows 换行转换破坏已核验原文；来源与字体条款见 `THIRD_PARTY_NOTICES.md`。

## 本轮验证结果与证据

全部使用虚构数据/SMTP 替身，没有实际投递。

| 验证 | 2026-10-12 实际结果 | 工件/入口 |
| --- | --- | --- |
| 单元/接口/跨进程 | **92 项通过**，21.589 秒；包括 Windows DPAPI 两进程读取、偏好、旧备份、Office/MIME、状态与时钟退避。 | `python -B -m unittest discover -s tests -q` |
| 完整浏览器流程 | 10 accepted、0 failed、0 uncertain，覆盖筛选/预览/模拟测试/暂停续发/失败与待确认人工重发/导出；1440/1024/390 无横向溢出，页面错误 0。 | `tests/browser/workflow.cjs`；`tests/artifacts/browser/report.json` |
| 专项 UI | **47/47 通过**；字体实际加载、格式选区、草稿/旧变量、4 类附件、简化账号、选择与空选择、live/demo、帮助与触屏、浅/深及减少动画；该脚本禁止发信/建任务请求。 | `tests/browser/product-ui.cjs`、`product-fixtures.py`；`tests/artifacts/browser/product-ui-report.json` |
| 源码 WebView2 | 版本 0.2.1、编辑器 1、logo 自然宽 1254、32 行 demo、renderer edgechromium、errors=[]；JS 桥只有 import_legacy/open_data_folder/save_export。 | `tests/desktop_smoke.py`；`tests/artifacts/desktop-report.json` |
| 静态检查 | `node --check`、Git staged whitespace 检查、升级脚本 AST 解析通过。 | 安装/升级脚本只验证了语法，**尚未运行**。 |

新截图已原样复制到 `docs/screenshots/07-editor.png`、`08-account-simple.png`、`09-help-detail.png`、`10-help-mobile.png`，README 已引用 07–09。旧 01–06 保留。测试报告是被 gitignore 排除的本机证据，下一次运行会覆盖。

已修复、不要回退的具体问题：

- Snow 主题会吞掉自定义 select，字体/字号变成空白：初始化前临时移出 4 个原生 select，完成后放回。
- 首次启动先读到空账号，再载 demo 后不再恢复选择：demo 载入后重新读取偏好，仍尊重明确空选择。
- 撤销/重做将 `{0,5}` 选区变 `{5,0}`：现在保存并按文本长度钳制、恢复选区。
- `onfocusout` 属性没能关闭帮助详情：改为真实 `focusout` 事件监听，47 项复验通过。
- 时钟替身测试结束后用真实日期读到了另一日的 quota：断言也使用同一 fake clock，不是把预算保护去掉。

## 明确未完成与优先检查

1. **预览字体已修复并复验。** 本地字体读取一次并缓存为 data URL，隔离 srcdoc 使用 @font-face + `font-src data:`，空 sandbox 及其他禁止策略不变。专项 UI 已确认 iframe 字体 loaded、字体族和 CSP；字体仅用于本地预览，不嵌入发出的邮件。
2. 完整重建 0.2.1，再做冻结 EXE 与实际安装后的字体、资源和账号两次重开检查。准备好的 `tests/browser/installed.cjs` 本轮**没有对 0.2.1 执行**。
3. 隔离 `0.2.0 -> 0.2.1` 安装升级与卸载；准备好的 `tests/installer_upgrade.py` 本轮**没有执行**。它复制旧 manifest 中的程序文件到测试候选，使用独立 AppId/快捷方式/目录，种入虚构账号、旧草稿及未启动冻结任务，检查原名参数/DPAPI/快照/目录/卸载留数据，不触发任何发送。
4. 升级 harness 默认旧来源是用户当前 0.2.0 安装目录，逐文件校验 `release/0.2.0/build-manifest.json`。**在 harness 完成前不要先覆盖用户安装为 0.2.1**，否则默认旧来源不再匹配。若来源已变，另提供真实 0.2.0 candidate，用 `--old-candidate` 指定；不要改 manifest 骗过校验。
5. 复核构建清单、源码提交、实际文件和缺失 WebView2/目录/运行中拦截等场景；干净 Windows、本版原生保存对话框人工验收、真实收件箱投递均未完成。
6. 再分组提交/推送并看新仓库的 0.2.1 CI。原 workflow 已接入专项 UI 与字体资源检查；远端目前没有这次验证结果。
7. 更新 PRODUCT/运行指南/HANDOFF 的实际结果，再决定是否覆盖用户安装。原生第三方许可未决项仍在 THIRD_PARTY_NOTICES：proxy-tools 条款冲突、pydantic-core 编译/传递依赖清单、VC/UCRT 来源和分发授权等。**不能自动发布正式 GitHub Release 或声称已清除分发风险**。

## 接续命令

以下是下一轮执行入口，不是本轮已经运行的安装步骤。先检查状态，不重做仓库改名，也不重开产品访谈。

```powershell
Set-Location D:\New_Project\auto_email
git status --short
git log -5 --oneline
git remote -v
uv sync --locked
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q
```

需要 UI 验证时，一终端启动隔离服务，另一终端运行脚本；8132 被占用则两处一致换端口，不关闭未知进程：

```powershell
$env:YUNYOUBAO_DATA_DIR = Join-Path $PWD '.runtime/validation-v021'
.\.venv\Scripts\python.exe -B main.py --headless --demo --port 8132
```

```powershell
$env:YUNYOUBAO_TEST_URL = 'http://127.0.0.1:8132'
$env:BROWSER_EXECUTABLE = Join-Path $env:LOCALAPPDATA 'ms-playwright/chromium-1223/chrome-win64/chrome.exe'
node tests/browser/workflow.cjs
node tests/browser/product-ui.cjs
.\.venv\Scripts\python.exe -B tests/desktop_smoke.py
```

如 browser executable 已更新，查真实安装路径或在 `tests/browser` 执行 `npx playwright install chromium`，不要把失效路径当产品故障。现有 Playwright 为 1.64.0，Python 3.12 x64，pywebview 6.1，Inno Setup 7.1.0 在 `.tools/InnoSetup/ISCC.exe`。

源码/测试通过并提交后再构建，随后先做隔离升级，再考虑实际安装：

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File scripts/build_release.ps1
.\.venv\Scripts\python.exe -B tests/installer_upgrade.py
.\.venv\Scripts\python.exe -B tests/installer_ui_smoke.py release/0.2.1/云邮宝-0.2.1-setup.exe
# 安装后校验，必须使用与该包匹配的 manifest；当前用户安装还是 0.2.0 时不能提前跑此行
node tests/browser/installed.cjs "$env:LOCALAPPDATA/Programs/YunYouBao/YunYouBao.exe" release/0.2.1/build-manifest.json
```

## 工作树与交接纪律

- 原有删除：整棵 `.codex/skills/remotion-best-practices/`、根 `AGENTS.md`、旧 `remotion/yunyoubao-tutorial/`；原有未跟踪：`.agents/`、`skills-lock.json`。**不是本轮删除，不恢复、不提交、不用 git add -A。** 全程用明确文件列表暂存。
- 不因 `git status` dirty 就 reset。构建 manifest 如实记录 dirty；这可能来自上述用户原有删除，并不表示要替用户处理。
- 使用 `apply_patch` 编辑；GitHub 操作优先 `gh`，不 force push、不改写提交历史。通常终端需正常 `require_escalated` 审批；审批失败不能绕过。
- `.runtime/`、`tests/artifacts/`、`.build/`、`release/` 是忽略的本地产物，不随源码提交。不要把旧 dist 或个人 .env 放进 candidate。
- 分工 Agent 的内容已经整合到文件，不依赖它们继续运行；旧 agent/session ID 可能失效。压缩后从本文和 Git 恢复，不从记忆猜状态或重复并行编辑同一文件。
- 当前阶段停止在“源码回归检查点”，不是整个 0.2.1 目标完成。下一轮从上面的未完成清单开始。
