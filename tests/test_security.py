"""HTTP boundary and hostile-input regressions. No live AI calls or secrets."""
import http.client
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server
import xlsx_reader as reader
from security import FinovaHTTPServer, SecuritySettings
from tools.check_secrets import findings

CSV = b'Date,Type,Category,Description,Amount_USD\n2026-01-01,Income,Sales,Example,123\n'
PROXY_TOKEN = 'x' * 43
ORIGIN = 'https://finova.example.com'


def multipart(blob=CSV, filename='example.csv', extra=False):
    part = (b'--finova-test\r\nContent-Disposition: form-data; name="file"; filename="'
            + filename.encode() + b'"\r\nContent-Type: application/octet-stream\r\n\r\n'
            + blob + b'\r\n')
    return part + (part if extra else b'') + b'--finova-test--\r\n'


class HTTPBoundaryTests(unittest.TestCase):
    def setUp(self):
        server.SESSIONS.clear()
        self.backend = FinovaHTTPServer(('127.0.0.1', 0), server.Handler,
                                       SecuritySettings('proxy', ORIGIN, PROXY_TOKEN))
        self.thread = threading.Thread(target=self.backend.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.backend.shutdown()
        self.backend.server_close()
        self.thread.join()
        server.SESSIONS.clear()

    def request(self, method='GET', path='/api/dashboard', body=None, headers=None, trusted=True):
        supplied = {'Host': 'finova.example.com'}
        if trusted:
            supplied.update({'X-Finova-Proxy-Token': PROXY_TOKEN, 'X-Finova-User': 'alice',
                             'X-Forwarded-Proto': 'https'})
        if method == 'POST':
            supplied.update({'Content-Type': 'application/json', 'X-Finova-Request': '1'})
        supplied.update(headers or {})
        conn = http.client.HTTPConnection('127.0.0.1', self.backend.server_port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=supplied)
            response = conn.getresponse()
            payload = response.read()
            return response.status, dict(response.getheaders()), payload
        finally:
            conn.close()

    def test_every_sensitive_route_rejects_direct_or_spoofed_proxy_access(self):
        for method, path in [('GET', '/api/health'), ('GET', '/api/dashboard'),
                             ('GET', '/api/akamai-test'), ('POST', '/api/upload'),
                             ('POST', '/api/reset'), ('POST', '/api/ask'), ('POST', '/api/cover')]:
            with self.subTest(path=path):
                with patch.object(server, 'call_akamai') as upstream:
                    status, headers, _ = self.request(method, path, '{}', trusted=False,
                                                     headers={'X-Finova-User': 'alice', 'X-Forwarded-Proto': 'https'})
                    self.assertEqual(status, 403)
                    self.assertNotIn('Set-Cookie', headers)
                    upstream.assert_not_called()
        self.assertFalse(server.SESSIONS)
        self.assertEqual(self.request(headers={'X-Finova-Proxy-Token': 'wrong'})[0], 403)

    def test_https_identity_host_and_origin_are_required(self):
        for headers in [{'X-Finova-User': ''}, {'X-Forwarded-Proto': 'http'},
                        {'Host': 'evil.example'}, {'Origin': 'https://evil.example'},
                        {'Origin': 'null'}, {'Sec-Fetch-Site': 'cross-site'}]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request(headers=headers)[0], 403)

    def test_browser_can_open_home_page_from_an_external_link(self):
        headers = {'Sec-Fetch-Site': 'cross-site', 'Sec-Fetch-Mode': 'navigate',
                   'Sec-Fetch-Dest': 'document', 'Sec-Fetch-User': '?1'}
        status, response_headers, body = self.request(path='/', headers=headers)
        self.assertEqual(status, 200)
        self.assertIn('text/html', response_headers['Content-Type'])
        self.assertIn(b'FINOVA', body)
        self.assertNotIn('Set-Cookie', response_headers)
        self.assertFalse(server.SESSIONS)
        # The exception must not bypass the authenticated proxy.
        self.assertEqual(self.request(path='/', headers=headers, trusted=False)[0], 403)

    def test_navigation_exception_does_not_allow_cross_site_api_or_posts(self):
        headers = {'Sec-Fetch-Site': 'cross-site', 'Sec-Fetch-Mode': 'navigate',
                   'Sec-Fetch-Dest': 'document'}
        for path in ('/api/dashboard', '/api/health', '/api/akamai-test', '/static/app.js'):
            with self.subTest(path=path), patch.object(server, 'upstream_json') as upstream:
                self.assertEqual(self.request(path=path, headers=headers)[0], 403)
                upstream.assert_not_called()
        for method, path in [('POST', '/'), ('POST', '/api/upload'), ('POST', '/api/reset'),
                             ('POST', '/api/ask'), ('POST', '/api/cover')]:
            with self.subTest(method=method, path=path):
                self.assertEqual(self.request(method, path, '{}', headers)[0], 403)
        for changes in ({'Sec-Fetch-Mode': 'cors'}, {'Sec-Fetch-Dest': 'iframe'},
                        {'Origin': 'https://evil.example'}):
            with self.subTest(changes=changes):
                self.assertEqual(self.request(path='/', headers={**headers, **changes})[0], 403)

    def test_posts_require_csrf_marker_and_accept_same_origin_json(self):
        self.assertEqual(self.request('POST', '/api/reset', '{}', {'X-Finova-Request': ''})[0], 403)
        self.assertEqual(self.request('POST', '/api/reset', '{}', {'Origin': ORIGIN})[0], 200)
        with patch.object(server, 'akamai_configured', return_value=False):
            status, _, payload = self.request('POST', '/api/ask', json.dumps({'question': 'Why have costs changed?'}))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)['mode'], 'local')

    def test_cookie_is_secure_and_bound_to_authenticated_username(self):
        _, headers, _ = self.request()
        cookie = headers['Set-Cookie']
        for attribute in ('Secure', 'HttpOnly', 'SameSite=Strict', 'Max-Age=3600'):
            self.assertIn(attribute, cookie)
        status, _, _ = self.request('POST', '/api/upload', multipart(),
                                   {'Cookie': cookie.split(';')[0],
                                    'Content-Type': 'multipart/form-data; boundary=finova-test'})
        self.assertEqual(status, 200)
        _, _, alice = self.request(headers={'Cookie': cookie.split(';')[0]})
        self.assertEqual(json.loads(alice)['transaction_count'], 1)
        _, bob_headers, bob = self.request(headers={'Cookie': cookie.split(';')[0], 'X-Finova-User': 'bob'})
        self.assertEqual(json.loads(bob)['transaction_count'], server.DEFAULT_RESULT['transaction_count'])
        self.assertNotEqual(bob_headers['Set-Cookie'].split(';')[0], cookie.split(';')[0])

    def test_session_capacity_and_expiry(self):
        with patch.object(server, 'MAX_SESSIONS', 1):
            self.assertEqual(self.request()[0], 200)
            self.assertEqual(self.request()[0], 503)
            for entry in server.SESSIONS.values():
                entry['seen'] = time.monotonic() - server.SESSION_TTL - 1
            self.assertEqual(self.request()[0], 200)
            self.assertEqual(len(server.SESSIONS), 1)

    def test_rejects_large_json_file_and_multiple_uploads(self):
        self.assertEqual(self.request('POST', '/api/ask', b'x' * (server.MAX_JSON_BODY + 1))[0], 413)
        cases = [(multipart(extra=True), 400), (multipart(filename='file.exe'), 400),
                 (multipart(blob=b''), 400), (multipart(blob=b'x' * 10), 400)]
        for body, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(self.request('POST', '/api/upload', body,
                                 {'Content-Type': 'multipart/form-data; boundary=finova-test'})[0], expected)
        with patch.object(server, 'MAX_UPLOAD', 10):
            self.assertEqual(self.request('POST', '/api/upload', multipart(),
                             {'Content-Type': 'multipart/form-data; boundary=finova-test'})[0], 413)

    def test_json_requires_correct_content_type_and_object(self):
        self.assertEqual(self.request('POST', '/api/ask', '{}', {'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.request('POST', '/api/ask', '[]')[0], 400)
        self.assertEqual(self.request('POST', '/api/ask', 'invalid')[0], 400)

    def test_ambiguous_framing_and_truncated_bodies_are_rejected(self):
        requests = [
            ('Content-Length: 2\r\nContent-Length: 2\r\n', b'{}', 400),
            ('Transfer-Encoding: chunked\r\nContent-Length: 2\r\n', b'{}', 400),
            ('Content-Length: -1\r\n', b'', 400),
            ('', b'', 411),
            ('Content-Length: 3\r\n', b'{}', 400),
        ]
        for framing, body, expected in requests:
            with self.subTest(framing=framing):
                prefix = ('POST /api/reset HTTP/1.0\r\nHost: finova.example.com\r\n'
                          'X-Finova-User: alice\r\nX-Forwarded-Proto: https\r\n'
                          f'X-Finova-Proxy-Token: {PROXY_TOKEN}\r\nX-Finova-Request: 1\r\n'
                          + framing + '\r\n').encode()
                with socket.create_connection(self.backend.server_address, timeout=5) as conn:
                    conn.sendall(prefix + body)
                    conn.shutdown(socket.SHUT_WR)
                    response = conn.makefile('rb').read()
                self.assertEqual(int(response.split(b' ')[1]), expected)

    def test_api_responses_do_not_echo_upstream_secrets(self):
        secret = 'hk_' + 'do-not-disclose-' * 3
        with patch.object(server, 'akamai_configured', return_value=True), patch.object(server, 'ai_answer', side_effect=RuntimeError(secret)):
            status, _, payload = self.request('POST', '/api/ask', '{"question":"costs"}')
        self.assertEqual(status, 200)
        self.assertNotIn(secret.encode(), payload)
        with patch.object(server, 'akamai_configured', return_value=True), patch.object(server, 'call_akamai', side_effect=RuntimeError(secret)):
            status, _, payload = self.request('POST', '/api/cover', '{}')
        self.assertEqual(status, 502)
        self.assertNotIn(secret.encode(), payload)
        with patch.object(server, 'config', return_value={'OPENAI_API_KEY': secret}), patch.object(server, 'akamai_configured', return_value=True), patch.object(server, 'ai_answer', return_value=secret + ' ' + PROXY_TOKEN):
            status, _, payload = self.request('POST', '/api/ask', '{"question":"costs"}')
        self.assertEqual(status, 200)
        self.assertNotIn(secret.encode(), payload)
        self.assertNotIn(PROXY_TOKEN.encode(), payload)
        self.assertIn('[redacted]', json.loads(payload)['answer'])


class ConfigurationAndImporterTests(unittest.TestCase):
    def test_public_bind_and_incomplete_proxy_configuration_fail_closed(self):
        for host in ('0.0.0.0', '::', '192.0.2.1', 'localhost'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                SecuritySettings.from_config({'HOST': host})
        for conf in ({'FINOVA_DEPLOYMENT': 'other'}, {'FINOVA_DEPLOYMENT': 'proxy'},
                     {'FINOVA_DEPLOYMENT': 'proxy', 'FINOVA_PUBLIC_ORIGIN': 'http://finova.example.com', 'FINOVA_PROXY_TOKEN': PROXY_TOKEN}):
            with self.assertRaises(ValueError):
                SecuritySettings.from_config(conf)
        with self.assertRaises(ValueError):
            FinovaHTTPServer(('0.0.0.0', 0), server.Handler)

    def test_proxy_mode_ignores_checkout_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, '.env').write_text('FINOVA_DEPLOYMENT=local\nOPENAI_API_KEY=hk_from_file\n')
            with patch.object(server, 'BASE', Path(directory)), patch.dict(os.environ, {'FINOVA_DEPLOYMENT': 'proxy', 'OPENAI_API_KEY': 'from-service'}):
                self.assertEqual(server.config()['FINOVA_DEPLOYMENT'], 'proxy')
                self.assertEqual(server.config()['OPENAI_API_KEY'], 'from-service')

    def test_local_mode_blocks_rebinding_and_accepts_local_browser(self):
        backend = FinovaHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=backend.serve_forever, daemon=True)
        thread.start()
        try:
            navigation = {'Sec-Fetch-Site': 'cross-site', 'Sec-Fetch-Mode': 'navigate',
                          'Sec-Fetch-Dest': 'document'}
            for host, path, headers, status in [
                (f'127.0.0.1:{backend.server_port}', '/api/health', {}, 200),
                ('evil.example', '/api/health', {}, 403),
                (f'localhost:{backend.server_port}', '/', navigation, 200),
                (f'127.0.0.1:{backend.server_port}', '/', navigation, 200),
                (f'localhost:{backend.server_port}', '/api/dashboard', navigation, 403),
                ('evil.example', '/', navigation, 403),
            ]:
                conn = http.client.HTTPConnection(*backend.server_address, timeout=5)
                conn.request('GET', path, headers={'Host': host, **headers})
                response = conn.getresponse()
                self.assertEqual(response.status, status)
                response.read()
                conn.close()
        finally:
            backend.shutdown()
            backend.server_close()
            thread.join()

    def test_csv_limits_reject_rows_columns_and_malformed_records(self):
        with patch.object(reader, 'MAX_TOTAL_ROWS', 1):
            with self.assertRaises(ValueError):
                reader.read_data(CSV + CSV.splitlines()[-1] + b'\n', 'data.csv')
        with patch.object(reader, 'MAX_COLUMNS', 2), self.assertRaises(ValueError):
            reader.read_data(CSV, 'data.csv')
        with patch.object(reader, 'MAX_TOTAL_CELLS', 2), self.assertRaises(ValueError):
            reader.read_data(CSV, 'data.csv')
        with self.assertRaises(ValueError):
            reader.read_data(b'a,b\n1,2,3\n', 'data.csv')
        with self.assertRaises(ValueError):
            reader.read_data(b'a,b\n"unterminated,2\n', 'data.csv')

    def test_zip_structure_byte_row_column_and_xml_limits(self):
        sample = (ROOT / 'data/finova.xlsx').read_bytes()
        for name, limit in [('MAX_UNCOMPRESSED_BYTES', 1), ('MAX_ZIP_ENTRIES', 1),
                            ('MAX_SHEETS', 1), ('MAX_TOTAL_ROWS', 1), ('MAX_TOTAL_CELLS', 1)]:
            with self.subTest(limit=name), patch.object(reader, name, limit), self.assertRaises(ValueError):
                reader.read_data(sample, 'data.xlsx')
        with self.assertRaises(ValueError):
            reader._col_number('XFD1')
        with self.assertRaises(ValueError):
            reader._xml(b'<!DOCTYPE x [<!ENTITY boom "expanded">]><x>&boom;</x>')
        with self.assertRaises(ValueError):
            reader._xml('<x/>'.encode('utf-16'))
        with self.assertRaises(ValueError):
            reader.read_data(b'not a zip', 'data.xlsx')
        blob = io.BytesIO()
        with zipfile.ZipFile(blob, 'w') as archive:
            archive.writestr('xl/workbook.xml', b'<invalid>')
            archive.writestr('xl/_rels/workbook.xml.rels', b'<x/>')
        with self.assertRaises(ValueError):
            reader.read_data(blob.getvalue(), 'data.xlsx')

    def test_secret_scan_redacts_and_recognizes_placeholders(self):
        secret = ('hk_' + 'a' * 32).encode()
        self.assertTrue(findings(secret))
        self.assertTrue(findings(b'OPENAI_API_KEY=' + b'a' * 32))
        self.assertTrue(findings(b'echo ' + secret, [secret]))
        self.assertFalse(findings(b'OPENAI_API_KEY=paste_your_team_key_here'))
        self.assertFalse(findings(b'FINOVA_PROXY_TOKEN=REPLACE_WITH_SERVER_GENERATED_TOKEN'))
        self.assertFalse(findings(b'OPENAI_API_KEY=hk_from_file\\nOPENAI_BASE_URL=https://example.com'))
        self.assertFalse(findings(b'hk_old_shell_key'))
        self.assertNotIn(secret.decode(), ' '.join(findings(secret)))

    def test_upstream_credentials_are_server_only_and_redirects_are_blocked(self):
        secret = 'hk_' + 'a' * 32
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok":true}'
        with patch.object(server, 'config', return_value={'OPENAI_API_KEY': secret}), patch.object(server.UPSTREAM_OPENER, 'open', return_value=response) as opened:
            self.assertEqual(server.call_akamai('/chat/completions', {'question': 'hello'}), {'ok': True})
        req = opened.call_args.args[0]
        self.assertEqual(req.get_header('Authorization'), 'Bearer ' + secret)
        self.assertTrue(req.full_url.startswith('https://'))
        self.assertIsNone(server.NoUpstreamRedirects().redirect_request(req, None, 302, 'Found', {}, 'http://evil.example'))
        response.__enter__.return_value.read.return_value = b'12345'
        with patch.object(server.UPSTREAM_OPENER, 'open', return_value=response), self.assertRaises(RuntimeError):
            server.upstream_json(req, 1, 4)


if __name__ == '__main__':
    unittest.main()
