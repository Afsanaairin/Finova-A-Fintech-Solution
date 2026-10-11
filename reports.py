"""Financial reports built from the session's complete source records, without AI."""
from collections import defaultdict
from datetime import datetime, timezone
import re

from finance import add_month, analyze, money, num, parse_date, transaction_records
from investigations import investigation


class ReportInputError(ValueError):
    pass


def currency(value):
    return 'Not provided' if value is None else f'-${abs(value):,.2f}' if value < 0 else f'${value:,.2f}'


def month_name(month):
    return datetime.strptime(month, '%Y-%m').strftime('%B %Y')


def report_window(period, end):
    year, month = map(int, end.split('-'))
    start = end if period == 'monthly' else f'{year:04d}-{((month - 1) // 3) * 3 + 1:02d}' if period == 'quarterly' else f'{year:04d}-01'
    return start, end


def rows_table(headers, rows):
    return {'headers': headers, 'rows': rows}


def metric(label, value):
    return {'label': label, 'value': currency(value)}


def totals(records):
    income = money(sum(t['amount'] for t in records if t['type'] == 'Income'))
    expenses = money(sum(t['amount'] for t in records if t['type'] == 'Expense'))
    return income, expenses, money(income - expenses)


def categories(records):
    result = defaultdict(float)
    for record in records:
        if record['type'] == 'Expense':
            result[record['category']] += record['amount']
    return {key: money(value) for key, value in result.items()}


def evidence_table(finding, ledger):
    if finding['type'] == 'Overdue invoices':
        records = finding.get('invoices', [])
        return rows_table(['Customer / invoice', 'Due date', 'Known outstanding'], [
            [f'{r["customer"]} / {r["invoice"]}', r['due'], currency(r['amount'])] for r in records]), finding.get('evidence_count', len(records))
    if finding['type'] == 'Spending spike':
        matches = [r for r in ledger if r['month'] == finding['month'] and r['type'] == 'Expense' and r['category'] == finding['category']]
    else:
        matches = [r for r in ledger if r['type'] == 'Expense' and r['vendor'].lower() == finding.get('service', '').lower()
                   and r['category'] == finding['category'] and r['month'] <= finding['month']]
    matches.sort(key=lambda r: (r['date'], r['amount']), reverse=True)
    return rows_table(['Date', 'Counterparty / description', 'Cash paid'], [
        [r['date'], f'{r["vendor"]} / {r["description"]}', currency(r['amount'])] for r in matches[:40]]), len(matches)


def chart(title, labels, series, kind='bars'):
    return {'title': title, 'kind': kind, 'labels': labels, 'series': series}


def build_report(source, summary, options):
    """Return one structured document consumed by both the web preview and PDF renderer."""
    report_type = options.get('report_type', 'complete')
    period = options.get('period', 'monthly')
    if report_type not in ('complete', 'anomaly') or period not in ('monthly', 'quarterly', 'annual'):
        raise ReportInputError('Choose a supported report type and reporting period.')
    available = [r['month'] for r in summary['monthly']] or [summary['as_of'][:7]]
    end = options.get('end_month', available[-1])
    if not isinstance(end, str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', end) or end not in available:
        raise ReportInputError('Choose a reporting month available in the current dataset.')
    scenario = options.get('scenario', {})
    if not isinstance(scenario, dict):
        raise ReportInputError('Scenario adjustments must be an object.')
    adjustments = []
    for field in ('receipts_pct', 'expenses_pct'):
        value = scenario.get(field, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or num(value, None) is None or not -50 <= value <= 100:
            raise ReportInputError('Scenario adjustments must be numbers between -50% and 100%.')
        adjustments.append(value)
    start, end = report_window(period, end)
    ledger = transaction_records(source.get('Transactions', []))
    source_label = summary.get('import_source', {}).get('filename') or 'Uploaded financial records'
    generated = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    doc = {'report_type': report_type, 'company': summary['company'], 'currency': 'USD',
           'generated_at': generated, 'source': source_label, 'sections': [],
           'period': {'start': start, 'end': end, 'available_through': summary['as_of']},
           'filename': f'finova-{report_type}-{period}-{end}.pdf'}
    if report_type == 'anomaly':
        finding = next((a for a in summary['anomalies'] if a['id'] == options.get('anomaly_id')), None)
        if finding is None:
            raise ReportInputError('Select an anomaly in the current dataset.')
        info = finding.get('investigation') or investigation(finding, summary['as_of'])
        doc.update({'title': 'Anomaly Investigation Report', 'subtitle': info['title'],
                    'period': {'start': finding['month'], 'end': finding['month'],
                               'label': month_name(finding['month']), 'available_through': summary['as_of']},
                    'filename': f'finova-investigation-{finding["id"]}-{finding["month"]}.pdf'})
        doc['sections'].append({'title': 'FINOVA Risk Investigation', 'paragraphs': ['Needs review · Rule-based finding'+(' · Illustrative investigation · Demo workbook' if summary.get('import_source', {}).get('demo') else '')],
                                'metrics': [metric(m['label'], m['value']) for m in info['metrics']]})
        for index, question in enumerate(info['questions'], 1):
            doc['sections'].append({'title': f'{index}. {question["question"]}',
                                    'paragraphs': [question['text']], 'label': question['label']})
        if finding.get('history'):
            history = finding['history']
            doc['sections'].append({'title': 'Historical comparison', 'chart': chart('Recorded monthly payments',
                [h['month'] for h in history], [{'label': 'Recorded payments', 'values': [h['amount'] for h in history]}]),
                'paragraphs': ['The chart shows recorded payments. A spending spike does not establish an increase in usage.']})
        evidence, total = evidence_table(finding, ledger)
        doc['sections'].append({'title': 'Supporting source records', 'table': evidence,
                                'paragraphs': [f'{total} matching records; {len(evidence["rows"])} displayed. Amounts and findings use the source records, not only the displayed rows.']})
        doc['sections'].append({'title': 'Data & Methodology', 'paragraphs': [
            f'Source: {info["source"]}. File: {source_label}. Dataset reporting date: {summary["as_of"]}.', info['note'],
            'Facts are recorded amounts and calculated comparisons. Causes are unconfirmed possibilities; next steps are recommendations.',
            'Cash received minus cash paid is cash movement, not accounting profit.',
            f'Transaction coverage: {summary.get("data_scope", "complete")}. This investigation covers the uploaded records only.']})
        return doc

    month_number = int(end[5:])
    if period == 'monthly':
        label = month_name(end)
    elif period == 'quarterly':
        label = f'Q{(month_number - 1) // 3 + 1} {end[:4]}'
        if month_number % 3:
            label += f' through {month_name(end).split()[0]} (partial quarter)'
    else:
        label = end[:4] if month_number == 12 else f'{end[:4]} year-to-date through {month_name(end).split()[0]}'
    if available[0] > start:
        label += f' · records begin {month_name(available[0])}'
    doc['period']['label'] = label
    doc.update({'title': f'{"Monthly" if period == "monthly" else "Quarterly" if period == "quarterly" else "Annual"} Financial Intelligence Report',
                'subtitle': f'{label} · Based on available records through {summary["as_of"]}'})
    records = [r for r in ledger if start <= r['month'] <= end]
    has_cash = bool(records)
    cash_in, cash_out, net = totals(records) if has_cash else (None, None, None)
    shift = 1 if period == 'monthly' else 3 if period == 'quarterly' else 12
    prior_start, prior_end = add_month(start, -shift), add_month(end, -shift)
    previous = [r for r in ledger if prior_start <= r['month'] <= prior_end]
    old_in, old_out, old_net = totals(previous) if previous else (None, None, None)
    revenue_records = [r for r in source.get('Revenue', []) if parse_date(r.get('Date')) and start <= parse_date(r['Date']).strftime('%Y-%m') <= end]
    billed = money(sum(num(r.get('Invoiced_Revenue_USD')) for r in revenue_records)) if revenue_records else None
    findings = [a for a in summary['anomalies'] if start <= a['month'] <= end]
    overdue_flag = next((a for a in summary['anomalies'] if a['type'] == 'Overdue invoices'), None)
    closing_row = next((r for r in summary['monthly'] if r['month'] == end), {})
    closing = closing_row.get('closing_cash') if summary.get('has_opening_cash') else None
    category_totals, prior_categories = categories(records), categories(previous)
    top = sorted(category_totals.items(), key=lambda pair: -pair[1])
    facts = [f'{len(records)} cash transactions were recorded in the selected period.' if has_cash else 'Cash transaction records were not provided for this period.']
    if has_cash:
        facts.append(f'Recorded cash received was {currency(cash_in)} and cash paid was {currency(cash_out)}, giving net cash movement of {currency(net)}.')
    facts.append(f'{len(findings)} reported financial pattern(s) fall in this period. Overdue invoices are grouped as one pattern, even when several invoices are involved.')
    if top:
        facts.append(f'The largest recorded spending category was {top[0][0]} at {currency(top[0][1])}.')
    facts.append('Management should verify flagged records and confirm payment timing before changing budgets or supplier arrangements.')
    doc['sections'].append({'title': 'Executive Summary', 'paragraphs': facts})

    performance = [metric('Invoiced revenue', billed), metric('Cash received', cash_in),
                   metric('Cash paid', cash_out), metric('Net cash movement', net)]
    if summary['analysis_kind'] == 'invoices':
        performance.append(metric('Uploaded customer invoice amounts', summary['totals']['invoice_amount']))
    comparison = rows_table(['Metric', 'Selected period', 'Prior comparable period'], [
        ['Cash received', currency(cash_in), currency(old_in)], ['Cash paid', currency(cash_out), currency(old_out)],
        ['Net cash movement', currency(net), currency(old_net)]])
    notes = [f'Comparison window: {prior_start} to {prior_end}. Annual year-to-date comparisons use the same months in the previous year.',
             'Invoiced revenue describes amounts billed. Cash receipts describe money recorded as received. Cash movement is not accounting profit.']
    if not previous:
        notes.append('No cash transactions were supplied for the comparison window; a percentage change is not established.')
    if summary['analysis_kind'] == 'invoices':
        notes.append('Uploaded customer invoice amounts cover the supplied invoice documents, not period revenue or collected cash. Payment balances are a snapshot at the selected invoice reporting date.')
    performance_section = {'title': 'Financial Performance', 'metrics': performance, 'table': comparison, 'paragraphs': notes}
    month_rows = [m for m in summary['monthly'] if start <= m['month'] <= end]
    if period == 'monthly' and previous:
        month_rows = [m for m in summary['monthly'] if prior_start <= m['month'] <= end]
    if has_cash:
        performance_section['chart'] = chart('Recorded cash received and paid', [m['month'] for m in month_rows], [
            {'label': 'Cash received', 'values': [m['cash_in'] for m in month_rows]},
            {'label': 'Cash paid', 'values': [m['cash_out'] for m in month_rows]}])
    elif summary['analysis_kind'] == 'invoices':
        balances = sorted([r for r in summary['invoices'] if r['outstanding'] is not None and r['outstanding'] > 0], key=lambda r: -r['outstanding'])[:6]
        if balances:
            performance_section['chart'] = chart(f'Known outstanding invoices · as of {summary["as_of"]}',
                [r['invoice'] or r['customer'] for r in balances], [{'label': 'Known outstanding balance', 'values': [r['outstanding'] for r in balances]}], 'horizontal')
    doc['sections'].append(performance_section)

    expense_section = {'title': 'Expense Analysis', 'paragraphs': [
        'Payments are counted once from the transaction ledger. Payroll and operating-expense worksheets are not added again.',
        'An increase is a reason to review invoices and budgets; it does not establish waste or recoverable savings.'],
        'table': rows_table(['Category', 'Recorded cash paid', 'Change vs prior window'], [
            [name, currency(value), currency(value - prior_categories.get(name, 0)) if previous else 'Not available'] for name, value in top[:12]])}
    if top:
        expense_section['chart'] = chart('Largest recorded spending areas', [name for name, value in top[:6]],
                                         [{'label': 'Cash paid', 'values': [value for name, value in top[:6]]}], 'horizontal')
    else:
        expense_section['paragraphs'].append('Expense transaction records were not supplied for this period.')
    if len(top) > 12:
        expense_section['paragraphs'].append(f'Showing the largest 12 of {len(top)} spending categories. All categories are included in cash totals.')
    doc['sections'].append(expense_section)

    cash_notes = [f'Invoice balances are the latest supplied snapshot as of {summary["as_of"]}; historical payment balances are not reconstructed.',
                  'Scheduled obligations were not supplied. Historical recurring payments do not establish a complete schedule of future bills.']
    if closing is None:
        cash_notes.append('Available business cash is not established without opening cash and a complete ledger.')
    if net is not None and net < 0:
        cash_notes.append('Cash paid exceeded cash received in this period. Review collection timing and upcoming payments; this alone does not prove a cash shortage.')
    if summary['totals'].get('unknown_invoice_balances'):
        cash_notes.append(f'{summary["totals"]["unknown_invoice_balances"]} invoice(s) have unknown payment balances and are excluded from the known balance subtotal.')
    doc['sections'].append({'title': 'Cash-Flow Assessment', 'paragraphs': cash_notes, 'metrics': [
        metric('Estimated closing cash at period end', closing), metric('Latest known outstanding invoices', summary['totals'].get('outstanding_invoices')),
        metric('Latest known overdue balance', overdue_flag['amount'] if overdue_flag else 0 if summary['has_invoice_data'] else None)]})

    anomaly_rows = [[a['type'], a.get('service') or a['category'], a['month'], currency(a['amount'])] for a in findings]
    anomaly_section = {'title': 'Anomaly Investigation', 'paragraphs': [
        f'{len(findings)} reported patterns in this period. Counts reflect FINOVA’s displayed findings; the dashboard can retain up to 24 patterns.',
        'Several overdue invoices count as one grouped pattern. Select a finding for its individual report and supporting source records.'],
        'table': rows_table(['Finding', 'Category / service', 'Period', 'Recorded amount'], anomaly_rows),
        'investigations': [a.get('investigation') or investigation(a, summary['as_of']) for a in findings[:3]]}
    if len(findings) > 3:
        anomaly_section['paragraphs'].append('The first three investigations are expanded here. All reported patterns in this period appear in the table.')
    doc['sections'].append(anomaly_section)

    future = []
    history = [r for r in ledger if r['month'] <= end]
    if history and summary.get('data_scope') == 'complete':
        snapshot = {**source, 'Transactions': [{'Transaction_ID': r['id'], 'Date': r['date'], 'Type': r['type'],
                     'Category': r['category'], 'Description': r['description'], 'Counterparty': r['vendor'], 'Amount_USD': r['amount']} for r in history],
                    'Revenue': [r for r in source.get('Revenue', []) if parse_date(r.get('Date')) and parse_date(r['Date']).strftime('%Y-%m') <= end]}
        analyzed = analyze(snapshot)
        if analyzed['months_count'] >= 3:
            future = analyzed['forecast']
    forecast_section = {'title': 'Forecast & Scenario Analysis', 'paragraphs': [
        f'Outlook uses only cash and billing history through {end}. Estimates use 70% of the latest three-month average plus 30% of the same month last year when available; otherwise the recent average.',
        'These are illustrative estimates, not a fitted machine-learning model. Scenario changes are hypothetical, not expected outcomes.']}
    if future:
        forecast_section['table'] = rows_table(['Projected month', 'Invoiced revenue', 'Cash received', 'Cash paid', 'Net cash'], [
            [r['month'], currency(r['invoiced_revenue']), currency(r['cash_in']), currency(r['cash_out']), currency(r['net'])] for r in future])
        forecast_section['chart'] = chart('Illustrative cash outlook', [r['month'] for r in future], [
            {'label': 'Expected receipts', 'values': [r['cash_in'] for r in future]},
            {'label': 'Expected payments', 'values': [r['cash_out'] for r in future]}])
        first = future[0]
        scenario_in = money(first['cash_in'] * (1 + adjustments[0] / 100))
        scenario_out = money(first['cash_out'] * (1 + adjustments[1] / 100))
        forecast_section['paragraphs'].append(f'Next-month scenario: receipts adjusted {adjustments[0]:+g}% and payments {adjustments[1]:+g}%. '
            f'Receipts {currency(scenario_in)}, payments {currency(scenario_out)}, net cash movement {currency(money(scenario_in - scenario_out))}.')
        forecast_section['paragraphs'].append('Illustrative uncertainty bands: receipts ±20% and payments ±15%; these are assumptions, not statistical confidence intervals.')
    else:
        forecast_section['paragraphs'].append('An outlook is not available: provide a complete ledger covering at least three months. Invoice-only and partial-data reports do not create a business cash forecast.')
    doc['sections'].append(forecast_section)

    recommendations = []
    if overdue_flag:
        recommendations.append(['High', 'Confirm overdue customer balances and expected collection dates; prioritize disputed or delayed invoices.'])
    if net is not None and net < 0:
        recommendations.append(['High', 'Review upcoming payment dates and collection timing before committing additional cash.'])
    for finding in findings[:5]:
        info = finding.get('investigation') or investigation(finding, summary['as_of'])
        if finding['type'] != 'Overdue invoices':
            recommendations.append(['Medium', f'{info["title"]}: {info["questions"][4]["text"]}'])
    if summary.get('data_scope') != 'complete' or not has_cash:
        recommendations.append(['High', 'Provide a complete cash ledger and verify missing records before making business-wide cash decisions.'])
    if closing is None:
        recommendations.append(['Medium', 'Supply opening cash and confirm transaction coverage to establish available cash.'])
    if not recommendations:
        recommendations.append(['Routine', 'Reconcile the source records and review the spending budget and expected collections with the finance team.'])
    doc['sections'].append({'title': 'Recommendations', 'paragraphs': ['Recommended checks, ordered by priority. These actions require business judgment and source-document verification.'],
                            'table': rows_table(['Priority', 'Recommended action'], recommendations)})
    doc['sections'].append({'title': 'Data & Methodology', 'paragraphs': [
        f'Source: {source_label}. Selected months: {start} to {end}. Latest dataset reporting date: {summary["as_of"]}. Generated: {generated}.',
        f'{len(records)} canonical ledger records in the selected period; {len(ledger)} across the supplied ledger. Transaction IDs are deduplicated with the same rules as the dashboard.',
        f'Transaction coverage: {summary.get("data_scope", "complete")}. Calendar labels do not certify complete business coverage. Unrecorded activity cannot be inferred from missing records.',
        'Spending spikes exceed the median of 4–6 prior active category months by more than 40% and at least $100. Subscription changes compare the latest charge with the first recorded charge.',
        'Customer invoice balances reflect supplied payment statuses; unknown balances are excluded. Supplier bills and a future-obligation schedule are not inferred from customer invoices.',
        'Verified facts, conditional financial impacts, unconfirmed explanations and recommended actions are labeled separately. No AI model calculates the reported numbers.',
        'Cash receipts minus cash payments is net cash movement, not accounting profit. No accounting profit figure is calculated.']})
    return doc
