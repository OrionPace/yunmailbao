import datetime as dt
import json
import re
import threading
import time

from .email_sender import EmailSenderCore
from .store import timestamp


class DemoTransport:
    def send_attempt(self, sender, recipient, **kwargs):
        from .email_sender import SendResult
        position = int(recipient.get("position", 0))
        if recipient.get("demo_retry"):
            return SendResult("accepted", "演示：模拟人工复查后的重新提交，未发送真实邮件。")
        if position == 3:
            return SendResult("uncertain", "演示：模拟提交期间断连，未发送真实邮件。")
        if position == 6:
            return SendResult("failed", "演示：模拟地址拒绝，未发送真实邮件。", code=550)
        return SendResult("accepted", "演示：模拟服务器接受，未发送真实邮件。")

    def close_all_connections(self):
        pass


class TaskEngine:
    def __init__(self, service, transport_factory=None):
        self.service = service
        self.store = service.store
        self.transport_factory = transport_factory or (DemoTransport if service.demo else EmailSenderCore)
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.task_id = None
        self.runtime_errors = {}

    @property
    def busy(self):
        return self.lock.locked()

    @staticmethod
    def in_window(start, end, now=None):
        now = now or dt.datetime.now().time()
        start, end = dt.time.fromisoformat(start), dt.time.fromisoformat(end)
        if start == end:
            return True
        return start <= now < end if start < end else now >= start or now < end

    def _launch_locked(self, identifier):
        task = self.service.task(identifier)
        if task["legacy"]:
            raise ValueError("旧版导入记录仅供核对，不可直接续发。")
        if task["status"] not in {"ready", "paused"}:
            raise ValueError("此任务不能直接启动；已完成任务请选择失败重试或新建草稿。")
        if not task["counts"]["pending"]:
            raise ValueError("没有待发送对象；待确认必须人工单独处理。")
        config = task["config"]
        for profile in config["sender_profiles"]:
            self.service.sender(profile["id"], profile)
        item, _ = self.service.attachment(config.get("attachment_id"))
        if item and item["digest"] != config["attachment_digest"]:
            raise ValueError("附件已改变，请新建任务核对。")
        with self.store.transaction() as db:
            db.execute("UPDATE recipients SET status='uncertain',detail=? WHERE task_id=? AND status='sending'",
                       ("上次提交结果不明，请人工确认。", identifier))
            db.execute("UPDATE tasks SET status='starting',pause_reason='',updated_at=? WHERE id=?", (timestamp(), identifier))
        self.runtime_errors.pop(identifier, None)
        self.task_id = identifier
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, args=(identifier,), daemon=True, name="YunYouBaoSender")
        self.thread.start()
        return dict(task, status="starting", pause_reason="")

    def start(self, identifier):
        if not self.lock.acquire(blocking=False):
            raise ValueError("已有任务或测试正在运行，请等待停止完成。")
        try:
            return self._launch_locked(identifier)
        except BaseException:
            self.lock.release()
            raise

    def pause(self, identifier):
        if self.task_id != identifier or not self.busy:
            raise ValueError("这个任务没有正在发送。")
        self.stop_event.set()
        # A worker may finish while the request is being handled; never revive it.
        with self.store.transaction() as db:
            db.execute("UPDATE tasks SET status='stopping',pause_reason='manual',updated_at=? "
                       "WHERE id=? AND status IN ('starting','running')", (timestamp(), identifier))
        return self.service.task(identifier)

    def retry(self, identifier, selected=None, include_uncertain=False):
        if not self.lock.acquire(blocking=False):
            raise ValueError("请等待任务或测试停止后再重试。")
        try:
            task = self.service.task(identifier)
            if task["legacy"]:
                raise ValueError("旧版记录不能重试。")
            if task["status"] in {"starting", "running", "stopping"}:
                raise ValueError("任务未停止，不能重试。")
            rows = self.store.all("SELECT id,status FROM recipients WHERE task_id=? AND status IN ('failed','uncertain')", (identifier,))
            if include_uncertain and not selected:
                raise ValueError("待确认重发必须明确选择收件人。")
            choices = set(selected or [row["id"] for row in rows if row["status"] == "failed"])
            valid = {row["id"] for row in rows if row["status"] == "failed" or include_uncertain}
            if not choices or not choices.issubset(valid):
                raise ValueError("重试选择无效；已接收对象不能再次发送。")
            with self.store.transaction() as db:
                db.executemany("UPDATE recipients SET status='pending',detail='',attempts=0,next_attempt=0 WHERE id=? AND task_id=?",
                               [(choice, identifier) for choice in choices])
                db.execute("UPDATE tasks SET status='paused',pause_reason='retry',updated_at=? WHERE id=?", (timestamp(), identifier))
            self.store.log(identifier, f"人工选择重试 {len(choices)} 人；已接收对象保持不变。")
            return self._launch_locked(identifier)
        except BaseException:
            self.lock.release()
            raise

    def quota(self, profile):
        from .service import email_key
        row = self.store.one("SELECT count,last_attempt FROM quotas WHERE account_key=? AND day=?",
                             (email_key(profile["email"]), dt.date.today().isoformat()))
        return row or {"count": 0, "last_attempt": 0}

    def reserve(self, profile):
        from .service import email_key
        key, today, now = email_key(profile["email"]), dt.date.today().isoformat(), time.time()
        with self.store.transaction() as db:
            paused = db.execute("SELECT payload FROM preferences WHERE key=?", ("smtp_pause_until:" + key,)).fetchone()
            if not self.service.demo and paused and float(json.loads(paused["payload"])) > now:
                return False
            row = db.execute("SELECT count,last_attempt FROM quotas WHERE account_key=? AND day=?", (key, today)).fetchone()
            if row and row["count"] >= profile["daily_limit"]:
                return False
            if not self.service.demo and row and now - row["last_attempt"] < 60 / profile["per_minute"]:
                return False
            db.execute("INSERT INTO quotas VALUES(?,?,1,?) ON CONFLICT(account_key,day) DO UPDATE SET count=count+1,last_attempt=excluded.last_attempt",
                       (key, today, now))
        return True

    def _run(self, identifier):
        transport = None
        terminal_state = None
        try:
            transport = self.transport_factory()
            config = self.service.task(identifier)["config"]
            self.store.set_status(identifier, "running")
            self.store.log(identifier, "演示任务开始，所有发送均为模拟。" if self.service.demo else "开始处理冻结名单。")
            cursor, waiting, temporary_refusals = 0, False, 0
            retry_profile = None
            interval = 0 if self.service.demo else 60 / min(profile["per_minute"] for profile in config["sender_profiles"])
            while not self.stop_event.is_set():
                pending = self.store.all("SELECT * FROM recipients WHERE task_id=? AND status='pending' ORDER BY position", (identifier,))
                if not pending:
                    counts = self.store.counts(identifier)
                    terminal_state = ("completed_with_issues" if counts["failed"] or counts["uncertain"] else "completed", "")
                    self.store.log(identifier, "本轮处理完毕；待确认对象未自动重发。")
                    return
                if not self.service.demo and not self.in_window(config["start_time"], config["end_time"]):
                    if not waiting:
                        self.store.log(identifier, "当前不在发送窗口内，等待中，可随时暂停。")
                        self.store.set_status(identifier, "running", "window")
                        waiting = True
                    self.stop_event.wait(1)
                    continue
                if waiting:
                    self.store.set_status(identifier, "running")
                    waiting = False
                now = time.time()
                # All pending rows share the persisted task-wide cooldown; account quotas
                # also preserve normal pacing across an interruption or another task.
                deadline = max(row["next_attempt"] for row in pending)
                if interval:
                    keys = [profile["email"] for profile in config["sender_profiles"]]
                    from .service import email_key
                    last = self.store.one("SELECT MAX(last_attempt) AS last FROM quotas WHERE account_key IN ("
                                          + ",".join("?" for _ in keys) + ")", tuple(email_key(key) for key in keys))["last"]
                    deadline = max(deadline, (last or 0) + interval)
                    for key in keys:
                        paused = self.store.one("SELECT payload FROM preferences WHERE key=?", ("smtp_pause_until:" + email_key(key),))
                        if paused:
                            deadline = max(deadline, float(json.loads(paused["payload"])))
                if deadline > now:
                    self.stop_event.wait(min(1, max(0.01, deadline - now)))
                    continue
                recipient = pending[0]
                if self.store.one("SELECT email_key FROM suppressions WHERE email_key=?", (recipient["email_key"],)):
                    self.store.execute("UPDATE recipients SET status='failed',detail=? WHERE id=?",
                                       ("已排除：发送前命中退订／排除名单。", recipient["id"]))
                    self.store.log(identifier, f"第 {recipient['position'] + 1} 位已按排除名单停止发送。")
                    continue
                eligible = [retry_profile] if retry_profile else config["sender_profiles"]
                available = [profile for profile in eligible if self.quota(profile)["count"] < profile["daily_limit"]]
                if not available:
                    terminal_state = ("paused", "quota")
                    self.store.log(identifier, "所有账号的软件日预算已用尽，请次日继续。")
                    return
                chosen = None
                for offset in range(len(available)):
                    profile = available[(cursor + offset) % len(available)]
                    if self.reserve(profile):
                        chosen = profile
                        break
                if chosen is None:
                    self.stop_event.wait(0.25)
                    continue
                item, attachment = self.service.attachment(config.get("attachment_id"))
                with self.store.transaction() as db:
                    db.execute("UPDATE recipients SET next_attempt=MAX(next_attempt,?) WHERE task_id=? AND status='pending'",
                               (time.time() + interval, identifier))
                    db.execute("UPDATE recipients SET status='sending',attempts=attempts+1 WHERE id=?", (recipient["id"],))
                sender = self.service.sender(chosen["id"], chosen)
                prior = self.store.one("SELECT COUNT(*) AS n FROM attempts WHERE recipient_id=?", (recipient["id"],))["n"]
                result = transport.send_attempt(sender=sender, recipient=dict(recipient, values=json.loads(recipient["row_values"]), demo_retry=bool(prior)),
                    html_content=config["html_content"], subject=config["subject"], attachment_path=str(attachment) if attachment else None,
                    attachment_filename=(config.get("attachment_name") or item["filename"]) if item else None,
                    add_unsubscribe=config["add_unsubscribe"], message_id=recipient["message_id"])
                attempts = recipient["attempts"] + 1
                temporary = (result.status == "failed" and result.retryable and not result.account_error
                             and result.code is not None and 400 <= result.code < 500)
                provider_limit = (result.status == "failed" and result.code is not None and 400 <= result.code < 500
                                  and re.search(r"\b4\.7\.28\b", result.detail) is not None)
                if result.status == "accepted":
                    temporary_refusals = 0
                elif temporary:
                    temporary_refusals += 1
                retryable = result.status == "failed" and result.retryable and not result.account_error and attempts < 3
                state = "pending" if provider_limit or temporary or retryable or (result.status == "failed" and result.account_error) else result.status
                if state not in {"pending", "accepted", "failed", "uncertain"}:
                    raise ValueError("发送后端返回了未知状态。")
                streak = temporary_refusals if temporary else attempts
                delay = (30 if streak == 1 else 120) if (temporary or retryable) and not self.service.demo else 0
                if temporary and temporary_refusals >= 3:
                    delay = 0
                if provider_limit and not self.service.demo:
                    delay = 600
                detail = result.detail[:500].replace(sender["password"], "[已隐藏]") if sender.get("password") else result.detail[:500]
                with self.store.transaction() as db:
                    db.execute("UPDATE recipients SET status=?,detail=?,next_attempt=? WHERE id=?",
                               (state, detail, time.time() + max(delay, interval), recipient["id"]))
                    db.execute("UPDATE recipients SET next_attempt=MAX(next_attempt,?) WHERE task_id=? AND status='pending'",
                               (time.time() + max(delay, interval), identifier))
                    db.execute("INSERT INTO attempts(recipient_id,status,detail,code,created_at) VALUES(?,?,?,?,?)",
                               (recipient["id"], result.status, detail, result.code, timestamp()))
                    db.execute("UPDATE tasks SET updated_at=? WHERE id=?", (timestamp(), identifier))
                    if result.permanent_address:
                        db.execute("INSERT OR IGNORE INTO suppressions VALUES(?,?)", (recipient["email_key"], recipient["email"]))
                    if provider_limit and not self.service.demo:
                        db.execute("INSERT INTO preferences VALUES(?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload",
                                   ("smtp_pause_until:" + email_key(chosen["email"]), json.dumps(time.time() + 600)))
                if provider_limit:
                    terminal_state = ("paused", "provider_rate_limit")
                    self.store.log(identifier, "服务商返回 4.7.28，任务已暂停；至少等待 10 分钟并排查原因后人工继续。")
                    return
                if result.account_error:
                    terminal_state = ("paused", "account_error")
                    self.store.log(identifier, "账号认证或策略拒绝，整个任务已暂停，请处理后人工继续。")
                    return
                if temporary and temporary_refusals >= 3:
                    terminal_state = ("paused", "temporary_rejection")
                    self.store.log(identifier, "连续三次临时拒绝，整个任务已暂停，请核对后人工继续。")
                    return
                retry_profile = chosen if state == "pending" else None
                if retry_profile is None:
                    cursor += 1
                labels = {"accepted": "服务器已接收", "failed": "失败", "uncertain": "待确认", "pending": "暂时拒绝，等待重试"}
                self.store.log(identifier, f"第 {recipient['position'] + 1} 位：{labels[state]}。")
                if self.service.demo:
                    self.stop_event.wait(0.25)
            terminal_state = ("paused", "manual")
            self.store.log(identifier, "正在结束任务并关闭本轮连接。")
        except BaseException as error:
            terminal_state = None
            self.runtime_errors[identifier] = f"任务已停止：{type(error).__name__}。未确认的提交不会自动重发。"
            try:
                with self.store.transaction() as db:
                    db.execute("UPDATE recipients SET status='uncertain',detail=? WHERE task_id=? AND status='sending'",
                               ("处理异常，提交结果不明，请人工确认。", identifier))
                    db.execute("UPDATE tasks SET status='paused',pause_reason='error',updated_at=? WHERE id=?", (timestamp(), identifier))
                self.store.log(identifier, self.runtime_errors[identifier])
            except Exception:
                pass
        finally:
            if transport:
                try:
                    transport.close_all_connections()
                except Exception:
                    pass
            if terminal_state:
                try:
                    self.store.set_status(identifier, *terminal_state)
                except Exception:
                    self.runtime_errors[identifier] = "任务已停止，但结束状态未能保存，请检查磁盘后重新打开。"
            self.task_id = None
            self.lock.release()

    def test_send(self, config):
        from .service import mail_subject, mail_unsubscribe
        if not self.lock.acquire(blocking=False):
            raise ValueError("任务正在运行或停止中，暂不能测试发送。")
        transport = None
        try:
            sender = self.service.sender(config["account_id"])
            email = config.get("test_email", "").strip()
            if not EmailSenderCore.validate_email(email):
                raise ValueError("测试邮箱格式不正确。")
            recipient = {"name": config.get("test_name") or "测试用户", "email": email, "values": config.get("values", {})}
            subject = mail_subject(config)
            subject = "AD 【测试】" + subject[3:] if subject.startswith("AD ") else "【测试】" + subject
            item, path = self.service.attachment(config.get("attachment_id"))
            add_unsubscribe = mail_unsubscribe(config)
            EmailSenderCore().create_email_msg(sender, recipient, 1, config.get("html_content", ""), subject,
                attachment_path=str(path) if path else None, attachment_filename=item["filename"] if item else None,
                add_unsubscribe=add_unsubscribe)
            if not self.reserve(sender):
                raise ValueError("此账号已达到发送预算或间隔，请稍后重试。")
            transport = self.transport_factory()
            result = transport.send_attempt(sender=sender, recipient=recipient, subject=subject,
                html_content=config.get("html_content", ""), attachment_path=str(path) if path else None,
                attachment_filename=item["filename"] if item else None, add_unsubscribe=add_unsubscribe)
            detail = result.detail.replace(sender["password"], "[已隐藏]") if sender.get("password") else result.detail
            return {"status": result.status, "detail": detail, "retryable": result.retryable, "account_error": result.account_error,
                    "code": result.code, "permanent_address": result.permanent_address}
        finally:
            if transport:
                transport.close_all_connections()
            self.lock.release()

    def shutdown(self, timeout=5):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout)
