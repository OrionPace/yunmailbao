import os
import time
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

# Initialize dotenv
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/email_app.log", encoding="utf-8") if os.path.exists("logs") else logging.StreamHandler()
    ]
)
if not os.path.exists("logs"):
    os.makedirs("logs", exist_ok=True)

logger = logging.getLogger("AutoEmailApp")
engine = MarketingEngine(logger)

app = FastAPI(title="AutoEmail AI Marketing")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("static", exist_ok=True)
os.makedirs("uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_index():
    return FileResponse("static/index.html")

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """API for uploading Excel, Image or PDF attachments"""
    try:
        file_location = f"uploads/{file.filename}"
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

@app.post("/api/start")
async def start_campaign(request: dict, background_tasks: BackgroundTasks):
    config = request
    
    senders_text = config.get("senders_text", "")
    senders = []
    lines = senders_text.strip().split("\n")
    for line in lines:
        if "----" in line:
            email, pwd = line.split("----", 1)
            email, pwd = email.strip(), pwd.strip()
            if email and pwd:
                smtp_srv = "smtp.qq.com" if "qq.com" in email.lower() else "smtp.163.com"
                smtp_pt = 587 if "qq.com" in email.lower() else 465 # commonly 465 is SSL logic or 25
                senders.append({
                    "email": email,
                    "password": pwd,
                    "name": "通知部",
                    "smtp_server": smtp_srv,
                    "smtp_port": smtp_pt
                })
    
    if not senders:
        return JSONResponse(status_code=400, content={"status": "error", "message": "账户池配置格式不正确或为空，请确保使用 邮箱----授权码 格式。"})
    
    config['senders'] = senders
    
    if engine.is_running:
         return JSONResponse(status_code=400, content={"status": "error", "message": "任务已在运行中"})
         
    background_tasks.add_task(engine.run_campaign, config)
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
        "logs": engine.logs
    })

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8123)

if __name__ == '__main__':
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()
    
    # Optional delay to wait for fastAPI to bind to port
    time.sleep(1)
    
    webview.create_window('智能营销中心 - Deep Ocean', 'http://127.0.0.1:8123', width=1280, height=850, 
                          background_color='#0B1320', text_select=True)
    webview.start()
