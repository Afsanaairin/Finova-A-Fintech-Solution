"""PDF extraction, financial boundaries, and upload/review lifecycle regressions."""
import io
import json
from email.message import Message
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from finance import analyze
from pdf_reader import (document_amount, pdf_capabilities, preview_pdf,
                        reviewed_data, transaction_drafts)
import server


def pdf_objects(objects):
    result = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for index, item in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f'{index} 0 obj\n'.encode() + item + b'\nendobj\n')
    xref = len(result)
    result.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        result.extend(f'{offset:010d} 00000 n \n'.encode())
    result.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(result)


def text_pdf(lines):
    escaped = [line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)') for line in lines]
    content = ('BT /F1 12 Tf 40 740 Td ' + ' 0 -22 Td '.join(f'({line}) Tj' for line in escaped) + ' ET').encode()
    return pdf_objects([
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1000 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>',
        f'<< /Length {len(content)} >>\nstream\n'.encode() + content + b'\nendstream'
    ])


def scanned_pdf(searchable):
    """Render a real page, then embed its pixels without a searchable text layer."""
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary, 'source.pdf')
        path.write_bytes(searchable)
        prefix = Path(temporary, 'scan')
        subprocess.run(['pdftoppm', '-singlefile', '-r', '150', '-gray', str(path), str(prefix)],
                       capture_output=True, check=True, timeout=20)
        image = prefix.with_suffix('.pgm').read_bytes()
    match = re.match(rb'P5\s+(\d+)\s+(\d+)\s+255\s', image)
    if not match:
        raise ValueError('Unexpected PGM test image.')
    width, height = map(int, match.groups())
    pixels = zlib.compress(image[match.end():])
    content = b'q 1000 0 0 792 0 0 cm /Scan Do Q'
    return pdf_objects([
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1000 792] /Resources << /XObject << /Scan 4 0 R >> >> /Contents 5 0 R >>',
        f'<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length {len(pixels)} >>\nstream\n'.encode() + pixels + b'\nendstream',
        f'<< /Length {len(content)} >>\nstream\n'.encode() + content + b'\nendstream'
    ])


def multipart(blob, filename):
    boundary = 'finova-test-boundary'
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            'Content-Type: application/pdf\r\n\r\n').encode() + blob + f'\r\n--{boundary}--\r\n'.encode()
    return body, f'multipart/form-data; boundary={boundary}'


def post(path, payload, session='pdf-test-session', content_type='application/json'):
    handler = object.__new__(server.Handler)
    body = json.dumps(payload).encode() if content_type == 'application/json' else payload
    handler.path = path
    handler.headers = Message()
    for name, value in {'Content-Length': str(len(body)), 'Content-Type': content_type,
                        'Host': '127.0.0.1:8000', 'X-Finova-Request': '1'}.items():
        handler.headers[name] = value
    handler.command = 'POST'
    handler.server = SimpleNamespace(security=server.SecuritySettings(), server_port=8000)
    handler.rfile = io.BytesIO(body)
    handler._session = lambda: session
    handler._require_login = lambda: True
    handler.send_json = lambda status, data: (status, data)
    return handler.do_POST()


class PdfParserTests(unittest.TestCase):
    def test_unsigned_amount_requires_direction_review(self):
        rows = transaction_drafts([{'page': 1, 'method': 'text',
                                   'text': 'Date Description Amount\n09/02/2026 Office rent 300.00'}])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['Type'], '')
        self.assertTrue(rows[0]['issues'])
        with self.assertRaisesRegex(ValueError, 'choose Income or Expense'):
            reviewed_data({'kind': 'transactions', 'confirmed': True, 'rows': rows})

    def test_signed_transactions_ignore_opening_balance(self):
        rows = transaction_drafts([{'page': 2, 'method': 'text', 'text':
            '2026-09-01 Opening Balance 5000.00\n2026-09-02 Customer payment +1200.00\n2026-09-03 Rent (300.00)'}])
        self.assertEqual([row['Type'] for row in rows], ['Income', 'Expense'])
        self.assertEqual([row['Amount_USD'] for row in rows], [1200, 300])
        self.assertEqual(rows[0]['Source_Page'], 2)

    def test_amounts_reject_nonfinite_and_excess_precision(self):
        for value in ('NaN', 'Infinity', '1000000000001', '1.234'):
            self.assertIsNone(document_amount(value))
        self.assertEqual(document_amount('$1,200.00 DR'), -1200)

    def test_partial_statement_has_no_closing_cash_or_business_forecast(self):
        data = reviewed_data({'kind': 'transactions', 'confirmed': True, 'scope': 'expenses',
                              'rows': [{'Date': '2026-09-01', 'Type': 'Expense', 'Amount_USD': '300'}]})
        result = analyze(data)
        self.assertEqual(result['totals']['cash_out'], 300)
        self.assertIsNone(result['totals']['closing_cash'])
        self.assertIsNone(result['totals']['outstanding_invoices'])
        self.assertIsNone(result['totals']['subscription_monthly'])
        self.assertEqual(result['forecast'], [])
        self.assertIn('unavailable', server.offline_answer('Forecast next month', result))
        self.assertIn('No customer invoice records', server.offline_answer('Any invoices overdue?', result))

    def test_complete_statement_needs_history_for_forecast(self):
        payload = {'kind': 'transactions', 'confirmed': True, 'scope': 'complete', 'opening_cash': '1000',
                   'rows': [{'Date': '2026-09-01', 'Type': 'Expense', 'Amount_USD': '300'}]}
        result = analyze(reviewed_data(payload))
        self.assertEqual(result['totals']['closing_cash'], 700)
        self.assertEqual(result['forecast'], [])
        payload['rows'] += [{'Date': f'2026-{month:02d}-01', 'Type': 'Expense', 'Amount_USD': '200'} for month in (7, 8)]
        self.assertEqual(len(analyze(reviewed_data(payload))['forecast']), 3)

    def test_review_rejects_unconfirmed_invalid_or_conflicting_records(self):
        payload = {'kind': 'transactions', 'confirmed': True, 'scope': 'expenses',
                   'rows': [{'Date': '2026-09-01', 'Type': 'Income', 'Amount_USD': '300'}]}
        with self.assertRaisesRegex(ValueError, 'expenses-only'):
            reviewed_data(payload)
        payload['confirmed'] = False
        with self.assertRaisesRegex(ValueError, 'confirm'):
            reviewed_data(payload)
        payload['confirmed'] = True
        payload['rows'][0]['Date'] = '2026-02-30'
        with self.assertRaisesRegex(ValueError, 'valid date'):
            reviewed_data(payload)

    def test_invoice_only_analysis_preserves_unknown_balances(self):
        payload = {'kind': 'invoices', 'confirmed': True, 'as_of': '2026-10-10', 'rows': [
            {'Invoice_ID': 'INV-1', 'Customer': 'A', 'Due_Date': '2026-09-15',
             'Amount_USD': '1200', 'Status': 'Unpaid'},
            {'Invoice_ID': 'INV-2', 'Customer': 'B', 'Amount_USD': '500', 'Status': 'Paid'},
            {'Invoice_ID': 'INV-3', 'Customer': 'C', 'Amount_USD': '800', 'Status': 'Unknown'}]}
        result = analyze(reviewed_data(payload))
        self.assertEqual(result['invoice_count'], 3)
        self.assertEqual(result['totals']['invoice_amount'], 2500)
        self.assertEqual(result['totals']['outstanding_invoices'], 1200)
        self.assertEqual(result['totals']['unknown_invoice_balances'], 1)
        self.assertEqual(result['totals']['overdue_invoices'], 1)
        self.assertIsNone(result['totals']['cash_in'])
        self.assertIsNone(result['wrapped'])
        self.assertEqual(result['forecast'], [])
        self.assertIn('Invoices alone do not establish cash received', server.offline_answer('Cash forecast?', result))

    def test_invoice_review_rejects_duplicate_ids_and_conflicting_payment_status(self):
        row = {'Invoice_ID': 'INV-1', 'Customer': 'A', 'Amount_USD': '100', 'Status': 'Paid', 'Outstanding_USD': '50'}
        payload = {'kind': 'invoices', 'confirmed': True, 'as_of': '2026-10-10', 'rows': [row]}
        with self.assertRaisesRegex(ValueError, 'paid invoice'):
            reviewed_data(payload)
        row['Outstanding_USD'] = '0'
        payload['rows'] = [row, dict(row)]
        with self.assertRaisesRegex(ValueError, 'duplicate invoice'):
            reviewed_data(payload)

    def test_invalid_pdf_missing_tools_and_page_limits_have_clear_errors(self):
        with self.assertRaisesRegex(ValueError, 'valid PDF'):
            preview_pdf(b'not a PDF', 'bad.pdf')
        with patch('pdf_reader.pdf_capabilities', return_value={'text': False, 'ocr': False}):
            with self.assertRaisesRegex(ValueError, 'Poppler'):
                preview_pdf(b'%PDF-1.4', 'example.pdf')
        with patch('pdf_reader.pdf_capabilities', return_value={'text': True, 'ocr': False}):
            with patch('pdf_reader._run', return_value='Pages: 21\n'):
                with self.assertRaisesRegex(ValueError, '20 pages'):
                    preview_pdf(b'%PDF-1.4', 'long.pdf')
            with patch('pdf_reader._run', side_effect=['Pages: 1\n', '\f']):
                with self.assertRaisesRegex(ValueError, 'needs OCR'):
                    preview_pdf(b'%PDF-1.4', 'scan.pdf')

    def test_extraction_budget_stops_before_starting_another_command(self):
        with patch('pdf_reader.pdf_capabilities', return_value={'text': True, 'ocr': True}):
            with patch('pdf_reader.time.monotonic', side_effect=[0, 0, 61]):
                with patch('pdf_reader._run', return_value='Pages: 1\n') as command:
                    with self.assertRaisesRegex(ValueError, 'exceeded 60 seconds'):
                        preview_pdf(b'%PDF-1.4', 'slow.pdf')
        self.assertEqual(command.call_count, 1)

    def test_too_many_scanned_pages_rejects_before_ocr_work(self):
        with patch('pdf_reader.pdf_capabilities', return_value={'text': True, 'ocr': True}):
            with patch('pdf_reader._run', side_effect=['Pages: 6\n', '\f' * 6]) as command:
                with self.assertRaisesRegex(ValueError, 'up to 5 OCR pages'):
                    preview_pdf(b'%PDF-1.4', 'long-scan.pdf')
        self.assertEqual(command.call_count, 2)


@unittest.skipUnless(pdf_capabilities()['text'], 'Poppler not installed')
class PdfExtractionTests(unittest.TestCase):
    def test_real_bank_pdf_excludes_running_balance(self):
        lines = [
            f"{'Date':<12}{'Description':<24}{'Debit':>12}{'Credit':>12}{'Balance':>12}",
            f"{'09/01/2026':<12}{'Customer payment':<24}{'':>12}{'1200.00':>12}{'6200.00':>12}",
            f"{'09/02/2026':<12}{'Office rent':<24}{'300.00':>12}{'':>12}{'5900.00':>12}",
        ]
        result = preview_pdf(text_pdf(lines), 'bank.pdf')
        self.assertEqual(result['kind'], 'transactions')
        self.assertFalse(result['used_ocr'])
        self.assertEqual([row['Amount_USD'] for row in result['transaction_rows']], [1200, 300])
        self.assertEqual([row['Type'] for row in result['transaction_rows']], ['Income', 'Expense'])

    def test_real_customer_invoice_pdf(self):
        result = preview_pdf(text_pdf(['Invoice Number: INV-001', 'Invoice Date: 09/01/2026',
                                      'Bill To: Example Customer', 'Due Date: 09/15/2026',
                                      'Invoice Total: $1,200.00', 'Amount Due: $1,200.00']), 'invoice.pdf')
        self.assertEqual(result['kind'], 'invoices')
        row = result['invoice_rows'][0]
        self.assertEqual(row['Invoice_ID'], 'INV-001')
        self.assertEqual(row['Customer'], 'Example Customer')
        self.assertEqual(row['Due_Date'], '2026-09-15')
        self.assertEqual(row['Amount_USD'], 1200)
        self.assertEqual(row['Outstanding_USD'], 1200)
        self.assertEqual(row['Status'], 'Unknown')

    @unittest.skipUnless(pdf_capabilities()['ocr'], 'Tesseract not installed')
    def test_real_scanned_pdf_uses_ocr(self):
        scanned = scanned_pdf(text_pdf(['Bank statement', '2026-09-01 Income Customer payment +1200.00',
                                        '2026-09-02 Expense Office rent -300.00']))
        result = preview_pdf(scanned, 'scanned.pdf')
        self.assertTrue(result['used_ocr'])
        self.assertEqual([row['Amount_USD'] for row in result['transaction_rows']], [1200, 300])
        self.assertEqual([row['Type'] for row in result['transaction_rows']], ['Income', 'Expense'])


class PdfUploadLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.session = 'pdf-test-session'
        server.SESSIONS[self.session] = {'data': server.DEFAULT_RESULT, 'user': 'local', 'seen': time.monotonic()}
        server.PENDING_IMPORTS.pop(self.session, None)
        self.document = {'filename': 'bank.pdf', 'kind': 'transactions', 'pages': 1, 'used_ocr': False,
                         'transaction_rows': [{'Date': '2026-09-01', 'Type': 'Income', 'Amount_USD': 1200}],
                         'invoice_rows': [], 'source_text': 'fixture', 'warnings': [], 'requires_review': True}

    def tearDown(self):
        server.SESSIONS.pop(self.session, None)
        server.PENDING_IMPORTS.pop(self.session, None)

    def upload(self):
        body, content_type = multipart(b'%PDF-1.4 test', 'bank.pdf')
        with patch.object(server, 'preview_pdf', return_value=self.document):
            status, response = post('/api/upload', body, content_type=content_type)
        self.assertEqual(status, 200)
        return response

    def test_preview_does_not_replace_dashboard_and_confirm_imports_corrections(self):
        response = self.upload()
        self.assertTrue(response['review_required'])
        self.assertIs(server.SESSIONS[self.session]['data'], server.DEFAULT_RESULT)
        payload = {'review_token': response['review_token'], 'kind': 'transactions', 'confirmed': True,
                   'rows': [{'Date': '2026-09-01', 'Type': 'Income', 'Amount_USD': 1250}]}
        status, response = post('/api/pdf/confirm', payload)
        self.assertEqual(status, 200)
        self.assertEqual(response['summary']['totals']['cash_in'], 1250)
        self.assertTrue(response['summary']['import_source']['reviewed'])
        self.assertNotIn(self.session, server.PENDING_IMPORTS)
        self.assertEqual(post('/api/pdf/confirm', payload)[0], 400)

    def test_invalid_token_or_record_preserves_dashboard(self):
        response = self.upload()
        payload = {'review_token': 'different-session-token', 'kind': 'transactions', 'confirmed': True,
                   'rows': [{'Date': '2026-09-01', 'Type': 'Income', 'Amount_USD': 1200}]}
        self.assertEqual(post('/api/pdf/confirm', payload)[0], 400)
        payload['review_token'] = response['review_token']
        payload['rows'][0]['Amount_USD'] = 'not an amount'
        self.assertEqual(post('/api/pdf/confirm', payload)[0], 400)
        self.assertIs(server.SESSIONS[self.session]['data'], server.DEFAULT_RESULT)

    def test_cancel_and_expired_reviews_preserve_dashboard(self):
        response = self.upload()
        status, _ = post('/api/pdf/cancel', {'review_token': response['review_token']})
        self.assertEqual(status, 200)
        self.assertNotIn(self.session, server.PENDING_IMPORTS)
        response = self.upload()
        server.PENDING_IMPORTS[self.session]['created'] = time.monotonic() - 901
        self.assertEqual(post('/api/pdf/confirm', {'review_token': response['review_token']})[0], 400)
        self.assertIs(server.SESSIONS[self.session]['data'], server.DEFAULT_RESULT)

    @unittest.skipUnless(pdf_capabilities()['text'], 'Poppler not installed')
    def test_pdf_only_invoice_upload_and_confirmation(self):
        body, content_type = multipart(text_pdf(['Invoice Number: INV-001', 'Bill To: Customer A',
                                                'Due Date: 09/15/2026', 'Total: $1,200.00']), 'invoice.pdf')
        status, response = post('/api/upload', body, content_type=content_type)
        self.assertEqual(status, 200)
        self.assertEqual(response['document']['kind'], 'invoices')
        row = response['document']['invoice_rows'][0]
        row['Status'] = 'Unpaid'
        status, response = post('/api/pdf/confirm', {'review_token': response['review_token'], 'kind': 'invoices',
                                                   'confirmed': True, 'as_of': '2026-10-10', 'rows': [row]})
        self.assertEqual(status, 200)
        self.assertEqual(response['summary']['totals']['outstanding_invoices'], 1200)
        self.assertIsNone(response['summary']['totals']['cash_in'])


if __name__ == '__main__':
    unittest.main()
