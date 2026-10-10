import csv
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from finance import analyze, money
from xlsx_reader import read_data


class DemoDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = read_data((ROOT/'data'/'finova.xlsx').read_bytes(),'finova.xlsx')
        cls.summary = analyze(cls.source)

    def test_input_sheets_present(self):
        expected = ['Transactions','Revenue','Invoices','Operating Expenses','Vendors','Payroll','Subscriptions','Business Profile']
        self.assertTrue(all(x in self.source for x in expected))

    def test_cash_ledger_matches_source_records(self):
        transactions = self.source['Transactions']
        operating = self.source['Operating Expenses']
        payroll = self.source['Payroll']
        invoices = self.source['Invoices']
        self.assertEqual(len(transactions),len(operating)+len(payroll)+sum(bool(i['Payment_Date']) for i in invoices))
        tx_exp = round(sum(float(t['Amount_USD']) for t in transactions if t['Type']=='Expense'),2)
        source_exp = round(sum(float(r['Amount_USD']) for r in operating)+sum(float(p['Gross_Pay_USD']) for p in payroll),2)
        self.assertEqual(tx_exp,source_exp)
        tx_income = round(sum(float(t['Amount_USD']) for t in transactions if t['Type']=='Income'),2)
        source_paid = round(sum(float(i['Amount_USD']) for i in invoices if i['Payment_Date']),2)
        self.assertEqual(tx_income,source_paid)

    def test_monthly_balance(self):
        s = self.summary
        self.assertEqual(s['months_count'],33)
        self.assertEqual(s['transaction_count'],722)
        self.assertAlmostEqual(52000+s['totals']['cash_in']-s['totals']['cash_out'],s['totals']['closing_cash'])
        self.assertEqual(s['totals']['last_month_invoiced_revenue'],39032.14)

    def test_anomalies_and_subscriptions(self):
        s = self.summary
        self.assertEqual(len(s['subscriptions']),5)
        self.assertTrue(any(x['name']=='Adobe' and x['price_increase']==15 for x in s['subscriptions']))
        self.assertTrue(any(a['category']=='Electricity' and a['month']=='2026-06' for a in s['anomalies']))
        self.assertEqual(s['totals']['overdue_invoices'],3)

    def test_forecast_and_reporting(self):
        x = self.summary
        self.assertEqual([r['month'] for r in x['forecast']],['2026-10','2026-11','2026-12'])
        self.assertGreater(x['forecast'][0]['invoiced_revenue'],0)

    def test_csv_import_works(self):
        content = b'Date,Type,Category,Description,Amount_USD\n2026-01-01,Income,Sales,Customer invoice,1000\n2026-01-02,Expense,Rent,Main office,300\n'
        csvsummary=analyze(read_data(content,'example.csv'))
        self.assertEqual(csvsummary['totals']['cash_in'],1000)
        self.assertEqual(csvsummary['totals']['cash_out'],300)
        self.assertEqual(csvsummary['months_count'],1)
        self.assertEqual(csvsummary['forecast'][0]['invoiced_revenue'],None)


if __name__=='__main__':
    unittest.main()
