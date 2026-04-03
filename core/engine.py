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

    def run_campaign(self, config):
        """
        config dict containing:
        - excel_path, image_path, attachment_path
        - subject, html_content
        - min_interval, max_interval
        - start_time, end_time
        - senders: list of dicts (email, password, name, smtp_server, smtp_port)
        """
        self.is_running = True
        self.logs.clear()
        self._log("初始化发件营销计划...")
        
        try:
            # 1. Load Excel
            df = pd.read_excel(config['excel_path'])
            recipients = []
            for _, row in df.iterrows():
                name = str(row.iloc[0]).strip() if not pd.isna(row.iloc[0]) else ''
                email = str(row.iloc[1]).strip() if not pd.isna(row.iloc[1]) else ''
                if name and email and self.sender_core.validate_email(email):
                    recipients.append({"name": name, "email": email})

            total = len(recipients)
            self.progress = {"total": total, "sent": 0, "failed": 0, "current": 0}
            
            if total == 0:
                self._log("未在Excel中找到有效的收件人（A列姓名，B列邮箱）。")
                self.is_running = False
                return

            self._log(f"成功加载 {total} 个有效收件人。")
            senders = config['senders']
            if not senders:
                self._log("未配置任何发件箱。")
                self.is_running = False
                return

            email_index = 1
            start_t = datetime.datetime.strptime(config['start_time'], "%H:%M").time()
            end_t = datetime.datetime.strptime(config['end_time'], "%H:%M").time()
            batch_size = int(config.get('batch_size', 1))

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
                    self._log(f"❌ 发送失败 - {msg}")

                email_index += 1

                if i < total - 1 and self.is_running:
                    if (i + 1) % batch_size == 0:
                        wait_sec = random.randint(int(config['min_interval']), int(config['max_interval']))
                        self._log(f"防封锁机制：单批次发送完毕，随机休眠 {wait_sec} 秒...")
                        time.sleep(wait_sec)
                    else:
                        # 极短的内部强制间隔避免自身进程崩溃或触发服务商极速断流
                        time.sleep(0.5)

        except Exception as e:
            self._log(f"发生了严重的结构性错误: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            
        self.is_running = False
        self._log("营销计划执行完毕。")
