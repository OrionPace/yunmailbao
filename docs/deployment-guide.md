# 云邮宝 YunMailBao 本地运行与演练

**本版不支持公网部署。** 不要将应用端口暴露到公网或局域网，不放行旧版 8123，也不以 Nginx/域名/HTTPS 代替登录与权限设计。会话令牌及 Host/Origin 校验只服务于本机边界。

[源码](https://github.com/OrionPace/yunmailbao)与[发布入口](https://github.com/OrionPace/yunmailbao/releases)使用新仓库名，本地工作目录仍为 `auto_email`。当前准备 `0.2.1` 候选，不代表安装或公开分发许可已经验收。

## Windows 桌面

安装前核对随包 `SHA256SUMS.txt` 和 `build-manifest.json`。当前候选为未签名构建。

- 默认按当前用户安装到 `%LOCALAPPDATA%\Programs\YunYouBao`，目录页可选其他当前用户可写目录，升级沿用上次目录，不请求管理员权限。
- 主程序为 `YunYouBao.exe`；正式 AppId 保持 `{A3859DE6-BCF4-4CCE-9D4C-816A51BF2648}`。
- 默认数据根目录为 `%LOCALAPPDATA%\YunYouBao`，`live\` / `demo\` 分别保存 `yunyoubao.sqlite3` 和受控文件。英文更名不改变路径或迁移数据。
- 需要 [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)；缺失时安装器提示官方获取途径，不自动下载安装。
- 升级或卸载前关闭应用并备份。安装目录与数据目录分离；更改安装目录不迁移数据，卸载保留用户数据。

授权码在应用内配置，不编辑安装目录 `.env`。Windows 记住授权码使用当前用户 DPAPI；备份不包含保存的授权码，跨设备或恢复后需重新填写。DPAPI 不加密名单、正文或整个数据库。

账号勾选通过 `GET/PUT /api/account-selection` 保存到后端 SQLite `preferences`，只存账号 ID，不存授权码。原生窗口保持隐私模式，桌面端口动态分配，不能依赖 localStorage 跨重开恢复勾选。源码跨进程与浏览器偏好检查已通过；实际安装版重开与升级仍待验收，详见 [阶段交接](HANDOFF.md)。

## 源码演示

需要 Python 3.12+ 和 uv。在仓库根目录 PowerShell 执行：

```powershell
uv sync --locked
$env:YUNYOUBAO_DATA_DIR = Join-Path $env:TEMP "YunYouBao-demo"
uv run python main.py --demo
```

无桌面窗口的浏览器演示：

```powershell
uv run python main.py --headless --demo --port 8131
# 已有虚拟环境时
.\.venv\Scripts\python.exe main.py --headless --demo --port 8131
```

访问 `http://127.0.0.1:8131`。headless 固定监听 loopback；`--port` 不影响桌面动态端口。不设置数据环境变量时源码使用 `.runtime\dev`。`YUNYOUBAO_DATA_DIR` 可覆盖数据根目录，不改变正式/演示隔离。

`--demo` 仅设初始模式，界面可切换正式模式；演练保持演示且不输入真实账号。demo 模拟服务器接收、拒绝和提交结果不明，不真实投递。

## 远程 demo 演练

仅用于开发核对，不是服务器产品部署。远端准备 Python/uv 环境后，在仓库目录使用独立数据目录，并保持 loopback：

```sh
uv sync --locked
YUNYOUBAO_DATA_DIR="$HOME/.local/share/yunyoubao-demo" uv run python main.py --headless --demo --port 8131
```

本机另一终端建立 SSH 隧道：

```sh
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8131:127.0.0.1:8131 user@server
```

本机访问 `http://127.0.0.1:8131`，结束后关闭服务和隧道。两端端口均不得公开监听，不新增应用端口安全组或防火墙放行规则；端口占用时选择两端一致的新端口，不覆盖既有服务。

远程演练使用浏览器下载，不能据此验收 Windows 原生保存对话框。非 Windows 不支持 DPAPI 持久保存授权码，本节只做 demo。

## 检查与构建

```powershell
uv run python -B -m unittest discover -s tests -v
uv run python -B tests/manual_email_smoke.py
.\build.bat
```

单元测试与手动烟测使用替身/模拟传输，不读取根 `.env`。2026-10-12 已通过 92 项回归、47 项专项 UI 检查、完整浏览器模拟链及源码 WebView2 烟测；0.2.1 已完整构建，冻结 EXE 的 916 个文件、字体、账号重开及隔离升级/卸载验收通过。

构建需要 Python 3.12 x64、uv 和 `.tools\InnoSetup\ISCC.exe` 中的 Inno Setup 7.1.0。版本由 `pyproject.toml` 的 `project.version` 读取，须与 `main.py` 保持一致；本轮目标为 `0.2.1`。

构建按锁文件新建 `.build\candidate\YunYouBao\` 和 `.build\work\`，写入来源清单后生成以下候选目标，不从旧 `dist\` / `dist_release\` / `dist_candidate\` 拼包：

- `release\0.2.1\云邮宝-0.2.1-setup.exe`
- `release\0.2.1\build-manifest.json`
- `release\0.2.1\SHA256SUMS.txt`

`release\0.2.0\` 保留；同版本旧产物进入对应版本的 `archive/<时间>/`，不覆盖归档。`scripts/build_release.ps1 -PackageOnly` 只接受有完整来源清单且哈希匹配的候选。隔离安装烟测应使用独立 AppId、快捷方式名称及安装目录，不改变正式安装身份。

官方 `2.005R` 字体及 OFL 原文保存在 `static/fonts/`，来源和 SHA-256 见 [第三方声明](../THIRD_PARTY_NOTICES.md)。本机隔离安装已逐文件校验字体与原文，并确认编辑器和隔离预览中的字体实际加载。

构建成功不等于 tag 或 GitHub Release 已发布。0.2.0 → 0.2.1 隔离升级、卸载留数据、原生两次重开、中文许可及目录选择已通过，实际用户安装仍未覆盖。干净 Windows、缺失 WebView2、运行中升级拦截和本版原生导出对话框仍待验收；原有第三方许可未决项未解决前不自动公开发布。完整状态见 [阶段交接](HANDOFF.md)。

旧数据仅经应用只读导入供核对，不迁移授权码，不能直接续发；先保留备份，不删除原目录。策略依据及本轮待核验项见 [产品说明](PRODUCT.md)。
