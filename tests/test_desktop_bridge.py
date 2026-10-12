import ctypes
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

from core.credentials import protect, unprotect
from core.service import ProductService


class DesktopBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        with patch.dict(os.environ, {"YUNYOUBAO_DATA_DIR": str(self.root / "module-app")}):
            from main import DesktopBridge
        self.service = ProductService(self.root / "demo", demo=True)
        self.addCleanup(self.service.engine.shutdown)
        app = SimpleNamespace(state=SimpleNamespace(services={"demo": self.service}))
        self.bridge = DesktopBridge(app)
        self.bridge._window = Mock()
        output = io.BytesIO()
        pd.DataFrame([{"状态": "模拟失败"}]).to_excel(output, index=False)
        self.export_bytes = output.getvalue()

    def test_cancel_save_leaves_no_destination(self):
        item = self.service.add_file("问题记录.xlsx", self.export_bytes, "export")
        self.bridge._window.create_file_dialog.return_value = None
        self.assertEqual(self.bridge.save_export(item["id"], "demo"), {"status": "cancelled"})
        self.assertEqual(list(self.root.glob("*.xlsx")), [])
        self.assertEqual(self.service.file(item["id"], "export")[1].read_bytes(), self.export_bytes)

    def test_native_save_preserves_bytes_at_chinese_path(self):
        item = self.service.add_file("问题记录.xlsx", self.export_bytes, "export")
        destination = self.root / "中文路径" / "导出.xlsx"
        destination.parent.mkdir()
        self.bridge._window.create_file_dialog.return_value = (str(destination),)
        result = self.bridge.save_export(item["id"], "demo")
        self.assertEqual(result["status"], "success")
        self.assertEqual(destination.read_bytes(), self.export_bytes)

    def test_file_ids_and_modes_cannot_escape_bridge(self):
        with self.assertRaises(ValueError):
            self.bridge.save_export("anything", "../live")
        with self.assertRaises(KeyError):
            self.bridge.save_export("../file", "demo")
        item = self.service.add_file("附件.pdf", b"%PDF-fixture", "attachment")
        with self.assertRaises(KeyError):
            self.bridge.save_export(item["id"], "demo")
        self.bridge._window.create_file_dialog.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_dpapi_roundtrip_is_ciphertext(self):
        value = "test-only-not-a-mail-password"
        encrypted = protect(value)
        self.assertNotIn(value, encrypted)
        self.assertEqual(unprotect(encrypted), value)

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI across processes")
    def test_saved_account_and_selection_survive_process_restart(self):
        script = """
import sys
from unittest.mock import patch
from core.service import ProductService
with patch('smtplib.SMTP', side_effect=AssertionError('Real SMTP forbidden')), \\
     patch('smtplib.SMTP_SSL', side_effect=AssertionError('Real SMTP forbidden')):
    service = ProductService(sys.argv[1])
    if sys.argv[2] == 'save':
        account = service.save_account({'id':'restart-fixture', 'email':'restart@example.test',
            'name':'Restart fixture', 'smtp_host':'smtp.example.test', 'smtp_port':465,
            'security':'ssl', 'password':'FAKE-RESTART-SECRET', 'remember':True})
        service.save_account_selection([account['id']])
    else:
        assert service.account_selection() == ['restart-fixture']
        assert service.sender('restart-fixture')['password'] == 'FAKE-RESTART-SECRET'
        assert service.accounts()[0]['has_secret'] is True
        assert 'password' not in service.accounts()[0]
    service.engine.shutdown()
"""
        root = self.root / "restart"
        for operation in ("save", "read"):
            subprocess.run([sys.executable, "-B", "-c", script, str(root), operation],
                           cwd=Path(__file__).resolve().parents[1], check=True,
                           capture_output=True, text=True, timeout=30)

    @unittest.skipUnless(os.name == "nt", "Windows mutex")
    def test_second_instance_is_rejected_before_opening_data(self):
        from main import acquire_instance
        handle = acquire_instance(self.root)
        try:
            with self.assertRaises(ValueError):
                acquire_instance(self.root)
        finally:
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(handle))


if __name__ == "__main__":
    unittest.main()
