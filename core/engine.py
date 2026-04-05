import os
import time
import random
import datetime
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

    def run_campaign(self, config):
        """
        config dict containing:
        - excel_path, image_path, attachment_path
        - subject, html_content
        - min_interval, max_interval
        - start_time, end_time
        - name_column, email_column (column name mapping)
        - senders: list of dicts (email, password, name, smtp_server, smtp_port)
        """
        self.is_running = True
        self.logs.clear()
        self.failed_recipients.clear()
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
            self.progress = {"total": total, "sent": 0, "failed": 0, "current": 0}
            
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
                    break
                
                self.progress["current"] = i + 1

                # Time window enforcement
                now_t = datetime.datetime.now().time()
                while not (start_t <= now_t <= end_t) and self.is_running:
                    self._log("当前时间不在发件允许窗口内，挂起等待...")
                    time.sleep(60)
                    now_t = datetime.datetime.now().time()

                if not self.is_running: break

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

        except Exception as e:
            self._log(f"发生了严重的结构性错误: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
        
        # Clean up SMTP connections
        self.sender_core.close_all_connections()
        self._log("所有 SMTP 连接已安全关闭。")
        
        # Summary report
        if self.failed_recipients:
            self._log(f"⚠️ 本次共有 {len(self.failed_recipients)} 个邮箱投递失败，可点击「导出失败记录」按钮下载清单。")
        
        self.is_running = False
        self._log("营销计划执行完毕。")
