import datetime as dt
import hashlib
import io
import json
import math
import re
import shutil
import sqlite3
import tempfile
import threading
import uuid
import zipfile
from functools import wraps
from collections import Counter, defaultdict
from pathlib import Path, PureWindowsPath

import pandas as pd

from . import credentials
from .email_sender import EmailSenderCore
from .store import Store, encode, timestamp


MAX_UPLOAD = 20 * 1024 * 1024
MAX_EXPANDED = 100 * 1024 * 1024
MAX_BACKUP = 100 * 1024 * 1024
ACTIVE = ("starting", "running", "stopping")


def uid():
    return uuid.uuid4().hex


def clean(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def email_key(email):
    local, domain = email.strip().rsplit("@", 1)
    domain = domain.lower()
    if domain in {"qq.com", "163.com"}:
        local = local.lower()
    return local + "@" + domain


def excel_safe(value):
    text = clean(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def mail_subject(config):
    subject = clean(config.get("subject"))
    if config.get("purpose") == "promotion" and not re.match(r"^(广告|AD)\b|^广告", subject, re.I):
        subject = "AD " + subject
    return subject


def idle_operation(function):
    @wraps(function)
    def guarded(self, *args, **kwargs):
        if getattr(self.operations, "owned", False):
            return function(self, *args, **kwargs)
        if not self.engine.lock.acquire(blocking=False):
            raise ValueError("请等待任务或测试停止后再修改数据。")
        self.operations.owned = True
        try:
            return function(self, *args, **kwargs)
        finally:
            self.operations.owned = False
            self.engine.lock.release()
    return guarded


class ProductService:
    def __init__(self, root, demo=False, transport_factory=None):
        self.store = Store(root)
        self.root = self.store.root
        self.demo = demo
        self.memory_secrets = {}
        self.operations = threading.local()
        self.store.recover()
        from .engine import TaskEngine
        self.engine = TaskEngine(self, transport_factory)

    def active(self):
        return (self.engine.busy and not getattr(self.operations, "owned", False)) or bool(self.store.one(
            "SELECT id FROM tasks WHERE status IN ('starting','running','stopping')"))

    def require_idle(self):
        if self.active():
            raise ValueError("请先暂停任务，并等待发送线程停止。")

    def accounts(self):
        result = []
        for row in self.store.all("SELECT * FROM accounts ORDER BY updated_at,id"):
            item = json.loads(row["payload"])
            item["has_secret"] = self.demo or bool(row["secret"] or self.memory_secrets.get(row["id"]))
            result.append(item)
        return result

    @idle_operation
    def save_account(self, data):
        self.require_idle()
        identifier = clean(data.get("id")) or uid()
        old = self.store.one("SELECT * FROM accounts WHERE id=?", (identifier,))
        email = clean(data.get("email"))
        if not EmailSenderCore.validate_email(email):
            raise ValueError("发件邮箱格式不正确。")
        key = email_key(email)
        if old and old["email_key"] != key:
            raise ValueError("修改发件邮箱请新建账号，避免历史任务关联错误。")
        duplicate = self.store.one("SELECT id FROM accounts WHERE email_key=? AND id<>?", (key, identifier))
        if duplicate:
            raise ValueError("此邮箱已在账号列表中。")
        domain = email.rsplit("@", 1)[1].lower()
        host = clean(data.get("smtp_host")) or {"qq.com": "smtp.qq.com", "163.com": "smtp.163.com"}.get(domain, "")
        if not re.fullmatch(r"[a-zA-Z0-9.-]+", host) or ".." in host:
            raise ValueError("请填写有效的 SMTP 主机。")
        security = data.get("security", "starttls" if domain == "qq.com" else "ssl")
        if security not in {"ssl", "starttls"}:
            raise ValueError("SMTP 必须使用 SSL 或 STARTTLS。")
        port = int(data.get("smtp_port") or (465 if security == "ssl" else 587))
        rate = int(data.get("per_minute", 6))
        limit = int(data.get("daily_limit", 200))
        if not 1 <= port <= 65535 or not 1 <= rate <= 120 or not 1 <= limit <= 100000:
            raise ValueError("端口或发送预算超出范围；每分钟 1–120 封，每日 1–100000 封。")
        name = clean(data.get("name")) or email.split("@")[0]
        if len(name) > 100 or any(ch in name for ch in "\r\n"):
            raise ValueError("发件人名称不正确。")
        remember = bool(data.get("remember", True))
        secret = clean(data.get("password"))
        if len(secret) > 512 or any(ch in secret for ch in "\r\n"):
            raise ValueError("授权码格式不正确。")
        if not secret and old:
            secret = self.memory_secrets.get(identifier, "")
            if not secret and old["secret"]:
                secret = credentials.unprotect(old["secret"])
        if not secret and not self.demo:
            raise ValueError("请填写 SMTP 授权码。")
        payload = {"id": identifier, "email": email, "name": name, "smtp_host": host,
                   "smtp_port": port, "security": security, "remember": remember,
                   "per_minute": rate, "daily_limit": limit}
        encrypted = credentials.protect(secret) if remember and not self.demo else None
        self.store.execute("INSERT INTO accounts VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                           "payload=excluded.payload,secret=excluded.secret,updated_at=excluded.updated_at",
                           (identifier, key, encode(payload), encrypted, timestamp()))
        if not remember and secret:
            self.memory_secrets[identifier] = secret
        else:
            self.memory_secrets.pop(identifier, None)
        return next(account for account in self.accounts() if account["id"] == identifier)

    @idle_operation
    def delete_account(self, identifier):
        self.require_idle()
        self.store.execute("DELETE FROM accounts WHERE id=?", (identifier,))
        self.memory_secrets.pop(identifier, None)

    def sender(self, identifier, profile=None):
        row = self.store.one("SELECT * FROM accounts WHERE id=?", (identifier,))
        if not row:
            raise ValueError("任务使用的账号已删除，请创建新任务并核对名单。")
        account = profile or json.loads(row["payload"])
        password = "demonstration-only" if self.demo else self.memory_secrets.get(identifier, "")
        if not password and row["secret"]:
            password = credentials.unprotect(row["secret"])
        if not password:
            raise ValueError("此账号未保存授权码，请在账号设置中重新填写。")
        return dict(account, password=password, smtp_server=account["smtp_host"])

    def file(self, identifier, kind=None):
        row = self.store.one("SELECT * FROM files WHERE id=?", (identifier,))
        if not row or (kind and row["kind"] != kind):
            raise KeyError("文件不存在。")
        path = (self.root / row["relative_path"]).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise ValueError("文件已丢失，请重新上传。")
        return row, path

    def add_file(self, filename, content, kind):
        if filename != Path(filename).name or filename != PureWindowsPath(filename).name:
            raise ValueError("文件名不能包含路径。")
        maximum = MAX_BACKUP if kind == "export" else MAX_UPLOAD
        if not content or len(content) > maximum:
            raise ValueError(f"请选择非空文件，最大 {maximum // (1024 * 1024)} MiB。")
        suffix = Path(filename).suffix.lower()
        allowed = {"import": {".xlsx", ".csv"}, "attachment": {".pdf"}, "export": {".xlsx", ".zip"}}
        if suffix not in allowed[kind]:
            raise ValueError("不支持该文件格式。")
        if suffix == ".pdf" and not content.startswith(b"%PDF-"):
            raise ValueError("附件不是有效的 PDF 文件。")
        if suffix == ".xlsx":
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    if len(archive.infolist()) > 10000 or sum(item.file_size for item in archive.infolist()) > MAX_EXPANDED:
                        raise ValueError("工作簿展开后过大。")
            except zipfile.BadZipFile:
                raise ValueError("文件不是有效的 xlsx 工作簿。") from None
        identifier = uid()
        relative = Path("exports" if kind == "export" else "files") / (identifier + ("-" + filename if kind == "export" else suffix))
        (self.root / relative.parent).mkdir(exist_ok=True)
        path = self.root / relative
        with path.open("xb") as stream:
            stream.write(content)
        row = (identifier, kind, filename, relative.as_posix(), hashlib.sha256(content).hexdigest(), len(content), timestamp())
        try:
            self.store.execute("INSERT INTO files VALUES(?,?,?,?,?,?,?)", row)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return {"id": identifier, "filename": filename, "size": len(content)}

    def dataframe(self, identifier, sheet=None):
        record, path = self.file(identifier, "import")
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["digest"]:
            raise ValueError("导入副本已改变，请重新上传；已冻结任务不受影响。")
        if path.suffix == ".csv":
            try:
                frame = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False, nrows=50001)
            except UnicodeDecodeError:
                frame = pd.read_csv(path, encoding="gb18030", dtype=str, keep_default_na=False, nrows=50001)
            sheets = ["CSV"]
        else:
            with pd.ExcelFile(path, engine="openpyxl") as workbook:
                sheets = workbook.sheet_names
                selected = sheet or sheets[0]
                if selected not in sheets:
                    raise ValueError("工作表不存在。")
                frame = pd.read_excel(workbook, sheet_name=selected, dtype=str, keep_default_na=False, nrows=50001)
        if len(frame) > 50000 or len(frame.columns) > 100:
            raise ValueError("单张名单最多 50000 行、100 列。")
        frame.columns = [clean(column) for column in frame.columns]
        if any(not column for column in frame.columns):
            raise ValueError("请为每一列填写表头。")
        return frame.fillna(""), sheets

    def import_file(self, filename, content):
        item = self.add_file(filename, content, "import")
        frame, sheets = self.dataframe(item["id"])
        sheet_columns = {sheets[0]: list(frame.columns)}
        if len(sheets) > 1:
            _, path = self.file(item["id"], "import")
            with pd.ExcelFile(path, engine="openpyxl") as workbook:
                sheet_columns = {name: [clean(column) for column in pd.read_excel(workbook, sheet_name=name, nrows=0).columns]
                                 for name in sheets}
        return {"import_id": item["id"], "filename": filename, "sheets": sheets, "sheet_columns": sheet_columns,
                "default_sheet": sheets[0], "columns": list(frame.columns), "total_rows": len(frame)}

    def demo_import(self):
        if not self.demo:
            raise ValueError("演示名单仅在演示模式提供。")
        if not self.accounts():
            self.save_account({"email": "demo@example.com", "name": "云邮宝演示", "smtp_host": "smtp.invalid",
                               "remember": False, "per_minute": 120, "daily_limit": 200})
        rows = [{"姓名": f"示例学员{i:02}", "邮箱": f"learner{i:02}@example.com", "单位": "示例机构",
                 "分工": ["工作人员 A", "工作人员 B", "工作人员 C"][(i - 1) % 3],
                 "类别": "培训" if i % 2 else "会议", "省内/省外": "省内" if i % 3 else "省外"}
                for i in range(1, 31)]
        rows += [dict(rows[0]), {"姓名": "无效示例", "邮箱": "not-an-address", "单位": "示例机构", "分工": "工作人员 A", "类别": "培训", "省内/省外": "省内"}]
        stream = io.BytesIO()
        pd.DataFrame(rows).to_excel(stream, index=False, engine="openpyxl")
        return self.import_file("演示分工名单.xlsx", stream.getvalue())

    def suppression_content(self):
        return "\n".join(row["email"] for row in self.store.all("SELECT email FROM suppressions ORDER BY email"))

    def set_suppressions(self, content):
        result = {}
        for line in content.splitlines():
            email = line.strip()
            if not email or email.startswith("#"):
                continue
            if not EmailSenderCore.validate_email(email):
                raise ValueError("排除名单含格式错误的邮箱，请检查。")
            result[email_key(email)] = email
        with self.store.transaction() as db:
            db.execute("DELETE FROM suppressions")
            db.executemany("INSERT INTO suppressions VALUES(?,?)", result.items())
        return {"content": self.suppression_content(), "count": len(result)}

    def precheck(self, identifier, config):
        frame, sheets = self.dataframe(identifier, config.get("sheet"))
        columns = list(frame.columns)
        email_column = config.get("email_column", "")
        name_column = config.get("name_column", "")
        if email_column not in columns or (name_column and name_column not in columns):
            raise ValueError("请确认邮箱列和姓名列，不能自动回退到其他列。")
        conditions = []
        for item in config.get("filters", []):
            column = item.get("column")
            values = {clean(value) for value in item.get("values", [])}
            if column not in columns or not values:
                raise ValueError("请选择筛选列和至少一个值，或移除此筛选条件。")
            conditions.append((column, values))
        filter_values = {column: [{"value": value, "count": count} for value, count in
                                 sorted(Counter(clean(value) for value in frame[column]).items())]
                         for column in columns}
        excluded = {row["email_key"] for row in self.store.all("SELECT email_key FROM suppressions")}
        selected, grouped = [], defaultdict(list)
        for position, raw in enumerate(frame.to_dict("records"), 2):
            values = {key: clean(value) for key, value in raw.items()}
            if not all(values[column] in allowed for column, allowed in conditions):
                continue
            email = values[email_column]
            name = " ".join(values.get(name_column, "").split()) or "收件人"
            item = {"row_number": position, "values": values, "name": name, "email": email,
                    "status": "valid", "reason": ""}
            if not EmailSenderCore.validate_email(email):
                item.update(status="invalid", reason="邮箱格式不正确")
            elif email_key(email) in excluded:
                item.update(status="excluded", reason="命中退订／排除名单")
            else:
                grouped[email_key(email)].append(item)
            selected.append(item)
        for group in grouped.values():
            if len({row["name"] for row in group}) > 1:
                for row in group:
                    row.update(status="conflict", reason="同一邮箱对应不同姓名，请调整名单或筛选")
            else:
                for row in group[1:]:
                    row.update(status="duplicate", reason="相同邮箱重复，仅保留第一行")
        counts = Counter(row["status"] for row in selected)
        record, _ = self.file(identifier, "import")
        digest_input = {"file": record["digest"], "sheet": config.get("sheet") or sheets[0],
                        "name": name_column, "email": email_column,
                        "filters": sorted((column, sorted(values)) for column, values in conditions),
                        "excluded": sorted(excluded)}
        revision = hashlib.sha256(encode(digest_input).encode()).hexdigest()
        return {"import_id": identifier, "columns": columns, "filter_values": filter_values, "revision": revision,
                "counts": {"total": len(frame), "selected": len(selected), "invalid": counts["invalid"],
                           "duplicates": counts["duplicate"], "excluded": counts["excluded"],
                           "conflicts": counts["conflict"], "sendable": counts["valid"]}, "rows": selected}

    def preview_import(self, identifier, config):
        frame, _ = self.dataframe(identifier, config.get("sheet"))
        if config.get("email_column") not in frame.columns:
            return {"import_id": identifier, "columns": list(frame.columns), "rows": [], "revision": None,
                    "mapping_required": True, "filter_values": {column: [{"value": value, "count": count}
                    for value, count in sorted(Counter(clean(v) for v in frame[column]).items())] for column in frame.columns},
                    "counts": dict(total=len(frame), selected=0, invalid=0, duplicates=0, excluded=0, conflicts=0, sendable=0)}
        result = self.precheck(identifier, config)
        offset = max(0, int(config.get("offset", 0)))
        limit = min(100, max(1, int(config.get("limit", 50))))
        result["rows"] = result["rows"][offset:offset + limit]
        return result

    def attachment(self, identifier):
        if not identifier:
            return None, None
        item, path = self.file(identifier, "attachment")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["digest"]:
            raise ValueError("附件已被修改，请重新上传并核对。")
        return item, path

    def preview_email(self, config):
        from .email_sender import render_email
        recipients = [row for row in self.precheck(config["import_id"], config)["rows"] if row["status"] == "valid"]
        if not recipients:
            raise ValueError("没有有效样例收件人。")
        index = max(0, min(len(recipients) - 1, int(config.get("recipient_index", 0))))
        sender = next((account for account in self.accounts() if account["id"] == config.get("account_id")),
                      {"email": "sender@example.com", "name": "示例发件人"})
        result = render_email(mail_subject(config), config.get("html_content", ""), recipients[index], sender,
                              bool(config.get("add_unsubscribe", True)))
        item, _ = self.attachment(config.get("attachment_id"))
        return dict(result, recipient=recipients[index], attachment_name=item["filename"] if item else "")

    def create_task(self, config):
        from .email_sender import render_email
        result = self.precheck(config["import_id"], config)
        if result["revision"] != config.get("revision"):
            raise ValueError("名单核对已过期，请重新核对筛选与排除名单。")
        if result["counts"]["conflicts"]:
            raise ValueError("名单存在姓名冲突，请调整源表或筛选后再发送。")
        recipients = [row for row in result["rows"] if row["status"] == "valid"]
        if not recipients:
            raise ValueError("没有有效待发收件人。")
        accounts = {account["id"]: account for account in self.accounts()}
        identifiers = list(dict.fromkeys(config.get("account_ids", [])))
        if not identifiers or any(identifier not in accounts for identifier in identifiers):
            raise ValueError("请选择有效的发件账号。")
        profiles = [accounts[identifier] for identifier in identifiers]
        for profile in profiles:
            self.sender(profile["id"])
        subject = mail_subject(config)
        body = str(config.get("html_content", ""))
        if not subject or (not re.sub(r"<[^>]*>|\s|&nbsp;", "", body) and not re.search(r"<img\b", body, re.I)):
            raise ValueError("请填写主题和正文。")
        if len(subject) > 200 or len(body.encode()) > 8 * 1024 * 1024:
            raise ValueError("主题或正文过长。")
        purpose = config.get("purpose", "notification")
        if purpose not in {"notification", "promotion"}:
            raise ValueError("请选择邮件用途。")
        if purpose == "promotion":
            if not clean(config.get("source_note")):
                raise ValueError("商业推广请填写名单来源与可联系依据。")
        start, end = config.get("start_time", "08:00"), config.get("end_time", "21:40")
        for value in (start, end):
            dt.datetime.strptime(value, "%H:%M")
        item, attachment_path = self.attachment(config.get("attachment_id"))
        frozen = {"import_id": config["import_id"], "sheet": config.get("sheet"),
                  "name_column": config.get("name_column", ""), "email_column": config["email_column"],
                  "filters": config.get("filters", []), "revision": result["revision"],
                  "subject": subject, "html_content": body, "attachment_id": config.get("attachment_id"),
                  "attachment_digest": item["digest"] if item else "", "attachment_name": item["filename"] if item else "",
                  "account_ids": identifiers, "sender_profiles": profiles, "start_time": start, "end_time": end,
                  "add_unsubscribe": bool(config.get("add_unsubscribe", True)), "purpose": purpose,
                  "source_note": clean(config.get("source_note"))}
        for recipient in recipients:
            try:
                render_email(subject, body, recipient, profiles[0], frozen["add_unsubscribe"])
            except ValueError as error:
                raise ValueError(f"表格第 {recipient['row_number']} 行：{error}") from None
        EmailSenderCore().create_email_msg(profiles[0], recipients[0], 1, body, subject,
            attachment_path=str(attachment_path) if attachment_path else None, add_unsubscribe=frozen["add_unsubscribe"])
        identifier, now = uid(), timestamp()
        with self.store.transaction() as db:
            db.execute("INSERT INTO tasks(id,title,status,config,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                       (identifier, clean(config.get("title"))[:100] or subject[:100], "ready", encode(frozen), now, now))
            db.executemany("INSERT INTO recipients(id,task_id,position,name,email,email_key,row_values,status,message_id) "
                           "VALUES(?,?,?,?,?,?,?,?,?)", [(uid(), identifier, position, row["name"], row["email"],
                            email_key(row["email"]), encode(row["values"]), "pending",
                            f"<{uid()}.{identifier}@yunyoubao.local>") for position, row in enumerate(recipients)])
        self.store.log(identifier, f"已冻结名单，拟发 {len(recipients)} 人。")
        return self.task(identifier)

    def task(self, identifier, offset=0, limit=100):
        with self.store.transaction() as db:
            found = db.execute("SELECT * FROM tasks WHERE id=?", (identifier,)).fetchone()
            if not found:
                raise KeyError("任务不存在。")
            row = dict(found)
            row["config"] = json.loads(row["config"])
            row["counts"] = self.store.counts(identifier, db)
            row["recipients"] = [dict(item) for item in db.execute(
                "SELECT id,position,name,email,status,detail,attempts FROM recipients "
                "WHERE task_id=? ORDER BY position LIMIT ? OFFSET ?",
                (identifier, min(100, max(1, int(limit))), max(0, int(offset)))).fetchall()]
            row["logs"] = list(reversed([dict(item) for item in db.execute(
                "SELECT time,message FROM logs WHERE task_id=? ORDER BY id DESC LIMIT 100", (identifier,)).fetchall()]))
        if identifier in self.engine.runtime_errors:
            row.update(status="paused", pause_reason="storage_error", runtime_error=self.engine.runtime_errors[identifier])
        return row

    def tasks(self):
        with self.store.transaction() as db:
            rows = db.execute("SELECT id,title,status,pause_reason,legacy,created_at,updated_at FROM tasks ORDER BY created_at DESC").fetchall()
            return [dict(row, counts=self.store.counts(row["id"], db)) for row in rows]

    def save_draft(self, data):
        allowed = {"import_id", "sheet", "name_column", "email_column", "filters", "revision", "subject",
                   "html_content", "attachment_id", "account_ids", "start_time", "end_time", "add_unsubscribe",
                   "purpose", "source_note", "test_email", "title"}
        config = {key: value for key, value in data.get("config", {}).items() if key in allowed}
        identifier = clean(data.get("id")) or uid()
        title = clean(data.get("title"))[:100] or clean(config.get("subject"))[:100] or "未命名草稿"
        self.store.execute("INSERT INTO drafts VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                           "title=excluded.title,config=excluded.config,updated_at=excluded.updated_at",
                           (identifier, title, encode(config), timestamp()))
        return {"id": identifier, "title": title, "config": config}

    def drafts(self):
        return [dict(row, config=json.loads(row["config"])) for row in self.store.all("SELECT * FROM drafts ORDER BY updated_at DESC")]

    def export_task(self, identifier, scope="failed"):
        self.task(identifier)
        if scope not in {"failed", "all"}:
            raise ValueError("导出范围不正确。")
        sql = "SELECT name,email,status,detail,attempts FROM recipients WHERE task_id=?"
        if scope == "failed":
            sql += " AND status IN ('failed','uncertain')"
        rows = self.store.all(sql + " ORDER BY position", (identifier,))
        if not rows:
            raise ValueError("暂无该范围的记录。")
        labels = {"accepted": "服务器已接收", "uncertain": "待确认", "failed": "失败", "pending": "待发送", "sending": "提交中"}
        for row in rows:
            row["status"] = labels[row["status"]]
            for key in row:
                row[key] = excel_safe(row[key])
        stream = io.BytesIO()
        pd.DataFrame(rows).rename(columns={"name": "姓名", "email": "邮箱", "status": "状态", "detail": "说明", "attempts": "尝试次数"}).to_excel(stream, index=False)
        title = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", self.task(identifier)["title"])[:50]
        filename = f"{title}_{'失败名单' if scope == 'failed' else '任务记录'}_{dt.date.today()}.xlsx"
        item = self.add_file(filename, stream.getvalue(), "export")
        return {"export_id": item["id"], "filename": filename}

    @staticmethod
    def templates():
        return [{"id": "training", "title": "培训通知", "subject": "培训安排通知",
                 "html_content": "<p>{{姓名}}，您好：</p><p>本次培训的时间、地点及准备事项如下。</p><p>期待与您见面。</p>"},
                {"id": "meeting", "title": "会议提醒", "subject": "会议参会提醒",
                 "html_content": "<p>{{姓名}}，您好：</p><p>感谢您报名参加本次会议，请查收会议安排及随附资料。</p>"},
                {"id": "materials", "title": "会后资料", "subject": "培训／会议资料",
                 "html_content": "<p>{{姓名}}，您好：</p><p>感谢您的参与，相关资料请查收附件。</p><p>祝学习顺利。</p>"}]

    @idle_operation
    def backup(self):
        self.require_idle()
        stream = io.BytesIO()
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            database = Path(temporary) / "yunyoubao.sqlite3"
            with self.store.lock:
                source = sqlite3.connect(self.store.path)
                target = sqlite3.connect(database)
                try:
                    source.backup(target)
                    target.execute("UPDATE accounts SET secret=NULL")
                    target.commit()
                finally:
                    source.close()
                    target.close()
            with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(database, "yunyoubao.sqlite3")
                archive.writestr("manifest.json", encode({"schema": 1, "secrets_included": False}))
                for item in self.store.all("SELECT * FROM files WHERE kind<>'export'"):
                    _, path = self.file(item["id"])
                    archive.write(path, item["relative_path"])
        item = self.add_file(f"云邮宝备份_{dt.date.today()}.zip", stream.getvalue(), "export")
        return {"export_id": item["id"], "filename": item["filename"]}

    @idle_operation
    def restore(self, content):
        self.require_idle()
        if len(content) > MAX_BACKUP:
            raise ValueError("备份最大 100 MiB。")
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            stage = Path(temporary).resolve()
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if len(archive.infolist()) > 10000 or sum(item.file_size for item in archive.infolist()) > MAX_EXPANDED:
                    raise ValueError("备份展开后过大。")
                for item in archive.infolist():
                    path = (stage / item.filename).resolve()
                    if not path.is_relative_to(stage) or PureWindowsPath(item.filename).is_absolute() or "\\" in item.filename:
                        raise ValueError("备份包含越界路径。")
                archive.extractall(stage)
            manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
            if manifest.get("schema") != 1 or manifest.get("secrets_included") is not False:
                raise ValueError("备份格式不受支持。")
            source = sqlite3.connect(stage / "yunyoubao.sqlite3")
            source.row_factory = sqlite3.Row
            try:
                if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("备份数据库损坏。")
                if source.execute("SELECT COUNT(*) FROM sqlite_master WHERE type IN ('view','trigger')").fetchone()[0]:
                    raise ValueError("备份包含不受支持的数据库对象。")
                staged_store = Store(stage / "schema-check")
                with staged_store.transaction() as template:
                    tables = [row[0] for row in template.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                    for table in tables:
                        expected = [row[1] for row in template.execute(f"PRAGMA table_info({table})")]
                        actual = [row[1] for row in source.execute(f"PRAGMA table_info({table})")]
                        if expected != actual:
                            raise ValueError("备份数据库结构不受支持。")
                records = {table: [dict(row) for row in source.execute(f"SELECT * FROM {table}")] for table in tables}
                for item in records["files"]:
                    if item["kind"] == "export":
                        continue
                    path = (stage / item["relative_path"]).resolve()
                    if not path.is_relative_to(stage) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item["digest"]:
                        raise ValueError("备份缺少文件，或文件校验不通过。")
                for row in records["accounts"]:
                    row["secret"] = None
                records["files"] = [row for row in records["files"] if row["kind"] != "export"]
                rollback = self.backup()
                rollback_record = self.store.one("SELECT * FROM files WHERE id=?", (rollback["export_id"],))
                records["files"].append(rollback_record)
                # Install files first; failed DB transactions leave only harmless unreferenced copies.
                for item in records["files"]:
                    if item["id"] == rollback["export_id"]:
                        continue
                    target = (self.root / item["relative_path"]).resolve()
                    if not target.is_relative_to(self.root):
                        raise ValueError("文件路径越界。")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != item["digest"]:
                        raise ValueError("恢复文件与当前数据冲突。")
                    if not target.exists():
                        shutil.copyfile(stage / item["relative_path"], target)
                with self.store.transaction() as db:
                    for table in reversed(tables):
                        db.execute(f"DELETE FROM {table}")
                    for table in tables:
                        rows = records[table]
                        if rows:
                            columns = list(rows[0])
                            db.executemany(f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                                           [tuple(row[column] for column in columns) for row in rows])
                self.memory_secrets.clear()
                self.store.recover()
            finally:
                source.close()
        return {"status": "success", "message": "数据已恢复；原数据已自动备份，授权码请重新填写。"}

    def data_info(self):
        return {"path": str(self.root), "size": sum(path.stat().st_size for path in self.root.rglob("*") if path.is_file()), "version": "0.2.0"}

    @idle_operation
    def cleanup(self, data):
        self.require_idle()
        deleted = 0
        if data.get("logs"):
            deleted += self.store.execute("DELETE FROM logs")
        if data.get("unused_imports"):
            used = set()
            for row in self.store.all("SELECT config FROM tasks UNION ALL SELECT config FROM drafts"):
                config = json.loads(row["config"])
                used.update(value for value in (config.get("import_id"), config.get("attachment_id")) if value)
            for item in self.store.all("SELECT * FROM files WHERE kind IN ('import','attachment')"):
                if item["id"] not in used:
                    _, path = self.file(item["id"])
                    path.unlink()
                    self.store.execute("DELETE FROM files WHERE id=?", (item["id"],))
                    deleted += 1
        return {"status": "success", "deleted": deleted}

    @idle_operation
    def import_legacy(self, directory):
        self.require_idle()
        directory = Path(directory).resolve()
        checkpoint = directory / "state" / "checkpoint.json"
        data = json.loads(checkpoint.read_text(encoding="utf-8"))
        source_key = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        if self.store.one("SELECT source FROM migrations WHERE source=?", (source_key,)):
            raise ValueError("这份旧记录已经导入。")
        config = data.get("config", {})
        identifier, now = uid(), timestamp()
        # No credentials or runnable paths from the old JSON enter the new database.
        frozen = {"subject": str(config.get("subject", "")), "html_content": str(config.get("html_content", "")),
                  "account_ids": [], "legacy_notice": "旧版记录缺少可靠名单快照，仅供核对，不可直接续发。"}
        records = {}
        for email in data.get("sent_emails", []):
            if EmailSenderCore.validate_email(email):
                records[email_key(email)] = {"name": "旧版收件人", "email": email, "status": "accepted", "detail": "旧版记录；未验证收件箱投递。"}
        for category, status in (("failed_recipients", "failed"), ("uncertain_recipients", "uncertain")):
            for row in data.get(category, []):
                email = row.get("email", "")
                if EmailSenderCore.validate_email(email) and email_key(email) not in records:
                    records[email_key(email)] = {"name": clean(row.get("name")) or "旧版收件人", "email": email,
                                                "status": status, "detail": "旧版失败／待确认记录，需人工核对。"}
        with self.store.transaction() as db:
            db.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)", (identifier, "旧版：" + frozen["subject"][:80],
                       "legacy", encode(frozen), "legacy_readonly", 1, now, now))
            for position, (key, row) in enumerate(records.items()):
                db.execute("INSERT INTO recipients(id,task_id,position,name,email,email_key,row_values,status,detail,message_id) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?)", (uid(), identifier, position, row["name"], row["email"], key,
                            "{}", row["status"], row["detail"], f"<{uid()}@legacy.yunyoubao.local>"))
            db.execute("INSERT INTO migrations VALUES(?,?)", (source_key, now))
        self.store.log(identifier, "只读导入旧版历史；原目录未修改，授权码未迁移。")
        return self.task(identifier)
