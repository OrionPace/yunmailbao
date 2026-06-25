import os
import smtplib
import random
import time
import datetime
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication
from email.utils import formataddr, formatdate, make_msgid
from email.header import Header

# Zero-width characters for subject uniqueness (invisible to human eyes)
ZWSP = '\u200b'  # Zero-Width Space
ZWNJ = '\u200c'  # Zero-Width Non-Joiner
ZWJ  = '\u200d'  # Zero-Width Joiner
ZW_CHARS = [ZWSP, ZWNJ, ZWJ]

# Simulated X-Mailer headers to mimic real email clients
MAILER_POOL = [
    "Foxmail 7.2.25.228 [cn]",
    "Microsoft Outlook 16.0",
    "Mozilla Thunderbird 115.9.0",
    "Foxmail 7.2.23 [cn]",
    "Microsoft Outlook 15.0",
    "Mozilla/5.0",
    "The Bat! 10.5",
]


class EmailSenderCore:
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger("email_sender_core")
        self._connection_cache = {}  # Cache SMTP connections per sender email

    @staticmethod
    def validate_email(email_str):
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, str(email_str).strip()) is not None

    def _generate_zwsp_salt(self):
        """Generate a random invisible zero-width character sequence.
        This makes every subject line unique by hash, but identical to human eyes."""
        length = random.randint(2, 5)
        return ''.join(random.choice(ZW_CHARS) for _ in range(length))

    def _generate_body_salt(self):
        """Generate an HTML comment with random content to make email body unique.
        HTML comments are ignored by renderers but change the content hash."""
        salt = f"<!-- ref-{random.randint(10000, 99999)}-{int(time.time() * 1000) % 100000} -->"
        return salt

    def create_email_msg(self, sender, recipient, email_index, html_content, subject,
                         image_path=None, attachment_path=None, add_unsubscribe=False):
        msg = MIMEMultipart()

        # --- Anti-spam: proper email headers ---
        sender_domain = sender["email"].split("@")[1] if "@" in sender["email"] else "mail.local"
        msg["From"] = formataddr((sender["name"], sender["email"]))
        msg["To"] = formataddr((recipient["name"], recipient["email"]))
        msg["Subject"] = Header(subject + self._generate_zwsp_salt(), 'utf-8').encode()
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=sender_domain)
        msg["X-Mailer"] = random.choice(MAILER_POOL)
        msg["MIME-Version"] = "1.0"
        msg["X-Priority"] = "3"  # Normal priority

        # 退订信息：标准 List-Unsubscribe 头（邮件客户端一键退订入口）
        if add_unsubscribe:
            msg["List-Unsubscribe"] = f"<mailto:{sender['email']}?subject=unsubscribe%20退订>"
            msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

        # Dynamic Content Replacement
        content = html_content.replace("<人名>", recipient["name"]).replace("&lt;人名&gt;", recipient["name"])

        # 退订脚注（正文底部）
        if add_unsubscribe:
            content += (
                "<hr style='margin-top:24px;border:none;border-top:1px solid #e5e7eb;'>"
                "<p style='color:#9ca3af;font-size:12px;line-height:1.6;margin-top:8px;'>"
                f"如不愿再收到此类邮件，请回复本邮件并注明「退订」，"
                f"或发送邮件至 {sender['email']}（主题填写「退订」）。</p>"
            )

        # Inject an invisible HTML comment for body uniqueness (instead of display:none div)
        content += self._generate_body_salt()

        msg.attach(MIMEText(content, "html"))

        # Attach Image if provided
        if image_path and os.path.exists(image_path):
            try:
                with open(image_path, "rb") as f:
                    img = MIMEImage(f.read())
                    img.add_header("Content-ID", "<image1>")
                    msg.attach(img)
            except Exception as e:
                self.logger.error(f"Failed to attach image: {str(e)}")

        # Attach PDF if provided
        if attachment_path and os.path.exists(attachment_path):
            try:
                with open(attachment_path, "rb") as f:
                    attach = MIMEApplication(f.read())
                    filename = Header(os.path.basename(attachment_path), 'utf-8').encode()
                    attach.add_header("Content-Disposition", "attachment", filename=filename)
                    msg.attach(attach)
            except Exception as e:
                self.logger.error(f"Failed to attach PDF: {str(e)}")

        return msg

    def _get_connection(self, sender):
        """Get or create a cached SMTP connection for connection reuse."""
        key = sender["email"]
        
        # Check if we have an existing connection
        if key in self._connection_cache:
            try:
                # Test if connection is still alive
                self._connection_cache[key].noop()
                return self._connection_cache[key]
            except Exception:
                # Connection is dead, remove it
                self._close_connection(key)
        
        # Create new connection
        port = int(sender["smtp_port"])
        server_host = sender["smtp_server"].lower()
        
        if port == 465:
            server = smtplib.SMTP_SSL(server_host, port, timeout=30)
        else:
            server = smtplib.SMTP(server_host, port, timeout=30)
            server.starttls()
        
        server.login(sender["email"], sender["password"])
        self._connection_cache[key] = server
        return server

    def _close_connection(self, key):
        """Safely close and remove a cached connection."""
        if key in self._connection_cache:
            try:
                self._connection_cache[key].quit()
            except Exception:
                pass
            del self._connection_cache[key]

    def close_all_connections(self):
        """Close all cached SMTP connections."""
        for key in list(self._connection_cache.keys()):
            self._close_connection(key)

    def send_single(self, sender, recipient, email_index, html_content, subject,
                    image_path=None, attachment_path=None, add_unsubscribe=False):
        """返回 (status, msg)，status ∈ {"success","failed","uncertain"}。
        连接中断时投递状态无法确认，返回 "uncertain"（既不算成功也不算失败），
        由上层记录为待确认、续传时重试，避免静默漏发。"""
        max_retries = 3
        retry_count = 0
        error_msg = ""

        while retry_count < max_retries:
            try:
                msg = self.create_email_msg(sender, recipient, email_index, html_content,
                                            subject, image_path, attachment_path, add_unsubscribe)

                # Use connection pool for reuse
                server = self._get_connection(sender)
                server.sendmail(sender["email"], recipient["email"], msg.as_string())

                return "success", "Success"

            except smtplib.SMTPAuthenticationError as e:
                return "failed", f"Auth Error: {str(e)}"
            except Exception as e:
                err_str = str(e).lower()
                # 连接中断：投递状态未知（可能已发出，也可能没有）
                if 'connection' in err_str or 'timeout' in err_str or '(-1,' in err_str:
                    # Connection died - clear cache so next call reconnects
                    self._close_connection(sender["email"])
                    return "uncertain", "连接中断，投递状态未知，请复查"
                retry_count += 1
                error_msg = str(e)
                # Clear connection cache on error so we reconnect
                self._close_connection(sender["email"])
                time.sleep(2)

        return "failed", f"Failed after {max_retries} retries: {error_msg}"
