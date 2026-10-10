import base64
import binascii
import hashlib
import html
import logging
import math
import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from email import policy
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import quote, urlsplit


MAX_INLINE_IMAGE_BYTES = 5 * 1024 * 1024
MAX_MESSAGE_BYTES = 25 * 1024 * 1024
_NAME = "\u4eba\u540d"
_NAME_COLUMN = "\u59d3\u540d"
_VARIABLE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}|<" + _NAME + r">|&lt;" + _NAME + r"&gt;")
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"), None)
_DATA_IMAGE = re.compile(r"data:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/=\s]+)", re.I)
_QUILL_STYLES = {
    "ql-font-serif": "font-family:Georgia,Times New Roman,serif",
    "ql-font-monospace": "font-family:Monaco,Courier New,monospace",
    "ql-size-small": "font-size:0.75em",
    "ql-size-large": "font-size:1.5em",
    "ql-size-huge": "font-size:2.5em",
    "ql-align-center": "text-align:center",
    "ql-align-right": "text-align:right",
    "ql-align-justify": "text-align:justify",
    "ql-direction-rtl": "direction:rtl",
}


@dataclass
class SendResult:
    status: Literal["accepted", "failed", "uncertain"]
    detail: str
    retryable: bool = False
    account_error: bool = False
    code: int | None = None
    permanent_address: bool = False


def _header(value):
    value = str(value).translate(_ZERO_WIDTH)
    if any(char in value for char in "\r\n\x00"):
        raise ValueError("Email headers must not contain CR, LF or NUL")
    return value


def _address(value):
    value = _header(value).strip()
    if not EmailSenderCore.validate_email(value):
        raise ValueError("Invalid email address")
    return value


def _decode_image(source):
    match = _DATA_IMAGE.fullmatch(source)
    if not match:
        raise ValueError("Only base64 PNG, JPEG, GIF and WebP images are supported")
    encoded = re.sub(r"\s", "", match[2])
    if len(encoded) > ((MAX_INLINE_IMAGE_BYTES + 2) // 3) * 4:
        raise ValueError("Inline image exceeds 5 MiB")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Invalid base64 image") from exc
    if not data or len(data) > MAX_INLINE_IMAGE_BYTES:
        raise ValueError("Empty or oversized inline image")
    return match[1].lower(), data


def _safe_style(value):
    styles = []
    for declaration in value.split(";"):
        key, separator, item = declaration.partition(":")
        key, item = key.strip().lower(), item.strip()
        if not separator or not item:
            continue
        valid = False
        if key in {"color", "background-color"}:
            valid = bool(re.fullmatch(r"#[0-9a-fA-F]{3,8}|[a-zA-Z]+|(?:rgb|rgba|hsl|hsla)\([\d\s.,%]+\)", item))
        elif key == "font-family":
            valid = bool(re.fullmatch(r"[a-zA-Z0-9 ,\"'-]+", item))
        elif key in {"font-size", "line-height", "margin", "margin-top", "margin-bottom", "margin-left", "margin-right", "padding", "width", "height"}:
            valid = bool(re.fullmatch(r"(?:\d+(?:\.\d+)?(?:px|pt|em|rem|%)?|normal)(?:\s+\d+(?:\.\d+)?(?:px|pt|em|rem|%)?){0,3}", item))
        elif key == "text-align":
            valid = item in {"left", "right", "center", "justify"}
        elif key == "direction":
            valid = item in {"ltr", "rtl"}
        elif key == "font-weight":
            valid = bool(re.fullmatch(r"normal|bold|[1-9]00", item))
        elif key == "font-style":
            valid = item in {"normal", "italic", "oblique"}
        elif key == "text-decoration":
            valid = item in {"none", "underline", "line-through"}
        if valid:
            styles.append(f"{key}:{item}")
    return ";".join(styles)


class _EmailHTML(HTMLParser):
    _tags = {"p", "div", "span", "br", "hr", "strong", "b", "em", "i", "u", "s", "strike", "sub", "sup", "a", "img", "ul", "ol", "li", "blockquote", "pre", "code", "h1", "h2", "h3", "h4", "h5", "h6", "table", "thead", "tbody", "tfoot", "tr", "td", "th"}
    _blocked = {"script", "style", "iframe", "object", "embed", "svg", "math", "head", "template"}
    _void = {"br", "hr", "img"}
    _blocks = {"p", "div", "br", "hr", "li", "blockquote", "pre", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self, inline_images=None):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.text = []
        self.blocked = []
        self.open_tags = []
        self.inline_images = inline_images

    def handle_starttag(self, tag, attrs):
        if self.blocked:
            if tag in self._blocked:
                self.blocked.append(tag)
            return
        if tag in self._blocked:
            if tag != "embed":
                self.blocked.append(tag)
            return
        if tag not in self._tags:
            return
        clean = []
        class_styles = []
        inline_styles = []
        for key, value in attrs:
            if value is None or key.startswith("on"):
                continue
            if key == "style":
                inline_styles.append(_safe_style(value))
                continue
            elif key == "class":
                value = " ".join(c for c in value.split() if re.fullmatch(r"ql-(?:font|size|align|indent|direction)-[a-zA-Z0-9-]+", c))
                for class_name in value.split():
                    if class_name in _QUILL_STYLES:
                        class_styles.append(_QUILL_STYLES[class_name])
                    elif re.fullmatch(r"ql-indent-[1-8]", class_name):
                        class_styles.append(f"margin-left:{int(class_name[-1]) * 3}em")
            elif key == "href" and tag == "a":
                value = "".join(c for c in value.strip() if ord(c) > 32)
                if urlsplit(value).scheme.lower() not in {"http", "https", "mailto"}:
                    continue
            elif key == "src" and tag == "img":
                if value.lower().startswith("data:"):
                    subtype, data = _decode_image(value)
                    if self.inline_images is not None:
                        cid = hashlib.sha256(data).hexdigest() + "@inline"
                        self.inline_images[cid] = (subtype, data)
                        value = "cid:" + cid
                elif value.startswith("cid:") and re.fullmatch(r"cid:[a-zA-Z0-9@._-]+", value):
                    pass
                else:
                    # Never fetch or retain remote tracking images.
                    continue
            elif key in {"alt", "title"}:
                pass
            elif key in {"width", "height", "colspan", "rowspan"}:
                if not re.fullmatch(r"\d{1,4}", value):
                    continue
            elif key == "dir":
                if value not in {"ltr", "rtl", "auto"}:
                    continue
            else:
                continue
            if value:
                clean.append(f'{key}="{html.escape(value, quote=True)}"')
        style_values = {}
        for item in class_styles + inline_styles:
            for declaration in item.split(";"):
                key, separator, value = declaration.partition(":")
                if separator:
                    style_values[key] = value
        styles = ";".join(f"{key}:{value}" for key, value in style_values.items())
        if styles:
            clean.append(f'style="{html.escape(styles, quote=True)}"')
        if tag in self._blocks:
            self.text.append("\n")
        if tag == "img":
            self.text.append(dict(attrs).get("alt") or "")
        self.output.append("<" + tag + (" " + " ".join(clean) if clean else "") + ">")
        if tag not in self._void:
            self.open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.blocked:
            if tag in self.blocked:
                index = len(self.blocked) - 1 - self.blocked[::-1].index(tag)
                del self.blocked[index:]
            return
        if tag in self._tags and tag not in self._void:
            if tag not in self.open_tags:
                return
            index = len(self.open_tags) - 1 - self.open_tags[::-1].index(tag)
            for opened in reversed(self.open_tags[index:]):
                self.output.append(f"</{opened}>")
            del self.open_tags[index:]
        if tag in self._blocks:
            self.text.append("\n")
        elif tag in {"td", "th"}:
            self.text.append("\t")

    def handle_data(self, data):
        if not self.blocked:
            self.output.append(html.escape(data, quote=False))
            self.text.append(data)

    def close(self):
        super().close()
        self.blocked.clear()
        for tag in reversed(self.open_tags):
            self.output.append(f"</{tag}>")
        self.open_tags.clear()


def render_email(subject, html_content, recipient, sender, add_unsubscribe=True):
    """Render the same validated content for preview and SMTP submission."""
    if len(str(html_content).encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ValueError("Email content exceeds the total size limit")
    values = recipient.get("values", {})
    if not isinstance(values, dict):
        raise ValueError("Recipient values must be a dict")

    def replace(match, escape):
        key = match[1].strip() if match[1] is not None else _NAME_COLUMN
        if key in values:
            value = values[key]
        elif key == _NAME_COLUMN:
            value = recipient.get("name") or "\u6536\u4ef6\u4eba"
        else:
            raise ValueError(f"Unknown email variable: {key}")
        if value is None or not str(value).strip():
            raise ValueError(f"Empty email variable: {key}")
        return html.escape(str(value), quote=True) if escape else str(value)

    rendered_subject = _header(_VARIABLE.sub(lambda m: replace(m, False), str(subject)))
    content = _VARIABLE.sub(lambda m: replace(m, True), str(html_content))
    if re.search(r"\{\{\s*\}\}", str(subject) + str(html_content)):
        raise ValueError("Empty email variable")
    parser = _EmailHTML()
    parser.feed(content)
    parser.close()
    if add_unsubscribe:
        address = _address(sender["email"])
        uri = "mailto:" + address + "?subject=" + quote("\u9000\u8ba2")
        footer = (
            '<hr><p style="color:#777;font-size:12px;line-height:1.6">'
            '\u5982\u4e0d\u613f\u518d\u6536\u5230\u6b64\u7c7b\u90ae\u4ef6\uff0c\u8bf7\u56de\u590d\u672c\u90ae\u4ef6\u5e76\u6ce8\u660e\u201c\u9000\u8ba2\u201d\uff0c\u6216'
            f'<a href="{html.escape(uri, quote=True)}">\u53d1\u9000\u8ba2\u90ae\u4ef6\u81f3 {html.escape(address)}</a>\u3002</p>'
        )
        # A closed parser may retain script/style CDATA state on older Python patches.
        footer_parser = _EmailHTML()
        footer_parser.feed(footer)
        footer_parser.close()
        parser.output.extend(footer_parser.output)
        parser.text.extend(footer_parser.text)
    content = "".join(parser.output)
    if len(content.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ValueError("Email content exceeds the total size limit")
    text = re.sub(r"\n[ \t]*\n+", "\n\n", "".join(parser.text)).strip()
    return {"subject": rendered_subject, "html_content": content, "text_content": text}


class EmailSenderCore:
    def __init__(self, logger=None, timeout=20):
        self.logger = logger or logging.getLogger("email_sender_core")
        self.timeout = float(timeout)
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("SMTP timeout must be positive and finite")
        self._connection_cache = {}

    render_email = staticmethod(render_email)

    @staticmethod
    def validate_email(email_str):
        return re.fullmatch(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", str(email_str).strip()) is not None

    def create_email_msg(self, sender, recipient, email_index, html_content, subject,
                         image_path=None, attachment_path=None, add_unsubscribe=False):
        return self._create_message(sender, recipient, html_content, subject,
                                    attachment_path, add_unsubscribe, image_path=image_path)

    def _create_message(self, sender, recipient, html_content, subject,
                        attachment_path, add_unsubscribe, message_id=None, image_path=None):
        rendered = render_email(subject, html_content, recipient, sender, add_unsubscribe)
        from_address, to_address = _address(sender["email"]), _address(recipient["email"])
        msg = MIMEMultipart("mixed")
        msg["From"] = formataddr((_header(sender.get("name", "")), from_address))
        msg["To"] = formataddr((_header(recipient.get("name", "")), to_address))
        msg["Subject"] = Header(rendered["subject"], "utf-8").encode()
        msg["Date"] = formatdate(localtime=True)
        if message_id is not None:
            message_id = _header(message_id)
            if not re.fullmatch(r"<[^<>\s]+@[^<>\s]+>", message_id):
                raise ValueError("Invalid Message-ID")
        msg["Message-ID"] = message_id or make_msgid(domain=from_address.split("@")[1])
        if add_unsubscribe:
            msg["List-Unsubscribe"] = f'<mailto:{from_address}?subject={quote(chr(0x9000) + chr(0x8ba2))}>'
        related = MIMEMultipart("related")
        alternative = MIMEMultipart("alternative")
        msg.attach(related)
        related.attach(alternative)
        images = {}
        parser = _EmailHTML(images)
        parser.feed(rendered["html_content"])
        parser.close()
        alternative.attach(MIMEText(rendered["text_content"], "plain", "utf-8"))
        alternative.attach(MIMEText("".join(parser.output), "html", "utf-8"))
        for cid, (subtype, data) in images.items():
            image = MIMEImage(data, _subtype=subtype)
            image.add_header("Content-ID", f"<{cid}>")
            image.add_header("Content-Disposition", "inline")
            related.attach(image)
        if image_path is not None:
            with open(image_path, "rb") as stream:
                data = stream.read(MAX_INLINE_IMAGE_BYTES + 1)
            if not data or len(data) > MAX_INLINE_IMAGE_BYTES:
                raise ValueError("Empty or oversized inline image")
            image = MIMEImage(data)
            if image.get_content_subtype() not in {"png", "jpeg", "gif", "webp"}:
                raise ValueError("Unsupported inline image type")
            image.add_header("Content-ID", "<image1>")
            image.add_header("Content-Disposition", "inline")
            related.attach(image)
        if attachment_path is not None:
            with open(attachment_path, "rb") as stream:
                data = stream.read(MAX_MESSAGE_BYTES + 1)
            if len(data) > MAX_MESSAGE_BYTES:
                raise ValueError("Attachment exceeds the total size limit")
            attachment = MIMEApplication(data)
            filename = _header(os.path.basename(attachment_path))
            attachment.add_header("Content-Disposition", "attachment", filename=("utf-8", "", filename))
            msg.attach(attachment)
        if len(msg.as_bytes(policy=policy.SMTP)) > MAX_MESSAGE_BYTES:
            raise ValueError("Email exceeds the total size limit")
        return msg

    def _connection_key(self, sender):
        port = int(sender["smtp_port"])
        security = sender.get("security", "ssl" if port == 465 else "starttls")
        if security not in {"ssl", "starttls"}:
            raise ValueError("SMTP security must be ssl or starttls")
        host = _header(sender["smtp_server"]).strip().lower()
        if not host or not 1 <= port <= 65535:
            raise ValueError("Invalid SMTP host or port")
        return (host, port, security, _address(sender["email"]), sender["password"])

    def _get_connection(self, sender):
        key = self._connection_key(sender)
        if key in self._connection_cache:
            try:
                code, _ = self._connection_cache[key].noop()
                if code == 250:
                    return self._connection_cache[key]
            except (OSError, smtplib.SMTPException):
                pass
            self._close_connection(key)
        host, port, security, email, password = key
        context = ssl.create_default_context()
        server = None
        try:
            if security == "ssl":
                server = smtplib.SMTP_SSL(host, port, timeout=self.timeout, context=context)
            else:
                server = smtplib.SMTP(host, port, timeout=self.timeout)
                server.ehlo_or_helo_if_needed()
                server.starttls(context=context)
                server.ehlo_or_helo_if_needed()
            server.login(email, password)
        except Exception:
            if server is not None:
                self._dispose(server)
            raise
        self._connection_cache[key] = server
        return server

    def _close_connection(self, key, graceful=False):
        server = self._connection_cache.pop(key, None)
        if server is not None:
            try:
                if graceful:
                    server.quit()
            except (OSError, smtplib.SMTPException):
                pass
            finally:
                self._dispose(server)

    @staticmethod
    def _dispose(server):
        try:
            server.close()
        except (OSError, smtplib.SMTPException):
            pass

    def close_all(self):
        for key in list(self._connection_cache):
            self._close_connection(key, graceful=True)

    def close_all_connections(self):
        self.close_all()

    @staticmethod
    def _rejection(code, detail, account_error=False, recipient_rejection=False):
        detail = detail.decode("utf-8", errors="replace") if isinstance(detail, bytes) else str(detail)
        permanent = recipient_rejection and 500 <= code < 600 and bool(re.search(
            r"\b5\.1\.1\b|\b(?:user|mailbox|recipient|address) (?:not found|unknown|does not exist)\b|\bno such (?:user|mailbox|recipient)\b", detail, re.I))
        account_error = account_error or bool(re.search(
            r"\b(?:account (?:disabled|suspended|blocked)|authentication required|relay(?:ing)? (?:denied|not permitted)|sender (?:rejected|not authorized)|daily (?:sending )?(?:limit|quota))\b", detail, re.I))
        return SendResult("failed", detail, retryable=400 <= code < 500,
                          account_error=account_error, code=code, permanent_address=permanent)

    def send_attempt(self, sender, recipient, html_content, subject, attachment_path=None,
                     add_unsubscribe=True, message_id=None) -> SendResult:
        return self._send_attempt(sender, recipient, html_content, subject, attachment_path,
                                  add_unsubscribe, message_id)

    def _send_attempt(self, sender, recipient, html_content, subject, attachment_path,
                      add_unsubscribe, message_id=None, image_path=None):
        stage = "prepare"
        key = None
        try:
            msg = self._create_message(sender, recipient, html_content, subject, attachment_path,
                                       add_unsubscribe, message_id, image_path)
            payload = msg.as_bytes(policy=policy.SMTP)
            key = self._connection_key(sender)
            stage = "connect"
            server = self._get_connection(sender)
            # A broken connection after this point cannot prove non-submission.
            stage = "sendmail"
            refused = server.sendmail(_address(sender["email"]), _address(recipient["email"]), payload)
            if refused:
                code, detail = next(iter(refused.values()))
                self._close_connection(key)
                return self._rejection(code, detail, recipient_rejection=True)
            return SendResult("accepted", "SMTP server accepted the message")
        except smtplib.SMTPRecipientsRefused as exc:
            if key is not None:
                self._close_connection(key)
            code, detail = next(iter(exc.recipients.values()))
            return self._rejection(code, detail, recipient_rejection=True)
        except smtplib.SMTPResponseException as exc:
            if key is not None:
                self._close_connection(key)
            if not 400 <= exc.smtp_code < 600:
                return SendResult("uncertain" if stage == "sendmail" else "failed", str(exc), code=exc.smtp_code)
            account_error = isinstance(exc, (smtplib.SMTPAuthenticationError, smtplib.SMTPSenderRefused)) or exc.smtp_code in {530, 534, 535, 538}
            return self._rejection(exc.smtp_code, exc.smtp_error, account_error=account_error)
        except smtplib.SMTPException as exc:
            if key is not None:
                self._close_connection(key)
            if isinstance(exc, smtplib.SMTPNotSupportedError):
                return SendResult("failed", str(exc), account_error=True)
            return SendResult("uncertain" if stage == "sendmail" else "failed", str(exc),
                              retryable=stage == "connect" and isinstance(exc, smtplib.SMTPServerDisconnected))
        except OSError as exc:
            if key is not None:
                self._close_connection(key)
            if stage == "sendmail":
                return SendResult("uncertain", f"SMTP submission status unknown: {exc}")
            return SendResult("failed", f"Message not submitted: {exc}",
                              retryable=stage == "connect" and not isinstance(exc, ssl.SSLError),
                              account_error=isinstance(exc, ssl.SSLError))
        except (ValueError, KeyError, TypeError) as exc:
            return SendResult("failed", f"Message not submitted: {exc}")

    def send_single(self, sender, recipient, email_index, html_content, subject,
                    image_path=None, attachment_path=None, add_unsubscribe=False):
        result = self._send_attempt(sender, recipient, html_content, subject, attachment_path,
                                    add_unsubscribe, image_path=image_path)
        return ("success" if result.status == "accepted" else result.status), result.detail
