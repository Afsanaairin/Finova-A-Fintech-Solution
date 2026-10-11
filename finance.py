"""FINOVA deterministic financial analytics.

Cash income in Transactions differs from billed revenue in Revenue; never sum
those datasets together. Transactions already includes paid Operating Expenses
and Payroll; source sheets are for drill-down, not additional ledger entries.
"""
from collections import defaultdict
from datetime import date, datetime
from statistics import median, mean
import math


def num(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def money(v):
    return round(num(v), 2)


def parse_date(value):
    if isinstance(value, (int, float)):
        return (datetime(1899, 12, 30).date() + __import__('datetime').timedelta(days=float(value)))
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def add_month(month, distance):
    y, m = map(int, month.split('-'))
    idx = y * 12 + m - 1 + distance
    return f'{idx // 12:04d}-{idx % 12 + 1:02d}'


def _short(s, length=100):
    return str(s or '')[:length]


def analyze_invoices(data):
    """Customer invoice analysis without manufacturing a cash ledger."""
    source = data.get('Invoices') or []
    if not source:
        raise ValueError('At least one customer invoice is required.')
    as_of = parse_date(data.get('Invoice Reporting Date')) or date.today()
    profile = {str(row.get('Field')): row.get('Value') for row in data.get('Business Profile', [])}
    invoices = []
    unknown = 0
    for record in source:
        amount = num(record.get('Amount_USD'))
        outstanding = num(record.get('Outstanding_USD'), None)
        status = _short(record.get('Status') or 'Unknown')
        if outstanding is None and status.lower() == 'unpaid':
            outstanding = amount
        elif status.lower() == 'paid':
            outstanding = 0.0
        if outstanding is None:
            unknown += 1
        due = parse_date(record.get('Due_Date'))
        invoices.append({'invoice': _short(record.get('Invoice_ID')), 'customer': _short(record.get('Customer')),
                         'invoice_date': _short(record.get('Invoice_Date')), 'amount': money(amount),
                         'outstanding': money(outstanding) if outstanding is not None else None,
                         'status': status, 'due': due.isoformat() if due else '',
                         'overdue_days': max((as_of - due).days, 0) if due and outstanding and outstanding > 0 else 0})
    overdue = [{**record, 'amount': record['outstanding']} for record in invoices if record['overdue_days'] > 0]
    overdue.sort(key=lambda record: record['overdue_days'], reverse=True)
    known_outstanding = money(sum(record['outstanding'] or 0 for record in invoices))
    outstanding_total = known_outstanding if unknown < len(invoices) else None
    anomalies = []
    if overdue:
        anomalies.append({'id': 'alert-1', 'type': 'Overdue invoices', 'category': 'Accounts Receivable',
                          'month': as_of.strftime('%Y-%m'), 'amount': money(sum(record['amount'] for record in overdue)),
                          'baseline': None, 'increase_pct': None,
                          'message': f'{len(overdue)} customer invoice(s) remain overdue as of {as_of.isoformat()}.',
                          'invoices': overdue[:15], 'evidence': [], 'evidence_count': len(overdue), 'history': [],
                          'method': f'Known outstanding balance above zero and due date before {as_of.isoformat()}.',
                          'action': 'Confirm the remaining balance and expected payment date with the customer.'})
    totals = dict.fromkeys(('cash_in', 'cash_out', 'net', 'closing_cash', 'last_month_cash_in',
                           'last_month_cash_out', 'last_month_net', 'last_month_invoiced_revenue',
                           'cash_in_change_pct', 'expense_change_pct', 'subscription_monthly', 'subscription_annual'))
    totals.update({'outstanding_invoices': outstanding_total, 'overdue_invoices': len(overdue),
                   'invoice_amount': money(sum(record['amount'] for record in invoices)),
                   'unknown_invoice_balances': unknown,
                   'missing_invoice_due_dates': sum(not record['due'] for record in invoices)})
    return {'company': _short(profile.get('Business Name') or 'Your business', 65), 'currency': 'USD',
            'analysis_kind': 'invoices', 'data_scope': 'customer_invoices', 'as_of': as_of.isoformat(),
            'reporting_period': f'Invoice review as of {as_of.isoformat()}', 'transaction_count': 0,
            'invoice_count': len(invoices), 'months_count': 0, 'has_revenue_data': False,
            'has_invoice_data': True, 'has_subscription_data': False, 'has_opening_cash': False,
            'forecast_available': False, 'totals': totals, 'monthly': [], 'forecast': [], 'categories': [],
            'invoices': invoices, 'subscriptions': [], 'anomalies': anomalies, 'overdue_invoices': overdue[:15],
            'recent_category_comparison': [], 'recent_transactions': [], 'wrapped': None,
            'limitations': ['Customer invoices do not establish that cash was collected.',
                            'Cash movements, closing cash and cash forecasts need transaction records.',
                            'Unknown invoice balances are excluded from the known outstanding subtotal.',
                            f'Overdue invoices are evaluated as of {as_of.isoformat()}.']}


def analyze(data):
    source = data.get('Transactions') or []
    if not source:
        if data.get('Invoices'):
            return analyze_invoices(data)
        raise ValueError('A Transactions worksheet with at least one record is required.')
    months = defaultdict(lambda: {'cash_in': 0.0, 'cash_out': 0.0, 'categories': defaultdict(float)})
    categories = defaultdict(float)
    by_month_category = defaultdict(lambda: defaultdict(float))
    normalized = []
    seen = set()
    for idx, t in enumerate(source):
        d = parse_date(t.get('Date') or t.get('date') or t.get('Transaction_Date'))
        if not d:
            continue
        ty = _short(t.get('Type') or t.get('type')).lower()
        signed = t.get('Signed_Amount_USD', '')
        raw_amt = t.get('Amount_USD', t.get('Amount', ''))
        if not ty:
            ty = 'income' if num(signed if signed != '' else raw_amt) >= 0 else 'expense'
        is_income = ty in ('income', 'revenue', 'credit', 'deposit')
        amount = abs(num(raw_amt if raw_amt != '' else signed))
        if amount == 0:
            continue
        category = _short(t.get('Category') or 'Uncategorized', 80)
        desc = _short(t.get('Description') or t.get('Counterparty') or category)
        vendor = _short(t.get('Counterparty') or t.get('Vendor') or desc)
        key = _short(t.get('Transaction_ID') or ('ROW' + str(idx)))
        if key in seen:
            continue
        seen.add(key)
        mon = d.strftime('%Y-%m')
        if is_income:
            months[mon]['cash_in'] += amount
        else:
            months[mon]['cash_out'] += amount
            months[mon]['categories'][category] += amount
            categories[category] += amount
            by_month_category[category][mon] += amount
        normalized.append({'id': key, 'date': d.isoformat(), 'month': mon,
                           'type': 'Income' if is_income else 'Expense',
                           'category': category, 'description': desc, 'vendor': vendor,
                           'amount': money(amount), 'signed': money(amount if is_income else -amount)})
    if not normalized:
        raise ValueError('No valid transaction dates and amounts were found.')
    normalized.sort(key=lambda t: (t['date'], t['id']))
    last = max(months)
    first = min(months)
    cash_opening = 0.0
    has_opening_cash = False
    for item in data.get('Business Profile', []):
        if str(item.get('Field', '')).strip() == 'Opening Cash Balance (USD)':
            opening = num(item.get('Value'), None)
            if opening is not None:
                cash_opening = opening
                has_opening_cash = True
    profile = {str(r.get('Field')): r.get('Value') for r in data.get('Business Profile', [])}
    scope = profile.get('Data Scope') or 'complete'
    has_opening_cash = has_opening_cash and scope == 'complete'
    company = _short(profile.get('Business Name') or 'Your business', 65)
    currency = _short(profile.get('Currency') or 'USD', 8)
    monthly = []
    balance = cash_opening
    cursor = first
    while cursor <= last:
        values = months[cursor]
        inc, exp = money(values['cash_in']), money(values['cash_out'])
        balance = money(balance + inc - exp)
        monthly.append({'month': cursor, 'cash_in': inc, 'cash_out': exp,
                        'net': money(inc-exp), 'closing_cash': balance if has_opening_cash else None})
        cursor = add_month(cursor, 1)
    last3 = monthly[-3:]
    recent = last3[-1]
    prev = last3[-2] if len(last3) > 1 else recent
    billed = defaultdict(float)
    for r in data.get('Revenue', []):
        d = parse_date(r.get('Date'))
        if d:
            billed[d.strftime('%Y-%m')] += num(r.get('Invoiced_Revenue_USD'))
    for row in monthly:
        row['invoiced_revenue'] = money(billed[row['month']]) if data.get('Revenue') else None
    overdue = []
    as_of = date.fromisoformat(last + '-01')
    as_of = date.fromisoformat(add_month(last, 1)+'-01') - __import__('datetime').timedelta(days=1)
    outstanding_total = 0.0
    for inv in data.get('Invoices', []):
        amount = num(inv.get('Outstanding_USD', 0))
        status = _short(inv.get('Status')).lower()
        if amount <= 0 and status == 'unpaid':
            amount = num(inv.get('Amount_USD'))
        if amount <= 0:
            continue
        outstanding_total += amount
        due = parse_date(inv.get('Due_Date'))
        overdue.append({'invoice': _short(inv.get('Invoice_ID')), 'customer': _short(inv.get('Customer')),
                        'amount': money(amount), 'due': due.isoformat() if due else '',
                        'overdue_days': max((as_of - due).days, 0) if due else 0})
    overdue.sort(key=lambda r: r['overdue_days'], reverse=True)
    invoices_overdue = [i for i in overdue if i['overdue_days'] > 0]
    subs = []
    exp_rows = data.get('Operating Expenses', [])
    for s in data.get('Subscriptions', []):
        name = _short(s.get('Service'))
        matched = []
        for r in exp_rows:
            if _short(r.get('Vendor')).lower() == name.lower() and parse_date(r.get('Date')):
                matched.append((str(r.get('Date'))[:7], num(r.get('Amount_USD'))))
        matched.sort()
        monthly_cost = matched[-1][1] if matched else num(s.get('Initial_Monthly_USD'))
        old = matched[-2][1] if len(matched) >= 2 else monthly_cost
        baseline = matched[0][1] if matched else monthly_cost
        subs.append({'name': name, 'monthly_cost': money(monthly_cost), 'annual_cost': money(monthly_cost*12),
                     'previous_cost': money(old), 'original_cost': money(baseline),
                     'price_increase': money(max(0, monthly_cost-baseline)),
                     'status': _short(s.get('Status') or 'Active'), 'has_usage_data': False})
    subs.sort(key=lambda s: s['monthly_cost'], reverse=True)
    anomalies = []
    for category, monthly_amounts in by_month_category.items():
        ordered = sorted(monthly_amounts)
        for j, mon in enumerate(ordered):
            if j < 4:
                continue
            previous = [monthly_amounts[m] for m in ordered[max(0, j-6):j]]
            typical = median(previous)
            current = monthly_amounts[mon]
            if typical > 0 and current > typical * 1.4 and current - typical >= 100:
                anomalies.append({'type': 'Spending spike', 'category': category, 'month': mon,
                                  'amount': money(current), 'baseline': money(typical),
                                  'increase_pct': round((current/typical-1)*100,1),
                                  'message': f'{category} spending was {round((current/typical-1)*100):,}% above its recent median in {mon}.'})
    for s in subs:
        if s['price_increase'] > 0:
            anomalies.append({'type':'Subscription increase','category':'Software Subscriptions',
                              'month':last,'amount':s['monthly_cost'],'baseline':s['original_cost'],
                              'increase_pct': round(100*s['price_increase']/max(s['original_cost'],.01),1),
                              'message': f'{s["name"]} now costs ${s["monthly_cost"]:,.2f}/month, up ${s["price_increase"]:,.2f} from its original recorded price.'})
    if invoices_overdue:
        anomalies.append({'type':'Overdue invoices', 'category':'Accounts Receivable', 'month':last,
                          'amount':money(sum(i['amount'] for i in invoices_overdue)), 'baseline':None,
                          'increase_pct':None,
                          'message': f'{len(invoices_overdue)} invoice(s) remain overdue as of {as_of.isoformat()}.'})
    # Evidence and explicit explanations are derived from the same ledger used
    # for the dashboard. Never invent a transaction to illustrate an alert.
    for anomaly in anomalies:
        category = anomaly['category']
        month = anomaly['month']
        if anomaly['type'] == 'Spending spike':
            evidence = [t for t in normalized if t['type'] == 'Expense' and
                        t['category'] == category and t['month'] == month]
            evidence.sort(key=lambda t: t['amount'], reverse=True)
            anomaly['evidence'] = evidence[:12]
            anomaly['evidence_count'] = len(evidence)
            anomaly['method'] = ('Current monthly category spending compared with the median of the '
                                 'previous six months with recorded spending in this category. '
                                 'Flagged when more than 40% higher and at least $100 above baseline.')
            anomaly['action'] = 'Review the listed payments, check quantity or price changes, and ask the vendor about unexpected costs.'
            anomaly['history'] = [{'month': mon, 'amount': money(val)} for mon, val in
                                  sorted(by_month_category[category].items()) if mon <= month][-7:]
        elif anomaly['type'] == 'Subscription increase':
            sub = next((s for s in subs if s['monthly_cost'] == anomaly['amount'] and
                        s['original_cost'] == anomaly['baseline'] and s['price_increase'] > 0), None)
            name = sub['name'] if sub else 'Subscription'
            evidence = [t for t in normalized if t['type']=='Expense' and
                        t['category']=='Software Subscriptions' and t['vendor'].lower() == name.lower()]
            evidence.sort(key=lambda t: t['date'], reverse=True)
            anomaly['evidence'] = evidence[:8]
            anomaly['evidence_count'] = len(evidence)
            anomaly['method'] = 'Latest recorded monthly charge compared with the first recorded monthly charge for the service.'
            anomaly['action'] = 'Review the vendor invoice and plan tier, confirm licenses in use, then evaluate whether a lower tier is appropriate.'
            anomaly['service'] = name
            anomaly['history'] = [{'month': t['month'], 'amount': t['amount']} for t in reversed(evidence[:8])]
        else:
            anomaly['invoices'] = invoices_overdue[:15]
            anomaly['evidence'] = []
            anomaly['evidence_count'] = len(invoices_overdue)
            anomaly['method'] = f'Invoice outstanding amount > $0 and due date before the reporting date {as_of.isoformat()}.'
            anomaly['action'] = 'Confirm expected payment dates with the listed customers and investigate disputed or delayed invoices.'
            anomaly['history'] = []
    anomalies.sort(key=lambda a:(a['type']=='Overdue invoices', a['type']=='Subscription increase', a.get('amount', 0)),reverse=True)
    for idx, anomaly in enumerate(anomalies):
        anomaly['id'] = f'alert-{idx+1}'

    last6 = monthly[-6:]
    billed_recent = [m['invoiced_revenue'] for m in monthly[-3:] if m['invoiced_revenue'] is not None]
    hist_income = [m['cash_in'] for m in last6]
    hist_exp = [m['cash_out'] for m in last6]
    future = []
    for i in (1,2,3):
        future_mon = add_month(last,i)
        year_ago = next((m for m in monthly if m['month']==add_month(future_mon,-12)), None)
        recent_income = mean(hist_income[-3:])
        income_est = .7*recent_income + .3*year_ago['cash_in'] if year_ago else recent_income
        exp_est = .7*mean(hist_exp[-3:]) + .3*year_ago['cash_out'] if year_ago else mean(hist_exp[-3:])
        # Highly simplified trend extrapolation; deliberately conservative.
        inc = money(income_est)
        exp = money(exp_est)
        predicted_sales = None
        if billed_recent:
            previous_year_billed = year_ago['invoiced_revenue'] if year_ago else None
            estimate = (.7*mean(billed_recent)+.3*previous_year_billed) if previous_year_billed is not None else mean(billed_recent)
            predicted_sales = money(estimate)
        future.append({'month':future_mon,'cash_in':inc,'cash_out':exp,'net':money(inc-exp),
                       'invoiced_revenue':predicted_sales,
                       'cash_in_low':money(inc*.8),'cash_in_high':money(inc*1.2),
                       'cash_out_low':money(exp*.85),'cash_out_high':money(exp*1.15)})
    recent_category_comparison = []
    for category in sorted(set(by_month_category)):
        current = money(by_month_category[category].get(last, 0))
        previous = money(by_month_category[category].get(prev['month'], 0))
        if current or previous:
            recent_category_comparison.append({'category':category, 'current':current,
                    'previous':previous, 'change':money(current-previous)})
    recent_category_comparison.sort(key=lambda r:r['change'],reverse=True)
    category_items = sorted([{'category':k,'amount':money(v)} for k,v in categories.items()],key=lambda x:-x['amount'])
    totals = {'cash_in':money(sum(m['cash_in'] for m in monthly)),
              'cash_out':money(sum(m['cash_out'] for m in monthly)),
              'net':money(sum(m['net'] for m in monthly)), 'closing_cash':money(balance) if has_opening_cash else None,
              'last_month_cash_in':recent['cash_in'], 'last_month_cash_out':recent['cash_out'],
              'last_month_net':recent['net'], 'last_month_invoiced_revenue':recent['invoiced_revenue'],
              'cash_in_change_pct':round(100*(recent['cash_in']/prev['cash_in']-1),1) if prev['cash_in'] else None,
              'expense_change_pct':round(100*(recent['cash_out']/prev['cash_out']-1),1) if prev['cash_out'] else None,
              'outstanding_invoices':money(outstanding_total) if data.get('Invoices') else None,
              'overdue_invoices':len(invoices_overdue) if data.get('Invoices') else None,
              'subscription_monthly':money(sum(s['monthly_cost'] for s in subs)) if data.get('Subscriptions') else None,
              'subscription_annual':money(sum(s['annual_cost'] for s in subs)) if data.get('Subscriptions') else None}
    past_12 = monthly[-12:]
    highest = max(past_12, key=lambda r:r['cash_out'])
    wrapped = {'period':f'{past_12[0]["month"]} to {last}',
               'cash_in':money(sum(r['cash_in'] for r in past_12)),
               'cash_out':money(sum(r['cash_out'] for r in past_12)),
               'biggest_expense_month':highest['month'],
               'biggest_expense_month_amount':highest['cash_out'],
               'largest_category': category_items[0]['category'] if category_items else 'Not available',
               'largest_category_amount': category_items[0]['amount'] if category_items else 0,
               'subscription_annual':totals['subscription_annual'],
               'financial_headline': 'Your money, explained.'}
    # Top recent records only. Source sheets are never sent to the LLM in full.
    # Reviewed partial PDFs describe only the selected records, not a complete cash outlook.
    forecast_available = scope == 'complete' and (len(monthly) >= 3 or 'Data Scope' not in profile)
    return {'company':company,'currency':currency,'reporting_period':f'{first} to {last}',
            'analysis_kind':'transactions', 'data_scope':scope, 'has_opening_cash':has_opening_cash,
            'has_subscription_data':bool(data.get('Subscriptions')), 'forecast_available':forecast_available,
            'as_of':as_of.isoformat(), 'transaction_count':len(normalized),
            'months_count':len(monthly), 'has_revenue_data':bool(data.get('Revenue')),
            'has_invoice_data':bool(data.get('Invoices')), 'totals':totals,
            'monthly':monthly, 'forecast':future if forecast_available else [],'categories':category_items[:12],
            'subscriptions':subs,'anomalies':anomalies[:24], 'overdue_invoices':invoices_overdue[:15],
            'recent_category_comparison':recent_category_comparison[:20],
            'wrapped':wrapped,'recent_transactions':list(reversed(normalized))[:100],
            'limitations': ['Cash receipts are not the same as invoiced revenue.',
                            'Forecasts are illustrative heuristic estimates, not trained ML predictions.',
                            'Expense outflows include payroll and subscriptions; do not add related source sheets again.',
                            'Subscription usage is unknown from bank transactions alone.',
                            'A projected net cash loss does not by itself prove a cash shortage.',
                            'Without supplied opening cash and a complete ledger, closing cash is unknown.',
                            f'Transaction coverage: {scope}. Totals describe only the uploaded records.']}
