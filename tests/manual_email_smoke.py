import os
import logging
from dotenv import load_dotenv
from pathlib import Path
from core.engine import MarketingEngine

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Test")

engine = MarketingEngine(logger)

senders = [{
    "email": os.environ["ACCOUNT_1_EMAIL"],
    "password": os.environ["ACCOUNT_1_PASSWORD"],
    "name": os.environ["ACCOUNT_1_NAME"],
    "smtp_server": os.environ["SMTP_SERVER_QQ"],
    "smtp_port": int(os.environ["SMTP_PORT_QQ"])
}]

config = {
    "excel_path": str(Path("tests/fixtures/sample_recipients.xlsx")),
    "image_path": None,
    "attachment_path": None,
    "subject": "【测试】新开发发件引擎自动检测",
    "html_content": "<h2>全自动邮件测试</h2><p>尊敬的<strong style='color:#10b981;'>&lt;人名&gt;</strong>，您好！</p><p>如果您收到此邮件，说明 FastAPI 邮件引擎与防封算法的各项指标已在本地完美运行！</p>",
    "start_time": "00:00",
    "end_time": "23:59",
    "min_interval": 3,
    "max_interval": 6,
    "senders": senders
}

engine.run_campaign(config)
