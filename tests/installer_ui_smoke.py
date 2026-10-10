"""Check the real Chinese installer wizard; cancel before installing files."""

import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import sys
import time

def run():
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.SetProcessDPIAware()
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback, wintypes.LPARAM]
    user.EnumChildWindows.argtypes = [wintypes.HWND, callback, wintypes.LPARAM]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetWindow.restype = wintypes.HWND
    user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.SendMessageW.restype = wintypes.LPARAM
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    output = Path(__file__).parent / "artifacts" / "installer-ui"
    output.mkdir(parents=True, exist_ok=True)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    process = subprocess.Popen([str(Path(sys.argv[1]).resolve()), "/SP-"], startupinfo=startup)

    def children(window):
        found = []

        @callback
        def collect(handle, _):
            if user.IsWindowVisible(handle):
                text = ctypes.create_unicode_buffer(32768)
                user.SendMessageW(handle, 0x000D, len(text), ctypes.addressof(text))
                found.append((handle, text.value))
            return True

        user.EnumChildWindows(window, collect, 0)
        return found

    def click(items, text):
        matches = []
        for handle, title in items:
            kind = ctypes.create_unicode_buffer(256)
            user.GetClassNameW(handle, kind, len(kind))
            if text in title and "button" in kind.value.lower():
                matches.append(handle)
        assert matches, f"Missing wizard control: {text}"
        user.SendMessageW(matches[0], 0x00F5, 0, 0)
        time.sleep(0.25)

    window = None
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and window is None:
            found = []

            @callback
            def collect(handle, _):
                pid = wintypes.DWORD()
                user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
                # Inno's loader may launch a child process; match the wizard title.
                title = ctypes.create_unicode_buffer(512)
                user.GetWindowTextW(handle, title, len(title))
                if "云邮宝" in title.value and "安装" in title.value and user.IsWindowVisible(handle):
                    found.append(handle)
                return True

            user.EnumWindows(collect, 0)
            window = next((handle for handle in found if any("下一步" in text for _, text in children(handle))), None)
            time.sleep(0.1)
        assert window, "Chinese installer wizard did not appear"
        for _ in range(4):
            items = children(window)
            content = "\n".join(text for _, text in items)
            if "GPL" in content:
                break
            click(items, "下一步")
        assert "GPL" in content and "授权" in content, "Chinese licence explanation missing"
        assert "用户数据" in content and "垃圾" in content, "Chinese data/send boundaries missing"
        (output / "licence-text.txt").write_text(content, encoding="utf-8")
        click(items, "我同意")
        click(children(window), "下一步")
        items = children(window)
        content = "\n".join(text for _, text in items)
        if "知情说明" in content:
            assert "本地存储" in content and "卸载保留数据" in content
            (output / "data-notice-text.txt").write_text(content, encoding="utf-8")
            click(items, "下一步")
            items = children(window)
            content = "\n".join(text for _, text in items)
        (output / "wizard-text.txt").write_text(content, encoding="utf-8")
        assert "目标" in content and "浏览" in content, "Directory selection page missing: " + content[:1500]
        assert "YunYouBao" in content, "Default directory missing"
        print("PASS: real Chinese licence page and selectable installation directory; no installation requested")
    finally:
        if window:
            user.PostMessageW(window, 0x0010, 0, 0)
            time.sleep(0.3)
            # Close only the cancellation confirmation owned by this installer.
            @callback
            def dismiss(handle, _):
                if user.GetWindow(handle, 4) != window:
                    return True
                items = children(handle)
                if any("退出" in text and "安装" in text for _, text in items):
                    matches = [item for item, text in items if "是" in text]
                    if matches:
                        user.SendMessageW(matches[0], 0x00F5, 0, 0)
                return True
            user.EnumWindows(dismiss, 0)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__":
    run()
