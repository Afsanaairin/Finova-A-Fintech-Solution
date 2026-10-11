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
MAX_ZIP_ENTRIES = 256
MAX_SHEETS = 16
MAX_COLUMNS = 128
MAX_TOTAL_ROWS = 50000
MAX_TOTAL_CELLS = 200000
MAX_INPUT_BYTES = 12 * 1024 * 1024


def _xml(blob):
    # XLSX does not need DTDs/entities. Reject them before ElementTree can
    # expand declarations. The ZIP byte limit alone cannot stop XML expansion.
    if re.search(br'<!\s*(?:DOCTYPE|ENTITY)\b', blob, re.IGNORECASE) or b'\x00' in blob:
        raise ValueError('Workbook XML must use UTF-8 without DTDs or entities.')
    try:
        return ET.fromstring(blob)
    except ET.ParseError as exc:
        raise ValueError('Workbook contains invalid XML.') from exc


def _col_number(address):
    match = re.fullmatch(r'([A-Z]{1,3})[1-9][0-9]*', address.upper())
    if not match:
        raise ValueError('Workbook contains an invalid cell address.')
    result = 0
    for ch in match.group(1):
        result = result * 26 + (ord(ch) - 64)
    if result > MAX_COLUMNS:
        raise ValueError('A worksheet exceeds the 128-column limit.')
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
        index = int(raw)
        if not 0 <= index < len(strings):
            raise ValueError('Workbook contains an invalid shared string index.')
        return strings[index]
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
        entries = z.infolist()
        if len(entries) > MAX_ZIP_ENTRIES:
            raise ValueError('Workbook exceeds the 256 ZIP-entry limit.')
        if len({entry.filename for entry in entries}) != len(entries):
            raise ValueError('Workbook contains duplicate ZIP entries.')
        if any(entry.flag_bits & 1 for entry in entries):
            raise ValueError('Encrypted workbooks are not supported.')
        if sum(x.file_size for x in entries) > MAX_UNCOMPRESSED_BYTES:
            raise ValueError('Workbook is too large after decompression (60 MB limit).')
        if not {'xl/workbook.xml', 'xl/_rels/workbook.xml.rels'} <= set(z.namelist()):
            raise ValueError('Workbook structure is missing xl/workbook.xml.')
        names = set(z.namelist())
        shared = []
        if 'xl/sharedStrings.xml' in names:
            root = _xml(z.read('xl/sharedStrings.xml'))
            shared = [''.join(n.text or '' for n in si.iter(S + 't')) for si in root.findall(S + 'si')]
            if len(shared) > MAX_TOTAL_CELLS:
                raise ValueError('Workbook contains too many shared strings.')
        book = _xml(z.read('xl/workbook.xml'))
        relationships = _xml(z.read('xl/_rels/workbook.xml.rels'))
        targets = {r.attrib['Id']: r.attrib['Target'] for r in relationships.findall(P + 'Relationship')}
        result = {}
        sheets = book.findall('.//' + S + 'sheet')
        if len(sheets) > MAX_SHEETS:
            raise ValueError('Workbook exceeds the 16-sheet limit.')
        total_rows = total_cells = 0
        for sheet in sheets:
            title = sheet.attrib['name']
            path = targets.get(sheet.attrib[R + 'id'], '')
            if path.startswith('/'):
                path = path.lstrip('/')
            else:
                path = posixpath.normpath(posixpath.join('xl', path))
            if path not in names:
                continue
            root = _xml(z.read(path))
            all_rows = []
            for row_count, row in enumerate(root.findall('.//' + S + 'sheetData/' + S + 'row'), 1):
                total_rows += 1
                if row_count > MAX_ROWS_PER_SHEET or total_rows > MAX_TOTAL_ROWS:
                    raise ValueError('A worksheet exceeds the 50,000-row demo limit.')
                values = {}
                cells = row.findall(S + 'c')
                total_cells += len(cells)
                if len(cells) > MAX_COLUMNS or total_cells > MAX_TOTAL_CELLS:
                    raise ValueError('Workbook exceeds the column or 200,000-cell limit.')
                for cell in cells:
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
    try:
        reader = csv.DictReader(io.StringIO(content), strict=True)
        if not reader.fieldnames or len(reader.fieldnames) > MAX_COLUMNS:
            raise ValueError('CSV requires a header with at most 128 columns.')
        rows = []
        for row in reader:
            if len(rows) >= MAX_TOTAL_ROWS:
                raise ValueError('CSV exceeds the 50,000-row limit.')
            if None in row:
                raise ValueError('CSV row has more fields than the header.')
            if (len(rows) + 1) * len(reader.fieldnames) > MAX_TOTAL_CELLS:
                raise ValueError('CSV exceeds the 200,000-cell limit.')
            rows.append(row)
        return {'Transactions': rows}
    except csv.Error as exc:
        raise ValueError('CSV is malformed or contains an oversized field.') from exc


def read_data(blob, filename):
    if not blob or len(blob) > MAX_INPUT_BYTES:
        raise ValueError('Files must be nonempty and no larger than 12 MiB.')
    lower = filename.lower()
    if lower.endswith('.xlsx'):
        try:
            return read_xlsx(blob)
        except (zipfile.BadZipFile, KeyError, IndexError, NotImplementedError, RuntimeError) as exc:
            raise ValueError('Workbook is corrupt or uses an unsupported format.') from exc
    if lower.endswith('.csv'):
        return read_csv(blob)
    raise ValueError('Upload an Excel .xlsx workbook or .csv transaction file.')
