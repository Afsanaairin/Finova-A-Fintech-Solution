"""Exercise passwordless login over HTTP without sending real email."""
import http.client
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from auth import AuthService
import server


class QuietHandler(server.Handler):
    def log_message(self, fmt, *args):
        pass


class AuthenticationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = {
            'COOKIE_SECURE': 'false',
            'AUTH_CODE_TTL_SECONDS': '300',
            'AUTH_SESSION_TTL_SECONDS': '604800',
        }
        self.messages = []
        self.auth = AuthService(
            Path(self.temp.name) / 'auth.sqlite3',
            config_callable=lambda: dict(self.settings),
            send_email=lambda email, code, ttl: self.messages.append((email, code, ttl)),
        )
        self.patches = [
            patch.object(server, 'AUTH', self.auth),
            patch.object(server, 'config', side_effect=lambda: dict(self.settings)),
            patch.object(server, 'SESSIONS', {}),
        ]
        for active_patch in self.patches:
            active_patch.start()
        self.http_server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.port = self.http_server.server_address[1]
        self.origin = f'http://127.0.0.1:{self.port}'
        self.thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http_server.shutdown()
        self.http_server.server_close()
        self.thread.join(timeout=5)
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.temp.cleanup()

    def request(self, method, path, payload=None, headers=None, raw=None, origin=True):
        request_headers = {}
        if method == 'POST':
            request_headers['Content-Type'] = 'application/json'
            if origin:
                request_headers['Origin'] = self.origin
        request_headers.update(headers or {})
        if raw is not None:
            body = raw
        elif payload is not None:
            body = json.dumps(payload).encode('utf-8')
        else:
            body = None
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            response_body = response.read()
            return response.status, json.loads(response_body), response.getheaders()
        finally:
            connection.close()

    def cookies(self, response_headers):
        result = SimpleCookie()
        for name, value in response_headers:
            if name.lower() == 'set-cookie':
                result.load(value)
        return result

    def login(self, email='reader@outlook.com'):
        status, payload, _ = self.request('POST', '/api/auth/send-code', {'email': email})
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload['ok'])
        recipient, code, ttl = self.messages[-1]
        self.assertEqual(recipient, email)
        self.assertEqual(ttl, 300)
        self.assertRegex(code, r'^\d{6}$')
        status, payload, headers = self.request(
            'POST', '/api/auth/verify-code', {'email': email, 'code': code}
        )
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload['user'], {'email': email})
        return self.cookies(headers), code

    def upload(self, cookie_header):
        boundary = 'finova-upload-boundary'
        body = (
            f'--{boundary}\r\n'
            'Content-Disposition: form-data; name="file"; filename="private.csv"\r\n'
            'Content-Type: text/csv\r\n\r\n'
            'Date,Type,Amount_USD,Category,Description\r\n'
            '2026-09-01,Expense,987.65,Private expense,Confidential account details\r\n'
            f'--{boundary}--\r\n'
        ).encode('utf-8')
        return self.request(
            'POST', '/api/upload', raw=body,
            headers={
                'Cookie': cookie_header,
                'Content-Type': f'multipart/form-data; boundary={boundary}',
            },
        )

    def test_login_restores_identity_and_logout_revokes_cookie(self):
        status, payload, headers = self.request('GET', '/api/auth/me')
        self.assertEqual(status, 200)
        self.assertEqual(payload, {'ok': True, 'user': None})
        self.assertIn('finova_demo', self.cookies(headers))

        cookies, code = self.login()
        self.assertIn('finova_auth', cookies)
        self.assertIn('finova_demo', cookies)
        auth_cookie = cookies['finova_auth']
        self.assertTrue(auth_cookie['httponly'])
        self.assertEqual(auth_cookie['samesite'], 'Lax')
        self.assertEqual(auth_cookie['path'], '/')
        self.assertEqual(auth_cookie['max-age'], '604800')
        self.assertFalse(auth_cookie['secure'])
        cookie_header = f'finova_auth={auth_cookie.value}'
        status, payload, _ = self.request(
            'GET', '/api/auth/me', headers={'Cookie': cookie_header}
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload['user'], {'email': 'reader@outlook.com'})

        status, payload, headers = self.request(
            'POST', '/api/auth/logout', {}, headers={'Cookie': cookie_header}
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload['ok'])
        self.assertEqual(self.cookies(headers)['finova_auth']['max-age'], '0')
        status, payload, _ = self.request(
            'GET', '/api/auth/me', headers={'Cookie': cookie_header}
        )
        self.assertEqual(status, 200)
        self.assertIsNone(payload['user'])
        status, payload, _ = self.request(
            'POST', '/api/auth/verify-code',
            {'email': 'reader@outlook.com', 'code': code},
        )
        self.assertEqual(status, 400)
        self.assertIn('error', payload)

    def test_anonymous_and_authenticated_dashboard_remain_available(self):
        status, anonymous, headers = self.request('GET', '/api/dashboard')
        self.assertEqual(status, 200)
        demo_cookie = self.cookies(headers)['finova_demo'].value
        cookies, _ = self.login()
        status, authenticated, _ = self.request(
            'GET', '/api/dashboard',
            headers={'Cookie': (
                f'finova_demo={demo_cookie}; '
                f'finova_auth={cookies["finova_auth"].value}'
            )},
        )
        self.assertEqual(status, 200)
        self.assertEqual(authenticated, anonymous)
        self.assertEqual(authenticated['transaction_count'], server.DEFAULT_RESULT['transaction_count'])

    def test_logout_removes_uploaded_data_and_rotates_the_demo_cookie(self):
        cookies, _ = self.login()
        old_sid = cookies['finova_demo'].value
        token = cookies['finova_auth'].value
        old_cookie_header = f'finova_demo={old_sid}; finova_auth={token}'
        status, payload, _ = self.upload(old_cookie_header)
        self.assertEqual(status, 200, payload)
        self.assertIn('Confidential account details', json.dumps(payload))

        status, payload, headers = self.request(
            'POST', '/api/auth/logout', {}, headers={'Cookie': old_cookie_header}
        )
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload, {'ok': True, 'user': None})
        logout_cookies = self.cookies(headers)
        new_sid = logout_cookies['finova_demo'].value
        self.assertNotEqual(new_sid, old_sid)
        self.assertEqual(logout_cookies['finova_auth']['max-age'], '0')
        self.assertIsNone(self.auth.get_user(token))
        self.assertNotIn(old_sid, server.SESSIONS)

        for cookie_header in (f'finova_demo={new_sid}', old_cookie_header):
            with self.subTest(cookie_header=cookie_header):
                status, dashboard, _ = self.request(
                    'GET', '/api/dashboard', headers={'Cookie': cookie_header}
                )
                self.assertEqual(status, 200, dashboard)
                self.assertEqual(dashboard, server.DEFAULT_RESULT)
                self.assertNotIn('Confidential account details', json.dumps(dashboard))
        self.assertNotIn(old_sid, server.SESSIONS)

    def test_upload_in_progress_cannot_restore_data_after_logout(self):
        cookies, _ = self.login()
        old_sid = cookies['finova_demo'].value
        cookie_header = (
            f'finova_demo={old_sid}; finova_auth={cookies["finova_auth"].value}'
        )
        started = threading.Event()
        proceed = threading.Event()
        completed = []
        failures = []
        original_read_data = server.read_data

        def paused_read_data(raw, filename):
            started.set()
            if not proceed.wait(timeout=5):
                raise RuntimeError('The test did not release the upload.')
            return original_read_data(raw, filename)

        def upload_in_background():
            try:
                completed.append(self.upload(cookie_header))
            except Exception as exc:
                failures.append(exc)

        with patch.object(server, 'read_data', side_effect=paused_read_data):
            worker = threading.Thread(target=upload_in_background)
            worker.start()
            try:
                self.assertTrue(started.wait(timeout=3))
                status, payload, headers = self.request(
                    'POST', '/api/auth/logout', {}, headers={'Cookie': cookie_header}
                )
                self.assertEqual(status, 200, payload)
            finally:
                proceed.set()
                worker.join(timeout=5)

        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0][0], 409, completed)
        self.assertNotIn('Confidential account details', json.dumps(completed[0][1]))
        self.assertNotIn(old_sid, server.SESSIONS)
        new_sid = self.cookies(headers)['finova_demo'].value
        status, dashboard, _ = self.request(
            'GET', '/api/dashboard', headers={'Cookie': f'finova_demo={new_sid}'}
        )
        self.assertEqual(status, 200)
        self.assertEqual(dashboard, server.DEFAULT_RESULT)

    def test_reset_in_progress_cannot_recreate_a_retired_session(self):
        cookies, _ = self.login()
        old_sid = cookies['finova_demo'].value
        cookie_header = (
            f'finova_demo={old_sid}; finova_auth={cookies["finova_auth"].value}'
        )
        started = threading.Event()
        proceed = threading.Event()
        completed = []
        failures = []
        original_session = QuietHandler._session

        def paused_session(handler):
            sid = original_session(handler)
            if handler.path == '/api/reset':
                started.set()
                if not proceed.wait(timeout=5):
                    raise RuntimeError('The test did not release the reset.')
            return sid

        def reset_in_background():
            try:
                completed.append(self.request(
                    'POST', '/api/reset', {}, headers={'Cookie': cookie_header}
                ))
            except Exception as exc:
                failures.append(exc)

        with patch.object(QuietHandler, '_session', paused_session):
            worker = threading.Thread(target=reset_in_background)
            worker.start()
            try:
                self.assertTrue(started.wait(timeout=3))
                status, payload, _ = self.request(
                    'POST', '/api/auth/logout', {}, headers={'Cookie': cookie_header}
                )
                self.assertEqual(status, 200, payload)
            finally:
                proceed.set()
                worker.join(timeout=5)

        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0][0], 409, completed)
        self.assertNotIn(old_sid, server.SESSIONS)

    def test_authentication_rejects_foreign_or_opaque_origins(self):
        for path, body in (
            ('/api/auth/send-code', {'email': 'reader@gmail.com'}),
            ('/api/auth/verify-code', {'email': 'reader@gmail.com', 'code': '123456'}),
            ('/api/auth/logout', {}),
        ):
            for bad_origin in ('https://foreign.example', 'null', self.origin + '.evil.example'):
                with self.subTest(path=path, origin=bad_origin):
                    status, payload, _ = self.request(
                        'POST', path, body, headers={'Origin': bad_origin}
                    )
                    self.assertEqual(status, 403)
                    self.assertIn('error', payload)
        self.assertEqual(self.messages, [])

    def test_originless_clients_are_allowed_but_cross_site_fetch_is_rejected(self):
        status, payload, _ = self.request(
            'POST', '/api/auth/send-code', {'email': 'cli@example.com'}, origin=False
        )
        self.assertEqual(status, 200, payload)
        status, payload, _ = self.request(
            'POST', '/api/auth/send-code', {'email': 'blocked@example.com'},
            headers={'Sec-Fetch-Site': 'cross-site'}, origin=False,
        )
        self.assertEqual(status, 403)
        self.assertIn('error', payload)
        self.assertEqual(len(self.messages), 1)

    def test_public_origin_overrides_the_inferred_host(self):
        self.settings['PUBLIC_ORIGIN'] = 'https://finova.example'
        status, payload, _ = self.request(
            'POST', '/api/auth/send-code', {'email': 'reader@example.com'}
        )
        self.assertEqual(status, 403)
        status, payload, _ = self.request(
            'POST', '/api/auth/send-code', {'email': 'reader@example.com'},
            headers={'Origin': self.settings['PUBLIC_ORIGIN']},
        )
        self.assertEqual(status, 200, payload)

    def test_authentication_rejects_malformed_or_non_object_json(self):
        for body in (b'{', b'[]', b'null', b'"text"', b'123', b'\xff'):
            with self.subTest(body=body):
                status, payload, _ = self.request('POST', '/api/auth/send-code', raw=body)
                self.assertEqual(status, 400)
                self.assertIn('error', payload)
        self.assertEqual(self.messages, [])

    def test_authentication_rejects_large_body_and_wrong_content_type(self):
        status, payload, _ = self.request(
            'POST', '/api/auth/send-code', raw=b' ' * 4097
        )
        self.assertEqual(status, 413)
        self.assertIn('error', payload)
        status, payload, _ = self.request(
            'POST', '/api/auth/send-code', {'email': 'reader@example.com'},
            headers={'Content-Type': 'text/plain'},
        )
        self.assertEqual(status, 415)
        self.assertIn('error', payload)
        self.assertEqual(self.messages, [])

    def test_production_cookie_is_secure(self):
        self.settings['COOKIE_SECURE'] = 'true'
        self.origin = f'https://127.0.0.1:{self.port}'
        cookies, _ = self.login()
        self.assertTrue(cookies['finova_auth']['secure'])
        self.assertTrue(cookies['finova_auth']['httponly'])
        status, _, headers = self.request(
            'POST', '/api/auth/logout', {},
            headers={'Cookie': f'finova_auth={cookies["finova_auth"].value}'},
        )
        self.assertEqual(status, 200)
        self.assertTrue(self.cookies(headers)['finova_auth']['secure'])
        self.assertEqual(self.cookies(headers)['finova_auth']['max-age'], '0')


if __name__ == '__main__':
    unittest.main()
