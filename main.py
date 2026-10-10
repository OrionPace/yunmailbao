import argparse
import contextlib
import ctypes
import hashlib
import json
import os
import secrets
import shutil
import socket
import sqlite3
import sys
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.service import MAX_BACKUP, MAX_UPLOAD, ProductService

VERSION = "0.2.0"
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def data_directory():
    if os.environ.get("YUNYOUBAO_DATA_DIR"):
        return Path(os.environ["YUNYOUBAO_DATA_DIR"]).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(os.environ["LOCALAPPDATA"]) / "YunYouBao"
    return Path(__file__).resolve().parent / ".runtime" / "dev"


def create_app(data_root=None, transport_factory=None, initial_mode="live", desktop=False, allowed_hosts=None):
    root = Path(data_root or data_directory()).resolve()
    services = {"live": ProductService(root / "live", transport_factory=transport_factory),
                "demo": ProductService(root / "demo", demo=True)}
    token = secrets.token_urlsafe(32)
    hosts = set(allowed_hosts or {"127.0.0.1", "localhost"})

    @contextlib.asynccontextmanager
    async def lifespan(application):
        yield
        for service in services.values():
            service.engine.shutdown()

    application = FastAPI(title="云邮宝", version=VERSION, docs_url=None, redoc_url=None,
                          openapi_url=None, lifespan=lifespan)
    application.state.services = services
    application.state.token = token
    application.state.initial_mode = initial_mode
    application.state.desktop = desktop

    @application.middleware("http")
    async def local_boundary(request, call_next):
        hostname = request.url.hostname
        origin = request.headers.get("origin")
        expected_origin = str(request.base_url).rstrip("/")
        if hostname not in hosts or (origin and origin != expected_origin):
            return JSONResponse({"detail": "不允许的请求来源。"}, status_code=403)
        if request.url.path.startswith("/api/"):
            if not secrets.compare_digest(request.headers.get("authorization", ""), "Bearer " + token):
                return JSONResponse({"detail": "本地会话已失效，请重新打开应用。"}, status_code=401)
            mode = request.headers.get("x-yunyoubao-mode", initial_mode)
            if mode not in services:
                return JSONResponse({"detail": "运行模式不正确。"}, status_code=400)
            request.state.service = services[mode]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if request.url.path == "/":
            response.headers["Cache-Control"] = "no-store"
            response.headers["Content-Security-Policy"] = ("default-src 'self'; script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; "
                "connect-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        return response

    @application.exception_handler(ValueError)
    async def value_error(request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @application.exception_handler(KeyError)
    async def missing(request, error):
        return JSONResponse({"detail": "请求的记录不存在，请刷新后重试。"}, status_code=404)

    @application.exception_handler(sqlite3.Error)
    async def database_error(request, error):
        return JSONResponse({"detail": "无法保存或读取本机数据；发送已停止，请检查磁盘与权限。"}, status_code=503)

    application.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    if (BASE_DIR / "assets" / "branding").exists():
        application.mount("/brand", StaticFiles(directory=BASE_DIR / "assets" / "branding"), name="brand")

    @application.get("/")
    def index():
        config = {"token": token, "version": VERSION, "initial_mode": application.state.initial_mode,
                  "desktop": application.state.desktop}
        page = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
        script = "<script>window.YUNYOUBAO=" + json.dumps(config, ensure_ascii=False) + ";</script>"
        return HTMLResponse(page.replace("</head>", script + "</head>"))

    @application.get("/api/accounts")
    def accounts(request: Request):
        return {"accounts": request.state.service.accounts()}

    @application.post("/api/accounts")
    def save_account(request: Request, data: dict):
        return request.state.service.save_account(data)

    @application.delete("/api/accounts/{identifier}")
    def delete_account(identifier: str, request: Request):
        request.state.service.delete_account(identifier)
        return {"status": "success"}

    @application.post("/api/imports")
    async def upload_import(request: Request, file: UploadFile = File(...)):
        content = await file.read(MAX_UPLOAD + 1)
        return request.state.service.import_file(file.filename or "", content)

    @application.get("/api/demo/import")
    def demo_import(request: Request):
        return request.state.service.demo_import()

    @application.post("/api/imports/{identifier}/preview")
    def preview_import(identifier: str, request: Request, data: dict):
        return request.state.service.preview_import(identifier, data)

    @application.post("/api/attachments")
    async def upload_attachment(request: Request, file: UploadFile = File(...)):
        item = request.state.service.add_file(file.filename or "", await file.read(MAX_UPLOAD + 1), "attachment")
        return {"attachment_id": item["id"], "filename": item["filename"], "size": item["size"]}

    @application.post("/api/preview-email")
    def preview_email(request: Request, data: dict):
        return request.state.service.preview_email(data)

    @application.get("/api/tasks")
    def tasks(request: Request):
        return {"tasks": request.state.service.tasks()}

    @application.post("/api/tasks")
    def create_task(request: Request, data: dict):
        return request.state.service.create_task(data)

    @application.get("/api/tasks/{identifier}")
    def task(identifier: str, request: Request, offset: int = 0, limit: int = 100):
        return request.state.service.task(identifier, offset, limit)

    @application.post("/api/tasks/{identifier}/start")
    @application.post("/api/tasks/{identifier}/resume")
    def start(identifier: str, request: Request):
        return request.state.service.engine.start(identifier)

    @application.post("/api/tasks/{identifier}/pause")
    def pause(identifier: str, request: Request):
        return request.state.service.engine.pause(identifier)

    @application.post("/api/tasks/{identifier}/retry")
    def retry(identifier: str, request: Request, data: dict):
        return request.state.service.engine.retry(identifier, data.get("recipient_ids"), bool(data.get("include_uncertain")))

    @application.post("/api/tasks/{identifier}/export")
    def export(identifier: str, request: Request, data: dict):
        return request.state.service.export_task(identifier, data.get("scope", "failed"))

    @application.get("/api/exports/{identifier}")
    def download(identifier: str, request: Request):
        item, path = request.state.service.file(identifier, "export")
        return FileResponse(path, filename=item["filename"])

    @application.post("/api/test-send")
    def test_send(request: Request, data: dict):
        return request.state.service.engine.test_send(data)

    @application.get("/api/drafts")
    def drafts(request: Request):
        return {"drafts": request.state.service.drafts()}

    @application.post("/api/drafts")
    def save_draft(request: Request, data: dict):
        return request.state.service.save_draft(data)

    @application.delete("/api/drafts/{identifier}")
    def delete_draft(identifier: str, request: Request):
        request.state.service.store.execute("DELETE FROM drafts WHERE id=?", (identifier,))
        return {"status": "success"}

    @application.get("/api/templates")
    def templates():
        return {"templates": ProductService.templates()}

    @application.get("/api/suppressions")
    def suppressions(request: Request):
        return {"content": request.state.service.suppression_content()}

    @application.put("/api/suppressions")
    def save_suppressions(request: Request, data: dict):
        return request.state.service.set_suppressions(str(data.get("content", "")))

    @application.get("/api/data")
    def data_info(request: Request):
        return request.state.service.data_info()

    @application.post("/api/data/backup")
    def backup(request: Request):
        return request.state.service.backup()

    @application.post("/api/data/restore")
    async def restore(request: Request, file: UploadFile = File(...)):
        return request.state.service.restore(await file.read(MAX_BACKUP + 1))

    @application.post("/api/data/cleanup")
    def cleanup(request: Request, data: dict):
        return request.state.service.cleanup(data)

    return application


class DesktopBridge:
    def __init__(self, application):
        self._application = application
        self._window = None

    def _service(self, mode):
        if mode not in self._application.state.services:
            raise ValueError("运行模式不正确。")
        return self._application.state.services[mode]

    def save_export(self, identifier, mode):
        import webview
        item, source = self._service(mode).file(identifier, "export")
        selected = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=item["filename"],
                                                 file_types=("导出文件 (*" + source.suffix + ")",))
        if not selected:
            return {"status": "cancelled"}
        destination = Path(selected[0]).resolve()
        if destination == source.resolve():
            return {"status": "success", "path": str(destination)}
        shutil.copyfile(source, destination)
        return {"status": "success", "path": str(destination)}

    def open_data_folder(self, mode):
        os.startfile(self._service(mode).root)
        return {"status": "success"}

    def import_legacy(self, mode):
        import webview
        selected = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not selected:
            return {"status": "cancelled"}
        try:
            task = self._service(mode).import_legacy(selected[0])
            return {"status": "success", "task_id": task["id"]}
        except (ValueError, OSError, KeyError, json.JSONDecodeError):
            return {"status": "error", "message": "无法导入该目录的旧版记录，请选择包含 state/checkpoint.json 的旧版本目录。"}


def acquire_instance(root):
    if os.name != "nt":
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    digest = hashlib.sha256(str(root).encode()).hexdigest()[:20]
    handle = kernel.CreateMutexW(None, False, "Local\\YunYouBao-" + digest)
    if not handle:
        raise OSError("无法创建应用实例锁。")
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(ctypes.c_void_p(handle))
        raise ValueError("云邮宝已经运行，请使用已打开的窗口。")
    return handle


def run_desktop(application, handle=None):
    import webview
    handle = handle or acquire_instance(data_directory())
    application.state.desktop = True
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(application, log_level="warning", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        if not thread.is_alive():
            raise RuntimeError("本地服务无法启动。")
        threading.Event().wait(0.05)
    if not server.started:
        raise RuntimeError("本地服务启动超时。")
    bridge = DesktopBridge(application)
    bridge._window = webview.create_window("云邮宝", f"http://127.0.0.1:{port}", width=1320, height=900,
                                           min_size=(900, 650), background_color="#f5f6f8", js_api=bridge)
    try:
        webview.start(icon=str(BASE_DIR / "assets" / "branding" / "yunyoubao-fox-v1.ico"))
    finally:
        for service in application.state.services.values():
            service.engine.shutdown()
        server.should_exit = True
        thread.join(3)
        listener.close()
        if handle:
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(handle))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--port", type=int, default=8131)
    args = parser.parse_args()
    if args.headless:
        app = create_app(initial_mode="demo" if args.demo else "live")
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
    else:
        try:
            handle = acquire_instance(data_directory())
            app = create_app(initial_mode="demo" if args.demo else "live")
            run_desktop(app, handle)
        except Exception as error:
            if os.name == "nt":
                ctypes.windll.user32.MessageBoxW(None, str(error), "云邮宝", 0x10)
            else:
                raise
else:
    app = create_app()
