# FINOVA · Finance Innovation
**Financial Intelligence. Smarter Decisions.**

FINOVA is a working Hack Midwest 2026 MVP for turning business financial records into meaningful financial intelligence. You can run it locally on **Windows, macOS, or Linux** with Python 3.10+ and **no third-party Python packages**.

## The first version already works

- Open a visual dashboard containing 33 months of fictional business data from `data/finova.xlsx`.
- Upload your own **.xlsx** workbook, **.csv** transactions file, or **.pdf** bank statement/customer invoice. Review PDF records before analysis; PDF extraction requires the optional tools below.
- Analyze cash receipts, payments, net cash movement, categories, and invoice-based revenue separately.
- Detect unusually high category spending, subscription price increases, and late invoices.
- Explore an illustrative three-month cash and invoiced-revenue forecast with a what-if calculator.
- Review a five-service subscription register and a searchable transaction ledger.
- Ask financial questions: offline rule-based answers work without credentials, with **Akamai `hackathon-chat`** used when your team's key is configured.
- Generate optional **Akamai `hackathon-image`** decorative cover artwork for Business Wrapped (requires key).

## 1 — Extract and launch (no package installation)

Download `FINOVA_Starter_v1.zip`, extract it, and **open a terminal inside the extracted `finova` folder** (the folder containing `run.py`).

### Windows — Command Prompt (CMD)

```bat
cd path\to\finova
py -3 run.py
```

If `py` isn't recognized, try `python run.py`. Use **CMD**, not PowerShell, if you follow the examples above.

### macOS

```bash
cd /path/to/finova
python3 run.py
```

### Linux

```bash
cd /path/to/finova
python3 run.py
```

Open **http://127.0.0.1:8000** in your browser.

No virtual environment or `pip install` is required. Stop with **Ctrl+C**. If you get *Address already in use*, edit `PORT=8000` in `.env` to `8001`, or set the `PORT` environment variable. `.env` is optional for basic operation.

## 2 — Connect your Akamai hackathon key

1. Copy `.env.example` to `.env` in the same directory as `run.py`.
2. Replace `paste_your_team_key_here` with **your own team's** Akamai key (provided by workshop organizers).
3. Keep the supplied endpoint and model aliases. Restart FINOVA.

**Windows CMD:**

```bat
copy .env.example .env
notepad .env
py -3 run.py
```

**macOS / Linux:**

```bash
cp .env.example .env
nano .env
python3 run.py
```

`OPENAI_BASE_URL=https://ws.akamai-workshops.com/v1` points to the shared workshop service.

- Chat uses **POST `/chat/completions`** with model `hackathon-chat`.
- Cover image generation uses **POST `/images/generations`** with model `hackathon-image`, 512×512 PNG.
- API keys are used **server-side only** and are never sent to the browser.
- Without the key, the dashboard, forecasts, upload, anomaly rules, scenarios, and local Q&A work normally.
- If your request is rejected or the service is offline, FINOVA shows an error. It does not pretend a remote model responded.

## 3 — Upload file format

### Excel

The default workbook `data/finova.xlsx` contains:

| Sheet | Purpose |
| --- | --- |
| `Business Profile` | Business name, opening cash, currency, synthetic-data note |
| `Transactions` | **Canonical cash ledger**, including each posted receipt and outgoing payment |
| `Revenue` | Invoiced **accrual sales**, linked by Invoice_ID |
| `Invoices` | Customer invoices, due dates, outstanding receivables |
| `Operating Expenses` | Source expense records; these are already included in Transactions |
| `Vendors` | Vendor list |
| `Payroll` | Source payroll; already included in Transactions |
| `Subscriptions` | Registry of recurring software costs |
| `Monthly Summary` | Reference totals, not re-added to financial ledger |

For custom Excel cash analysis, only a `Transactions` sheet is required. An invoice-only workbook with an `Invoices` sheet can instead produce a customer invoice report without a cash ledger. For transactions, use these headers:

`Date`, `Type`, `Category`, `Description`, `Amount_USD`

Dates should be `YYYY-MM-DD`. `Type` should be `Income` or `Expense` and `Amount_USD` should be positive. Optional `Signed_Amount_USD`, `Transaction_ID`, `Counterparty` enhance the audit trail.

For more complete analysis, include the extra sheets with the same headers used in the sample workbook. The v1 importer does not evaluate uncalculated formulas or support `.xls` files.

### CSV

A CSV is treated as a single `Transactions` sheet. Example:

```csv
Date,Type,Category,Description,Amount_USD
2026-01-10,Income,Sales,Customer payment,1200
2026-01-12,Expense,Utilities,Electricity bill,175
```

Financial metrics available from a CSV will be limited to the fields provided; invoice and subscription details require the corresponding sheets.

### PDF: start with the records you have

Clients do not need the complete demo workbook. FINOVA can start with a PDF bank statement, a transaction report, or a customer invoice in USD.

1. Upload a PDF with the same **Upload financial data** button.
2. FINOVA extracts text locally and uses OCR for scanned pages when the optional tools are installed.
3. Check the proposed document type and every extracted row. Correct dates, amounts, categories, and income/expense direction; uncheck rows to exclude them, and add any missing records.
4. For a statement, select its coverage: selected records/one account, expenses only, receipts only, or all cash transactions for the period. Opening cash is optional and available only for a complete cash ledger.
5. For customer invoices, confirm IDs, customers, due dates, invoice amounts, outstanding balances, and payment status. Select the date to use for overdue checks. A paid invoice does not by itself establish a cash receipt.
6. Confirm the review to replace the current dataset and run analysis. Uploading, editing, or cancelling a PDF draft leaves the existing dashboard intact.

**Supported initial layouts:** English documents with one dated transaction per line, ISO dates or U.S. dates including the year, amounts with two decimal places, and explicit income/expense, signed amounts, or debit/credit columns. Common running-balance columns are excluded from proposed payment amounts. Customer invoice extraction recognizes labels such as Invoice Number, Bill To, Invoice Date, Due Date, Total, and Amount Due.

This importer does not understand every bank or invoice layout. Wrapped rows, missing years, unusual tables, and OCR errors can need manual corrections. Unsigned amounts with no clear direction require the user to choose Income or Expense. Unsupported layouts can be entered manually using the extracted source text. **Retry with OCR** is available for PDFs whose text layer is incomplete.

Limits: **12 MB**, **20 pages**, up to **5 scanned/OCR pages**, and **1,000 reviewed records** per PDF. Reviews expire after 15 minutes. Password-protected or damaged PDFs are rejected. Records must be USD; currency conversion is not included. Vendor bills and payroll registers are not independently modeled; include only actual payments in transaction analysis.

PDF confirmation JSON is capped at **2 MiB** so reviewed record batches fit; other JSON endpoints retain an **8 KiB** limit. The deployment proxy template uses the same limits. PDF upload, confirmation, cancellation, and OCR retry use the same authentication, session isolation, and request checks as other routes.

Extraction has a 60-second processing budget, and the browser stops waiting for PDF uploads after 75 seconds. Upload errors stay visible until the next upload. If the screen asks you to restart FINOVA, stop the old process with **Ctrl+C**, run `python3 run.py` again from this folder, and reload the browser; the running Python server must be restarted to load the PDF routes.

Try the fictional files in [data/pdf_examples](data/pdf_examples): `bank-statement.pdf`, `customer-invoice.pdf`, and `scanned-bank-statement.pdf`.

Partial statements describe the uploaded records. Closing cash requires opening cash plus a complete cash ledger. Reviewed PDF cash forecasts additionally require at least three months of history and complete coverage. Customer invoice reports display known outstanding balances and unknown payment balances separately, with cash metrics and forecasts unavailable.

### Optional PDF tools

CSV, Excel, and the demo still run with Python's standard library alone. PDF support additionally needs the [Poppler command-line tools](https://poppler.freedesktop.org/) on the server's PATH: `pdfinfo` and `pdftotext`. Scanned PDFs need `pdftoppm`, [Tesseract](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html), and its English language data.

On Ubuntu/Debian:

```bash
sudo apt install poppler-utils tesseract-ocr tesseract-ocr-eng
```

On macOS or Windows, install Poppler and Tesseract for your platform and add their executables to PATH. Check installation with:

```bash
pdfinfo -v
pdftotext -v
tesseract --version
```

The upload screen reports whether PDF extraction is available. Processing is local; PDF files are written into a temporary directory that is cleaned up after extraction. No PDF or OCR data is sent to an AI service for extraction.

## 4 — How the calculations work

- **Cash receipts** = all positive transaction cash inflows.
- **Cash payments** = all recorded expense cash outflows.
- **Cash movement** = cash receipts − cash payments.
- **Estimated closing cash** = supplied opening cash + cumulative cash movement for a complete ledger. Without an opening balance or with declared partial coverage, closing cash is shown as not provided.
- **Invoiced revenue** comes from `Revenue` instead of treating deposits as sales.
- **Upcoming forecasts** use 70% recent 3-month average plus 30% prior-year corresponding month where available. They are *heuristics*, **not trained ML models** and their illustrative intervals are not statistical confidence intervals.
- **Price increase detection** compares the latest recorded subscription charge to its first recorded price.
- **Spend anomaly checks** compare recent category spending against the previous six observations' median.
- **Invoice overdue checks** use the last reporting month in the input data, not the computer's current date.

**DO NOT double count:** `Operating Expenses` and `Payroll` already feed `Transactions`; `Revenue` is invoice-based, while `Transactions` income means money collected. Adding those together is incorrect.

## 5 — Verification

On Windows:

```bat
py -3 -m unittest discover -s tests -v
```

On macOS/Linux:

```bash
python3 -m unittest discover -s tests -v
```

Tests cover financial reconciliations, anomalies, cash balances, forecasting, CSV/XLSX parsing, PDF extraction and OCR, invoice-only analysis, the review/confirmation lifecycle, proxy authentication, session isolation, request limits, and secret handling. They never require live AI credentials. Actual PDF/OCR integration tests are skipped if their optional system tools are not installed.

## 6 — Architecture

```
Web browser (HTML / CSS / vanilla JavaScript)
   │  Local JSON + multipart upload
   ▼
Python ThreadingHTTPServer (server.py)
   ├─ XLSX and CSV reader (xlsx_reader.py, stdlib zipfile + XML)
   ├─ PDF drafts (pdf_reader.py, local Poppler + optional Tesseract)
   │    └─ Browser review → confirmation → validated financial records
   ├─ Financial calculations (finance.py, stdlib statistics)
   ├─ Offline Q&A based on computed metrics
   └─ Akamai workshop API via HTTPS (optional)
         ├─ hackathon-chat: financial summaries and questions
         └─ hackathon-image: optional abstract Wrapped artwork
```

The app contains **no hidden dependency on Flask, pandas, Node.js, cloud databases, or local GPU**. Your team can replace the local server with a production backend later, while keeping the analytics functions and frontend.

## 7 — Next engineering steps (team priority)

1. **Data**: confirm the uploaded workbook reconciles to FINOVA's monthly summaries; record test cases.
2. **Financial modeling**: upgrade the forecast using time-based train/test validation, documented error metrics, and sufficient historical observations. Never present an untrained heuristic as an ML model.
3. **Akamai AI**: configure the real team key, demonstrate an AI explanation and optionally generate a Wrapped image.
4. **Frontend / Pitch**: show a full user journey: upload → anomaly → financial outlook → scenario → Wrapped. Keep the pitch within event constraints.
5. **Deployment**: use the workshop deployment guides to host FINOVA securely on Akamai Cloud. **Do not deploy this local development HTTP server to the public Internet as-is.**

## 8 — Security & limitations

**This version is a local hackathon demo, not a banking product or production-ready multitenant service.**

- Contains fictional financial records only. Do **not** upload real personal or business financial records to an exposed demo server.
- Files are capped at 12 MiB, with an additional 64 KiB multipart allowance. JSON requests are capped at 8 KiB. ZIP decompression, entries, sheets, rows, columns, and cells are bounded; XML entities are rejected.
- Demo records are kept in bounded, expiring browser sessions. Local mode is loopback-only; proxy mode requires an authenticated HTTPS gateway and binds sessions to its verified username. No persistent database is included.
- Financial summaries may be sent to the Akamai hosted AI endpoint when a real key is configured, but raw transactions are not sent to chat in this version.
- Forecasts and subscription signals are informational, not investment or accounting advice. No money movement or subscription cancellation occurs.
- Never commit `.env` or include secrets in a hackathon submission.
- Before remote publication, apply and verify the restricted service account, HTTPS/authenticated nginx proxy, host and cloud firewall, and server-only secret configuration in [deploy/README.md](deploy/README.md). The templates support a restricted demo; production still requires an appropriate application server and a reviewed account/data model.
- Run `python3 tools/check_secrets.py` before pushing. Keep `.env`, private keys, passwords, and populated deployment files out of Git and public JavaScript.

Built during Hack Midwest 2026 — **FINOVA = Finance Innovation**.

---
**FINOVA v2 update (Hack Midwest 2026):** For the newest Animated Business Wrapped, local video export, Akamai key test and artwork flow, read [README_V2_FIRST.md](README_V2_FIRST.md). This older README describes the v1 financial engine, which remains available.
