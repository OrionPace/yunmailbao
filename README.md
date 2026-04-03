# 智能邮件营销终端 (AutoEmail App)

![Deep Ocean Emerald](https://img.shields.io/badge/Theme-Deep%20Ocean%20Emerald-10b981?style=for-the-badge)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![uv](https://img.shields.io/badge/UV-⚡️-purple?style=for-the-badge)

本系统是基于 **FastAPI + PyWebView** 构建的 Windows 本地化富文本邮件营销工具。
使用极致轻量的高颜值玻璃拟物化前端方案（深海翡翠主题），有效实现了针对大量受众（如公共卫生研究院学员培训通知等）避免触发发件箱环境“过热”的反垃圾分发逻辑。

## 🎯 核心特性
- **本地化桌面集成**：不需要任何外部服务器即点即用，拥有原生的窗口外观。
- **发信防刷机制 (核心矛术)**：支持多账号池自动轮询、发送时间窗口智能卡点、时间随机抖动发送、占位符 `<人名>` 替换与不可见动态哈希注入来规避重复内容被封杀。
- **现代化极简流体 UI**：玻璃态 (Glassmorphism) 毛玻璃+极光辉光暗色面板，内置 Quill 富文本。
- **机密隔离**：通过 `.env` 分离硬编码信息，不再有账号泄漏风险。

---

## 🛠️ 安装与运行指引

本项目已被全面重构为使用最新包管理标准 `uv` 部署。

### 1. 配置 SMTP 账号
首先，将项目里的 `.env.example` 复制或重命名为 `.env`。
然后，在里头填入你真实的 QQ / 163 邮箱和应用专用的**SMTP授权码**。
```dotenv
# .env 文件示范
ACCOUNT_1_EMAIL=your_email@qq.com
ACCOUNT_1_PASSWORD=你的SMTP授权码
ACCOUNT_1_NAME=广东省公共卫生研究院
```

### 2. 启动应用
仅需运行以下命令，程序将自动拉起本地服务并弹出一个绝美的 Windows 独立应用窗口！

```bash
# 激活环境并启动入口
uv run main.py
```

## ⚠️ 免责声明
> 本系统的随机停顿、哈希注入、多账号智能轮换，初衷是使得正常的研学邀请邮件不被误打入垃圾箱。请勿将本软件工具用于发送非法骚扰、网络钓鱼等灰黑产用途。
