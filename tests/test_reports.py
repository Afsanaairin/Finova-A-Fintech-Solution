"""Financial correctness, evidence, valid PDF structure and report session boundaries."""
import http.client
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from finance import analyze, transaction_records
from report_pdf import render_pdf
from reports import ReportInputError, build_report, currency
from security import FinovaHTTPServer, SecuritySettings
import server


class ReportTests(unittest.TestCase):
    def report(self, **options):
        return build_report(server.DEFAULT_DATA, server.DEFAULT_RESULT, options)

    def section(self, document, title):
        return next(s for s in document['sections'] if s['title'] == title)

    def test_monthly_figures_and_same_document_sections(self):
        report = self.report()
        section = self.section(report, 'Financial Performance')
        self.assertEqual([m['value'] for m in section['metrics']], ['$39,032.14', '$31,217.08', '$24,490.30', '$6,726.78'])
        self.assertEqual(len(report['sections']), 8)
        self.assertEqual(section['chart']['labels'], ['2026-08', '2026-09'])
        self.assertEqual(self.section(report, 'Expense Analysis')['table']['rows'][0][0], 'Payroll')
        self.assertIn('not accounting profit', ' '.join(self.section(report, 'Data & Methodology')['paragraphs']))

    def test_quarter_uses_full_ledger_instead_of_latest_100_records(self):
        report = self.report(period='quarterly', end_month='2025-06')
        records = [r for r in transaction_records(server.DEFAULT_DATA['Transactions']) if '2025-04' <= r['month'] <= '2025-06']
        expected = currency(round(sum(r['amount'] for r in records if r['type'] == 'Expense'), 2))
        self.assertEqual(self.section(report, 'Financial Performance')['metrics'][2]['value'], expected)
        self.assertEqual(report['period']['start'], '2025-04')
        self.assertEqual(report['period']['label'], 'Q2 2025')
        self.assertEqual(report['sections'][0]['paragraphs'][0], f'{len(records)} cash transactions were recorded in the selected period.')

    def test_annual_ytd_and_partial_quarter_labels(self):
        report = self.report(period='annual')
        self.assertEqual(report['period']['label'], '2026 year-to-date through September')
        self.assertIn('2025-01 to 2025-09', ' '.join(self.section(report, 'Financial Performance')['paragraphs']))
        self.assertIn('partial quarter', self.report(period='quarterly', end_month='2026-08')['period']['label'])
        self.assertEqual(self.report(period='annual', end_month='2025-12')['period']['label'], '2025')

    def test_electricity_five_questions_match_verified_figures(self):
        finding = next(a for a in server.DEFAULT_RESULT['anomalies'] if a['category'] == 'Electricity' and a['month'] == '2026-06')
        report = self.report(report_type='anomaly', anomaly_id=finding['id'])
        self.assertEqual(report['subtitle'], 'Unusual Electricity Spending')
        question_sections = [s for s in report['sections'] if re.match(r'^\d\. ', s['title'])]
        self.assertEqual(len(question_sections), 5)
        self.assertIn('62.8%', question_sections[0]['paragraphs'][0])
        self.assertIn('$1,166.39', question_sections[0]['paragraphs'][0])
        self.assertIn('$716.43', question_sections[0]['paragraphs'][0])
        self.assertIn('$449.96', question_sections[2]['paragraphs'][0])
        self.assertIn('cannot establish', question_sections[3]['paragraphs'][0])
        self.assertIn('utility invoices', question_sections[4]['paragraphs'][0])
        evidence = self.section(report, 'Supporting source records')['table']['rows']
        self.assertAlmostEqual(sum(float(r[2].replace('$', '').replace(',', '')) for r in evidence), finding['amount'])

    def test_grouped_invoices_and_subscription_cost(self):
        for kind, fragment in [('Overdue invoices', 'grouped as one flagged pattern'), ('Subscription increase', '$15.00 per month')]:
            finding = next(a for a in server.DEFAULT_RESULT['anomalies'] if a['type'] == kind)
            report = self.report(report_type='anomaly', anomaly_id=finding['id'])
            self.assertIn(fragment, ' '.join(report['sections'][1]['paragraphs']))

    def test_free_to_paid_subscription_has_no_invented_percentage(self):
        source = {'Transactions':[{'Date':'2026-09-01','Type':'Expense','Category':'Software Subscriptions',
                  'Counterparty':'Example','Amount_USD':15}], 'Subscriptions':[{'Service':'Example','Initial_Monthly_USD':0}],
                  'Operating Expenses':[{'Date':'2026-08-01','Vendor':'Example','Amount_USD':0},
                                        {'Date':'2026-09-01','Vendor':'Example','Amount_USD':15}]}
        summary = analyze(source)
        finding = next(a for a in summary['anomalies'] if a['type'] == 'Subscription increase')
        report = build_report(source, summary, {'report_type':'anomaly','anomaly_id':finding['id']})
        self.assertIn('$15.00 per month', report['sections'][1]['paragraphs'][0])
        self.assertIn('percentage change is not defined', report['sections'][1]['paragraphs'][0])

    def test_partial_data_does_not_create_cash_balance_or_forecast(self):
        source = {'Transactions': [{'Date':'2026-09-01','Type':'Expense','Category':'Rent','Description':'Rent','Amount_USD':500}],
                  'Business Profile':[{'Field':'Data Scope','Value':'expenses'}]}
        report = build_report(source, analyze(source), {})
        self.assertEqual(self.section(report, 'Cash-Flow Assessment')['metrics'][0]['value'], 'Not provided')
        forecast = self.section(report, 'Forecast & Scenario Analysis')
        self.assertNotIn('chart', forecast)
        self.assertIn('not available', ' '.join(forecast['paragraphs']))

    def test_invoice_only_report_and_unknown_balances(self):
        source = {'Invoice Reporting Date':'2026-10-10', 'Invoices':[
            {'Invoice_ID':'INV-1','Customer':'Known','Amount_USD':1200,'Outstanding_USD':1200,'Due_Date':'2026-09-15'},
            {'Invoice_ID':'INV-2','Customer':'Unknown','Amount_USD':1000,'Due_Date':'2026-09-15'}]}
        report = build_report(source, analyze(source), {})
        self.assertEqual(self.section(report, 'Financial Performance')['metrics'][1]['value'], 'Not provided')
        self.assertEqual(self.section(report, 'Financial Performance')['metrics'][4]['value'], '$2,200.00')
        self.assertEqual(self.section(report, 'Financial Performance')['chart']['series'][0]['values'], [1200])
        self.assertEqual(self.section(report, 'Cash-Flow Assessment')['metrics'][2]['value'], '$1,200.00')
        self.assertIn('unknown payment balances', ' '.join(self.section(report, 'Cash-Flow Assessment')['paragraphs']))

    def test_historical_outlook_does_not_use_future_ledger(self):
        old_report = self.report(end_month='2025-06', scenario={'receipts_pct':10, 'expenses_pct':-5})
        source = {**server.DEFAULT_DATA, 'Transactions':[dict(r) for r in server.DEFAULT_DATA['Transactions']]}
        for record in source['Transactions']:
            if record['Date'] > '2025-06-30':
                record['Amount_USD'] = 999999
        changed = build_report(source, analyze(source), {'end_month':'2025-06','scenario':{'receipts_pct':10,'expenses_pct':-5}})
        expected = self.section(old_report, 'Forecast & Scenario Analysis')
        self.assertEqual(expected, self.section(changed, 'Forecast & Scenario Analysis'))
        self.assertEqual(expected['chart']['labels'][0], '2025-07')
        self.assertIn('receipts adjusted +10%', ' '.join(expected['paragraphs']))

    def test_invalid_selections_are_rejected(self):
        for options in [{'end_month':'2027-01'}, {'period':'weekly'}, {'report_type':'anomaly','anomaly_id':'missing'},
                        {'scenario':{'receipts_pct':float('nan')}}, {'scenario':{'expenses_pct':101}}, {'scenario':[]}]:
            with self.subTest(options=options), self.assertRaises(ReportInputError):
                self.report(**options)

    def test_pdf_has_valid_cross_references_and_extractable_figures(self):
        report = self.report(period='quarterly')
        blob = render_pdf(report)
        self.assertTrue(blob.startswith(b'%PDF-1.4'))
        self.assertTrue(blob.endswith(b'%%EOF\n'))
        xref = int(re.search(rb'startxref\n(\d+)', blob).group(1))
        self.assertEqual(blob[xref:xref+4], b'xref')
        count = int(re.search(rb'/Type /Pages /Count (\d+)', blob).group(1))
        self.assertGreater(count, 1)
        for match in re.finditer(rb'stream\n(.*?)\nendstream', blob, re.S):
            content = zlib.decompress(match.group(1))
            self.assertIn(b'BT /F', content)
        if shutil.which('pdftotext'):
            with tempfile.TemporaryDirectory() as temporary:
                filename = Path(temporary, 'report.pdf')
                filename.write_bytes(blob)
                text = subprocess.check_output(['pdftotext',str(filename),'-']).decode()
                self.assertIn('Q3 2026', text)
                self.assertIn('Financial Performance', text)
                self.assertIn('Data & Methodology', text)


class ReportHTTPTests(unittest.TestCase):
    def setUp(self):
        self.login = patch.object(server.AUTH, 'get_user', side_effect=lambda token:
                                 {'email': 'reader@example.com'} if token == 'report-test-login' else None)
        self.login.start()
        self.addCleanup(self.login.stop)
        self.sessions = patch.object(server, 'SESSIONS', {})
        self.sessions.start()
        self.http = FinovaHTTPServer(('127.0.0.1', 0), server.Handler, SecuritySettings('proxy','https://finova.example','x'*43))
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join()
        self.sessions.stop()

    def request(self, path, options=None, headers=None, raw=None):
        supplied = {'Host':'finova.example','X-Finova-Proxy-Token':'x'*43,'X-Finova-User':'alice',
                    'X-Forwarded-Proto':'https','X-Finova-Request':'1','Content-Type':'application/json'}
        supplied.update(headers or {})
        if 'finova_auth=' not in supplied.get('Cookie', ''):
            supplied['Cookie'] = 'finova_auth=report-test-login; ' + supplied.get('Cookie', '')
        conn = http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=10)
        try:
            conn.request('POST',path,raw if raw is not None else json.dumps(options or {}),supplied)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_pdf_download_and_preview_use_session_records(self):
        status, headers, body = self.request('/api/reports/preview')
        self.assertEqual(status, 200, body)
        sid = headers['Set-Cookie'].split('finova_demo=')[1].split(';')[0]
        source = {'Transactions':[{'Date':'2026-09-01','Type':'Income','Amount_USD':987,'Description':'Private upload'}]}
        server.SESSIONS[sid].update({'data':analyze(source), 'source':source})
        status, headers, body = self.request('/api/reports/preview',headers={'Cookie':f'finova_demo={sid}'})
        self.assertEqual(status, 200, body)
        metrics = json.loads(body)['report']['sections'][1]['metrics']
        self.assertEqual(metrics[1]['value'], '$987.00')
        status, headers, body = self.request('/api/reports/download', headers={'Cookie':f'finova_demo={sid}'})
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'application/pdf')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertIn('attachment;', headers['Content-Disposition'])
        self.assertTrue(body.startswith(b'%PDF-'))
        status, _, body = self.request('/api/reports/preview',headers={'Cookie':f'finova_demo={sid}','X-Finova-User':'bob'})
        self.assertEqual(status, 200)
        self.assertNotEqual(json.loads(body)['report']['sections'][1]['metrics'][1]['value'], '$987.00')

    def test_report_routes_keep_csrf_and_input_validation(self):
        for path in ['/api/reports/preview','/api/reports/download']:
            status, _, _ = self.request(path,headers={'X-Finova-Request':'0'})
            self.assertEqual(status, 403)
            status, _, _ = self.request(path,headers={'X-Finova-Proxy-Token':'invalid'})
            self.assertEqual(status, 403)
            status, _, body = self.request(path,{'period':'weekly'})
            self.assertEqual(status, 400)
            self.assertIn('reporting period', json.loads(body)['error'])

    def test_uploaded_csv_is_the_source_of_subsequent_reports(self):
        csv = b'Date,Type,Category,Description,Amount_USD\n2026-09-01,Income,Sales,Customer payment,1234\n2026-09-02,Expense,Rent,Office rent,200\n'
        body = (b'--report-upload\r\nContent-Disposition: form-data; name="file"; filename="client.csv"\r\n'
                b'Content-Type: text/csv\r\n\r\n'+csv+b'\r\n--report-upload--\r\n')
        status, headers, response = self.request('/api/upload', headers={'Content-Type':'multipart/form-data; boundary=report-upload'}, raw=body)
        self.assertEqual(status,200,response)
        cookie = headers['Set-Cookie'].split(';')[0]
        status, _, response = self.request('/api/reports/preview', headers={'Cookie':cookie})
        self.assertEqual(status,200,response)
        doc = json.loads(response)['report']
        self.assertEqual(doc['source'],'client.csv')
        self.assertEqual(doc['sections'][1]['metrics'][1]['value'],'$1,234.00')
        self.assertEqual(doc['sections'][1]['metrics'][2]['value'],'$200.00')

    def test_retired_session_cannot_return_a_report(self):
        original = server.build_report
        def retire(*args):
            result = original(*args)
            server.SESSIONS.clear()
            return result
        with patch.object(server,'build_report',side_effect=retire):
            status, _, body = self.request('/api/reports/download')
        self.assertEqual(status,409)
        self.assertIn('dataset changed',json.loads(body)['error'])


if __name__ == '__main__':
    unittest.main()
