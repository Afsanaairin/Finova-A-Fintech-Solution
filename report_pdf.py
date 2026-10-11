"""Small, offline PDF renderer with vector charts and paginated tables (stdlib only)."""
import re
import textwrap
import zlib

WIDTH, HEIGHT, MARGIN = 595, 842, 40
INK = (0.08, 0.18, 0.30)
MUTED = (0.35, 0.43, 0.52)
TEAL = (0.04, 0.61, 0.53)
PURPLE = (0.49, 0.43, 0.81)


def clean(value):
    return re.sub(r'[\x00-\x1f\x7f]', ' ', str(value)).translate(str.maketrans({'−': '-', '→': '>', '–': '-', '—': '-', 'ⓘ': 'i'}))


def text_width(value, size):
    # Helvetica's narrow/wide glyphs matter for currency columns and wrapped cells.
    return sum(0.27 if c in " .,:;!ilI'" else 0.83 if c in 'MWmw@%' else 0.56 for c in value) * size


def lines(value, width, size):
    words = clean(value).split()
    result, current = [], ''
    for word in words:
        pieces = textwrap.wrap(word, max(1, int(width / (size * .65))), break_long_words=True, break_on_hyphens=False) if text_width(word, size) > width else [word]
        for piece in pieces:
            candidate = f'{current} {piece}'.strip()
            if current and text_width(candidate, size) > width:
                result.append(current)
                current = piece
            else:
                current = candidate
    return result + ([current] if current else [''])


class PDF:
    def __init__(self, document):
        self.doc = document
        self.pages = []
        self.commands = []
        self.y = 0
        self.page()

    def rect(self, x, y, width, height, color):
        self.commands.append(f'q {color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg {x:.2f} {HEIGHT-y-height:.2f} {width:.2f} {height:.2f} re f Q')

    def text(self, value, x, y, size=10, bold=False, color=INK):
        value = clean(value).encode('cp1252', 'replace').decode('latin1').replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        self.commands.append(f'BT /F{2 if bold else 1} {size:.2f} Tf {color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg 1 0 0 1 {x:.2f} {HEIGHT-y-size:.2f} Tm ({value}) Tj ET')

    def page(self):
        if self.commands:
            self.pages.append('\n'.join(self.commands).encode('latin1'))
        self.commands = []
        self.rect(0, 0, WIDTH, 70, INK)
        self.text('FINOVA', MARGIN, 18, 21, True, (1, 1, 1))
        self.text('FINANCIAL INTELLIGENCE', MARGIN + 108, 26, 9, False, (.58, .9, .84))
        self.text(lines(self.doc['company'], WIDTH-2*MARGIN, 9)[0], MARGIN, 50, 9, False, (.8, .88, .94))
        self.text(f'FINOVA | {self.doc["generated_at"]} | USD', MARGIN, 809, 8, False, MUTED)
        self.text(f'Page {len(self.pages)+1}', WIDTH-MARGIN-40, 809, 8, False, MUTED)
        self.y = 92

    def ensure(self, height):
        if self.y + height > 790:
            self.page()

    def paragraph(self, value, size=10, bold=False, color=MUTED, after=8):
        for line in lines(value, WIDTH-2*MARGIN, size):
            self.ensure(size*1.5)
            self.text(line, MARGIN, self.y, size, bold, color)
            self.y += size * 1.5
        self.y += after

    def heading(self, value):
        self.ensure(56)
        self.y += 9
        self.paragraph(value, 14, True, INK, 7)

    def metrics(self, metrics):
        columns = 2 if len(metrics) > 3 else max(1, len(metrics))
        width = (WIDTH-2*MARGIN-10*(columns-1))/columns
        for start in range(0, len(metrics), columns):
            self.ensure(78)
            for index, metric in enumerate(metrics[start:start+columns]):
                x = MARGIN+index*(width+10)
                self.rect(x, self.y, width, 69, (.94, .97, .98))
                label = lines(metric['label'], width-20, 8)
                for offset, line in enumerate(label[:2]):
                    self.text(line, x+10, self.y+9+offset*10, 8, False, MUTED)
                self.text(metric['value'], x+10, self.y+37, 16, True, TEAL)
            self.y += 79

    def table(self, table):
        headers, rows = table['headers'], table['rows']
        if not rows:
            self.paragraph('No matching source records supplied for this section.')
            return
        weights = [1]*len(headers)
        if len(headers) == 2:
            weights = [.6, 2.8]
        elif len(headers) == 3:
            weights = [1.5, 1.1, 1]
            if 'Counterparty' in headers[1]:
                weights = [.8, 2.2, .8]
        elif len(headers) == 4:
            weights = [1.2, 1.2, .7, 1]
        widths = [(WIDTH-2*MARGIN)*w/sum(weights) for w in weights]

        def draw_header():
            self.ensure(44)
            wrapped = [lines(h, w-14, 8) for h, w in zip(headers, widths)]
            height = max(map(len, wrapped))*11+14
            self.rect(MARGIN, self.y, WIDTH-2*MARGIN, height, (.9, .95, .96))
            x = MARGIN
            for cell, width in zip(wrapped, widths):
                for offset, line in enumerate(cell):
                    self.text(line, x+7, self.y+7+offset*11, 8, True)
                x += width
            self.y += height

        draw_header()
        for index, row in enumerate(rows):
            wrapped = [lines(cell, width-14, 9) for cell, width in zip(row, widths)]
            height = max(map(len, wrapped))*13+12
            if self.y+height > 790:
                self.page()
                draw_header()
            if index % 2 == 0:
                self.rect(MARGIN, self.y, WIDTH-2*MARGIN, height, (.97, .98, .99))
            x = MARGIN
            for cell, width in zip(wrapped, widths):
                for offset, line in enumerate(cell):
                    self.text(line, x+7, self.y+6+offset*13, 9)
                x += width
            self.y += height
        self.y += 12

    def chart(self, chart):
        labels, series = chart['labels'], chart['series']
        if not labels or not series:
            return
        horizontal = chart.get('kind') == 'horizontal'
        height = max(180, len(labels)*28+48) if horizontal else 210
        self.ensure(height+24)
        self.text(chart['title'], MARGIN, self.y, 10, True)
        top = self.y+25
        colors = (TEAL, PURPLE)
        maximum = max([v for s in series for v in s['values']]+[1])
        if horizontal:
            for index, label in enumerate(labels):
                value = series[0]['values'][index]
                self.text(lines(label, 145, 8)[0], MARGIN, top+index*28, 8)
                self.rect(MARGIN+150, top+index*28, (WIDTH-2*MARGIN-222)*value/maximum, 14, TEAL)
                self.text(f'${value:,.0f}', WIDTH-MARGIN-68, top+index*28, 8)
        else:
            plot_height = 125
            group_width = (WIDTH-2*MARGIN)/len(labels)
            for index, label in enumerate(labels):
                for j, s in enumerate(series):
                    value = s['values'][index]
                    bar_width = min(44, (group_width-12)/len(series))
                    x = MARGIN+index*group_width+6+j*bar_width
                    bar_height = plot_height*value/maximum
                    self.rect(x, top+plot_height-bar_height, bar_width-3, bar_height, colors[j % 2])
                    if len(labels) <= 3:
                        self.text(f'${value:,.0f}', x, top+plot_height-bar_height-13, 7)
                self.text(label, MARGIN+index*group_width+5, top+plot_height+8, 7)
            for index, s in enumerate(series):
                x = MARGIN+index*240
                self.rect(x, top+plot_height+29, 7, 7, colors[index % 2])
                self.text(s['label'], x+12, top+plot_height+25, 8)
        self.y += height+15

    def render(self):
        self.paragraph(self.doc['title'], 21, True, INK)
        self.paragraph(self.doc['subtitle'], 11, False, MUTED)
        self.paragraph(f'Generated {self.doc["generated_at"]} · Amounts in USD', 8)
        for section in self.doc['sections']:
            self.heading(section['title'])
            if section.get('label'):
                self.paragraph(section['label'], 9, True, TEAL)
            if section.get('metrics'):
                self.metrics(section['metrics'])
            for paragraph in section.get('paragraphs', []):
                self.paragraph(paragraph)
            if section.get('chart'):
                self.chart(section['chart'])
            if section.get('table'):
                self.table(section['table'])
            for info in section.get('investigations', []):
                self.heading(info['title'])
                for index, question in enumerate(info['questions'], 1):
                    self.paragraph(f'{index}. {question["question"]} · {question["label"]}', 9, True, TEAL, 3)
                    self.paragraph(question['text'])
        self.pages.append('\n'.join(self.commands).encode('latin1'))
        objects = [b'', b'', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
                   b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>']
        page_ids = []
        for content in self.pages:
            stream = zlib.compress(content)
            stream_id = len(objects)+1
            objects.append(f'<< /Length {len(stream)} /Filter /FlateDecode >>\nstream\n'.encode()+stream+b'\nendstream')
            page_ids.append(len(objects)+1)
            objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {WIDTH} {HEIGHT}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {stream_id} 0 R >>'.encode())
        objects[0] = b'<< /Type /Catalog /Pages 2 0 R >>'
        objects[1] = f'<< /Type /Pages /Count {len(page_ids)} /Kids [{" ".join(f"{i} 0 R" for i in page_ids)}] >>'.encode()
        output = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
        offsets = [0]
        for index, obj in enumerate(objects, 1):
            offsets.append(len(output))
            output.extend(f'{index} 0 obj\n'.encode()+obj+b'\nendobj\n')
        cross_reference = len(output)
        output.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
        for offset in offsets[1:]:
            output.extend(f'{offset:010d} 00000 n \n'.encode())
        output.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{cross_reference}\n%%EOF\n'.encode())
        return bytes(output)


def render_pdf(document):
    return PDF(document).render()
