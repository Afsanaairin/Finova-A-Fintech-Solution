"""Evidence-based narratives shared by the investigation UI and reports."""
from datetime import datetime


QUESTIONS = ('What happened?', 'Why was it flagged?', 'Why does this matter?',
             'What might explain it?', 'What should the business do?')


def investigation(finding, as_of):
    kind = finding['type']
    category = finding.get('service') or finding['category']
    month = datetime.strptime(finding['month'], '%Y-%m').strftime('%B %Y')
    amount = finding['amount']
    baseline = finding.get('baseline')
    pct = round((amount / baseline - 1) * 100, 1) if baseline else None
    if kind == 'Spending spike':
        title = f'Unusual {category} Spending'
        happened = (f'{category} spending in {month} was ${amount:,.2f}, approximately '
                    f'{pct:.1f}% above the recent median of ${baseline:,.2f}.')
        why = (f'FINOVA compared {month} category payments with the median of the '
               'previous 4–6 months with recorded spending in this category. '
               'The increase exceeded both 40% and $100.')
        impact = (f'If this higher monthly amount recurs, operating cash payments could '
                  f'be approximately ${amount - baseline:,.2f} higher per month than the comparison level. '
                  'This is a conditional cash impact, not a forecast or a confirmed recurring cost.')
        possible = ('Possible explanations include higher quantities, a price change, an additional '
                    'billing period, a one-time purchase, or a recording error. Payment records '
                    'alone cannot establish the cause.')
        action = finding.get('action') or 'Compare the source invoices and investigate unexplained differences.'
        if 'electric' in category.lower():
            possible = ('Possible explanations include increased usage, a utility rate change, an additional '
                        'billing period, or a billing or recording error. The transactions alone '
                        'cannot establish which explanation is correct.')
            action = ('Compare the utility invoices, check billed usage, rates and billing periods, '
                      'and ask the supplier about any unexplained increase.')
        metrics = [{'label': f'{month} spending', 'value': amount},
                   {'label': 'Recent median', 'value': baseline},
                   {'label': 'Amount above median', 'value': round(amount - baseline, 2)}]
        source = 'FINOVA historical expense records'
    elif kind == 'Subscription increase':
        title = f'{category} Subscription Price Change'
        percentage = f' ({pct:.1f}%)' if pct is not None else ''
        happened = (f'The latest recorded monthly charge for {category} is ${amount:,.2f}, '
                    f'compared with the first recorded charge of ${baseline:,.2f}; '
                    f'an increase of ${amount - baseline:,.2f} per month{percentage}.')
        if pct is None:
            happened += ' A percentage change is not defined from a zero comparison charge.'
        why = 'FINOVA compared the latest recorded charge with the service’s first recorded monthly charge.'
        impact = (f'If the latest price continues unchanged, cash payments would be '
                  f'${amount - baseline:,.2f} higher per month, or ${(amount - baseline) * 12:,.2f} '
                  'over 12 months. This is an illustrative continuation, not a contract obligation or guaranteed saving.')
        possible = ('Possible explanations include a price increase, a different plan, additional seats, '
                    'taxes or a different billing period. Charges alone do not establish usage or the cause.')
        action = finding.get('action') or 'Check the vendor invoice, plan and licenses before changing the subscription.'
        metrics = [{'label': 'Latest monthly charge', 'value': amount},
                   {'label': 'First recorded charge', 'value': baseline},
                   {'label': 'Added monthly cost', 'value': round(amount - baseline, 2)}]
        source = 'FINOVA subscription records and recorded payment history'
    else:
        title = 'Overdue Customer Invoices'
        count = finding.get('evidence_count', len(finding.get('invoices', [])))
        happened = (f'{count} customer invoice(s) with known outstanding balances totaling '
                    f'${amount:,.2f} were overdue as of {as_of}. They are grouped as one flagged pattern.')
        why = f'FINOVA found positive known outstanding balances with due dates before {as_of}.'
        impact = ('Delayed collection can reduce cash available for operating payments. '
                  'The outstanding amount is money owed, not confirmed cash received or a confirmed loss.')
        possible = ('Possible explanations include payment processing delays, a disputed invoice, '
                    'an unrecorded payment, or customer cash constraints. Invoice records alone cannot establish the cause.')
        action = finding.get('action') or 'Confirm remaining balances, payment dates and any disputes with the customers.'
        metrics = [{'label': 'Known overdue balance', 'value': amount}]
        source = 'FINOVA customer invoice records'
    labels = ('Verified finding', 'Detection method', 'Conditional financial impact',
              'Possible explanations · unconfirmed', 'Recommended action')
    return {'title': title, 'status': 'Needs review', 'metrics': metrics,
            'questions': [{'question': question, 'label': label, 'text': text}
                          for question, label, text in zip(QUESTIONS, labels, (happened, why, impact, possible, action))],
            'source': source, 'as_of': as_of,
            'note': 'Rule-based investigation. Possible explanations require verification against source documents.'}
