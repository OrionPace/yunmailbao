# 本地运行与远程演练

**本版不支持公网部署。** 不要将应用端口暴露到公网或局域网，不放行旧版 8123，也不以 Nginx/域名/HTTPS 代替登录与权限设计。启动会话令牌及 Host/Origin 校验服务于本机边界，不是公网用户认证。

当前主要交付形态为 Windows 当前用户安装 EXE；`0.2.0` 的工件测试仍在进行，以下是当前实现的运行方式，不是已完成安装验收的声明。

## Windows 桌面

使用已验收版本的安装器前，核对随包 `SHA256SUMS.txt` 和 `build-manifest.json`。当前候选为未签名构建。

- 当前用户安装位置：`%LOCALAPPDATA%\Programs\YunYouBao`，无需管理员权限。
- 数据根目录：`%LOCALAPPDATA%\YunYouBao`，分别使用 `live\` / `demo\`。
- 需要 Microsoft Edge WebView2 Runtime；缺失时安装器提示官方获取途径，不自动下载安装。
- 升级/卸载前关闭应用，卸载保留用户数据。安装和卸载行为仍须在实际候选工件上验收。

授权码在应用内配置，不编辑安装目录 `.env`。Windows 记住授权码使用当前用户 DPAPI；跨设备或恢复备份后应重新填写。DPAPI 不保护名单、正文和整个数据库，数据目录与备份不能当公开附件分发。

## 源码演示

仓库根目录 PowerShell：

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

浏览器访问 `http://127.0.0.1:8131`。headless 固定监听 loopback；桌面模式选择动态本地端口，`--port` 不影响桌面窗口。不设置数据环境变量时源码使用 `.runtime\dev`。

`--demo` 仅设初始模式，界面可切换正式模式；演练保持演示且不输入真实账号。demo 模拟服务器接收、拒绝和提交结果不明，不投递真实邮件。

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

本机访问 `http://127.0.0.1:8131`，演练结束关闭服务和隧道。两端 8131 均不得公开监听；不新增应用端口安全组或防火墙放行规则。本机端口占用时先关闭已有演练进程或选择一致的新端口，不覆盖既有服务。

远程演练无 Windows 原生保存对话框，使用浏览器下载；不能据此验收桌面原生导出。非 Windows 不支持 DPAPI 持久保存授权码，本节只使用 demo，不做真实 SMTP。

## 核验与构建

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B tests/manual_email_smoke.py
.\build.bat
```

烟测只使用临时目录和模拟传输，无真实发送入口，也不读取根 `.env`。构建脚本按锁文件新建 `dist_candidate\YunYouBao\`，验证 candidate 后输出 `release\云邮宝-0.2.0-setup.exe`、构建清单和 SHA256；需要 Python 3.12 x64、uv 和 `.tools\InnoSetup\ISCC.exe` 中的 Inno Setup 7.1.0。不使用旧 `dist\` / `dist_release\` 交付目录。

构建生成成功也不能替代干净机器首装、升级、卸载、WebView2、离线编辑、数据恢复与原生导出的验收。第三方随包许可尚待核验；未完成前不宣称可公开发布。

旧版数据仅经应用只读导入供核对，不能直接续发；先保留备份，不删除原目录。完整范围及待验收项见 [README](../README.md) 和 [产品说明](PRODUCT.md)。
