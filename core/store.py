import contextlib
import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path


def timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "yunyoubao.sqlite3"
        self.lock = threading.RLock()
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY, email_key TEXT UNIQUE NOT NULL,
                    payload TEXT NOT NULL, secret TEXT, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, filename TEXT NOT NULL,
                    relative_path TEXT NOT NULL, digest TEXT NOT NULL, size INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL,
                    config TEXT NOT NULL, pause_reason TEXT NOT NULL DEFAULT '',
                    legacy INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS recipients (
                    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL, name TEXT NOT NULL, email TEXT NOT NULL,
                    email_key TEXT NOT NULL, row_values TEXT NOT NULL,
                    status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0,
                    message_id TEXT NOT NULL,
                    UNIQUE(task_id, email_key)
                );
                CREATE INDEX IF NOT EXISTS recipient_task ON recipients(task_id, position);
                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY, recipient_id TEXT NOT NULL REFERENCES recipients(id) ON DELETE CASCADE,
                    status TEXT NOT NULL, detail TEXT NOT NULL, code INTEGER,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS quotas (
                    account_key TEXT NOT NULL, day TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0, last_attempt REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY(account_key, day)
                );
                CREATE TABLE IF NOT EXISTS suppressions (email_key TEXT PRIMARY KEY, email TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS drafts (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, config TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    time TEXT NOT NULL, message TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS migrations (source TEXT PRIMARY KEY, created_at TEXT NOT NULL);
                PRAGMA user_version=1;
            """)

    @contextlib.contextmanager
    def transaction(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=15)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            try:
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    def all(self, sql, parameters=()):
        with self.transaction() as db:
            return [dict(row) for row in db.execute(sql, parameters).fetchall()]

    def one(self, sql, parameters=()):
        rows = self.all(sql, parameters)
        return rows[0] if rows else None

    def execute(self, sql, parameters=()):
        with self.transaction() as db:
            return db.execute(sql, parameters).rowcount

    def log(self, task_id, message):
        self.execute("INSERT INTO logs(task_id,time,message) VALUES(?,?,?)", (task_id, timestamp(), message))

    def set_status(self, task_id, status, reason=""):
        self.execute("UPDATE tasks SET status=?,pause_reason=?,updated_at=? WHERE id=?",
                     (status, reason, timestamp(), task_id))

    def recover(self):
        # Sending is deliberately committed before SMTP: a crash cannot imply failure.
        with self.transaction() as db:
            db.execute("UPDATE recipients SET status='uncertain',detail=? WHERE status='sending'",
                       ("程序曾在提交期间退出，请人工确认，未自动重发。",))
            db.execute("UPDATE tasks SET status='paused',pause_reason='interrupted',updated_at=? "
                       "WHERE status IN ('starting','running','stopping')", (timestamp(),))

    def counts(self, task_id, db=None):
        counts = dict.fromkeys(("pending", "sending", "accepted", "failed", "uncertain"), 0)
        query = "SELECT status,COUNT(*) AS n FROM recipients WHERE task_id=? GROUP BY status"
        rows = db.execute(query, (task_id,)).fetchall() if db else self.all(query, (task_id,))
        for row in rows:
            if row["status"] in counts:
                counts[row["status"]] = row["n"]
        counts["total"] = sum(counts.values())
        return counts
