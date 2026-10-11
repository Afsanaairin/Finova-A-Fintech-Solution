"""Local PDF extraction and review drafts; extracted amounts are never auto-posted."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

MAX_PDF_PAGES = 20
MAX_REVIEW_ROWS = 1000
MAX_TEXT_BYTES = 500_000
MAX_EXTRACTION_SECONDS = 60
DATE_PATTERN = r'(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/(?:\d{4}|\d{2})|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})'
DATE_START = re.compile(r'^\s*(' + DATE_PATTERN + r')\b')
AMOUNT = re.compile(r'(?<![\w.])(?:\(\s*)?[+-]?\$?\s*(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?:\s*\))?(?:\s*(?:CR|DR)\b)?', re.I)


def pdf_capabilities():
    return {'text': all(shutil.which(name) for name in ('pdfinfo', 'pdftotext')),
            'ocr': all(shutil.which(name) for name in ('pdfinfo', 'pdftotext', 'pdftoppm', 'tesseract'))}


def _run(command, timeout=20):
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('PDF processing took too long. Upload a shorter document.') from exc
    except OSError as exc:
        raise ValueError('PDF extraction tools are unavailable. See the PDF setup instructions in README.md.') from exc
    if result.returncode:
        raise ValueError('Unable to read this PDF. Use an unencrypted, undamaged PDF or export CSV/Excel.')
    if len(result.stdout) > MAX_TEXT_BYTES:
        raise ValueError('The PDF contains too much text. Upload a shorter document.')
    return result.stdout.decode('utf-8', errors='replace')


def extract_pdf(blob, force_ocr=False):
    if not isinstance(blob, bytes) or not blob.lstrip().startswith(b'%PDF-'):
        raise ValueError('This file is not a valid PDF.')
    if len(blob) > 12 * 1024 * 1024:
        raise ValueError('PDF uploads must be smaller than 12 MB.')
    capabilities = pdf_capabilities()
    if not capabilities['text']:
        raise ValueError('PDF support needs Poppler (pdfinfo and pdftotext) on the server. See README.md.')
    deadline = time.monotonic() + MAX_EXTRACTION_SECONDS

    def run(command, timeout=20):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('PDF extraction exceeded 60 seconds. Split the document into fewer pages and try again.')
        return _run(command, timeout=min(timeout, remaining))

    with tempfile.TemporaryDirectory(prefix='finova-pdf-') as temporary:
        folder = Path(temporary)
        source = folder / 'document.pdf'
        source.write_bytes(blob)
        info = run(['pdfinfo', str(source)])
        page_match = re.search(r'^Pages:\s*(\d+)\s*$', info, re.M)
        if not page_match:
            raise ValueError('Unable to determine the number of PDF pages.')
        count = int(page_match.group(1))
        if not 1 <= count <= MAX_PDF_PAGES:
            raise ValueError(f'PDF uploads support up to {MAX_PDF_PAGES} pages. Split this document first.')
        text = run(['pdftotext', '-layout', '-enc', 'UTF-8', str(source), '-'])
        pages = text.split('\f')
        scanned_pages = [index for index in range(count) if force_ocr or
                         sum(character.isalnum() for character in (pages[index] if index < len(pages) else '')) < 30]
        if len(scanned_pages) > 5:
            raise ValueError('Scanned PDFs support up to 5 OCR pages. Split this document first.')
        if scanned_pages and not capabilities['ocr']:
            raise ValueError('This PDF needs OCR. Install pdftoppm and Tesseract on the server, or upload a searchable PDF.')
        result = []
        total_bytes = 0
        for index in range(count):
            page = pages[index] if index < len(pages) else ''
            scanned = index in scanned_pages
            if force_ocr or scanned:
                prefix = folder / f'page-{index + 1}'
                run(['pdftoppm', '-f', str(index + 1), '-l', str(index + 1),
                      '-singlefile', '-scale-to', '2400', '-png', str(source), str(prefix)], timeout=25)
                page = run(['tesseract', str(prefix) + '.png', 'stdout', '-l', 'eng', '--psm', '6'], timeout=25)
            total_bytes += len(page.encode('utf-8'))
            if total_bytes > MAX_TEXT_BYTES:
                raise ValueError('The PDF contains too much text. Upload a shorter document.')
            result.append({'page': index + 1, 'text': page,
                           'method': 'ocr' if force_ocr or scanned else 'text'})
        return result


def document_date(value):
    value = str(value).strip().replace(',', '')
    for pattern in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%b %d %Y', '%B %d %Y'):
        try:
            parsed = datetime.strptime(value, pattern).date()
            return parsed.isoformat() if 1900 <= parsed.year <= 2100 else ''
        except ValueError:
            pass
    return ''


def document_amount(value):
    value = str(value).strip().upper()
    negative = value.startswith('(') or value.endswith('DR')
    value = re.sub(r'(?:CR|DR)$', '', value).strip().replace('$', '').replace(',', '').replace(' ', '')
    value = value.strip('()')
    try:
        amount = Decimal(value)
        if not amount.is_finite() or abs(amount) > Decimal('1000000000000'):
            return None
        if amount != amount.quantize(Decimal('0.01')):
            return None
        return float(-abs(amount) if negative else amount)
    except (InvalidOperation, ValueError):
        return None


def _columns(line):
    if not re.search(r'\bdate\b', line, re.I):
        return []
    return [(match.end(), match.group().lower()) for match in
            re.finditer(r'\b(?:withdrawals?|debits?|payments?|charges?|deposits?|credits?|amount|balance)\b', line, re.I)]


def transaction_drafts(pages):
    rows = []
    for page in pages:
        columns = []
        for line in page['text'].splitlines():
            header = _columns(line)
            if header:
                columns = header
                continue
            date_match = DATE_START.match(line)
            if not date_match:
                continue
            tail = line[date_match.end():]
            if re.search(r'\b(?:opening|closing|beginning|ending)\s+balance\b', tail, re.I):
                continue
            matches = list(AMOUNT.finditer(line, date_match.end()))
            if not matches:
                continue
            fields = []
            for match in matches:
                role = min(columns, key=lambda column: abs(column[0] - match.end()))[1] if columns else 'amount'
                if role != 'balance':
                    fields.append((match, role))
            if not fields:
                continue
            # Multiple non-balance monetary fields cannot safely identify one payment.
            issues = []
            match, role = fields[0]
            amount = document_amount(match.group())
            if len(fields) != 1:
                issues.append('Multiple amounts found; verify the transaction amount.')
            direction = ''
            if role.startswith(('withdrawal', 'debit', 'payment', 'charge')):
                direction = 'Expense'
            elif role.startswith(('deposit', 'credit')):
                direction = 'Income'
            elif re.search(r'\b(?:expense|debit|withdrawal|DR)\b', tail, re.I) or (amount is not None and amount < 0):
                direction = 'Expense'
            elif re.search(r'\b(?:income|credit|deposit|CR)\b', tail, re.I) or match.group().strip().startswith('+'):
                direction = 'Income'
            else:
                issues.append('Choose Income or Expense; a positive amount alone does not establish direction.')
            description = line[date_match.end():match.start()].strip(' |\t')
            description = re.sub(r'\b(?:Income|Expense)\b', '', description, flags=re.I).strip(' |\t')
            parsed_date = document_date(date_match.group(1))
            if not parsed_date:
                issues.append('Check the transaction date.')
            if page['method'] == 'ocr':
                issues.append('Extracted from a scan; check against the original.')
            rows.append({'Date': parsed_date, 'Type': direction, 'Category': 'Uncategorized',
                         'Description': description[:200], 'Amount_USD': abs(amount) if amount is not None else '',
                         'Source_Page': page['page'], 'Source_Text': line.strip()[:500], 'issues': issues})
            if len(rows) > MAX_REVIEW_ROWS:
                raise ValueError(f'PDF review supports up to {MAX_REVIEW_ROWS} records. Split this document first.')
    return rows


def _label(text, labels, pattern):
    match = re.search(r'(?:' + labels + r')\s*[:#]?\s*(' + pattern + ')', text, re.I)
    return match.group(1).strip() if match else ''


def invoice_drafts(pages):
    rows = []
    for page in pages:
        text = page['text']
        if not re.search(r'\binvoice\s*(?:number|no\.?|#|date|:)|\bbill\s+to\b', text, re.I):
            continue
        identifier = _label(text, r'\binvoice\s*(?:number|no\.?|#|:)', r'[A-Za-z0-9][A-Za-z0-9/_-]*')
        invoice_date = _label(text, r'\binvoice\s+date', DATE_PATTERN)
        due_date = _label(text, r'\bdue\s+date|\bpayment\s+due', DATE_PATTERN)
        customer = _label(text, r'\bbill\s+to|\bcustomer', r'[^\n\r]+')
        total = _label(text, r'\bgrand\s+total|\binvoice\s+total|(?<!sub)\btotal', AMOUNT.pattern)
        outstanding = _label(text, r'\bamount\s+due|\bbalance\s+due|\btotal\s+due', AMOUNT.pattern)
        parsed_total = document_amount(total or outstanding)
        parsed_outstanding = document_amount(outstanding)
        rows.append({'Invoice_ID': identifier, 'Invoice_Date': document_date(invoice_date),
                     'Customer': customer[:150], 'Due_Date': document_date(due_date),
                     'Amount_USD': abs(parsed_total) if parsed_total is not None else '',
                     'Outstanding_USD': abs(parsed_outstanding) if parsed_outstanding is not None else '',
                     'Status': 'Unknown', 'Source_Page': page['page'],
                     'Source_Text': text[:1000], 'issues': ['Confirm that this is a customer invoice and check its payment status.']})
    return rows


def preview_pdf(blob, filename, force_ocr=False):
    pages = extract_pdf(blob, force_ocr=force_ocr)
    invoices = invoice_drafts(pages)
    transactions = transaction_drafts(pages)
    return {'filename': Path(filename).name[:150], 'kind': 'invoices' if invoices else 'transactions',
            'pages': len(pages), 'used_ocr': any(page['method'] == 'ocr' for page in pages),
            'transaction_rows': transactions, 'invoice_rows': invoices,
            'source_text': '\n\n'.join(f"--- Page {page['page']} ---\n{page['text']}" for page in pages),
            'warnings': ['Extraction may miss or misread records. Compare every included row with the original PDF.',
                         'Confirming this import replaces the current dataset.'],
            'requires_review': True}


def reviewed_data(payload):
    """Validate every included correction; do not silently discard invalid financial records."""
    if payload.get('confirmed') is not True:
        raise ValueError('Review and confirm the extracted records before importing.')
    kind = payload.get('kind')
    if kind not in ('transactions', 'invoices'):
        raise ValueError('Choose a transaction statement or customer invoices.')
    rows = payload.get('rows')
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_REVIEW_ROWS:
        raise ValueError(f'Include between 1 and {MAX_REVIEW_ROWS} reviewed records.')
    profile = [{'Field': 'Business Name', 'Value': str(payload.get('company') or 'Your business')[:65]}]
    cleaned = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f'Record {index} is invalid.')
        amount = document_amount(row.get('Amount_USD', ''))
        if amount is None or amount <= 0:
            raise ValueError(f'Record {index}: enter a positive amount with at most two decimal places.')
        if kind == 'transactions':
            transaction_date = document_date(row.get('Date', ''))
            direction = row.get('Type')
            if not transaction_date or direction not in ('Income', 'Expense'):
                raise ValueError(f'Record {index}: provide a valid date and choose Income or Expense.')
            cleaned.append({'Transaction_ID': f'PDF-{index}', 'Date': transaction_date, 'Type': direction,
                            'Category': str(row.get('Category') or 'Uncategorized')[:80],
                            'Description': str(row.get('Description') or 'PDF transaction')[:200],
                            'Amount_USD': amount})
        else:
            identifier = str(row.get('Invoice_ID') or '').strip()[:100]
            customer = str(row.get('Customer') or '').strip()[:150]
            if not identifier or not customer:
                raise ValueError(f'Record {index}: provide an invoice ID and customer.')
            if any(record['Invoice_ID'] == identifier for record in cleaned):
                raise ValueError(f'Record {index}: duplicate invoice ID. Include each invoice once.')
            dates = {}
            for field in ('Invoice_Date', 'Due_Date'):
                dates[field] = document_date(row.get(field, ''))
                if row.get(field) and not dates[field]:
                    raise ValueError(f'Record {index}: check the {field.replace("_", " ").lower()}.')
            status = row.get('Status', 'Unknown')
            if status not in ('Unknown', 'Unpaid', 'Partial', 'Paid'):
                raise ValueError(f'Record {index}: choose a valid payment status.')
            outstanding = document_amount(row.get('Outstanding_USD', ''))
            if status == 'Paid':
                if outstanding not in (None, 0):
                    raise ValueError(f'Record {index}: a paid invoice must have zero outstanding.')
                outstanding = 0.0
            elif status == 'Unpaid' and outstanding is None:
                outstanding = amount
            if outstanding is not None and not 0 <= outstanding <= amount:
                raise ValueError(f'Record {index}: outstanding must be between zero and the invoice amount.')
            if status == 'Partial' and (outstanding is None or not 0 < outstanding < amount):
                raise ValueError(f'Record {index}: a partial payment needs the remaining outstanding amount.')
            if status == 'Unpaid' and outstanding != amount:
                raise ValueError(f'Record {index}: an unpaid invoice must have its full amount outstanding.')
            cleaned.append({'Invoice_ID': identifier, 'Customer': customer, **dates, 'Amount_USD': amount,
                            'Outstanding_USD': outstanding, 'Status': status})
    if kind == 'invoices':
        reporting_date = document_date(payload.get('as_of', ''))
        if not reporting_date:
            raise ValueError('Choose the date to use when checking overdue invoices.')
        return {'Invoices': cleaned, 'Business Profile': profile, 'Invoice Reporting Date': reporting_date}
    scope = payload.get('scope', 'selected')
    if scope not in ('selected', 'complete', 'expenses', 'receipts'):
        raise ValueError('Choose the scope of the uploaded transactions.')
    if scope == 'expenses' and any(row['Type'] != 'Expense' for row in cleaned):
        raise ValueError('An expenses-only import cannot contain income records.')
    if scope == 'receipts' and any(row['Type'] != 'Income' for row in cleaned):
        raise ValueError('A receipts-only import cannot contain expense records.')
    profile.append({'Field': 'Data Scope', 'Value': scope})
    opening = payload.get('opening_cash', '')
    if opening not in ('', None):
        amount = document_amount(opening)
        if amount is None:
            raise ValueError('Enter a valid opening cash balance.')
        if scope != 'complete':
            raise ValueError('Closing cash needs a complete cash ledger for the reporting period.')
        profile.append({'Field': 'Opening Cash Balance (USD)', 'Value': amount})
    return {'Transactions': cleaned, 'Business Profile': profile}
