import os
import sys
import time
import datetime
import shutil
import logging
import threading
import uvicorn
import webview
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks, File, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from core.engine import MarketingEngine

# --- Path Resolution for PyInstaller ---
def get_base_path():
    """Get the path where bundled resources (static, templates) are located.
    When frozen by PyInstaller, resources are in sys._MEIPASS temp dir.
    When running from source, resources are in the script's directory."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_runtime_dir():
    """Get the directory where the exe is located (for user data like logs, uploads, .env).
    When running from source, this is the script's directory."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

base_dir = get_base_path()       # Where bundled assets live
runtime_dir = get_runtime_dir()  # Where user data lives (next to .exe)

# Initialize dotenv - load from runtime directory (next to .exe)
env_path = os.path.join(runtime_dir, '.env')
env_example_path = os.path.join(runtime_dir, '.env.example')

# Auto-create .env from example if it doesn't exist
if not os.path.exists(env_path):
    # Copy bundled .env.example to runtime dir
    bundled_example = os.path.join(base_dir, '.env.example')
    if os.path.exists(bundled_example):
        shutil.copy2(bundled_example, env_path)
    elif os.path.exists(env_example_path):
        shutil.copy2(env_example_path, env_path)

load_dotenv(env_path)

# Set up directories in runtime location (next to .exe)
log_dir = os.path.join(runtime_dir, "logs")
upload_dir = os.path.join(runtime_dir, "uploads")
state_dir = os.path.join(runtime_dir, "state")  # 断点续传检查点目录
os.makedirs(log_dir, exist_ok=True)
os.makedirs(upload_dir, exist_ok=True)
os.makedirs(state_dir, exist_ok=True)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(log_dir, "email_app.log"), encoding="utf-8")
    ]
)

logger = logging.getLogger("AutoEmailApp")
engine = MarketingEngine(logger)
# 注册断点续传检查点路径，并恢复上次未完成任务的进度（供 UI 提示继续）
engine.set_checkpoint_path(os.path.join(state_dir, "checkpoint.json"))
engine.set_blacklist_path(os.path.join(state_dir, "blacklist.txt"))
blacklist_path = os.path.join(state_dir, "blacklist.txt")
engine.load_checkpoint_into_memory()


def parse_senders(senders_text):
    """解析账户池文本为 senders 列表。格式：别名||||邮箱----授权码（别名可省略）。"""
    senders = []
    for line in senders_text.strip().split("\n"):
        if "----" not in line:
            continue
        display_name = ""
        email_pwd_part = line
        if "||||" in line:
            display_name, email_pwd_part = line.split("||||", 1)
            display_name = display_name.strip()
        email, pwd = email_pwd_part.split("----", 1)
        email, pwd = email.strip(), pwd.strip()
        if not (email and pwd):
            continue
        if not display_name:
            display_name = email.split("@")[0] if "@" in email else email
        is_qq = "qq.com" in email.lower()
        senders.append({
            "email": email,
            "password": pwd,
            "name": display_name,
            "smtp_server": "smtp.qq.com" if is_qq else "smtp.163.com",
            "smtp_port": 587 if is_qq else 465,
        })
    return senders

app = FastAPI(title="AutoEmail AI Marketing")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = os.path.join(base_dir, "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """API for uploading Excel, Image or PDF attachments"""
    try:
        file_location = os.path.join(upload_dir, file.filename)
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)
        return JSONResponse(content={"status": "success", "file_path": file_location})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/api/config")
def get_env_config():
    """Reads configured Accounts from .env file to show to UI"""
    senders = []
    # Dynamic reading of ACCOUNT_X_EMAIL and so on.
    for i in range(1, 20):
        email = os.getenv(f"ACCOUNT_{i}_EMAIL")
        if email:
            senders.append({
                "email": email,
                "password": os.getenv(f"ACCOUNT_{i}_PASSWORD", ""),
                "name": os.getenv(f"ACCOUNT_{i}_NAME", "发件人"),
                "smtp_server": os.getenv("SMTP_SERVER_QQ") if "qq.com" in email else os.getenv("SMTP_SERVER_163", "smtp.qq.com"),
                "smtp_port": os.getenv("SMTP_PORT_QQ", 587) if "qq.com" in email else os.getenv("SMTP_PORT_163", 25)
            })
    return JSONResponse(content={"senders": senders, "total_accounts_loaded": len(senders)})

@app.get("/api/excel-columns")
async def get_excel_columns(file_path: str):
    """Read uploaded Excel headers and return column names for user mapping"""
    import pandas as pd
    try:
        df = pd.read_excel(file_path, nrows=0)
        columns = [str(c) for c in df.columns.tolist()]
        return JSONResponse(content={"status": "success", "columns": columns})
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "message": f"无法读取 Excel 表头: {str(e)}"})

@app.post("/api/start")
async def start_campaign(request: dict, background_tasks: BackgroundTasks):
    config = request

    if engine.is_running:
        return JSONResponse(status_code=400, content={"status": "error", "message": "任务已在运行中"})

    # 断点续传：mode=resume 时直接用磁盘上保存的 config 继续，无需前端重传账号/正文
    mode = config.get("mode", "new")
    if mode == "resume":
        resume_cfg = engine.get_resume_config()
        if not resume_cfg:
            return JSONResponse(status_code=400, content={"status": "error", "message": "没有可继续的任务，请重新发起。"})
        background_tasks.add_task(engine.run_campaign, resume_cfg, True)
        return JSONResponse(content={"status": "success", "message": "已继续上次未完成的任务"})

    senders = parse_senders(config.get("senders_text", ""))
    if not senders:
        return JSONResponse(status_code=400, content={"status": "error", "message": "账户池配置格式不正确或为空，请确保使用 邮箱----授权码 格式。"})

    config['senders'] = senders
    
    # Pass column mapping to engine
    config['name_column'] = config.get('name_column', '')
    config['email_column'] = config.get('email_column', '')

    background_tasks.add_task(engine.run_campaign, config, False)
    return JSONResponse(content={"status": "success", "message": "任务已启动"})

def __get_senders_sync():
    senders = []
    for i in range(1, 20):
        email = os.getenv(f"ACCOUNT_{i}_EMAIL")
        if email:
            senders.append({
                "email": email,
                "password": os.getenv(f"ACCOUNT_{i}_PASSWORD", ""),
                "name": os.getenv(f"ACCOUNT_{i}_NAME", "发件人"),
                "smtp_server": os.getenv("SMTP_SERVER_QQ") if "qq.com" in email else os.getenv("SMTP_SERVER_163", "smtp.163.com"),
                "smtp_port": os.getenv("SMTP_PORT_QQ", 587) if "qq.com" in email else os.getenv("SMTP_PORT_163", 25)
            })
    return senders

@app.post("/api/stop")
def stop_campaign():
    engine.stop()
    return JSONResponse(content={"status": "success", "message": "停止指令已发送"})

@app.get("/api/status")
def get_status():
    return JSONResponse(content={
        "is_running": engine.is_running,
        "progress": engine.progress,
        "logs": engine.logs,
        "failed_count": len(engine.failed_recipients),
        "uncertain_count": len(engine.uncertain_recipients),
        "resendable_count": len(engine.failed_recipients) + len(engine.uncertain_recipients),
    })

@app.get("/api/checkpoint")
def get_checkpoint():
    """返回是否存在可继续的未完成任务，供前端显示「继续上次任务」横幅。"""
    return JSONResponse(content=engine.checkpoint_summary())

@app.post("/api/clear-checkpoint")
def clear_checkpoint():
    """放弃上次未完成任务，清除磁盘检查点与内存进度。"""
    if engine.is_running:
        return JSONResponse(status_code=400, content={"status": "error", "message": "任务正在运行，无法清除进度。"})
    engine._clear_checkpoint()
    engine.progress = {"total": 0, "sent": 0, "failed": 0, "uncertain": 0, "current": 0,
                       "eta_seconds": None, "rate_per_min": None, "current_account": ""}
    engine.failed_recipients = []
    engine.uncertain_recipients = []
    return JSONResponse(content={"status": "success", "message": "已清除上次任务进度"})

@app.get("/api/export-failed")
def export_failed():
    """Export failed recipients as a downloadable Excel file."""
    failed = engine.get_failed_recipients()
    if not failed:
        return JSONResponse(content={"status": "error", "message": "暂无失败记录可导出"})
    
    import pandas as pd
    df = pd.DataFrame(failed, columns=["name", "email", "reason", "detail", "time", "sender_used"])
    df.columns = ["姓名", "邮箱", "失败原因", "详细错误", "发送时间", "使用的发件账号"]
    
    export_path = os.path.join(upload_dir, "failed_recipients.xlsx")
    df.to_excel(export_path, index=False, engine='openpyxl')
    
    return FileResponse(
        export_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"failed_recipients_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )

@app.post("/api/test-send")
def test_send(request: dict):
    """群发前先发一封测试邮件到指定邮箱，验证排版与占位符替换。"""
    senders = parse_senders(request.get("senders_text", ""))
    if not senders:
        return JSONResponse(status_code=400, content={"status": "error", "message": "请先配置至少一个发件账号。"})
    test_email = (request.get("test_email") or "").strip()
    if not engine.sender_core.validate_email(test_email):
        return JSONResponse(status_code=400, content={"status": "error", "message": "测试收件邮箱格式不正确。"})

    recipient = {"name": request.get("test_name", "测试用户"), "email": test_email}
    status, msg = engine.sender_core.send_single(
        sender=senders[0],
        recipient=recipient,
        email_index=1,
        html_content=request.get("html_content", ""),
        subject=request.get("subject", "（测试）"),
        attachment_path=request.get("attachment_path"),
        add_unsubscribe=bool(request.get("add_unsubscribe", True)),
    )
    engine.sender_core.close_all_connections()
    if status == "success":
        return JSONResponse(content={"status": "success", "message": f"测试邮件已发送至 {test_email}"})
    elif status == "uncertain":
        return JSONResponse(content={"status": "success", "message": f"已尝试发送至 {test_email}，但连接中断、状态未知，请到收件箱确认。"})
    return JSONResponse(status_code=400, content={"status": "error", "message": f"测试发送失败：{msg}"})


@app.post("/api/resend-failed")
async def resend_failed(background_tasks: BackgroundTasks):
    """仅对上次失败/待确认的收件人发起一次重发（复用上次任务配置）。"""
    if engine.is_running:
        return JSONResponse(status_code=400, content={"status": "error", "message": "任务正在运行中。"})
    targets = engine.failed_recipients + engine.uncertain_recipients
    if not targets:
        return JSONResponse(status_code=400, content={"status": "error", "message": "暂无失败或待确认的收件人可重发。"})
    base_cfg = engine.active_config or engine.get_resume_config()
    if not base_cfg:
        return JSONResponse(status_code=400, content={"status": "error", "message": "找不到上次任务配置，无法重发。请重新发起任务。"})

    cfg = dict(base_cfg)
    cfg["recipients_override"] = [{"name": t["name"], "email": t["email"]} for t in targets]
    background_tasks.add_task(engine.run_campaign, cfg, False)
    return JSONResponse(content={"status": "success", "message": f"已对 {len(targets)} 个失败/待确认收件人发起重发"})


@app.get("/api/blacklist")
def get_blacklist():
    try:
        if os.path.exists(blacklist_path):
            with open(blacklist_path, "r", encoding="utf-8") as f:
                return JSONResponse(content={"status": "success", "content": f.read()})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    return JSONResponse(content={"status": "success", "content": ""})


@app.post("/api/blacklist")
def save_blacklist(request: dict):
    """保存退订/黑名单（每行一个邮箱），发送时自动排除。"""
    try:
        with open(blacklist_path, "w", encoding="utf-8") as f:
            f.write(request.get("content", ""))
        count = len(engine.load_blacklist())
        return JSONResponse(content={"status": "success", "message": f"已保存，黑名单共 {count} 个邮箱"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8123)

if __name__ == '__main__':
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()
    
    # Optional delay to wait for fastAPI to bind to port
    time.sleep(1)
    
    webview.create_window('云邮宝', 'http://127.0.0.1:8123', width=1280, height=850, 
                          background_color='#eff1f5', text_select=True)
    webview.start()
