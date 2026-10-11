"""Exercise email login without contacting an SMTP server."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from auth import AuthError, AuthService, normalize_email


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "private" / "auth.sqlite3"
        self.now = 1_800_000_000.0
        self.config = {}
        self.messages = []
        self.auth = self.service()

    def send_email(self, email, code, ttl):
        self.messages.append((email, code, ttl))

    def service(self, sender=None):
        return AuthService(
            self.db_path, lambda: self.config,
            send_email=sender or self.send_email,
            clock=lambda: self.now,
        )

    def issue(self, email="Customer@example.com", ip="203.0.113.1"):
        self.auth.send_code(email, ip)
        return self.messages[-1][1]

    def assert_auth_error(self, status, action):
        with self.assertRaises(AuthError) as raised:
            action()
        self.assertEqual(raised.exception.status, status)
        return raised.exception

    def test_import_and_empty_token_do_not_create_database(self):
        self.assertIsNone(self.auth.get_user(""))
        self.auth.logout("")
        self.assertFalse(self.db_path.exists())

    def test_login_persists_across_service_restart_and_logout(self):
        code = self.issue("Customer@EXAMPLE.COM")
        result = self.auth.verify_code("Customer@example.com", code)
        self.assertEqual(result["user"], {"email": "Customer@example.com"})
        restarted = self.service()
        self.assertEqual(restarted.get_user(result["token"]), result["user"])
        restarted.logout(result["token"])
        self.assertIsNone(self.auth.get_user(result["token"]))

    def test_successful_code_cannot_be_replayed(self):
        code = self.issue()
        self.auth.verify_code("Customer@example.com", code)
        self.assert_auth_error(400, lambda: self.auth.verify_code("Customer@example.com", code))

    def test_code_expires_at_deadline(self):
        code = self.issue()
        self.now += 300
        self.assert_auth_error(400, lambda: self.auth.verify_code("Customer@example.com", code))

    def test_five_wrong_attempts_invalidate_even_correct_code(self):
        code = self.issue()
        wrong = "000000" if code != "000000" else "000001"
        for _ in range(5):
            self.assert_auth_error(400, lambda: self.auth.verify_code("Customer@example.com", wrong))
        self.assert_auth_error(400, lambda: self.auth.verify_code("Customer@example.com", code))

    def test_malformed_codes_count_toward_attempt_limit(self):
        code = self.issue()
        for _ in range(5):
            self.assert_auth_error(400, lambda: self.auth.verify_code("Customer@example.com", "bad"))
        self.assert_auth_error(400, lambda: self.auth.verify_code("Customer@example.com", code))

    def test_session_expires_and_new_login_rotates_old_session(self):
        self.config["AUTH_SESSION_TTL_SECONDS"] = "300"
        first = self.auth.verify_code("Customer@example.com", self.issue())
        self.now += 60
        second = self.auth.verify_code("Customer@example.com", self.issue(), previous_token=first["token"])
        self.assertNotEqual(first["token"], second["token"])
        self.assertIsNone(self.auth.get_user(first["token"]))
        self.assertIsNotNone(self.auth.get_user(second["token"]))
        self.now += 300
        self.assertIsNone(self.auth.get_user(second["token"]))

    def test_resending_invalidates_previous_code(self):
        with patch("auth.secrets.randbelow", side_effect=[111111, 222222]):
            old_code = self.issue()
            self.now += 60
            new_code = self.issue()
        self.assert_auth_error(400, lambda: self.auth.verify_code("Customer@example.com", old_code))
        self.auth.verify_code("Customer@example.com", new_code)

    def test_email_cooldown_survives_restart(self):
        self.issue()
        error = self.assert_auth_error(429, lambda: self.service().send_code("Customer@example.com", "203.0.113.2"))
        self.assertEqual(error.retry_after, 60)
        self.assertEqual(len(self.messages), 1)
        self.now += 60
        self.issue()
        self.assertEqual(len(self.messages), 2)

    def test_email_can_request_more_than_five_codes_per_hour_with_cooldowns(self):
        for _ in range(6):
            self.issue()
            self.now += 60
        self.assertEqual(len(self.messages), 6)
        self.now += 3240
        self.issue()
        with closing(sqlite3.connect(str(self.db_path))) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM send_events").fetchone()[0], 6)

    def test_shared_ip_can_send_to_more_than_ten_recipients_without_waiting(self):
        for number in range(11):
            self.issue(f"person{number}@example{number}.com")
        self.assertEqual(len(self.messages), 11)
        error = self.assert_auth_error(429, lambda: self.issue("person0@example0.com"))
        self.assertEqual(error.retry_after, 60)

    def test_email_validation_rejects_header_injection(self):
        for value in ("", None, "bad", "a@", "a@example.com\r\nBcc: attacker@example.com", "a..b@example.com", "a@-example.com"):
            with self.subTest(value=value):
                self.assert_auth_error(400, lambda: self.auth.send_code(value, "203.0.113.1"))
        self.assertEqual(normalize_email("User.Name+tag@GMAIL.COM"), "User.Name+tag@gmail.com")
        self.assertFalse(self.db_path.exists())

    def test_delivery_failure_leaves_no_usable_code_or_raw_error(self):
        def fail(email, code, ttl):
            self.messages.append((email, code, ttl))
            raise RuntimeError("SMTP secret details")
        self.auth = self.service(fail)
        error = self.assert_auth_error(503, lambda: self.issue())
        self.assertNotIn("secret details", error.message)
        self.assert_auth_error(400, lambda: self.auth.verify_code("Customer@example.com", self.messages[-1][1]))
        self.assert_auth_error(429, lambda: self.issue())

    def test_pending_delivery_cannot_verify_and_late_failure_preserves_new_code(self):
        started = threading.Event()
        finish = threading.Event()
        old_code = []

        def delayed_failure(email, code, ttl):
            old_code.append(code)
            started.set()
            if not finish.wait(5):
                raise RuntimeError("Test timed out")
            raise RuntimeError("Old delivery failed")

        pending = self.service(delayed_failure)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(pending.send_code, "Customer@example.com", "203.0.113.1")
            self.assertTrue(started.wait(5))
            try:
                self.assert_auth_error(400, lambda: self.auth.verify_code("Customer@example.com", old_code[0]))
                self.now += 60
                new_code = self.issue()
            finally:
                finish.set()
            self.assert_auth_error(503, future.result)
        self.assertIsNotNone(self.auth.verify_code("Customer@example.com", new_code)["user"])

    def test_concurrent_verification_allows_only_one_session(self):
        code = self.issue()
        barrier = threading.Barrier(2)

        def verify():
            barrier.wait(timeout=5)
            try:
                return self.service().verify_code("Customer@example.com", code)
            except AuthError as error:
                return error.status

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: verify(), range(2)))
        self.assertEqual(sum(isinstance(outcome, dict) for outcome in outcomes), 1)
        self.assertIn(400, outcomes)

    def test_database_does_not_store_raw_session_token(self):
        result = self.auth.verify_code("Customer@example.com", self.issue())
        with closing(sqlite3.connect(str(self.db_path))) as connection:
            saved_token = connection.execute("SELECT token_hash FROM sessions").fetchone()[0]
        self.assertNotEqual(saved_token, result["token"])
        self.assertEqual(len(saved_token), 64)

    def test_smtp_requires_credentials_before_creating_database(self):
        sender = AuthService(self.db_path, lambda: self.config, clock=lambda: self.now)
        self.assert_auth_error(503, lambda: sender.send_code("user@example.com", "203.0.113.1"))
        self.assertFalse(self.db_path.exists())
        self.config.update(SMTP_USER="your-account@gmail.com", SMTP_APP_PASSWORD="your-app-password")
        self.assert_auth_error(503, lambda: sender.send_code("user@example.com", "203.0.113.1"))

    def test_default_smtp_uses_tls_and_can_send_to_other_domains(self):
        self.config.update(SMTP_USER="sender@gmail.com", SMTP_APP_PASSWORD="abcd efgh ijkl mnop")
        sender = AuthService(self.db_path, lambda: self.config, clock=lambda: self.now)
        with patch("auth.smtplib.SMTP") as smtp_class:
            smtp = smtp_class.return_value.__enter__.return_value
            sender.send_code("recipient@qq.com", "203.0.113.1")
        smtp_class.assert_called_once_with("smtp.gmail.com", 587, timeout=20)
        self.assertEqual(smtp.ehlo.call_count, 2)
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("sender@gmail.com", "abcdefghijklmnop")
        self.assertEqual(
            [call[0] for call in smtp.method_calls],
            ["ehlo", "starttls", "ehlo", "login", "send_message"],
        )
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["To"], "recipient@qq.com")
        self.assertEqual(message["From"], "sender@gmail.com")
        self.assertIn("Your FINOVA login code is:", message.get_content())


if __name__ == "__main__":
    unittest.main()
