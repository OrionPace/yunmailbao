"""Demo-only smoke test; importing this module never starts a campaign."""

import argparse
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def run_demo_smoke(root):
    from core.engine import DemoTransport
    from core.service import ProductService

    check = unittest.TestCase()
    service = ProductService(root, demo=True)
    check.assertIs(service.engine.transport_factory, DemoTransport)
    try:
        imported = service.demo_import()
        config = {
            "import_id": imported["import_id"],
            "sheet": imported["default_sheet"],
            "name_column": "\u59d3\u540d",
            "email_column": "\u90ae\u7bb1",
            "filters": [
                {"column": "\u5206\u5de5", "values": ["\u5de5\u4f5c\u4eba\u5458 A"]}
            ],
            "subject": "Demo {{\u59d3\u540d}}",
            "html_content": "<p>{{\u59d3\u540d}}: {{\u5355\u4f4d}}</p>",
            "account_ids": [service.accounts()[0]["id"]],
            "account_id": service.accounts()[0]["id"],
            "start_time": "00:00",
            "end_time": "00:00",
            "add_unsubscribe": True,
        }
        preview = service.preview_import(imported["import_id"], config)
        check.assertEqual(preview["counts"], {
            "total": 32, "selected": 12, "invalid": 1, "duplicates": 1,
            "excluded": 0, "conflicts": 0, "sendable": 10,
        })
        config["revision"] = preview["revision"]
        draft = service.save_draft({"title": "Demo smoke", "config": config})
        check.assertEqual(service.drafts()[0]["id"], draft["id"])
        rendered = service.preview_email(config)
        check.assertNotIn("{{", rendered["subject"] + rendered["html_content"])
        check.assertIn("mailto:demo@example.com", rendered["html_content"])

        task = service.create_task(config)
        identifier = task["id"]
        service.engine.start(identifier)
        service.engine.thread.join(15)
        check.assertFalse(service.engine.thread.is_alive(), "Demo task timed out")
        check.assertFalse(service.engine.busy)
        result = service.task(identifier)
        check.assertEqual(result["status"], "completed_with_issues")
        expected = {
            "pending": 0, "sending": 0, "accepted": 8, "failed": 1,
            "uncertain": 1, "total": 10,
        }
        check.assertEqual(result["counts"], expected)
        check.assertEqual(service.store.one("SELECT COUNT(*) AS n FROM attempts")["n"], 10)

        exported = service.export_task(identifier)
        _, export_path = service.file(exported["export_id"], "export")
        import pandas as pd

        rows = pd.read_excel(io.BytesIO(export_path.read_bytes()), dtype=str)
        check.assertEqual(len(rows), 2)

        # Reopen only after shutdown so recovery cannot affect an active worker.
        service.engine.shutdown()
        reopened = ProductService(root, demo=True)
        try:
            check.assertEqual(reopened.task(identifier)["counts"], expected)
            check.assertEqual(reopened.drafts()[0]["id"], draft["id"])
        finally:
            reopened.engine.shutdown()
        return expected
    finally:
        service.engine.shutdown()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Demo only; no real SMTP or .env.")
    parser.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    # Fail closed if a future refactor accidentally selects a real transport.
    with patch("smtplib.SMTP", side_effect=AssertionError("Real SMTP forbidden")) as smtp, \
         patch("smtplib.SMTP_SSL", side_effect=AssertionError("Real SMTP forbidden")) as smtp_ssl, \
         patch("socket.create_connection", side_effect=AssertionError("Network forbidden")) as network:
        with tempfile.TemporaryDirectory(prefix="yunyoubao-demo-smoke-") as temporary:
            counts = run_demo_smoke(Path(temporary) / "demo")
        smtp.assert_not_called()
        smtp_ssl.assert_not_called()
        network.assert_not_called()
    print("\u6f14\u793a\u70df\u6d4b\u901a\u8fc7\uff0c\u672a\u53d1\u9001\u771f\u5b9e\u90ae\u4ef6\u3002", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
