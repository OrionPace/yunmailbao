# 云邮宝部署与域名上线手册

更新时间：2026-04-25

这份文档按“第一次把项目部署到服务器并绑定域名”的路径写。当前项目本质是本地桌面工具：`main.py` 同时包含 FastAPI 后端和 pywebview 桌面窗口。部署到阿里云 ECS 时，不要运行桌面窗口，而是用 `uvicorn main:app` 只启动 Web 服务。

## 0. 先确定上线目标

推荐分两阶段走：

1. 低风险演练：先用 ECS 公网 IP 访问，例如 `http://服务器IP:8123`，确认代码、端口、安全组、环境变量和日志目录都正常。
2. 域名正式访问：再购买或绑定域名，配置 DNS、备案、HTTPS 和反向代理。

如果 ECS 是中国内地节点，并且要用域名对外访问，必须完成 ICP 备案。阿里云官方说明：使用中国内地阿里云资源时，需要通过备案流程；如果资源在中国香港或海外节点，则通常不需要 ICP 备案。参考：阿里云 ICP 备案流程与所需资料文档。

## 1. 免费域名和低成本域名怎么选

### 方案 A：完全不买域名，先用公网 IP

成本最低，适合你现在“走完整开发部署流程”的试验阶段。

步骤：

1. 阿里云 ECS 控制台复制公网 IP。
2. ECS 安全组放行端口：先放行 `22`、`80`、`443`，如果临时直连测试再放行 `8123`。
3. 服务器运行 `uvicorn main:app --host 0.0.0.0 --port 8123`。
4. 浏览器访问 `http://公网IP:8123`。

缺点：没有好记的地址，没有 HTTPS 证书体验，也不适合长期公开。

### 方案 B：免费二级域名

GitHub Pages 和 Cloudflare Pages 都提供免费平台子域名，例如 `项目名.github.io` 或 `项目名.pages.dev`。但它们主要适合静态站点。云邮宝有 FastAPI 后端、文件上传、日志和 SMTP 发送，不是纯静态站。

可用方式：

1. 只部署产品介绍页、文档页或演示静态页面到 GitHub Pages / Cloudflare Pages。
2. 后端仍部署在 ECS，用 IP 或另一个域名访问 API。

不建议把当前项目直接塞进 Pages，因为动态接口不会运行。

### 方案 C：低成本自有域名

如果 ECS 在中国内地，建议优先在阿里云中国站或其他支持备案的国内注册商购买域名，后续备案最省心。阿里云域名注册流程通常是：创建信息模板、查询域名、下单支付、完成实名认证。

如果只是海外节点或学习用，不走中国内地备案，可以考虑 Cloudflare Registrar。Cloudflare 官方说明它按注册局成本价收费、无加价，并包含 DNS、SSL、WHOIS 信息隐藏等能力。注意：海外注册商购买的域名未必适合中国内地备案，请以阿里云备案系统当时校验结果为准。

实用建议：

1. 试验阶段：先不买域名，使用公网 IP。
2. 想练完整“域名 + DNS + HTTPS”：买便宜后缀，首年低价即可，但一定看续费价。
3. 要部署到阿里云中国内地 ECS：优先选择能顺利备案的域名注册商和后缀。

## 2. 阿里云 ECS 部署步骤

以下以 Ubuntu 服务器为例。

### 2.1 准备服务器

1. 登录阿里云 ECS 控制台。
2. 创建或使用已有实例，系统建议 Ubuntu 22.04/24.04 LTS。
3. 安全组放行：
   - `22/tcp`：SSH 登录。
   - `80/tcp`：HTTP。
   - `443/tcp`：HTTPS。
   - `8123/tcp`：仅临时调试用，正式部署后关闭。
4. SSH 登录服务器：

```bash
ssh root@你的服务器公网IP
```

### 2.2 安装运行环境

```bash
apt update
apt install -y git curl nginx
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

### 2.3 拉取项目并安装依赖

```bash
mkdir -p /opt/apps
cd /opt/apps
git clone 你的仓库地址 auto_email
cd auto_email
uv sync
```

如果你还没有远程仓库，先在本机执行：

```bash
git remote add origin 你的仓库地址
git push -u origin main
```

### 2.4 配置环境变量

```bash
cp .env.example .env
nano .env
```

填入真实 SMTP 配置。不要把 `.env` 提交到 Git。

### 2.5 先用临时命令验证

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8123
```

本地浏览器访问：

```text
http://你的服务器公网IP:8123
```

验证通过后按 `Ctrl+C` 停止，继续配置 systemd。

### 2.6 配置 systemd 常驻服务

创建服务文件：

```bash
nano /etc/systemd/system/auto-email.service
```

写入：

```ini
[Unit]
Description=AutoEmail FastAPI Service
After=network.target

[Service]
WorkingDirectory=/opt/apps/auto_email
ExecStart=/root/.local/bin/uv run uvicorn main:app --host 127.0.0.1 --port 8123
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

启动：

```bash
systemctl daemon-reload
systemctl enable --now auto-email
systemctl status auto-email
```

查看日志：

```bash
journalctl -u auto-email -f
```

## 3. 绑定域名

### 3.1 购买或准备域名

阿里云中国站购买域名的大致流程：

1. 域名控制台创建信息模板。
2. 等待实名认证通过。
3. 查询目标域名是否可注册。
4. 下单支付。
5. 在域名控制台确认域名状态正常。

### 3.2 ICP 备案

如果使用中国内地 ECS：

1. 进入阿里云 ICP 备案系统。
2. 选择首次备案或新增网站，系统会自动判断。
3. 准备身份证明、域名信息、服务器信息、网站负责人信息。
4. 按流程完成真实性核验。
5. 等待初审、管局审核。
6. 备案号下来后再开放域名访问。

没有备案前，把域名解析到中国内地 ECS 通常会被接入商拦截。

### 3.3 DNS 解析

在阿里云云解析 DNS 添加记录：

| 主机记录 | 记录类型 | 记录值 |
| --- | --- | --- |
| `@` | `A` | ECS 公网 IP |
| `www` | `A` 或 `CNAME` | ECS 公网 IP 或根域名 |

保存后等待 DNS 生效。可以用下面命令检查：

```bash
nslookup 你的域名
```

## 4. Nginx 反向代理

创建配置：

```bash
nano /etc/nginx/sites-available/auto-email
```

写入，把域名换成自己的：

```nginx
server {
    listen 80;
    server_name example.com www.example.com;

    client_max_body_size 30m;

    location / {
        proxy_pass http://127.0.0.1:8123;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用：

```bash
ln -s /etc/nginx/sites-available/auto-email /etc/nginx/sites-enabled/auto-email
nginx -t
systemctl reload nginx
```

访问：

```text
http://你的域名
```

## 5. HTTPS

低成本选择：

1. 使用阿里云免费/低成本 SSL 证书并在 Nginx 配置证书。
2. 使用 Certbot 申请 Let's Encrypt 证书。
3. 如果域名托管在 Cloudflare，可使用 Cloudflare DNS/CDN 和其自动证书能力。

Certbot 示例：

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d example.com -d www.example.com
```

成功后测试：

```bash
certbot renew --dry-run
```

## 6. 正式公开前必须补的安全项

当前应用适合本地使用。公开到公网前，建议至少补齐：

1. 登录鉴权：否则任何知道域名的人都能打开控制台。
2. CORS 白名单：把 `allow_origins=["*"]` 改为你的正式域名。
3. 上传限制：限制文件后缀、大小、文件名，避免任意文件落盘。
4. SMTP 密钥保护：`.env` 只放服务器本地，权限设为 `600`。
5. 发送审计：保留任务 ID、操作者、发送时间、失败原因。
6. 频率限制：公开接口需要限流，避免被滥用。

## 7. Windows EXE 打包

本项目仍然支持打包成本地 Windows 桌面版。

本机执行：

```bat
build.bat
```

或手动执行：

```bash
uv sync --dev
uv run pyinstaller auto_email.spec --noconfirm --clean
```

输出目录：

```text
dist\云邮宝\
```

交付时复制整个 `dist\云邮宝\` 文件夹。第一次运行会自动根据 `.env.example` 创建 `.env`，你需要在目标机器上填写真实 SMTP 授权码。

## 8. 推荐执行清单

1. 本机确认功能正常：`uv run main.py`。
2. 推送代码到远程 Git 仓库。
3. ECS 拉取代码并用 `uvicorn main:app` 运行。
4. 用公网 IP 验证。
5. 决定是否购买域名。
6. 如果是中国内地 ECS，完成域名实名认证和 ICP 备案。
7. 配置 DNS A 记录。
8. 配置 Nginx 反向代理。
9. 配置 HTTPS。
10. 补登录鉴权、CORS 白名单和上传安全。
11. 最后再执行 `build.bat` 输出 Windows EXE。

## 参考资料

- 阿里云：ICP备案流程，https://www.alibabacloud.com/help/zh/icp-filing/icp-filing-regulations-for-guangdong
- 阿里云：ICP备案所需资料，https://help.aliyun.com/zh/icp-filing/basic-icp-service/user-guide/required-materials
- 阿里云：添加网站解析，https://www.alibabacloud.com/help/zh/doc-detail/2933070.html
- 阿里云：如何注册域名，https://www.alibabacloud.com/help/zh/dws/user-guide/how-to-register-a-domain-name
- GitHub Docs：GitHub Pages custom domains，https://docs.github.com/articles/about-custom-domains-for-github-pages-sites
- Cloudflare Docs：Pages custom domains，https://developers.cloudflare.com/pages/configuration/custom-domains/
- Cloudflare Registrar，https://www.cloudflare.com/products/registrar/
