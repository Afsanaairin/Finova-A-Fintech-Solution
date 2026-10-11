"""Boundary checks for the local FINOVA demo and an authenticated HTTPS proxy."""
from dataclasses import dataclass, field
from http.server import ThreadingHTTPServer
import re
import threading
from urllib.parse import urlsplit


@dataclass(frozen=True)
class SecuritySettings:
    mode: str = 'local'
    public_origin: str = ''
    proxy_token: str = field(default='', repr=False)

    @classmethod
    def from_config(cls, conf):
        # Keep the stdlib backend off every public/LAN interface, in both modes.
        if conf.get('HOST', '127.0.0.1') != '127.0.0.1':
            raise ValueError('HOST must be 127.0.0.1. Use an authenticated HTTPS reverse proxy for remote access.')
        mode = conf.get('FINOVA_DEPLOYMENT', 'local')
        if mode not in ('local', 'proxy'):
            raise ValueError('FINOVA_DEPLOYMENT must be local or proxy.')
        if mode == 'local':
            return cls()
        origin = conf.get('FINOVA_PUBLIC_ORIGIN', '').rstrip('/')
        parsed = urlsplit(origin)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError('Proxy mode requires FINOVA_PUBLIC_ORIGIN=https://your-hostname.')
        # Require the same format as secrets.token_urlsafe(32), without examples.
        token = conf.get('FINOVA_PROXY_TOKEN', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', token):
            raise ValueError('Proxy mode requires a random FINOVA_PROXY_TOKEN (at least 43 URL-safe characters).')
        return cls(mode, origin, token)


class FinovaHTTPServer(ThreadingHTTPServer):
    """Loopback-only backend with bounded workers and socket read timeouts."""
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address, handler, settings=None):
        if address[0] != '127.0.0.1':
            raise ValueError('The FINOVA backend may only listen on 127.0.0.1.')
        self.security = settings or SecuritySettings()
        self._workers = threading.BoundedSemaphore(8)
        super().__init__(address, handler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(15)
        return connection, address

    def process_request(self, connection, address):
        if not self._workers.acquire(blocking=False):
            self.shutdown_request(connection)
            return
        try:
            super().process_request(connection, address)
        except Exception:
            self._workers.release()
            raise

    def process_request_thread(self, connection, address):
        try:
            super().process_request_thread(connection, address)
        finally:
            self._workers.release()
