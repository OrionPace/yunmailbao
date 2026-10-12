"""Generate browser fixtures and serve a disposable, real product backend."""

import argparse
import json
import socket
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import uvicorn
from main import create_app
from test_product_service import office_bytes


def pdf_bytes():
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>"]
    data = b"%PDF-1.4\n"
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    start = len(data)
    data += b"xref\n0 4\n0000000000 65535 f \n"
    data += b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:])
    return data + f"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "tests"):
        parser.error("Fixture output must remain under tests")
    output.mkdir(parents=True, exist_ok=True)
    for extension in ("pdf", "docx", "xlsx", "pptx"):
        (output / f"attachment.{extension}").write_bytes(
            pdf_bytes() if extension == "pdf" else office_bytes(extension))

    with tempfile.TemporaryDirectory(prefix="product-ui-", dir=output) as temporary:
        app = create_app(data_root=temporary, initial_mode="demo")
        live = app.state.services["live"]
        live.save_account({"email": "isolated-live@example.com", "smtp_host": "smtp.invalid",
                           "password": "QA-MEMORY-ONLY", "remember": False})
        live.save_account_selection([])
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

        class FixtureServer(uvicorn.Server):
            async def startup(self, sockets=None):
                await super().startup(sockets=sockets)
                print(json.dumps({"kind": "ready", "url": f"http://127.0.0.1:{port}"}), flush=True)

        server = FixtureServer(uvicorn.Config(app, log_level="error"))

        def stop_on_stdin():
            sys.stdin.readline()
            server.should_exit = True

        threading.Thread(target=stop_on_stdin, daemon=True).start()
        with patch("smtplib.SMTP", side_effect=AssertionError("SMTP forbidden in UI QA")), \
             patch("smtplib.SMTP_SSL", side_effect=AssertionError("SMTP forbidden in UI QA")), \
             patch("socket.create_connection", side_effect=AssertionError("Outbound sockets forbidden")):
            server.run(sockets=[sock])
        persisted = {}
        for mode, service in app.state.services.items():
            preferences = service.store.all("SELECT key,payload FROM preferences")
            accounts = service.store.all("SELECT payload FROM accounts")
            persisted[mode] = {"preferences": [dict(row) for row in preferences],
                               "accounts": [json.loads(row["payload"]) for row in accounts],
                               "task_count": len(service.tasks())}
        print(json.dumps({"kind": "persisted", "data": persisted}), flush=True)


if __name__ == "__main__":
    main()
