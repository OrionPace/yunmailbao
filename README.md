# 云邮宝 AutoEmail

云邮宝是一个本地优先的邮件发送控制台，基于 **FastAPI + pywebview + Quill** 构建。它面向培训通知、会议邀约、名单邮件等需要批量发送但仍希望保留人工可控性的场景，支持 Excel 收件人导入、富文本正文、附件、多发件账号轮换、发送窗口、随机抖动、进度监控和失败记录导出。

## 当前定位

- 桌面版：默认用 `uv run main.py` 启动本地服务并打开 Windows 桌面窗口。
- 服务端部署：可用 `uvicorn main:app` 只启动 FastAPI 服务，适合部署到阿里云 ECS。
- 产品化方向：公网部署前需要补登录鉴权、CORS 白名单、上传限制和任务审计。

## 运行环境

- Python 3.12+
- uv
- Windows 桌面版需要 WebView2 运行环境

安装依赖：

```bash
uv sync
```

配置账号：

```bash
cp .env.example .env
```

在 `.env` 中填写真实 SMTP 邮箱和授权码。不要提交 `.env`。

## 本地启动

```bash
uv run main.py
```

应用会启动本地 FastAPI 服务并打开桌面窗口。

## 服务器启动

服务器上不要启动 pywebview，直接运行：

```bash
uv run uvicorn main:app --host 127.0.0.1 --port 8123
```

完整阿里云 ECS、域名、备案、DNS、Nginx、HTTPS 和 EXE 打包流程见 [docs/deployment-guide.md](docs/deployment-guide.md)。

## Windows EXE 打包

```bat
build.bat
```

输出目录为：

```text
dist\云邮宝\
```

`build/` 和 `dist/` 是生成物，已加入 `.gitignore`，不再提交到仓库。

## 演示操作视频

项目内已包含云邮宝操作教程的 Remotion 工程：

```bash
cd remotion/yunyoubao-tutorial
npm install
npm run studio
```

渲染完整视频：

```bash
npm run render
```

默认输出为 `remotion/yunyoubao-tutorial/out/yunyoubao-tutorial.mp4`。

## 测试资料

测试相关文件放在 `tests/`：

```bash
uv run python tests/create_sample_recipients.py
uv run python tests/manual_email_smoke.py
```

`manual_email_smoke.py` 会读取 `.env` 中的真实 SMTP 配置，执行前请确认不会误发。

## 项目结构

```text
core/                  邮件发送与队列引擎
static/                前端界面
assets/                图标资源
docs/                  部署与运维文档
tests/                 手动测试脚本和测试资料生成脚本
main.py                FastAPI 应用与桌面启动入口
auto_email.spec        PyInstaller 打包配置
build.bat              Windows 一键打包脚本
```

## 合规提醒

本项目用于正常通知、邀约和名单邮件发送。请勿用于垃圾邮件、钓鱼、骚扰或任何违法用途。公网部署时务必增加登录鉴权和访问控制。
