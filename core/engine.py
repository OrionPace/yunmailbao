import os
import json
import time
import random
import datetime
import tempfile
import pandas as pd
from core.email_sender import EmailSenderCore

class MarketingEngine:
    def __init__(self, logger):
        self.logger = logger
        self.sender_core = EmailSenderCore(logger)
        self.is_running = False
        self.logs = []
        self.progress = {"total": 0, "sent": 0, "failed": 0, "current": 0}
        self.failed_recipients = []  # Track failed emails for export
        # --- Resume / checkpoint state ---
        self.sent_emails = set()        # Emails confirmed delivered (for idempotent skip)
        self.checkpoint_path = None     # Set by main.py at startup
        self.active_config = None       # Config of the in-flight / paused campaign

    def _log(self, msg):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {msg}"
        self.logger.info(log_entry)
        self.logs.append(log_entry)
        if len(self.logs) > 500:
            self.logs = self.logs[-500:]

    def stop(self):
        self.is_running = False
        self._log("收到停止指令，正在安全终止任务...")

    def get_failed_recipients(self):
        """Return the list of failed recipients for export."""
        return self.failed_recipients

    # ------------------------------------------------------------------
    # Checkpoint / Resume (断点续传)
    # ------------------------------------------------------------------
    def set_checkpoint_path(self, path):
        """Register where the resume checkpoint lives (called once at startup)."""
        self.checkpoint_path = path

    def _save_checkpoint(self, config, status):
        """Atomically persist current campaign progress so it survives a crash
        or power loss. Written after every email send, so at most one email is
        ever re-sent on resume."""
        if not self.checkpoint_path:
            return
        data = {
            "campaign_id": self._campaign_id(config),
            "status": status,  # running | paused | done
            "config": config,
            "total": self.progress.get("total", 0),
            "sent_emails": sorted(self.sent_emails),
            "failed_recipients": self.failed_recipients,
            "progress": self.progress,
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            os.makedirs(os.path.dirname(self.checkpoint_path), exist_ok=True)
            dir_name = os.path.dirname(self.checkpoint_path)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.checkpoint_path)  # atomic on same volume
        except Exception as e:
            self.logger.error(f"保存断点续传检查点失败: {e}")

    def _read_checkpoint(self):
        """Return parsed checkpoint dict, or None if missing/corrupt."""
        if not self.checkpoint_path or not os.path.exists(self.checkpoint_path):
            return None
        try:
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"读取断点续传检查点失败: {e}")
            return None

    def _clear_checkpoint(self):
        """Discard any saved progress (used by '放弃并新建' and fresh starts)."""
        self.sent_emails = set()
        self.active_config = None
        if self.checkpoint_path and os.path.exists(self.checkpoint_path):
            try:
                os.remove(self.checkpoint_path)
            except Exception as e:
                self.logger.error(f"清除断点续传检查点失败: {e}")

    @staticmethod
    def _campaign_id(config):
        """Stable signature of a campaign (excel + subject + recipient count)."""
        import hashlib
        raw = f"{config.get('excel_path', '')}|{config.get('subject', '')}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]

    def has_resumable_checkpoint(self):
        """True if there is an unfinished campaign that can be continued."""
        cp = self._read_checkpoint()
        if not cp:
            return False
        if cp.get("status") == "done":
            return False
        total = cp.get("total", 0)
        sent = len(cp.get("sent_emails", []))
        return total > 0 and sent < total

    def checkpoint_summary(self):
        """Lightweight summary for the frontend resume banner (no passwords)."""
        cp = self._read_checkpoint()
        if not cp:
            return {"resumable": False}
        total = cp.get("total", 0)
        sent = len(cp.get("sent_emails", []))
        return {
            "resumable": self.has_resumable_checkpoint(),
            "status": cp.get("status"),
            "total": total,
            "sent": sent,
            "failed": len(cp.get("failed_recipients", [])),
            "subject": cp.get("config", {}).get("subject", ""),
            "updated_at": cp.get("updated_at", ""),
        }

    def get_resume_config(self):
        """Return the stored config needed to continue an interrupted campaign."""
        cp = self._read_checkpoint()
        if not cp:
            return None
        return cp.get("config")

    def load_checkpoint_into_memory(self):
        """On startup, surface a paused campaign so /api/status reflects it
        (lets the UI show progress before the user clicks 继续)."""
        cp = self._read_checkpoint()
        if not cp or not self.has_resumable_checkpoint():
            return
        self.sent_emails = set(cp.get("sent_emails", []))
        self.failed_recipients = cp.get("failed_recipients", [])
        self.progress = cp.get("progress", {"total": 0, "sent": 0, "failed": 0, "current": 0})
        self.active_config = cp.get("config")

    @staticmethod
    def _classify_error(error_msg: str) -> str:
        """Classify SMTP error into human-readable bounce reason."""
        err = error_msg.lower()
        if 'user not found' in err or 'no such user' in err or '550' in err or 'does not exist' in err or 'invalid' in err:
            return "地址不存在/被退回"
        elif 'quota' in err or 'full' in err or 'over' in err:
            return "收件箱已满"
        elif 'spam' in err or 'reject' in err or 'blocked' in err or 'denied' in err or 'blacklist' in err:
            return "被反垃圾拦截"
        elif 'auth' in err:
            return "发件人认证失败"
        elif 'timeout' in err or 'connection' in err:
            return "连接超时/中断"
        else:
            return "其他失败"

    def run_campaign(self, config, resume=False):
        """
        config dict containing:
        - excel_path, image_path, attachment_path
        - subject, html_content
        - min_interval, max_interval
        - start_time, end_time
        - name_column, email_column (column name mapping)
        - senders: list of dicts (email, password, name, smtp_server, smtp_port)

        resume=True 时从磁盘检查点恢复进度（断点续传），已成功投递的邮箱会被跳过，
        不重复发送；resume=False 表示全新任务，会清空历史进度并删除旧检查点。
        """
        self.is_running = True
        self.active_config = config
        if resume:
            cp = self._read_checkpoint()
            if cp:
                self.sent_emails = set(cp.get("sent_emails", []))
                self.failed_recipients = list(cp.get("failed_recipients", []))
                self._log(f"断点续传：已恢复进度，{len(self.sent_emails)} 个邮箱此前已成功投递，将自动跳过。")
            else:
                self.sent_emails = set()
                self.failed_recipients = []
        else:
            # Fresh campaign: wipe any previous progress on disk and in memory
            self._clear_checkpoint()
            self.logs.clear()
            self.failed_recipients = []
            self.sent_emails = set()
        self._log("初始化发件营销计划...")
        
        try:
            # 1. Load Excel
            df = pd.read_excel(config['excel_path'])
            
            # Determine column mapping
            name_col = config.get('name_column', '')
            email_col = config.get('email_column', '')
            
            recipients = []
            for _, row in df.iterrows():
                # Use column name if provided, otherwise fall back to positional index
                if name_col and name_col in df.columns:
                    name = str(row[name_col]).strip() if not pd.isna(row[name_col]) else ''
                else:
                    name = str(row.iloc[0]).strip() if not pd.isna(row.iloc[0]) else ''
                    
                if email_col and email_col in df.columns:
                    email = str(row[email_col]).strip() if not pd.isna(row[email_col]) else ''
                else:
                    email = str(row.iloc[1]).strip() if not pd.isna(row.iloc[1]) else ''
                    
                if name and email and self.sender_core.validate_email(email):
                    recipients.append({"name": name, "email": email})

            total = len(recipients)
            # On resume, seed counters from restored state so the dashboard and
            # fatigue logic continue where they left off.
            already_sent = sum(1 for r in recipients if r["email"] in self.sent_emails)
            self.progress = {
                "total": total,
                "sent": already_sent,
                "failed": len(self.failed_recipients),
                "current": already_sent,
            }

            if total == 0:
                self._log("未在Excel中找到有效的收件人。请检查列映射是否正确。")
                self.is_running = False
                return

            self._log(f"成功加载 {total} 个有效收件人。")
            if name_col:
                self._log(f"列映射: 姓名列={name_col}, 邮箱列={email_col}")
            
            senders = config['senders']
            if not senders:
                self._log("未配置任何发件箱。")
                self.is_running = False
                return

            email_index = 1
            start_t = datetime.datetime.strptime(config['start_time'], "%H:%M").time()
            end_t = datetime.datetime.strptime(config['end_time'], "%H:%M").time()
            batch_size = int(config.get('batch_size', 1))
            base_min = int(config.get('min_interval', 5))
            base_max = int(config.get('max_interval', 15))

            for i, recipient in enumerate(recipients):
                if not self.is_running:
                    self._log("任务已手动终止。")
                    self._save_checkpoint(config, "paused")
                    break

                self.progress["current"] = i + 1

                # 断点续传：已成功投递的邮箱直接跳过，避免重复发送
                if recipient["email"] in self.sent_emails:
                    self._log(f"⏭️ 第 {i+1} 封 {recipient['email']} 此前已成功投递，跳过。")
                    continue

                # Time window enforcement
                now_t = datetime.datetime.now().time()
                while not (start_t <= now_t <= end_t) and self.is_running:
                    self._log("当前时间不在发件允许窗口内，挂起等待...")
                    time.sleep(60)
                    now_t = datetime.datetime.now().time()

                if not self.is_running:
                    self._save_checkpoint(config, "paused")
                    break

                # Rotate Senders
                sender = senders[i % len(senders)]

                # Send
                self._log(f"正在发送第 {i+1} 封至 {recipient['email']} (使用账号: {sender['email']})")
                success, msg = self.sender_core.send_single(
                    sender=sender,
                    recipient=recipient,
                    email_index=email_index,
                    html_content=config['html_content'],
                    subject=config['subject'],
                    image_path=config.get('image_path'),
                    attachment_path=config.get('attachment_path')
                )

                if success:
                    self.progress["sent"] += 1
                    self.sent_emails.add(recipient["email"])
                    self._log(f"✅ 发送成功 - {msg}")
                else:
                    self.progress["failed"] += 1
                    reason = self._classify_error(msg)
                    self._log(f"❌ 发送失败 [{reason}] → {recipient['email']} - {msg}")
                    self.failed_recipients.append({
                        "name": recipient["name"],
                        "email": recipient["email"],
                        "reason": reason,
                        "detail": msg,
                        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "sender_used": sender["email"]
                    })

                # 每发完一封即原子化落盘，断网/断电最多只丢失/重发一封
                self._save_checkpoint(config, "running")

                email_index += 1

                if i < total - 1 and self.is_running:
                    if (i + 1) % batch_size == 0:
                        # Fatigue-increasing interval: the longer we send, the slower we go
                        fatigue_factor = 1.0 + (self.progress["sent"] // 50) * 0.15
                        adjusted_min = int(base_min * fatigue_factor)
                        adjusted_max = int(base_max * fatigue_factor)
                        wait_sec = random.randint(adjusted_min, adjusted_max)
                        
                        if fatigue_factor > 1.0:
                            self._log(f"疲劳递增机制：已发送 {self.progress['sent']} 封，疲劳因子 x{fatigue_factor:.2f}，休眠 {wait_sec} 秒...")
                        else:
                            self._log(f"防封锁机制：单批次发送完毕，随机休眠 {wait_sec} 秒...")
                        time.sleep(wait_sec)
                    else:
                        # Micro-jitter between emails in same batch (0.3~1.5s)
                        time.sleep(random.uniform(0.3, 1.5))

            # 循环正常跑完（未被手动终止）→ 标记任务完成
            if self.is_running:
                self._save_checkpoint(config, "done")

        except Exception as e:
            self._log(f"发生了严重的结构性错误: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            # 异常中断也落盘为 paused，便于排查后续传
            self._save_checkpoint(config, "paused")

        # Clean up SMTP connections
        self.sender_core.close_all_connections()
        self._log("所有 SMTP 连接已安全关闭。")

        # Summary report
        if self.failed_recipients:
            self._log(f"⚠️ 本次共有 {len(self.failed_recipients)} 个邮箱投递失败，可点击「导出失败记录」按钮下载清单。")

        self.is_running = False
        self._log("营销计划执行完毕。")
