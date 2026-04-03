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
from email.utils import formataddr
from email.header import Header

class EmailSenderCore:
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger("email_sender_core")

    @staticmethod
    def validate_email(email_str):
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, str(email_str).strip()) is not None

    def create_email_msg(self, sender, recipient, email_index, html_content, subject, image_path=None, attachment_path=None):
        msg = MIMEMultipart()
        msg["From"] = formataddr((sender["name"], sender["email"]))
        msg["To"] = recipient["email"]
        
        # Subject with rotating formatting to avoid hash collision
        dynamic_subject = f"{subject} - No.{email_index}"
        msg["Subject"] = Header(dynamic_subject, 'utf-8').encode()

        # Dynamic Content Replacement (Anti-spam strategy)
        content = html_content.replace("<人名>", recipient["name"])
        
        # Inject an invisible random hash to make every email body unique
        random_hash = f"<div style='display:none;'>uid-{random.random()}-{time.time()}</div>"
        content += random_hash

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

    def send_single(self, sender, recipient, email_index, html_content, subject, image_path=None, attachment_path=None):
        max_retries = 3
        retry_count = 0
        error_msg = ""
        
        while retry_count < max_retries:
            try:
                msg = self.create_email_msg(sender, recipient, email_index, html_content, subject, image_path, attachment_path)
                
                # SMTP logic
                port = int(sender["smtp_port"])
                server_host = sender["smtp_server"].lower()
                
                if port == 465:
                    server = smtplib.SMTP_SSL(server_host, port, timeout=30)
                else:
                    server = smtplib.SMTP(server_host, port, timeout=30)
                    server.starttls()
                
                server.login(sender["email"], sender["password"])
                server.sendmail(sender["email"], recipient["email"], msg.as_string())
                server.quit()
                
                return True, "Success"
                
            except smtplib.SMTPAuthenticationError as e:
                return False, f"Auth Error: {str(e)}"
            except Exception as e:
                err_str = str(e).lower()
                # If connection closed but practically sent
                if 'connection' in err_str or 'timeout' in err_str or '(-1,' in err_str:
                    return True, "Warning: Connection closed but likely sent."
                retry_count += 1
                error_msg = str(e)
                time.sleep(2)
                
        return False, f"Failed after {max_retries} retries: {error_msg}"
