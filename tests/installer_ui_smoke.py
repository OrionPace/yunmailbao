"""Check the real Chinese installer wizard; cancel before installing files."""

import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import sys
import time

from PIL import ImageGrab


def run():
    user = ctypes.WinDLL("user32", use_last_error=True)
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback, wintypes.LPARAM]
    user.EnumChildWindows.argtypes = [wintypes.HWND, callback, wintypes.LPARAM]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.SendMessageW.restype = wintypes.LPARAM
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
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
        matches = [handle for handle, title in items if text in title]
        assert matches, f"Missing wizard control: {text}"
        user.SendMessageW(matches[0], 0x00F5, 0, 0)
        time.sleep(0.25)

    def screenshot(window, name):
        rect = wintypes.RECT()
        assert user.GetWindowRect(window, ctypes.byref(rect))
        ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom)).save(output / name)

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
        screenshot(window, "01-chinese-licence.png")
        click(items, "我同意")
        click(children(window), "下一步")
        items = children(window)
        content = "\n".join(text for _, text in items)
        assert "目标" in content and "浏览" in content, "Directory selection page missing"
        assert "YunYouBao" in content, "Default directory missing"
        screenshot(window, "02-directory-selection.png")
        print("PASS: real Chinese licence page and selectable installation directory; no installation requested")
    finally:
        if window:
            user.PostMessageW(window, 0x0010, 0, 0)
            time.sleep(0.3)
            # Close only the cancellation confirmation owned by this installer.
            @callback
            def dismiss(handle, _):
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
