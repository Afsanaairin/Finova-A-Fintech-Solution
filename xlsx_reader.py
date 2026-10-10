"""Minimal XLSX and CSV input reader using the Python standard library.

The v1 importer accepts ordinary non-encrypted XLSX files. It does not evaluate
Excel formulas; if a formula has no cached value, the field will be blank.
"""
import csv
import io
import posixpath
import re
import zipfile
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

S = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
P = '{http://schemas.openxmlformats.org/package/2006/relationships}'
MAX_ROWS_PER_SHEET = 50000
MAX_UNCOMPRESSED_BYTES = 60 * 1024 * 1024


def _col_number(address):
    result = 0
    for ch in re.match(r'([A-Z]+)', address.upper()).group(1):
        result = result * 26 + (ord(ch) - 64)
    return result - 1


def _cell_value(cell, strings):
    ty = cell.attrib.get('t', '')
    if ty == 'inlineStr':
        return ''.join(t.text or '' for t in cell.iter(S + 't'))
    v = cell.find(S + 'v')
    if v is None or v.text is None:
        return ''
    raw = v.text
    if ty == 's':
        return strings[int(raw)]
    if ty in ('str', 'e'):
        return raw
    if ty == 'b':
        return raw == '1'
    try:
        return float(raw) if ('.' in raw or 'E' in raw.upper()) else int(raw)
    except ValueError:
        return raw


def read_xlsx(blob):
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as e:
        raise ValueError('This file is not a valid .xlsx workbook.') from e
    with z:
        if sum(x.file_size for x in z.infolist()) > MAX_UNCOMPRESSED_BYTES:
            raise ValueError('Workbook is too large after decompression (60 MB limit).')
        if 'xl/workbook.xml' not in z.namelist():
            raise ValueError('Workbook structure is missing xl/workbook.xml.')
        names = set(z.namelist())
        shared = []
        if 'xl/sharedStrings.xml' in names:
            root = ET.fromstring(z.read('xl/sharedStrings.xml'))
            shared = [''.join(n.text or '' for n in si.iter(S + 't')) for si in root.findall(S + 'si')]
        book = ET.fromstring(z.read('xl/workbook.xml'))
        relationships = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        targets = {r.attrib['Id']: r.attrib['Target'] for r in relationships.findall(P + 'Relationship')}
        result = {}
        for sheet in book.findall('.//' + S + 'sheet'):
            title = sheet.attrib['name']
            path = targets.get(sheet.attrib[R + 'id'], '')
            if path.startswith('/'):
                path = path.lstrip('/')
            else:
                path = posixpath.normpath(posixpath.join('xl', path))
            if path not in names:
                continue
            root = ET.fromstring(z.read(path))
            all_rows = []
            for row in root.findall('.//' + S + 'sheetData/' + S + 'row'):
                if len(all_rows) >= MAX_ROWS_PER_SHEET:
                    raise ValueError('A worksheet exceeds the 50,000-row demo limit.')
                values = {}
                for cell in row.findall(S + 'c'):
                    ref = cell.attrib.get('r')
                    if ref:
                        values[_col_number(ref)] = _cell_value(cell, shared)
                if values:
                    all_rows.append([values.get(i, '') for i in range(max(values) + 1)])
            if not all_rows:
                result[title] = []
                continue
            headers = [str(x).strip() for x in all_rows[0]]
            result[title] = [{h: row[i] if i < len(row) else '' for i, h in enumerate(headers) if h}
                             for row in all_rows[1:] if any(str(x).strip() for x in row)]
        return result


def read_csv(blob):
    try:
        content = blob.decode('utf-8-sig')
    except UnicodeDecodeError as e:
        raise ValueError('CSV must use UTF-8 encoding.') from e
    return {'Transactions': list(csv.DictReader(io.StringIO(content)))}


def read_data(blob, filename):
    lower = filename.lower()
    if lower.endswith('.xlsx'):
        return read_xlsx(blob)
    if lower.endswith('.csv'):
        return read_csv(blob)
    raise ValueError('Upload an Excel .xlsx workbook or .csv transaction file.')
