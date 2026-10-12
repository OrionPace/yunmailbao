"""Manual Windows WebView2 smoke check with temporary demonstration data."""

import contextlib
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run():
    if os.name != "nt":
        raise SystemExit("This manual check requires Windows and WebView2.")
    import uvicorn
    import webview

    report = {"errors": [], "smtp": "forbidden", "mode": "demo"}
    with tempfile.TemporaryDirectory() as temporary, contextlib.ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {"YUNYOUBAO_DATA_DIR": temporary}))
        for target in ("smtplib.SMTP", "smtplib.SMTP_SSL"):
            stack.enter_context(patch(target, side_effect=AssertionError("Real SMTP forbidden")))
        from main import BASE_DIR, VERSION, DesktopBridge, create_app

        app = create_app(temporary, initial_mode="demo", desktop=True)
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        if not server.started:
            raise RuntimeError("Local service did not start")
        bridge = DesktopBridge(app)
        window = webview.create_window("云邮宝桌面验收", f"http://127.0.0.1:{port}",
                                       width=1320, height=900, hidden=True, js_api=bridge)
        bridge._window = window

        def validate():
            try:
                assert window.events.loaded.wait(20), "Native page did not load"
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    ready = window.evaluate_js("Boolean(window.Quill && window.pywebview && window.pywebview.api.save_export && document.querySelector('.ql-editor'))")
                    if ready:
                        break
                    time.sleep(0.1)
                assert ready, "Editor or native bridge not ready"
                report.update(window.evaluate_js("({version:window.YUNYOUBAO.version, editor_count:document.querySelectorAll('.ql-editor').length, logo_width:document.querySelector('.brand img').naturalWidth, bridge_functions:Object.keys(window.pywebview.api).sort()})"))
                assert report["version"] == VERSION
                assert report["editor_count"] == 1
                assert report["logo_width"] > 0
                assert report["bridge_functions"] == ["import_legacy", "open_data_folder", "save_export"]
                window.evaluate_js("document.getElementById('demo-load').click(); true")
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    value = window.evaluate_js("document.getElementById('import-counts').textContent")
                    if "32" in value:
                        break
                    time.sleep(0.1)
                assert "32" in value, "Demonstration import did not complete"
                report["demonstration_rows"] = 32
                report["renderer"] = getattr(webview.guilib, "renderer", "unknown")
            except BaseException as error:
                report["errors"].append(str(error))
            finally:
                window.destroy()

        watchdog = threading.Timer(45, window.destroy)
        watchdog.daemon = True
        watchdog.start()
        try:
            webview.start(validate, private_mode=True, icon=str(BASE_DIR / "assets/branding/yunyoubao-fox-v1.ico"))
        finally:
            watchdog.cancel()
            server.should_exit = True
            thread.join(5)
            listener.close()
            for service in app.state.services.values():
                service.engine.shutdown()
        output = Path(__file__).resolve().parent / "artifacts" / "desktop-report.json"
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        if report["errors"] or "demonstration_rows" not in report:
            raise SystemExit(1)


if __name__ == "__main__":
    run()
