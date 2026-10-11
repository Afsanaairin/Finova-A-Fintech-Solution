# FINOVA · Finance Innovation
**Financial Intelligence. Smarter Decisions.**

FINOVA is a working Hack Midwest 2026 MVP for turning business financial records into meaningful financial intelligence. You can run it locally on **Windows, macOS, or Linux** with Python 3.10+ and **no third-party Python packages**.

## The first version already works

- Open a visual dashboard containing 33 months of fictional business data from `data/finova.xlsx`.
- Upload your own **.xlsx** workbook or **.csv** transactions file and recalculate all available metrics.
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

## Passwordless email login

The top-right **Log in** button accepts an email address and sends a six-digit
one-time code. Users do not need a password, and recipient addresses are not
restricted to Gmail. The dashboard remains available as an anonymous demo.

To enable delivery, configure the following values in the existing `.env` file
without replacing the Akamai settings:

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-account@gmail.com
SMTP_APP_PASSWORD=your-google-app-password
SMTP_FROM=your-account@gmail.com
AUTH_CODE_TTL_SECONDS=300
AUTH_SESSION_TTL_SECONDS=604800
COOKIE_SECURE=false
PUBLIC_ORIGIN=
```

Enable Google 2-Step Verification on the sending account, then create an
[app password](https://support.google.com/accounts/answer/185833?hl=en).
Use that app password without its grouping spaces, rather than the account's
normal password. Leave `SMTP_FROM` blank to use `SMTP_USER`, or set it to the
same sending address. Gmail uses STARTTLS on port 587. Delivery remains subject
to Gmail sending limits and recipient spam filters.

Restart the server after setup. Click **Log in**, request a code, check the inbox
and spam folder, and enter the code. Codes expire after five minutes by default,
are valid once, and allow at most five incorrect attempts. Sending keeps a
60-second resend cooldown for each email address, with no application-level
hourly cap per email or IP. Different addresses can request codes independently.

Authentication uses an HttpOnly cookie and stores users, verification challenges,
rate limits, and session hashes in `data/auth.sqlite3`, which is ignored by Git.
Login sessions survive server restarts and expire after seven days by default.
Uploaded financial data still belongs to the existing browser demo session;
logging in does not synchronize it across devices or persist it across restarts.
Logging out deletes the current financial demo session, clears the user's email,
uploaded results, AI answers, artwork and playback state from the page, and opens
a fresh default demo. Existing tabs in the same browser are notified to reset,
and pages restored from browser history reload the current server state. Pending
uploads cannot restore a session that was retired during logout.

When serving through an HTTPS reverse proxy, set `COOKIE_SECURE=true` and set
`PUBLIC_ORIGIN` to the exact browser origin, such as `https://finova.example.com`.
For local HTTP development, keep `COOKIE_SECURE=false` and `PUBLIC_ORIGIN` blank.
Keep the `.env` file and authentication database private.

Run the local test suite without sending real email:

```bash
python -m unittest discover -s tests -v
```

If Node.js is available, check the login UI event handlers as well:

```bash
node tests/test_auth_ui.js
node tests/test_story_reset.js
```

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

For custom Excel, only a `Transactions` sheet is required. For cash, at minimum include these headers:

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

## 4 — How the calculations work

- **Cash receipts** = all positive transaction cash inflows.
- **Cash payments** = all recorded expense cash outflows.
- **Cash movement** = cash receipts − cash payments.
- **Estimated closing cash** = supplied opening cash + cumulative cash movement. Missing opening cash defaults to zero and is not a verified bank balance.
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

You should see six passing tests covering financial reconciliations, anomalies, cash balances, forecasting, and CSV upload logic.

## 6 — Architecture

```
Web browser (HTML / CSS / vanilla JavaScript)
   │  Local JSON + multipart upload
   ▼
Python ThreadingHTTPServer (server.py)
   ├─ XLSX and CSV reader (xlsx_reader.py, stdlib zipfile + XML)
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
- File uploads are capped at 12 MB; ZIP decompression and row counts are capped.
- Demo records are kept in memory per browser session; no account system or persistent database is included.
- Financial summaries may be sent to the Akamai hosted AI endpoint when a real key is configured, but raw transactions are not sent to chat in this version.
- Forecasts and subscription signals are informational, not investment or accounting advice. No money movement or subscription cancellation occurs.
- Never commit `.env` or include secrets in a hackathon submission.
- Recommended production work: authentication, tenant isolation, encrypted storage, rate limits, HTTPS/reverse proxy, access logs and retention rules.

Built during Hack Midwest 2026 — **FINOVA = Finance Innovation**.

---
**FINOVA v2 update (Hack Midwest 2026):** For the newest Animated Business Wrapped, local video export, Akamai key test and artwork flow, read [README_V2_FIRST.md](README_V2_FIRST.md). This older README describes the v1 financial engine, which remains available.
