import base64
import copy
import os
import smtplib
import ssl
import tempfile
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

from core.email_sender import EmailSenderCore, SendResult, render_email


SENDER = {
    "email": "sender@example.com", "password": "secret", "name": "Sender",
    "smtp_server": "smtp.example.com", "smtp_port": 465, "security": "ssl",
}
RECIPIENT = {"email": "reader@example.com", "name": "Reader", "values": {}}
NAME = "\u4eba\u540d"
NAME_COLUMN = "\u59d3\u540d"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6nWQAAAAASUVORK5CYII=")


class EmailTestCase(unittest.TestCase):
    def setUp(self):
        self.sender = copy.deepcopy(SENDER)
        self.recipient = copy.deepcopy(RECIPIENT)
        self.core = EmailSenderCore()
        self.server = Mock()
        self.server.noop.return_value = (250, b"OK")
        self.server.sendmail.return_value = {}
        self.ssl_factory = self.enterContext(patch("core.email_sender.smtplib.SMTP_SSL", return_value=self.server))
        self.tls_factory = self.enterContext(patch("core.email_sender.smtplib.SMTP", return_value=self.server))
        self.enterContext(patch("socket.create_connection", side_effect=AssertionError("Real SMTP forbidden")))
        self.sleep = self.enterContext(patch("time.sleep", side_effect=AssertionError("Sleeping forbidden")))

    def send(self, **kwargs):
        return self.core.send_attempt(self.sender, self.recipient, "<p>Hello</p>", "Subject", **kwargs)

    def message(self, html_content="<p>Hello</p>", subject="Subject", **kwargs):
        msg = self.core.create_email_msg(self.sender, self.recipient, 0, html_content, subject, **kwargs)
        return BytesParser(policy=policy.default).parsebytes(msg.as_bytes(policy=policy.SMTP))


class SendAttemptTests(EmailTestCase):
    def test_result_defaults(self):
        self.assertEqual(SendResult("accepted", "OK"), SendResult("accepted", "OK", False, False, None, False))

    def test_accepted_is_one_submission_with_supplied_message_id(self):
        result = self.send(message_id="<stable@example.com>")
        self.assertEqual(result.status, "accepted")
        self.server.sendmail.assert_called_once()
        args = self.server.sendmail.call_args.args
        self.assertEqual(args[:2], (self.sender["email"], self.recipient["email"]))
        msg = BytesParser(policy=policy.default).parsebytes(args[2])
        self.assertEqual(msg["Message-ID"], "<stable@example.com>")
        self.assertIn("List-Unsubscribe", msg)
        self.assertNotIn("List-Unsubscribe-Post", msg)
        self.sleep.assert_not_called()

    def test_submission_transport_errors_are_uncertain_without_retry(self):
        for exc in (TimeoutError("timed out"), OSError("broken pipe"), smtplib.SMTPServerDisconnected("gone")):
            with self.subTest(exception=type(exc).__name__):
                self.server.reset_mock()
                self.server.sendmail.side_effect = exc
                result = self.send()
                self.assertEqual(result.status, "uncertain")
                self.assertFalse(result.retryable)
                self.server.sendmail.assert_called_once()
                self.server.close.assert_called_once()
                self.assertFalse(self.core._connection_cache)
                self.sleep.assert_not_called()

    def test_connect_timeout_is_failed_not_submitted(self):
        self.ssl_factory.side_effect = TimeoutError("timed out")
        result = self.send()
        self.assertEqual(result.status, "failed")
        self.assertTrue(result.retryable)
        self.server.sendmail.assert_not_called()
        self.ssl_factory.assert_called_once()

    def test_login_timeout_is_failed_not_submitted_and_closed(self):
        self.server.login.side_effect = TimeoutError("timed out")
        result = self.send()
        self.assertEqual(result.status, "failed")
        self.assertTrue(result.retryable)
        self.server.sendmail.assert_not_called()
        self.server.close.assert_called_once()

    def test_auth_error_marks_account(self):
        self.server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad credentials")
        result = self.send()
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.code, 535)
        self.assertTrue(result.account_error)
        self.assertFalse(result.retryable)
        self.assertFalse(result.permanent_address)
        self.server.sendmail.assert_not_called()
        self.server.close.assert_called_once()

    def test_explicit_4xx_refusals_are_retryable_without_retry(self):
        exceptions = (
            smtplib.SMTPDataError(451, b"4.3.0 Try later"),
            smtplib.SMTPRecipientsRefused({self.recipient["email"]: (450, b"4.2.0 Busy")}),
            smtplib.SMTPSenderRefused(421, b"4.7.0 Rate limit", self.sender["email"]),
        )
        for exc in exceptions:
            with self.subTest(exception=type(exc).__name__):
                self.server.reset_mock()
                self.server.sendmail.side_effect = exc
                result = self.send()
                self.assertEqual(result.status, "failed")
                self.assertTrue(result.retryable)
                self.assertFalse(result.permanent_address)
                self.server.sendmail.assert_called_once()

    def test_only_explicit_invalid_recipient_is_permanent(self):
        cases = ((b"5.1.1 No such mailbox", True), (b"User not found", True),
                 (b"User unknown", True), (b"5.7.1 Spam content rejected", False),
                 (b"5.2.2 Mailbox full", False), (b"Rejected", False))
        for detail, permanent in cases:
            with self.subTest(detail=detail):
                self.server.sendmail.side_effect = smtplib.SMTPRecipientsRefused({self.recipient["email"]: (550, detail)})
                result = self.send()
                self.assertEqual(result.status, "failed")
                self.assertEqual(result.code, 550)
                self.assertEqual(result.permanent_address, permanent)
                self.assertFalse(result.retryable)

    def test_invalid_sender_is_account_error_not_recipient_error(self):
        self.server.sendmail.side_effect = smtplib.SMTPSenderRefused(550, b"5.1.1 User not found", self.sender["email"])
        result = self.send()
        self.assertTrue(result.account_error)
        self.assertFalse(result.permanent_address)

    def test_data_rejection_does_not_invalidate_address(self):
        self.server.sendmail.side_effect = smtplib.SMTPDataError(550, b"5.1.1 User not found")
        result = self.send()
        self.assertFalse(result.permanent_address)

    def test_account_policy_and_content_policy_are_distinct(self):
        for detail, account in ((b"5.7.1 Account suspended", True), (b"5.7.1 Relay denied", True),
                                (b"5.7.1 Daily sending limit", True), (b"5.7.1 Spam content rejected", False)):
            with self.subTest(detail=detail):
                self.server.sendmail.side_effect = smtplib.SMTPDataError(550, detail)
                result = self.send()
                self.assertEqual(result.account_error, account)
                self.assertFalse(result.permanent_address)

    def test_returned_refusal_is_not_accepted(self):
        self.server.sendmail.return_value = {self.recipient["email"]: (450, b"Later")}
        result = self.send()
        self.assertEqual(result.status, "failed")
        self.assertTrue(result.retryable)

    def test_unexpected_smtp_submission_exception_is_uncertain(self):
        self.server.sendmail.side_effect = smtplib.SMTPException("Unexpected protocol state")
        self.assertEqual(self.send().status, "uncertain")
        self.server.sendmail.assert_called_once()

    def test_unparseable_smtp_reply_is_uncertain_not_rejected(self):
        self.server.sendmail.side_effect = smtplib.SMTPDataError(-1, b"Malformed reply")
        result = self.send()
        self.assertEqual(result.status, "uncertain")
        self.assertFalse(result.retryable)
        self.server.sendmail.assert_called_once()

    def test_disconnected_during_connect_is_retryable_not_uncertain(self):
        self.ssl_factory.side_effect = smtplib.SMTPServerDisconnected("gone")
        result = self.send()
        self.assertEqual(result.status, "failed")
        self.assertTrue(result.retryable)
        self.server.sendmail.assert_not_called()

    def test_close_failure_does_not_mask_uncertain_status(self):
        self.server.sendmail.side_effect = TimeoutError("timed out")
        self.server.close.side_effect = OSError("already closed")
        self.assertEqual(self.send().status, "uncertain")
        self.assertFalse(self.core._connection_cache)

    def test_tls_certificate_failure_never_submits(self):
        self.ssl_factory.side_effect = ssl.SSLCertVerificationError("certificate verify failed")
        result = self.send()
        self.assertEqual(result.status, "failed")
        self.assertTrue(result.account_error)
        self.assertFalse(result.retryable)
        self.server.sendmail.assert_not_called()

    def test_missing_attachment_prevents_connection(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = os.path.join(folder, "missing.pdf")
            with self.assertRaises(FileNotFoundError):
                self.message(attachment_path=missing)
            result = self.send(attachment_path=missing)
        self.assertEqual(result.status, "failed")
        self.assertFalse(result.retryable)
        self.ssl_factory.assert_not_called()
        self.server.sendmail.assert_not_called()

    def test_attachment_read_error_prevents_connection(self):
        with patch("builtins.open", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                self.message(attachment_path="secret.pdf")
            result = self.send(attachment_path="secret.pdf")
        self.assertEqual(result.status, "failed")
        self.ssl_factory.assert_not_called()
        self.server.sendmail.assert_not_called()

    def test_invalid_headers_and_variables_prevent_connection(self):
        for subject in ("Subject\r\nBcc: evil@example.com", "{{unknown}}"):
            with self.subTest(subject=subject):
                result = self.core.send_attempt(self.sender, self.recipient, "Hello", subject)
                self.assertEqual(result.status, "failed")
        self.ssl_factory.assert_not_called()

    def test_legacy_send_single_does_not_retry_timed_out(self):
        self.server.sendmail.side_effect = TimeoutError("timed out")
        status, detail = self.core.send_single(self.sender, self.recipient, 1, "Hello", "Subject")
        self.assertEqual(status, "uncertain")
        self.assertTrue(detail)
        self.server.sendmail.assert_called_once()
        self.sleep.assert_not_called()

    def test_legacy_success_status_is_preserved(self):
        status, _ = self.core.send_single(self.sender, self.recipient, 1, "Hello", "Subject")
        self.assertEqual(status, "success")


class ConnectionTests(EmailTestCase):
    def test_ssl_uses_verified_context_and_default_timeout(self):
        self.send()
        kwargs = self.ssl_factory.call_args.kwargs
        self.assertEqual(kwargs["timeout"], 20)
        self.assertIsInstance(kwargs["context"], ssl.SSLContext)
        self.assertTrue(kwargs["context"].check_hostname)
        self.assertEqual(kwargs["context"].verify_mode, ssl.CERT_REQUIRED)
        self.tls_factory.assert_not_called()
        self.server.starttls.assert_not_called()

    def test_explicit_starttls_overrides_port_and_verifies(self):
        self.sender["security"] = "starttls"
        self.assertEqual(self.send().status, "accepted")
        self.tls_factory.assert_called_once_with("smtp.example.com", 465, timeout=20)
        self.ssl_factory.assert_not_called()
        context = self.server.starttls.call_args.kwargs["context"]
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(self.server.ehlo_or_helo_if_needed.call_count, 2)
        calls = [call[0] for call in self.server.method_calls]
        self.assertLess(calls.index("starttls"), calls.index("login"))

    def test_legacy_missing_security_defaults_from_port(self):
        del self.sender["security"]
        self.sender["smtp_port"] = 587
        self.assertEqual(self.send().status, "accepted")
        self.server.starttls.assert_called_once()

    def test_tls_not_supported_does_not_fall_back(self):
        self.sender["security"] = "starttls"
        self.server.starttls.side_effect = smtplib.SMTPNotSupportedError("No STARTTLS")
        result = self.send()
        self.assertEqual(result.status, "failed")
        self.assertTrue(result.account_error)
        self.server.login.assert_not_called()
        self.server.sendmail.assert_not_called()
        self.server.close.assert_called_once()

    def test_security_validation_prevents_connection(self):
        self.sender["security"] = "plain"
        self.assertEqual(self.send().status, "failed")
        self.ssl_factory.assert_not_called()
        self.tls_factory.assert_not_called()

    def test_cache_reuses_only_same_configuration(self):
        self.send()
        self.send()
        self.ssl_factory.assert_called_once()
        self.server.noop.assert_called_once()
        for key, value in (("smtp_server", "other.example.com"), ("smtp_port", 2465),
                           ("password", "new-secret"), ("security", "starttls"),
                           ("email", "other@example.com")):
            with self.subTest(key=key):
                self.sender[key] = value
                before = self.ssl_factory.call_count + self.tls_factory.call_count
                self.send()
                self.assertEqual(self.ssl_factory.call_count + self.tls_factory.call_count, before + 1)

    def test_bad_noop_reconnects_before_single_submission(self):
        self.send()
        self.server.sendmail.reset_mock()
        self.server.noop.return_value = (421, b"Closed")
        self.assertEqual(self.send().status, "accepted")
        self.assertEqual(self.ssl_factory.call_count, 2)
        self.server.close.assert_called_once()
        self.server.sendmail.assert_called_once()

    def test_close_all_does_not_close_other_instances(self):
        other_core = EmailSenderCore()
        other_server = Mock()
        other_server.sendmail.return_value = {}
        self.send()
        with patch("core.email_sender.smtplib.SMTP_SSL", return_value=other_server):
            self.assertEqual(other_core.send_attempt(self.sender, self.recipient, "Hello", "Subject").status, "accepted")
        self.core.close_all()
        self.server.quit.assert_called_once()
        other_server.quit.assert_not_called()
        other_server.close.assert_not_called()
        self.assertFalse(self.core._connection_cache)
        self.assertTrue(other_core._connection_cache)
        other_core.close_all_connections()
        other_server.quit.assert_called_once()


class RenderingTests(EmailTestCase):
    def test_subject_and_html_share_variables_but_only_html_escapes(self):
        self.recipient["name"] = '<Reader & "friend">'
        self.recipient["values"] = {"company": "A&B", "count": 0}
        template = "{{company}} <" + NAME + "> &lt;" + NAME + "&gt; {{" + NAME_COLUMN + "}} {{count}}"
        rendered = render_email(template, "<p>" + template + "</p>", self.recipient, self.sender, False)
        self.assertEqual(rendered["subject"], 'A&B <Reader & "friend"> <Reader & "friend"> <Reader & "friend"> 0')
        self.assertIn("A&amp;B", rendered["html_content"])
        self.assertNotIn("<Reader", rendered["html_content"])
        self.assertEqual(rendered["text_content"], rendered["subject"])

    def test_name_default_and_table_name_override(self):
        self.recipient["name"] = ""
        template = "{{" + NAME_COLUMN + "}}"
        rendered = render_email(template, template, self.recipient, self.sender, False)
        self.assertEqual(rendered["subject"], "\u6536\u4ef6\u4eba")
        self.recipient["values"][NAME_COLUMN] = "Table Name"
        self.assertEqual(render_email(template, template, self.recipient, self.sender, False)["subject"], "Table Name")

    def test_unknown_and_empty_values_raise_in_both_templates(self):
        self.recipient["values"] = {"empty": "  ", "none": None}
        for template in ("{{missing}}", "{{empty}}", "{{none}}", "{{}}", "{{   }}"):
            for subject, body in ((template, "Hello"), ("Subject", template)):
                with self.subTest(subject=subject, body=body), self.assertRaises(ValueError):
                    render_email(subject, body, self.recipient, self.sender, False)

    def test_header_injection_from_variable_is_rejected(self):
        self.recipient["values"]["evil"] = "Value\r\nBcc: evil@example.com"
        with self.assertRaises(ValueError):
            render_email("{{evil}}", "Hello", self.recipient, self.sender, False)

    def test_structured_sanitizing_keeps_safe_quill_styles(self):
        content = ('<script>alert(1)</script><style>body{display:none}</style>'
                   '<p class="ql-font-serif ql-size-large unsafe" onclick="bad()" '
                   'style="font-family:Arial;font-size:18px;color:rgb(1, 2, 3);line-height:1.8;'
                   'background-image:url(https://evil);position:fixed;behavior:url(evil)">'
                   'Hello <a href="java&#x09;script:alert(1)" onmouseover="bad()">link</a>'
                   '<img src="https://evil/tracker.png" onerror="bad()"></p>')
        rendered = render_email("Subject", content, self.recipient, self.sender, False)
        for bad in ("script", "onclick", "onmouseover", "onerror", "background-image", "position", "behavior", "https://evil", "unsafe", "alert(1)"):
            self.assertNotIn(bad, rendered["html_content"])
        for good in ("ql-font-serif", "ql-size-large", "font-family:Arial", "font-size:18px", "color:rgb(1, 2, 3)", "line-height:1.8"):
            self.assertIn(good, rendered["html_content"])
        self.assertEqual(rendered["text_content"], "Hello link")

    def test_variable_cannot_inject_html_attributes_or_tags(self):
        self.recipient["values"]["evil"] = '\"><img src=x onerror=alert(1)>'
        rendered = render_email("Subject", '<p title="{{evil}}">{{evil}}</p>', self.recipient, self.sender, False)
        self.assertNotIn("<img", rendered["html_content"])
        self.assertIn("&lt;img", rendered["html_content"])

    def test_safe_links_and_unsubscribe_footer(self):
        rendered = render_email("Subject", '<a href="https://example.com">Web</a>', self.recipient, self.sender, True)
        self.assertIn('href="https://example.com"', rendered["html_content"])
        self.assertIn("mailto:sender@example.com?subject=", rendered["html_content"])
        self.assertIn("\u56de\u590d\u672c\u90ae\u4ef6", rendered["text_content"])
        self.assertIn("\u9000\u8ba2", rendered["text_content"])

    def test_preview_matches_mime_without_inline_images(self):
        self.recipient["values"]["company"] = "A&B"
        content = '<p onclick="evil()">{{company}}</p>'
        rendered = render_email("{{company}}", content, self.recipient, self.sender, True)
        msg = self.message(content, "{{company}}", add_unsubscribe=True)
        self.assertEqual(str(msg["Subject"]), rendered["subject"])
        self.assertEqual(msg.get_body(preferencelist=("html",)).get_content(), rendered["html_content"])
        self.assertEqual(msg.get_body(preferencelist=("plain",)).get_content(), rendered["text_content"])

    def test_quill_class_styles_are_inline_and_rendering_is_idempotent(self):
        content = '<p class="ql-font-serif ql-size-large ql-indent-2" style="font-size:18px;color:red">Hello</p>'
        rendered = render_email("Subject", content, self.recipient, self.sender, False)
        msg = self.message(content)
        body = msg.get_body(preferencelist=("html",)).get_content()
        self.assertEqual(body, rendered["html_content"])
        self.assertIn("font-family:Georgia", body)
        self.assertIn("font-size:18px", body)
        self.assertIn("margin-left:6em", body)
        self.assertEqual(body.count("font-size:"), 1)

    def test_unclosed_script_and_tags_cannot_swallow_unsubscribe_footer(self):
        for content in ("<p><b>Hello", "<script>alert(1)", "<iframe>ignored", "<style>body{display:none}"):
            with self.subTest(content=content):
                rendered = render_email("Subject", content, self.recipient, self.sender, True)
                self.assertIn("\u56de\u590d\u672c\u90ae\u4ef6", rendered["text_content"])
                self.assertIn("mailto:sender@example.com", rendered["html_content"])
                self.assertNotIn("alert(1)", rendered["html_content"])
                if content.startswith("<p>"):
                    self.assertIn("</b></p><hr>", rendered["html_content"])

    def test_no_salts_comments_or_fake_mailer(self):
        msg = self.message("<p>Hello</p><!-- ref-12345 -->", "Subject\u200b\u200c\u200d")
        self.assertEqual(str(msg["Subject"]), "Subject")
        self.assertNotIn("X-Mailer", msg)
        self.assertNotIn("ref-12345", msg.get_body(preferencelist=("html",)).get_content())
        self.assertNotIn("List-Unsubscribe", msg)
        self.assertNotIn("List-Unsubscribe-Post", msg)


class MimeTests(EmailTestCase):
    def test_mixed_related_alternative_tree_with_utf8_attachment(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "\u9644\u4ef6.pdf"
            path.write_bytes(b"%PDF-fixture")
            msg = self.message(attachment_path=path)
        self.assertEqual(msg.get_content_type(), "multipart/mixed")
        related, attachment = msg.get_payload()
        self.assertEqual(related.get_content_type(), "multipart/related")
        alternative = related.get_payload()[0]
        self.assertEqual(alternative.get_content_type(), "multipart/alternative")
        self.assertEqual([p.get_content_type() for p in alternative.get_payload()], ["text/plain", "text/html"])
        self.assertEqual(attachment.get_filename(), "\u9644\u4ef6.pdf")
        self.assertEqual(attachment.get_payload(decode=True), b"%PDF-fixture")

    def test_all_inline_types_become_deduplicated_cid_parts(self):
        fixtures = {"png": PNG, "jpeg": b"\xff\xd8\xfffixture", "gif": b"GIF89afixture", "webp": b"RIFFxxxxWEBPfixture"}
        for subtype, data in fixtures.items():
            with self.subTest(subtype=subtype):
                source = "data:image/" + subtype + ";base64," + base64.b64encode(data).decode("ascii")
                content = f'<p>Hello</p><img src="{source}"><img src="{source}">'
                msg = self.message(content)
                images = [p for p in msg.walk() if p.get_content_maintype() == "image"]
                self.assertEqual(len(images), 1)
                self.assertEqual(images[0].get_content_subtype(), subtype)
                self.assertEqual(images[0].get_payload(decode=True), data)
                body = msg.get_body(preferencelist=("html",)).get_content()
                self.assertNotIn("data:image", body)
                self.assertEqual(body.count("cid:" + images[0]["Content-ID"][1:-1]), 2)
                self.assertIn(source, render_email("Subject", content, self.recipient, self.sender, False)["html_content"])

    def test_invalid_or_unsupported_data_images_raise(self):
        for source in ("data:image/svg+xml;base64,PHN2Zz4=", "data:image/png;base64,@@@", "data:image/png;base64,A", "data:image/png;base64,"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.message(f'<img src="{source}">')
        self.ssl_factory.assert_not_called()

    def test_per_image_limit_is_enforced_before_connection(self):
        source = "data:image/png;base64," + base64.b64encode(PNG).decode("ascii")
        with patch("core.email_sender.MAX_INLINE_IMAGE_BYTES", len(PNG) - 1):
            result = self.core.send_attempt(self.sender, self.recipient, f'<img src="{source}">', "Subject")
        self.assertEqual(result.status, "failed")
        self.ssl_factory.assert_not_called()

    def test_total_serialized_limit_includes_base64_and_attachment(self):
        with patch("core.email_sender.MAX_MESSAGE_BYTES", 2000), patch("builtins.open", mock_open(read_data=b"a" * 1000)):
            with self.assertRaises(ValueError):
                self.message(attachment_path="fixture.pdf")
            result = self.send(attachment_path="fixture.pdf")
        self.assertEqual(result.status, "failed")
        self.ssl_factory.assert_not_called()

    def test_total_html_limit_is_checked(self):
        with patch("core.email_sender.MAX_MESSAGE_BYTES", 10), self.assertRaises(ValueError):
            render_email("Subject", "x" * 11, self.recipient, self.sender, False)

    def test_legacy_image_path_attaches_and_missing_path_raises(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "fixture.png"
            image.write_bytes(PNG)
            msg = self.message('<img src="cid:image1">', image_path=image)
            images = [p for p in msg.walk() if p.get_content_maintype() == "image"]
            self.assertEqual(images[0]["Content-ID"], "<image1>")
            with self.assertRaises(FileNotFoundError):
                self.message(image_path=Path(folder) / "missing.png")


if __name__ == "__main__":
    unittest.main()
