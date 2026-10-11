"""Passwordless email authentication using standard-library SMTP and SQLite."""

from contextlib import contextmanager
from email.message import EmailMessage
import hashlib
import hmac
import math
from pathlib import Path
import re
import secrets
import smtplib
import sqlite3
import ssl
import threading
import time


CODE_ITERATIONS = 210_000
EMAIL_COOLDOWN = 60
SEND_EVENT_RETENTION = 3_600
MAX_CODE_ATTEMPTS = 5
INVALID_CODE_MESSAGE = "Incorrect or expired verification code. Request a new code if needed."


class AuthError(Exception):
    """An authentication failure that can be returned safely to a client."""

    def __init__(self, status, message, retry_after=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.retry_after = retry_after


def normalize_email(value):
    if not isinstance(value, str) or "\r" in value or "\n" in value:
        raise AuthError(400, "Enter a valid email address.")
    value = value.strip()
    if len(value) > 254 or value.count("@") != 1:
        raise AuthError(400, "Enter a valid email address.")
    local, domain = value.rsplit("@", 1)
    labels = domain.split(".")
    valid_local = (
        0 < len(local) <= 64
        and re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+", local)
        and not local.startswith(".")
        and not local.endswith(".")
        and ".." not in local
    )
    valid_domain = len(labels) >= 2 and all(
        0 < len(label) <= 63
        and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
        for label in labels
    )
    if not valid_local or not valid_domain:
        raise AuthError(400, "Enter a valid email address.")
    return local + "@" + domain.lower()


def bounded_setting(config, name, default, minimum, maximum):
    try:
        return max(minimum, min(maximum, int(config.get(name, default))))
    except (TypeError, ValueError):
        return default


class AuthService:
    def __init__(self, db_path, config_callable, send_email=None, clock=None):
        self.db_path = Path(db_path)
        self.config_callable = config_callable
        self.send_email = send_email
        self.clock = clock or time.time
        self._initialized = False
        self._init_lock = threading.Lock()

    @contextmanager
    def _connection(self):
        # Defer disk writes until authentication is actually used.
        with self._init_lock:
            if not self._initialized:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                initializer = sqlite3.connect(str(self.db_path), timeout=10)
                try:
                    initializer.executescript("""
                        PRAGMA journal_mode = WAL;
                        CREATE TABLE IF NOT EXISTS users (
                            id INTEGER PRIMARY KEY,
                            email TEXT UNIQUE NOT NULL,
                            created_at REAL NOT NULL
                        );
                        CREATE TABLE IF NOT EXISTS challenges (
                            email TEXT PRIMARY KEY,
                            generation TEXT NOT NULL,
                            salt BLOB NOT NULL,
                            code_hash BLOB NOT NULL,
                            expires_at REAL NOT NULL,
                            attempts INTEGER NOT NULL DEFAULT 0,
                            ready INTEGER NOT NULL DEFAULT 0
                        );
                        CREATE TABLE IF NOT EXISTS sessions (
                            token_hash TEXT PRIMARY KEY,
                            user_id INTEGER NOT NULL REFERENCES users(id),
                            expires_at REAL NOT NULL,
                            created_at REAL NOT NULL
                        );
                        CREATE TABLE IF NOT EXISTS send_events (
                            id INTEGER PRIMARY KEY,
                            email TEXT NOT NULL,
                            client_ip TEXT NOT NULL,
                            sent_at REAL NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS send_events_email_time
                            ON send_events(email, sent_at);
                        CREATE INDEX IF NOT EXISTS send_events_ip_time
                            ON send_events(client_ip, sent_at);
                        CREATE INDEX IF NOT EXISTS sessions_expiry
                            ON sessions(expires_at);
                    """)
                    initializer.commit()
                finally:
                    initializer.close()
                self._initialized = True
        connection = sqlite3.connect(str(self.db_path), timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _cleanup(connection, now):
        connection.execute("DELETE FROM challenges WHERE expires_at <= ?", (now,))
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        connection.execute("DELETE FROM send_events WHERE sent_at <= ?", (now - SEND_EVENT_RETENTION,))

    @staticmethod
    def _code_hash(code, salt):
        return hashlib.pbkdf2_hmac("sha256", code.encode("ascii"), salt, CODE_ITERATIONS)

    @staticmethod
    def _token_hash(token):
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            return None
        return hashlib.sha256(token.encode("ascii")).hexdigest()

    @staticmethod
    def _smtp_settings(config):
        username = str(config.get("SMTP_USER", "")).strip()
        password = str(config.get("SMTP_APP_PASSWORD", "")).replace(" ", "").strip()
        placeholder_words = ("your-", "your_", "yourgoogle", "yourapp", "paste", "replace", "changeme")
        if (
            not username or not password
            or any(word in username.lower() or word in password.lower() for word in placeholder_words)
        ):
            raise AuthError(503, "Email login is not configured. Set SMTP_USER and SMTP_APP_PASSWORD in .env.")
        try:
            username = normalize_email(username)
            sender = normalize_email(config.get("SMTP_FROM") or username)
            port = int(config.get("SMTP_PORT", 587))
            if not 1 <= port <= 65535:
                raise ValueError("Invalid SMTP port")
        except (AuthError, TypeError, ValueError):
            raise AuthError(503, "Email login configuration is invalid. Check the SMTP settings in .env.") from None
        host = str(config.get("SMTP_HOST", "smtp.gmail.com")).strip()
        if not host or any(char.isspace() for char in host):
            raise AuthError(503, "Email login configuration is invalid. Check SMTP_HOST in .env.")
        return host, port, username, password, sender

    @staticmethod
    def _send_smtp(email, code, ttl_seconds, settings):
        host, port, username, password, sender = settings
        message = EmailMessage()
        message["Subject"] = "Your FINOVA login code"
        message["From"] = sender
        message["To"] = email
        message.set_content(
            f"Your FINOVA login code is: {code}\n\n"
            f"This code expires in {ttl_seconds // 60} minutes.\n"
            "If you did not request this email, you can ignore it.\n"
        )
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(username, password)
            smtp.send_message(message)

    def send_code(self, email, client_ip):
        email = normalize_email(email)
        if not isinstance(client_ip, str) or not client_ip or len(client_ip) > 128:
            raise AuthError(400, "The client address is invalid.")
        config = self.config_callable()
        settings = self._smtp_settings(config) if self.send_email is None else None
        ttl = bounded_setting(config, "AUTH_CODE_TTL_SECONDS", 300, 60, 900)
        code = f"{secrets.randbelow(1_000_000):06d}"
        salt = secrets.token_bytes(16)
        code_hash = self._code_hash(code, salt)
        generation = secrets.token_urlsafe(16)
        now = self.clock()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup(connection, now)
            latest = connection.execute(
                "SELECT MAX(sent_at) FROM send_events WHERE email = ?", (email,)
            ).fetchone()[0]
            if latest is not None and now - latest < EMAIL_COOLDOWN:
                retry = max(1, math.ceil(EMAIL_COOLDOWN - (now - latest)))
                raise AuthError(429, "Please wait before requesting another code.", retry)
            connection.execute(
                "INSERT INTO send_events(email, client_ip, sent_at) VALUES (?, ?, ?)",
                (email, client_ip, now),
            )
            connection.execute(
                "INSERT OR REPLACE INTO challenges "
                "(email, generation, salt, code_hash, expires_at, attempts, ready) "
                "VALUES (?, ?, ?, ?, ?, 0, 0)",
                (email, generation, salt, code_hash, now + ttl),
            )
        try:
            # Network delivery happens after the reservation transaction commits.
            if self.send_email is not None:
                self.send_email(email, code, ttl)
            else:
                self._send_smtp(email, code, ttl, settings)
        except Exception:
            with self._connection() as connection:
                connection.execute(
                    "DELETE FROM challenges WHERE email = ? AND generation = ?", (email, generation)
                )
            raise AuthError(
                503, "Could not send the login email. Check the SMTP settings and try again after the cooldown."
            ) from None
        with self._connection() as connection:
            updated = connection.execute(
                "UPDATE challenges SET ready = 1 WHERE email = ? AND generation = ? AND expires_at > ?",
                (email, generation, self.clock()),
            ).rowcount
        if not updated:
            raise AuthError(409, "This verification code expired or was replaced. Request a new code.")
        return {"ok": True, "message": "Verification code sent. Check your inbox and spam folder.", "retry_after": EMAIL_COOLDOWN}

    def verify_code(self, email, code, previous_token=""):
        email = normalize_email(email)
        valid_format = isinstance(code, str) and re.fullmatch(r"[0-9]{6}", code)
        ttl = bounded_setting(self.config_callable(), "AUTH_SESSION_TTL_SECONDS", 604800, 300, 2592000)
        now = self.clock()
        failure = False
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup(connection, now)
            challenge = connection.execute(
                "SELECT * FROM challenges WHERE email = ? AND ready = 1", (email,)
            ).fetchone()
            if challenge is None:
                failure = True
            elif not valid_format or not hmac.compare_digest(
                self._code_hash(code, challenge["salt"]), challenge["code_hash"]
            ):
                failure = True
                if challenge["attempts"] + 1 >= MAX_CODE_ATTEMPTS:
                    connection.execute("DELETE FROM challenges WHERE email = ?", (email,))
                else:
                    connection.execute("UPDATE challenges SET attempts = attempts + 1 WHERE email = ?", (email,))
            else:
                connection.execute("DELETE FROM challenges WHERE email = ?", (email,))
                connection.execute("INSERT OR IGNORE INTO users(email, created_at) VALUES (?, ?)", (email, now))
                user_id = connection.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
                previous_hash = self._token_hash(previous_token)
                if previous_hash is not None:
                    connection.execute("DELETE FROM sessions WHERE token_hash = ?", (previous_hash,))
                token = secrets.token_urlsafe(32)
                connection.execute(
                    "INSERT INTO sessions(token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                    (self._token_hash(token), user_id, now + ttl, now),
                )
        # Commit failed-attempt updates before returning an error.
        if failure:
            raise AuthError(400, INVALID_CODE_MESSAGE)
        return {"token": token, "max_age": ttl, "user": {"email": email}}

    def get_user(self, token):
        token_hash = self._token_hash(token)
        if token_hash is None:
            return None
        with self._connection() as connection:
            self._cleanup(connection, self.clock())
            user = connection.execute(
                "SELECT users.email FROM sessions JOIN users ON users.id = sessions.user_id "
                "WHERE sessions.token_hash = ?", (token_hash,)
            ).fetchone()
        return {"email": user["email"]} if user is not None else None

    def logout(self, token):
        token_hash = self._token_hash(token)
        if token_hash is None:
            return
        with self._connection() as connection:
            self._cleanup(connection, self.clock())
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
