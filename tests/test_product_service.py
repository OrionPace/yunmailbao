import contextlib
import copy
import csv
import datetime as dt
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import zipfile
from collections import deque
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import Workbook

from core.email_sender import SendResult, render_email
from core.service import ProductService


class FakeTransport:
    def __init__(self, outcomes=(), on_send=None):
        self.outcomes = deque(outcomes)
        self.on_send = on_send
        self.calls = []
        self.close_count = 0

    def send_attempt(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        result = self.outcomes.popleft() if self.outcomes else SendResult("accepted", "Accepted")
        if self.on_send:
            self.on_send()
        return result

    def close_all_connections(self):
        self.close_count += 1


def recipient(email, name="Reader", team="A", region="In"):
    return {"Name": name, "Email": email, "Team": team, "Region": region}


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=("Name", "Email", "Team", "Region"))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


class ProductServiceIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.services = []
        for target in ("smtplib.SMTP", "smtplib.SMTP_SSL", "socket.create_connection"):
            self.enterContext(patch(target, side_effect=AssertionError("Real SMTP/network forbidden")))
        for target in ("core.credentials.protect", "core.credentials.unprotect"):
            self.enterContext(patch(target, side_effect=AssertionError("DPAPI forbidden in tests")))
        self.transport = FakeTransport()
        self.service = self.make_service("service", demo=True, transport=self.transport)
        self.account = self.save_account(self.service)

    def tearDown(self):
        for service in self.services:
            service.engine.shutdown(timeout=1)
            thread = service.engine.thread
            self.assertFalse(thread and thread.is_alive(), "Test left a sender thread running")

    def make_service(self, folder, demo=True, transport=None):
        factory = (lambda: transport) if transport is not None else None
        service = ProductService(self.root / folder, demo=demo, transport_factory=factory)
        self.services.append(service)
        return service

    def save_account(self, service, **changes):
        data = {"email": "sender@example.com", "name": "Original Sender", "smtp_host": "smtp.invalid",
                "smtp_port": 465, "security": "ssl", "remember": False,
                "password": "MEMORY-SECRET-fixture", "per_minute": 120, "daily_limit": 100}
        data.update(changes)
        return service.save_account(data)

    def config(self, rows, filters=None, service=None, account=None):
        service = service or self.service
        account = account or self.account
        imported = service.import_file("recipients.csv", csv_bytes(rows))
        config = {"import_id": imported["import_id"], "sheet": "CSV", "email_column": "Email",
                  "name_column": "Name", "filters": filters or [], "account_ids": [account["id"]],
                  "subject": "Notice {{Name}}", "html_content": "<p>{{Name}}</p>",
                  "start_time": "00:00", "end_time": "00:00", "add_unsubscribe": True}
        config["revision"] = service.preview_import(imported["import_id"], config)["revision"]
        return config

    def create_task(self, rows=None, **kwargs):
        service = kwargs.get("service") or self.service
        return service.create_task(self.config(rows or [recipient("one@example.com")], **kwargs))

    def wait_for_task(self, service, identifier):
        thread = service.engine.thread
        self.assertIsNotNone(thread)
        thread.join(timeout=1.5)
        self.assertFalse(thread.is_alive(), "Sender did not stop within the short test timeout")
        self.assertFalse(service.engine.busy)
        task = service.task(identifier)
        self.assert_conserved(task["counts"])
        return task

    def assert_conserved(self, counts):
        self.assertEqual(counts["total"], sum(counts[key] for key in ("pending", "sending", "accepted", "failed", "uncertain")))

    def test_send_window_crosses_midnight_and_excludes_the_end_boundary(self):
        cases = (("22:00", "06:00", "21:59:59", False), ("22:00", "06:00", "22:00:00", True),
                 ("22:00", "06:00", "23:59:59", True), ("22:00", "06:00", "00:00:00", True),
                 ("22:00", "06:00", "05:59:59", True), ("22:00", "06:00", "06:00:00", False),
                 ("22:00", "06:00", "12:00:00", False), ("08:00", "18:00", "08:00:00", True),
                 ("08:00", "18:00", "18:00:00", False), ("00:00", "00:00", "23:59:59", True))
        for start, end, current, expected in cases:
            with self.subTest(start=start, end=end, current=current):
                self.assertEqual(self.service.engine.in_window(start, end, dt.time.fromisoformat(current)), expected)

    def test_mock_dpapi_and_data_operations_share_the_task_execution_lock(self):
        live = self.make_service("remembered-live", demo=False, transport=self.transport)
        first_secret, next_secret = "REMEMBERED-SECRET", "UPDATED-SECRET"
        first_cipher, next_cipher = "mock-protected-original", "mock-protected-updated"
        with patch("core.credentials.protect", return_value=first_cipher) as protect, patch(
                "core.credentials.unprotect", side_effect=lambda value: {first_cipher: first_secret, next_cipher: next_secret}[value]) as unprotect:
            account = self.save_account(live, remember=True, password=first_secret)
            protect.assert_called_once_with(first_secret)
            self.assertNotIn(first_secret, json.dumps(account))
            self.assertNotIn(account["id"], live.memory_secrets)
            stored = live.store.one("SELECT payload,secret FROM accounts WHERE id=?", (account["id"],))
            self.assertEqual(stored["secret"], first_cipher)
            self.assertNotIn(first_secret, stored["payload"])
            reopened = self.make_service("remembered-live", demo=False, transport=self.transport)
            self.assertTrue(reopened.accounts()[0]["has_secret"])
            self.assertEqual(reopened.sender(account["id"])["password"], first_secret)
            unprotect.assert_called_with(first_cipher)
            task = self.create_task(service=live, account=account)
            entered, release = threading.Event(), threading.Event()
            errors = []

            def blocking_protect(secret):
                self.assertEqual(secret, next_secret)
                entered.set()
                if not release.wait(1.5):
                    raise AssertionError("Test did not release credential protection")
                return next_cipher

            def update_account():
                try:
                    self.save_account(live, id=account["id"], remember=True, password=next_secret)
                except BaseException as error:
                    errors.append(error)

            with patch("core.credentials.protect", side_effect=blocking_protect):
                worker = threading.Thread(target=update_account, daemon=True)
                try:
                    worker.start()
                    self.assertTrue(entered.wait(1))
                    self.assertTrue(live.engine.busy)
                    actions = (lambda: live.engine.start(task["id"]),
                               lambda: live.engine.test_send({"account_id": account["id"], "test_email": "test@example.com"}),
                               lambda: live.delete_account(account["id"]), live.backup,
                               lambda: live.restore(b"not-a-backup"), lambda: live.cleanup({"logs": True}),
                               lambda: live.import_legacy(self.root / "missing-legacy"))
                    for action in actions:
                        with self.assertRaises(ValueError):
                            action()
                    self.assertEqual(live.task(task["id"])["status"], "ready")
                    self.assertEqual(self.transport.calls, [])
                finally:
                    release.set()
                    worker.join(timeout=1)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            self.assertFalse(live.engine.busy)
            self.assertEqual(live.sender(account["id"])["password"], next_secret)
            with patch("core.credentials.protect", side_effect=ValueError("Mock protection failure")):
                with self.assertRaises(ValueError):
                    self.save_account(live, id=account["id"], remember=True, password="FAILED-SECRET")
            self.assertFalse(live.engine.busy)
            self.assertEqual(live.sender(account["id"])["password"], next_secret)
            live.engine.start(task["id"])
            self.assertEqual(self.wait_for_task(live, task["id"])["counts"]["accepted"], 1)

    def test_workbook_discovers_each_sheets_headers_and_requires_remapping(self):
        workbook = Workbook()
        first = workbook.active
        first.title = "Notices"
        first.append(["Name", "Email", "Team"])
        first.append(["Ann", "ann@example.com", "A"])
        second = workbook.create_sheet("Attendees")
        second.append(["Contact", "Address", "Category"])
        second.append(["Bob", "bob@example.com", "Meeting"])
        second.append(["Cora", "cora@example.com", "Training"])
        stream = io.BytesIO()
        workbook.save(stream)
        workbook.close()
        imported = self.service.import_file("multiple-sheets.xlsx", stream.getvalue())
        self.assertEqual(imported["sheets"], ["Notices", "Attendees"])
        self.assertEqual(imported["columns"], ["Name", "Email", "Team"])
        self.assertEqual(imported["sheet_columns"], {"Notices": ["Name", "Email", "Team"],
                                                    "Attendees": ["Contact", "Address", "Category"]})
        config = {"sheet": "Attendees", "name_column": "Name", "email_column": "Email"}
        discovery = self.service.preview_import(imported["import_id"], config)
        self.assertTrue(discovery["mapping_required"])
        self.assertIsNone(discovery["revision"])
        self.assertEqual(discovery["rows"], [])
        self.assertEqual(discovery["columns"], ["Contact", "Address", "Category"])
        self.assertEqual((discovery["counts"]["total"], discovery["counts"]["sendable"]), (2, 0))
        config.update(import_id=imported["import_id"], account_ids=[self.account["id"]],
                      subject="Notice", html_content="<p>{{Contact}}</p>", revision=discovery["revision"])
        with self.assertRaises(ValueError):
            self.service.create_task(config)
        config.update(name_column="Contact", email_column="Address")
        mapped = self.service.preview_import(imported["import_id"], config)
        self.assertEqual(mapped["counts"]["sendable"], 2)
        config["revision"] = mapped["revision"]
        task = self.service.create_task(config)
        self.assertEqual(task["config"]["sheet"], "Attendees")
        self.assertEqual([(row["name"], row["email"]) for row in task["recipients"]],
                         [("Bob", "bob@example.com"), ("Cora", "cora@example.com")])
        with self.assertRaises(ValueError):
            self.service.preview_import(imported["import_id"], dict(config, sheet="Missing"))

    def test_promotion_preview_and_frozen_subject_use_the_same_ad_prefix(self):
        cases = (("Offer {{Name}}", "AD Offer {{Name}}", "AD Offer Reader"),
                 ("AD Offer {{Name}}", "AD Offer {{Name}}", "AD Offer Reader"),
                 ("ad Offer {{Name}}", "ad Offer {{Name}}", "ad Offer Reader"),
                 ("\u5e7f\u544a {{Name}}", "\u5e7f\u544a {{Name}}", "\u5e7f\u544a Reader"))
        for subject, frozen_subject, rendered_subject in cases:
            with self.subTest(subject=subject):
                config = self.config([recipient("promotion@example.com")])
                config.update(subject=subject, purpose="promotion", account_id=self.account["id"])
                preview = self.service.preview_email(config)
                self.assertEqual(preview["subject"], rendered_subject)
                with self.assertRaises(ValueError):
                    self.service.create_task(config)
                config["source_note"] = "Explicit opt-in webinar registration fixture"
                task = self.service.create_task(config)
                frozen = task["config"]
                self.assertEqual(frozen["subject"], frozen_subject)
                rendered = render_email(frozen["subject"], frozen["html_content"], preview["recipient"],
                                        self.account, frozen["add_unsubscribe"])
                for field in ("subject", "html_content", "text_content"):
                    self.assertEqual(rendered[field], preview[field])

    def test_filter_counts_revision_and_frozen_snapshot(self):
        self.service.set_suppressions("excluded@example.com")
        rows = [recipient("ann@example.com", "Ann"), recipient("ann@example.com", "Ann"),
                recipient("bob@example.com", "Bob"), recipient("excluded@example.com"),
                recipient("not-an-address"), recipient("other@example.com", team="B"),
                recipient("outside@example.com", region="Out")]
        filters = [{"column": "Team", "values": ["A"]}, {"column": "Region", "values": ["In"]}]
        config = self.config(rows, filters)
        preview = self.service.preview_import(config["import_id"], config)
        self.assertEqual(preview["counts"], {"total": 7, "selected": 5, "invalid": 1, "duplicates": 1,
                                            "excluded": 1, "conflicts": 0, "sendable": 2})
        self.assertEqual(preview["counts"]["selected"], sum(preview["counts"][key] for key in
                         ("invalid", "duplicates", "excluded", "conflicts", "sendable")))
        self.service.set_suppressions("excluded@example.com\nbob@example.com")
        with self.assertRaises(ValueError):
            self.service.create_task(config)
        self.assertEqual(self.service.tasks(), [])
        self.service.set_suppressions("excluded@example.com")
        config["revision"] = self.service.preview_import(config["import_id"], config)["revision"]
        task = self.service.create_task(config)
        _, source = self.service.file(config["import_id"], "import")
        source.write_bytes(csv_bytes([recipient("replacement@example.com", "Replacement", team="B")]))
        config["filters"][0]["values"][:] = ["B"]
        self.save_account(self.service, id=self.account["id"], name="Changed Sender")
        frozen = self.service.task(task["id"])
        self.assertEqual(frozen["config"]["filters"][0]["values"], ["A"])
        self.assertEqual(frozen["config"]["sender_profiles"][0]["name"], "Original Sender")
        self.service.engine.start(task["id"])
        completed = self.wait_for_task(self.service, task["id"])
        self.assertEqual(completed["counts"]["total"], 2)
        self.assertEqual(completed["counts"]["accepted"], 2)
        self.assertEqual([call["recipient"]["email"] for call in self.transport.calls], ["ann@example.com", "bob@example.com"])
        self.assertEqual([call["recipient"]["values"]["Name"] for call in self.transport.calls], ["Ann", "Bob"])
        self.assertTrue(all(call["sender"]["name"] == "Original Sender" for call in self.transport.calls))

    def test_name_conflicts_block_creation_and_filter_can_resolve_them(self):
        config = self.config([recipient("Same@163.com", "Ann", team="A"),
                              recipient("same@163.com", "Bob", team="B"), recipient("other@example.com")])
        preview = self.service.preview_import(config["import_id"], config)
        self.assertEqual(preview["counts"]["conflicts"], 2)
        self.assertEqual(preview["counts"]["sendable"], 1)
        with self.assertRaises(ValueError):
            self.service.create_task(config)
        self.assertEqual(self.service.tasks(), [])
        config["filters"] = [{"column": "Team", "values": ["B"]}]
        filtered = self.service.preview_import(config["import_id"], config)
        self.assertEqual(filtered["counts"]["conflicts"], 0)
        config["revision"] = filtered["revision"]
        task = self.service.create_task(config)
        self.assertEqual([(row["name"], row["email"]) for row in task["recipients"]], [("Bob", "same@163.com")])

    def test_quota_is_shared_by_tasks_test_send_and_restart(self):
        self.account = self.save_account(self.service, id=self.account["id"], daily_limit=2)
        first = self.create_task()
        second = self.create_task([recipient("two@example.com")])
        self.service.engine.start(first["id"])
        self.assertEqual(self.wait_for_task(self.service, first["id"])["counts"]["accepted"], 1)
        result = self.service.engine.test_send({"account_id": self.account["id"], "test_email": "test@example.com",
                                                "subject": "Test", "html_content": "<p>Test</p>"})
        self.assertEqual(result["status"], "accepted")
        self.service.engine.start(second["id"])
        paused = self.wait_for_task(self.service, second["id"])
        self.assertEqual((paused["status"], paused["pause_reason"], paused["counts"]["pending"]), ("paused", "quota", 1))
        self.assertEqual(len(self.transport.calls), 2)
        restored = self.make_service("service", demo=True, transport=self.transport)
        self.assertEqual(restored.engine.quota(self.account)["count"], 2)
        restored.engine.start(second["id"])
        self.assertEqual(self.wait_for_task(restored, second["id"])["pause_reason"], "quota")
        self.assertEqual(len(self.transport.calls), 2)
        with self.assertRaises(ValueError):
            restored.engine.test_send({"account_id": self.account["id"], "test_email": "test@example.com",
                                       "subject": "Test", "html_content": "<p>Test</p>"})

    def test_uncertain_and_interrupted_submissions_are_not_automatically_replayed(self):
        self.transport.outcomes.extend([SendResult("uncertain", "Reply lost"), SendResult("accepted", "Accepted")])
        task = self.create_task([recipient("unknown@example.com"), recipient("accepted@example.com")])
        self.service.engine.start(task["id"])
        completed = self.wait_for_task(self.service, task["id"])
        self.assertEqual((completed["counts"]["uncertain"], completed["counts"]["accepted"]), (1, 1))
        with self.assertRaises(ValueError):
            self.service.engine.start(task["id"])
        with self.assertRaises(ValueError):
            self.service.engine.retry(task["id"])
        with self.assertRaises(ValueError):
            self.service.engine.retry(task["id"], include_uncertain=True)
        interrupted = self.create_task([recipient("interrupted@example.com"), recipient("pending@example.com")])
        self.service.store.execute("UPDATE recipients SET status='sending' WHERE id=?", (interrupted["recipients"][0]["id"],))
        self.service.store.set_status(interrupted["id"], "running")
        restored = self.make_service("service", demo=True, transport=self.transport)
        recovered = restored.task(interrupted["id"])
        self.assertEqual((recovered["status"], recovered["counts"]["uncertain"], recovered["counts"]["pending"]), ("paused", 1, 1))
        restored.engine.start(interrupted["id"])
        resumed = self.wait_for_task(restored, interrupted["id"])
        self.assertEqual((resumed["counts"]["uncertain"], resumed["counts"]["accepted"]), (1, 1))
        self.assertEqual([call["recipient"]["email"] for call in self.transport.calls],
                         ["unknown@example.com", "accepted@example.com", "pending@example.com"])
        self.assertEqual(restored.task(task["id"])["counts"]["uncertain"], 1)
        self.transport.outcomes.append(SendResult("invalid-backend-status", "Unexpected status fixture"))
        malformed = self.create_task([recipient("malformed@example.com"), recipient("untouched@example.com")], service=restored)
        before = len(self.transport.calls)
        restored.engine.start(malformed["id"])
        stopped = self.wait_for_task(restored, malformed["id"])
        self.assertEqual((stopped["counts"]["uncertain"], stopped["counts"]["pending"]), (1, 1))
        self.assertEqual(len(self.transport.calls), before + 1)
        self.assertEqual(self.transport.calls[-1]["recipient"]["email"], "malformed@example.com")

    def test_successful_automatic_and_manual_retries_leave_no_failed_recipient(self):
        for retryable in (True, False):
            with self.subTest(retryable=retryable):
                self.transport.outcomes.extend([SendResult("failed", "Initial failure", retryable=retryable, code=451 if retryable else 550),
                                                SendResult("accepted", "Accepted after retry")])
                task = self.create_task([recipient(f"retry-{retryable}@example.com")])
                before = len(self.transport.calls)
                self.service.engine.start(task["id"])
                current = self.wait_for_task(self.service, task["id"])
                if not retryable:
                    self.assertEqual(current["counts"]["failed"], 1)
                    self.service.engine.retry(task["id"])
                    current = self.wait_for_task(self.service, task["id"])
                self.assertEqual(current["status"], "completed")
                self.assertEqual((current["counts"]["accepted"], current["counts"]["failed"], current["counts"]["total"]), (1, 0, 1))
                self.assertEqual(current["recipients"][0]["detail"], "Accepted after retry")
                with self.assertRaises(ValueError):
                    self.service.export_task(task["id"], "failed")
                calls = self.transport.calls[before:]
                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[0]["message_id"], calls[1]["message_id"])
                history = self.service.store.all("SELECT status FROM attempts WHERE recipient_id=? ORDER BY id", (task["recipients"][0]["id"],))
                self.assertEqual([row["status"] for row in history], ["failed", "accepted"])

    def test_double_start_and_stopping_keep_the_execution_lock(self):
        entered, release = threading.Event(), threading.Event()

        def block_submission():
            entered.set()
            if not release.wait(1.5):
                raise AssertionError("Test did not release the fake submission")

        self.transport.on_send = block_submission
        first = self.create_task([recipient("first@example.com"), recipient("not-started@example.com")])
        second = self.create_task([recipient("second-task@example.com")])
        try:
            self.service.engine.start(first["id"])
            self.assertTrue(entered.wait(1))
            with self.assertRaises(ValueError):
                self.service.engine.start(second["id"])
            stopping = self.service.engine.pause(first["id"])
            self.assertEqual(stopping["status"], "stopping")
            self.assertTrue(self.service.engine.busy)
            for action in (lambda: self.service.engine.start(first["id"]),
                           lambda: self.service.engine.start(second["id"]), self.service.backup,
                           lambda: self.service.engine.test_send({"account_id": self.account["id"]})):
                with self.assertRaises(ValueError):
                    action()
        finally:
            release.set()
        paused = self.wait_for_task(self.service, first["id"])
        self.assertEqual((paused["status"], paused["counts"]["accepted"], paused["counts"]["pending"]), ("paused", 1, 1))
        self.assertEqual(self.service.task(second["id"])["status"], "ready")
        self.assertEqual(len(self.transport.calls), 1)

    def test_storage_failure_after_submission_stops_and_recovers_as_uncertain(self):
        submitted, entered, release = threading.Event(), threading.Event(), threading.Event()

        def finish_submission():
            entered.set()
            if not release.wait(1.5):
                raise AssertionError("Test did not release the fake submission")
            submitted.set()

        self.transport.on_send = finish_submission
        task = self.create_task([recipient("committed@example.com"), recipient("still-pending@example.com")])
        real_transaction = self.service.store.transaction

        @contextlib.contextmanager
        def failing_transaction():
            if submitted.is_set():
                raise sqlite3.OperationalError("disk full fixture")
            with real_transaction() as database:
                yield database

        with patch.object(self.service.store, "transaction", failing_transaction):
            try:
                self.service.engine.start(task["id"])
                self.assertTrue(entered.wait(1))
                release.set()
                self.service.engine.thread.join(timeout=1)
                self.assertFalse(self.service.engine.thread.is_alive())
                self.assertFalse(self.service.engine.busy)
            finally:
                release.set()
        stopped = self.service.task(task["id"])
        self.assertEqual((stopped["status"], stopped["pause_reason"]), ("paused", "storage_error"))
        self.assertIn("runtime_error", stopped)
        self.assertEqual(len(self.transport.calls), 1)
        self.assert_conserved(stopped["counts"])
        restored = self.make_service("service", demo=True, transport=self.transport)
        recovered = restored.task(task["id"])
        self.assertEqual((recovered["counts"]["uncertain"], recovered["counts"]["pending"]), (1, 1))
        self.transport.on_send = None
        restored.engine.start(task["id"])
        completed = self.wait_for_task(restored, task["id"])
        self.assertEqual((completed["counts"]["uncertain"], completed["counts"]["accepted"]), (1, 1))
        self.assertEqual([call["recipient"]["email"] for call in self.transport.calls], ["committed@example.com", "still-pending@example.com"])

    def test_backup_restore_preserves_data_but_not_credentials(self):
        live = self.make_service("live", demo=False, transport=self.transport)
        account = self.save_account(live)
        config = self.config([recipient("backup@example.com")], service=live, account=account)
        attachment = live.add_file("materials.pdf", b"%PDF-fixture", "attachment")
        config["attachment_id"] = attachment["id"]
        task = live.create_task(config)
        draft = live.save_draft({"title": "Draft", "config": {"subject": "Draft", "password": "DRAFT-SECRET", "token": "TOKEN-SECRET"}})
        live.store.execute("UPDATE accounts SET secret=? WHERE id=?", ("ENCRYPTED-SECRET-fixture", account["id"]))
        backup = live.backup()
        _, backup_path = live.file(backup["export_id"], "export")
        content = backup_path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertEqual(json.loads(archive.read("manifest.json"))["secrets_included"], False)
            database = self.root / "backup-check.sqlite3"
            database.write_bytes(archive.read("yunyoubao.sqlite3"))
        with contextlib.closing(sqlite3.connect(database)) as db:
            self.assertIsNone(db.execute("SELECT secret FROM accounts WHERE id=?", (account["id"],)).fetchone()[0])
        for secret in (b"MEMORY-SECRET-fixture", b"ENCRYPTED-SECRET-fixture", b"DRAFT-SECRET", b"TOKEN-SECRET"):
            self.assertNotIn(secret, database.read_bytes())
        target = self.make_service("restored", demo=False, transport=self.transport)
        self.assertEqual(target.restore(content)["status"], "success")
        restored_account = target.accounts()[0]
        self.assertEqual(restored_account["id"], account["id"])
        self.assertFalse(restored_account["has_secret"])
        self.assertEqual(target.memory_secrets, {})
        with self.assertRaises(ValueError):
            target.sender(account["id"])
        self.assertEqual(target.task(task["id"])["counts"], task["counts"])
        self.assertEqual(target.drafts()[0]["id"], draft["id"])
        self.assertEqual(target.drafts()[0]["config"], {"subject": "Draft"})
        self.assertEqual(target.file(config["import_id"], "import")[1].read_bytes(), csv_bytes([recipient("backup@example.com")]))
        self.assertEqual(target.attachment(attachment["id"])[1].read_bytes(), b"%PDF-fixture")
        rollback_files = target.store.all("SELECT id FROM files WHERE kind='export'")
        self.assertEqual(len(rollback_files), 1)
        rollback_record, rollback_path = target.file(rollback_files[0]["id"], "export")
        self.assertTrue(rollback_record["filename"].endswith(".zip"))
        with zipfile.ZipFile(rollback_path) as archive:
            self.assertIn("yunyoubao.sqlite3", archive.namelist())
            self.assertFalse(json.loads(archive.read("manifest.json"))["secrets_included"])

    def test_zip_traversal_is_rejected_before_data_changes(self):
        task = self.create_task()
        backup = self.service.backup()
        _, path = self.service.file(backup["export_id"], "export")
        content = path.read_bytes()
        original_accounts, original_tasks = self.service.accounts(), self.service.tasks()
        paths = ("../escape.txt", "../../escape.txt", "/absolute.txt", "C:/escape.txt", "files\\..\\..\\escape.txt", "\\\\server\\share\\escape.txt")
        for name in paths:
            with self.subTest(path=name):
                stream = io.BytesIO()
                with zipfile.ZipFile(io.BytesIO(content)) as source, zipfile.ZipFile(stream, "w") as target:
                    for entry in source.infolist():
                        target.writestr(entry.filename, source.read(entry))
                    target.writestr(name, b"escape fixture")
                with self.assertRaises(ValueError):
                    self.service.restore(stream.getvalue())
                self.assertEqual(self.service.accounts(), original_accounts)
                self.assertEqual(self.service.tasks(), original_tasks)
                self.assertEqual(self.service.task(task["id"])["counts"]["pending"], 1)
                self.assertFalse((self.root / "escape.txt").exists())

    def test_legacy_import_is_read_only_and_omits_secrets(self):
        legacy = self.root / "legacy"
        (legacy / "state").mkdir(parents=True)
        checkpoint = legacy / "state" / "checkpoint.json"
        checkpoint.write_text(json.dumps({"config": {"subject": "Old notice", "html_content": "<p>Old</p>",
            "password": "LEGACY-SECRET", "senders_text": "sender@example.com LEGACY-SECRET", "attachment_path": "C:/old/private.pdf"},
            "sent_emails": ["accepted@example.com"], "failed_recipients": [{"email": "failed@example.com", "name": "Failed"}, {"email": "accepted@example.com"}],
            "uncertain_recipients": [{"email": "uncertain@example.com", "name": "Unknown"}]}), encoding="utf-8")
        original = checkpoint.read_bytes()
        task = self.service.import_legacy(legacy)
        self.assertEqual((task["legacy"], task["status"]), (1, "legacy"))
        self.assertEqual((task["counts"]["accepted"], task["counts"]["failed"], task["counts"]["uncertain"], task["counts"]["total"]), (1, 1, 1, 3))
        self.assert_conserved(task["counts"])
        serialized = json.dumps(task)
        self.assertNotIn("LEGACY-SECRET", serialized)
        self.assertNotIn("C:/old/private.pdf", serialized)
        for action in (lambda: self.service.engine.start(task["id"]), lambda: self.service.engine.retry(task["id"]),
                       lambda: self.service.import_legacy(legacy)):
            with self.assertRaises(ValueError):
                action()
        exported = self.service.export_task(task["id"], "all")
        self.assertTrue(self.service.file(exported["export_id"], "export")[1].is_file())
        self.assertEqual(checkpoint.read_bytes(), original)
        self.assertEqual(self.transport.calls, [])

    def test_default_demo_transport_never_opens_a_socket(self):
        demo = self.make_service("default-demo", demo=True)
        with patch("socket.socket", side_effect=AssertionError("Demo must not create sockets")):
            imported = demo.demo_import()
            config = {"import_id": imported["import_id"], "sheet": imported["default_sheet"],
                      "name_column": "\u59d3\u540d", "email_column": "\u90ae\u7bb1", "account_ids": [demo.accounts()[0]["id"]],
                      "filters": [{"column": "\u59d3\u540d", "values": ["\u793a\u4f8b\u5b66\u545801"]}],
                      "subject": "Demo", "html_content": "<p>{{\u59d3\u540d}}</p>"}
            preview = demo.preview_import(config["import_id"], config)
            self.assertEqual((preview["counts"]["sendable"], preview["counts"]["duplicates"]), (1, 1))
            config["revision"] = preview["revision"]
            task = demo.create_task(config)
            demo.engine.start(task["id"])
            self.assertEqual(self.wait_for_task(demo, task["id"])["counts"]["accepted"], 1)
            result = demo.engine.test_send({"account_id": demo.accounts()[0]["id"], "test_email": "demo-test@example.com",
                                            "subject": "Demo", "html_content": "<p>Demo</p>"})
            self.assertEqual(result["status"], "accepted")
            for position, expected_status in ((3, "uncertain"), (6, "failed")):
                with self.subTest(demo_status=expected_status):
                    demo.set_suppressions("")
                    config["filters"][0]["values"] = [f"\u793a\u4f8b\u5b66\u5458{i:02}" for i in range(1, position + 2)]
                    config["revision"] = demo.preview_import(config["import_id"], config)["revision"]
                    retry_task = demo.create_task(config)
                    chosen = retry_task["recipients"][position]
                    demo.set_suppressions("\n".join(f"learner{i:02}@example.com" for i in range(1, position + 1)))
                    demo.engine.start(retry_task["id"])
                    processed = self.wait_for_task(demo, retry_task["id"])
                    self.assertEqual(processed["recipients"][position]["status"], expected_status)
                    demo.engine.retry(retry_task["id"], [chosen["id"]], include_uncertain=expected_status == "uncertain")
                    retried = self.wait_for_task(demo, retry_task["id"])
                    self.assertEqual(retried["recipients"][position]["status"], "accepted")
                    self.assertEqual(retried["counts"]["uncertain"], 0)
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.service.tasks(), [])
        self.assertEqual(len(self.service.accounts()), 1)

    def test_api_auth_host_origin_mode_and_file_id_boundaries(self):
        # main's module-level app must also use temporary storage on first import.
        with patch.dict(os.environ, {"YUNYOUBAO_DATA_DIR": str(self.root / "import-main")}):
            from main import create_app
        app = create_app(self.root / "api", transport_factory=lambda: self.transport, allowed_hosts={"testserver"})
        headers = {"Authorization": "Bearer " + app.state.token, "x-yunyoubao-mode": "live"}
        demo_headers = dict(headers, **{"x-yunyoubao-mode": "demo"})
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/accounts").status_code, 401)
            self.assertEqual(client.get("/api/accounts", headers=dict(headers, Authorization="Bearer wrong")).status_code, 401)
            self.assertEqual(client.get("/api/accounts", headers=dict(headers, Host="evil.example")).status_code, 403)
            self.assertEqual(client.get("/api/accounts", headers=dict(headers, Origin="https://evil.example")).status_code, 403)
            self.assertEqual(client.get("/api/accounts", headers=dict(headers, Origin="http://testserver")).status_code, 200)
            self.assertEqual(client.get("/api/accounts", headers=dict(headers, **{"x-yunyoubao-mode": "invalid"})).status_code, 400)
            saved = client.post("/api/accounts", headers=headers, json={"email": "api@example.com", "smtp_host": "smtp.invalid",
                "security": "ssl", "smtp_port": 465, "password": "API-SECRET", "remember": False, "per_minute": 120})
            self.assertEqual(saved.status_code, 200, saved.text)
            self.assertNotIn("API-SECRET", saved.text)
            self.assertTrue(saved.json()["has_secret"])
            self.assertEqual(client.get("/api/accounts", headers=demo_headers).json()["accounts"], [])
            self.assertEqual(client.get("/api/demo/import", headers=demo_headers).status_code, 200)
            self.assertEqual(len(client.get("/api/accounts", headers=headers).json()["accounts"]), 1)
            self.assertEqual(client.post("/api/attachments", headers=headers,
                             files={"file": ("../escape.pdf", b"%PDF-fixture", "application/pdf")}).status_code, 400)
            attachment = client.post("/api/attachments", headers=headers,
                                     files={"file": ("fixture.pdf", b"%PDF-fixture", "application/pdf")})
            self.assertEqual(attachment.status_code, 200, attachment.text)
            live = app.state.services["live"]
            task = self.create_task(service=live, account=saved.json())
            exported = client.post(f"/api/tasks/{task['id']}/export", headers=headers, json={"scope": "all"})
            self.assertEqual(exported.status_code, 200, exported.text)
            file_id = exported.json()["export_id"]
            downloaded = client.get("/api/exports/" + file_id, headers=headers)
            self.assertEqual(downloaded.status_code, 200)
            self.assertTrue(downloaded.content.startswith(b"PK"))
            self.assertEqual(client.get("/api/exports/" + file_id, headers=demo_headers).status_code, 404)
            self.assertEqual(client.get("/api/exports/" + attachment.json()["attachment_id"], headers=headers).status_code, 404)
            self.assertEqual(client.get("/api/exports/not-a-file-id", headers=headers).status_code, 404)
            sent = client.post("/api/test-send", headers=headers, json={"account_id": saved.json()["id"],
                "test_email": "api-test@example.com", "subject": "Test", "html_content": "<p>Test</p>"})
            self.assertEqual(sent.status_code, 200, sent.text)
            self.assertEqual(sent.json()["status"], "accepted")
        self.assertEqual(len(self.transport.calls), 1)


if __name__ == "__main__":
    unittest.main()
