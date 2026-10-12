"""Isolated Windows 0.2.0 -> 0.2.1 installation check; never request SMTP sending."""

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time
import winreg

import httpx


ROOT = Path(__file__).resolve().parents[1]
APP_ID = "{E7B5B140-9561-4D21-8A42-13A484655EDC}"
UNINSTALL_KEY = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + APP_ID + "_is1"


def hidden(command, log):
    startup = subprocess.STARTUPINFO()
    startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    with log.open("w", encoding="utf-8") as stream:
        subprocess.run([str(part) for part in command], cwd=ROOT, startupinfo=startup,
                       stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=120)


def registration():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            return Path(winreg.QueryValueEx(key, "InstallLocation")[0]).resolve()
    except FileNotFoundError:
        return None


@contextlib.contextmanager
def application(executable, data):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    startup = subprocess.STARTUPINFO()
    startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    process = subprocess.Popen([str(executable), "--headless", "--demo", "--port", str(port)],
                               startupinfo=startup, env=dict(os.environ, YUNYOUBAO_DATA_DIR=str(data)),
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
            deadline = time.monotonic() + 30
            while True:
                try:
                    page = client.get("/")
                    page.raise_for_status()
                    break
                except httpx.HTTPError:
                    assert process.poll() is None, "Frozen application exited before serving"
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.2)
            boot = json.loads(re.search(r"window\.YUNYOUBAO=(\{.*?\});", page.text).group(1))
            client.headers.update(Authorization="Bearer " + boot["token"], **{"X-Yunyoubao-Mode": "live"})
            yield client
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=10)


def api(client, method, endpoint, **kwargs):
    assert not re.search(r"test-send|/(start|resume|retry)$", endpoint), "Sending forbidden in upgrade check"
    response = client.request(method, "/api/" + endpoint, **kwargs)
    response.raise_for_status()
    return response.json()


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-candidate", default=str(Path(os.environ["LOCALAPPDATA"]) / "Programs/YunYouBao"))
    args = parser.parse_args()
    base = (ROOT / "tests/artifacts/upgrade").resolve()
    assert base.is_relative_to(ROOT / "tests/artifacts")
    assert registration() is None, "Independent smoke AppId already registered; refusing to replace it"
    assert not (base / "installed").exists(), "Smoke install directory must be new"
    base.mkdir(parents=True, exist_ok=True)
    old_manifest = json.loads((ROOT / "release/0.2.0/build-manifest.json").read_text(encoding="utf-8"))
    old_source = Path(args.old_candidate).resolve()
    old_candidate = base / "candidate-0.2.0"
    for entry in old_manifest["candidate_files"]:
        source, target = old_source / entry["path"], old_candidate / entry["path"]
        assert source.resolve().is_relative_to(old_source) and target.resolve().is_relative_to(base)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == entry["sha256"], entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    installed, data = base / "installed", base / "data"
    real_executable = Path(os.environ["LOCALAPPDATA"]) / "Programs/YunYouBao/YunYouBao.exe"
    real_hash = hashlib.sha256(real_executable.read_bytes()).hexdigest()
    iscc = ROOT / ".tools/InnoSetup/ISCC.exe"
    specs = ["--no-ide-signtools", "--no-signing", "--define=AppName=云邮宝升级验收",
             "--define=InstallerAppId={" + APP_ID]
    fixture = {"id": "upgrade-fixture", "email": "upgrade@example.test", "name": "Upgrade fixture",
               "smtp_host": "smtp.example.test", "smtp_port": 465, "security": "ssl",
               "remember": True, "per_minute": 5, "daily_limit": 75}
    task_id = None
    frozen = None
    try:
        for version, candidate in (("0.2.0", old_candidate), ("0.2.1", ROOT / ".build/candidate/YunYouBao")):
            package = base / version
            package.mkdir(exist_ok=True)
            hidden([iscc, *specs, "--define=AppVersion=" + version,
                    "--define=CandidateDir=" + str(candidate), "--define=ReleaseDir=" + str(package),
                    ROOT / "packaging/yunyoubao.iss"], base / ("compile-" + version + ".log"))
            setup = package / ("云邮宝升级验收-" + version + "-setup.exe")
            arguments = [setup, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"]
            if version == "0.2.0":
                arguments.append("/DIR=" + str(installed))
            hidden(arguments, base / ("install-" + version + ".log"))
            assert registration() == installed, "Upgrade did not preserve chosen directory"
            with application(installed / "YunYouBao.exe", data) as client:
                if version == "0.2.0":
                    api(client, "POST", "accounts", json=dict(fixture, password="FAKE-UPGRADE-SECRET"))
                    imported = api(client, "POST", "imports", files={"file": ("legacy.csv",
                        b"Name,Email\r\nLegacy Reader,legacy-reader@example.test\r\n", "text/csv")})
                    config = {"import_id": imported["import_id"], "sheet": "CSV", "name_column": "Name",
                              "email_column": "Email", "filters": [], "account_ids": [fixture["id"]],
                              "subject": "Legacy <人名>", "html_content": "<p>&lt;人名&gt;, hello.</p>",
                              "start_time": "00:00", "end_time": "00:00", "add_unsubscribe": True}
                    config["revision"] = api(client, "POST", "imports/" + imported["import_id"] + "/preview", json=config)["revision"]
                    draft = api(client, "POST", "drafts", json={"title": "Upgrade legacy draft", "config": config})
                    task = api(client, "POST", "tasks", json=config)
                    task_id, frozen = task["id"], task["config"]
                else:
                    accounts = api(client, "GET", "accounts")["accounts"]
                    restored = next(account for account in accounts if account["id"] == fixture["id"])
                    for key, value in fixture.items():
                        assert restored[key] == value, key
                    assert restored["has_secret"] and "password" not in restored
                    api(client, "POST", "accounts", json=fixture)  # DPAPI decrypt/re-encrypt with no new password.
                    task = api(client, "GET", "tasks/" + task_id)
                    assert task["config"] == frozen and task["counts"]["pending"] == 1
                    assert task["counts"]["accepted"] == 0
                    assert any(item["id"] == draft["id"] for item in api(client, "GET", "drafts")["drafts"])
        env = dict(os.environ, YUNYOUBAO_SMOKE_DATA_DIR=str(data))
        subprocess.run(["node", "tests/browser/installed.cjs", str(installed / "YunYouBao.exe"),
                        "release/0.2.1/build-manifest.json"], cwd=ROOT, env=env, check=True, timeout=120)
    finally:
        if registration() is not None:
            assert registration() == installed and installed.is_relative_to(base)
            hidden([installed / "unins000.exe", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], base / "uninstall.log")
            assert registration() is None and not (installed / "YunYouBao.exe").exists()
        assert hashlib.sha256(real_executable.read_bytes()).hexdigest() == real_hash, "Real installation changed"
    assert (data / "live/yunyoubao.sqlite3").is_file(), "Uninstall removed synthetic user data"
    report = {"upgrade": "0.2.0 -> 0.2.1", "account_and_dpapi_preserved": True,
              "draft_preserved": True, "frozen_task_preserved": True, "isolated_uninstall": True,
              "real_installation_unchanged": True, "smtp": "no send requested"}
    (base / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    run()
