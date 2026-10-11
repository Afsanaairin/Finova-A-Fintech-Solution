# FINOVA — Finance Innovation

**Financial intelligence that helps businesses understand their numbers and decide what to do next.**

[Live FINOVA demo](https://finova-intelligence.duckdns.org/) · [GitHub repository](https://github.com/Afsanaairin/Finova-A-Fintech-Solution) · Hack Midwest 2026

> **Important release distinction:** A previous tested FINOVA version was deployed successfully on Akamai Linode with DuckDNS and HTTPS. This updated GitHub ZIP adds email-code login, SQLite authentication, PDF intake, and downloadable reports. These changes still need to be deployed and verified on the public site. The live URL may not yet reflect all features listed in this README. Use fictional data for this restricted demo.

## Why FINOVA exists

A business can know its balance and still not understand *why* spending rose, which invoices need follow-up, or how its cash position might change. Financial records are useful only when someone can understand them and act.

**FINOVA turns records into understandable evidence and practical next steps.** Upload financial data, see what changed, inspect flagged patterns with supporting records, explore possible future cash conditions, ask questions, and share findings. The user should be able to make a better-informed business decision, not simply look at another dashboard.

## What FINOVA does

| Feature | Value to the user |
| --- | --- |
| **Overview** | Cash receipts, outgoing payments, net cash movement, estimated cash position, and invoice revenue presented separately. |
| **Existing-file uploads** | `.xlsx`, `.csv`, and reviewed PDF bank statements/customer invoices (PDF tools are optional system packages). |
| **Anomaly Explorer** | Spending spikes, subscription price changes and overdue invoices, with history, evidence and investigative next steps. |
| **Downloadable PDF reports** | Investigation evidence and financial summaries that can be shared outside the app. |
| **Forecast & Scenarios** | Illustrative three-month cash outlook and what-if controls, not guaranteed predictions. |
| **Subscriptions** | Understand recurring charges and price increases. |
| **Transactions** | Explore ledger records and search recent activity. |
| **Ask FINOVA** | Calculated offline responses plus optional Akamai-hosted financial explanations. |
| **Business Wrapped** | Play an animated financial story and export a video in the browser. |
| **Email-code login (newer source)** | Users request a six-digit code to access their dashboard; the hosted demo also uses nginx Basic Auth. |

![FINOVA sign-in screen](images/login_page.png)

**Important distinctions:** Recorded cash receipts are not necessarily invoiced revenue. Net cash movement is not accounting profit. An anomaly is a signal to review, not proof of fraud. FINOVA does not move money or automatically cancel subscriptions.

## Run FINOVA locally

Requires **Python 3.10+**. Core app logic uses only standard-library modules; no pip installation is required for `.xlsx`, `.csv`, or the demo financial engine.

Clone from GitHub (or extract the ZIP) and open a terminal in the directory containing `run.py`.

**Windows CMD:**

```bat
py -3 run.py
```

**macOS/Linux:**

```bash
python3 run.py
```

Visit **http://127.0.0.1:8000**. Stop with `Ctrl+C`. To change the listening port locally, set `PORT=8001` in `.env` or your local environment and restart.

### Configure email-code login

The updated version requires authorized SMTP settings to email login codes. Copy `.env.example` to the ignored `.env` file in the project folder and edit it privately.

**Windows CMD:**

```bat
copy .env.example .env
notepad .env
```

**macOS/Linux:**

```bash
cp .env.example .env
```

For Gmail, use an account with app-password access and STARTTLS (`smtp.gmail.com`, port `587`). Configure `SMTP_USER`, `SMTP_APP_PASSWORD`, and `SMTP_FROM`. The code is six digits, normally expires after five minutes and establishes a seven-day session by default. Keep `COOKIE_SECURE=false`, `PUBLIC_ORIGIN=` blank for local HTTP. For HTTPS, use secure cookies and the exact public origin. Do **not** commit the `.env` file.

### Optional Akamai workshop AI

Add an authorized Hack Midwest team inference key **to the same private `.env`**:

```dotenv
OPENAI_BASE_URL=https://ws.akamai-workshops.com/v1
OPENAI_API_KEY=YOUR_TEAM_KEY
```

The workshop key is **not** a Linode API token. Financial calculations, forecasts, reports and bounded offline Q&A work without it. Optional `hackathon-chat` and `hackathon-image` use server-side HTTPS requests; no API secret goes to the browser.

### Optional PDF/OCR tools

PDFs need Poppler; scanned PDFs additionally need Tesseract. On Debian/Ubuntu:

```bash
sudo apt-get install -y poppler-utils tesseract-ocr tesseract-ocr-eng
```

See the fictional PDFs under [`data/pdf_examples/`](data/pdf_examples/). The app proposes extracted records for users to review, correct and confirm; it does not treat OCR guesses as final facts. PDF input is capped at 12 MiB and 20 pages; additional row and processing limits apply.

## Data fields and calculations

The synthetic [`data/finova.xlsx`](data/finova.xlsx) includes `Business Profile`, `Transactions`, `Revenue`, `Invoices`, `Operating Expenses`, `Vendors`, `Payroll`, `Subscriptions`, and `Monthly Summary`.

You can upload a simple CSV with columns:

```csv
Date,Type,Category,Description,Amount_USD
2026-01-10,Income,Sales,Customer payment,1200
2026-01-12,Expense,Utilities,Electricity bill,175
```

`Date` is `YYYY-MM-DD`, `Type` is `Income` or `Expense`, and `Amount_USD` is a positive amount. A workbook needs a `Transactions` sheet for ledger cash analysis. An invoice-only file can be reviewed for unpaid invoices but does not establish cash receipts or a cash forecast. Optional fields provide additional traceability.

FINOVA separates actual money received from invoiced revenue, prevents double counting when expense/payroll sheets are included, and only estimates closing cash when opening balance and complete ledger coverage support that figure. Overdue invoices are evaluated at the supplied reporting date, not today's date.

**Forecast method:** 70% recent three-month average plus 30% same month last year, where available. The ranges are illustrative—not statistical confidence intervals or trained machine-learning predictions. **Anomaly method:** deterministic category baseline comparisons, subscription price shifts, and late invoices. Investigation reports explain evidence and possible next steps, not assumed causes.

## Test the current source

**Windows CMD:**

```bat
py -3 -m unittest discover -s tests -v
```

**macOS/Linux:**

```bash
python3 -m unittest discover -s tests -v
```

Optional Node.js browser behavior checks:

```bash
node tests/test_auth_ui.js
node tests/test_story_reset.js
```

**Audited updated ZIP (October 11, 2026):** **95 Python tests passed** and both login/story JavaScript tests passed. The earlier running Akamai server passed **28 tests** on its older deployed commit. The 95 tests do not prove live SMTP, PDF system dependencies, cloud AI connectivity, or all hosted browser flows.

## Code and documents

| Path | Purpose |
| --- | --- |
| `run.py`, `server.py`, `security.py` | App entry point, HTTP routes and proxy guards. |
| `auth.py` | SMTP login codes, SQLite sessions and email identities. |
| `finance.py`, `investigations.py` | Financial metrics, flags and evidence. |
| `xlsx_reader.py`, `pdf_reader.py` | Read/validate financial source files. |
| `reports.py`, `report_pdf.py` | Build downloadable evidence reports and PDFs. |
| `static/` | Login and dashboard UI, PDF review, story/video, and report controls. |
| `data/` | Fictional workbook, example PDFs; ignored local auth DB created at runtime. |
| `tests/` | Unit, HTTP/security and UI regression checks. |
| `deploy/` | Non-root systemd, nginx proxy and certificate renewal templates. |
| `tools/check_secrets.py` | Heuristic Git/history secret scanner. |

**Complete guides:**

- [README_CONFIGURATION.md](README_CONFIGURATION.md) — **exact Akamai setup:** SSH keys, CLI, Linode/firewall, Python service, DuckDNS, Certbot, nginx, security layers, troubleshooting, future GitHub updates, and the critical **new SQLite/SMTP upgrade**.
- [README_TECHNOLOGY.md](README_TECHNOLOGY.md) — technologies, modules, data flow, decisions and limitations.
- [architecture.txt](architecture.txt) — ASCII network, authentication and analytics diagram.
- [deploy/README.md](deploy/README.md) — original restricted-demo server templates; adapt to Debian and DuckDNS using the configuration guide above.

## How the Akamai-hosted site updates

[FINOVA website](https://finova-intelligence.duckdns.org/) uses **Akamai Linode (Debian 12)**, **DuckDNS**, **Let's Encrypt HTTPS**, **nginx Basic Auth**, a private Python service on `127.0.0.1:8000`, and a restricted Cloud Firewall. The GitHub checkout is `/root/finova-source`; the **actual running copy** is `/opt/finova`.

A GitHub `push` does **not** automatically update the website. The workflow is **push reviewed code -> pull on Akamai -> test -> back up -> copy tested release -> restart FINOVA -> verify in browser**. The hostname, HTTPS certificate, SSH keys and nginx settings normally stay in place across code updates.

**Before deploying the current ZIP**, follow **Part H of [README_CONFIGURATION.md](README_CONFIGURATION.md)**. The new email login needs both private SMTP configuration and a writable SQLite state directory; the original service is read-only. Don't unintentionally lose login state or expose private uploads.

## Security, caveats, and next steps

- **Restricted fictional-data demo**, not a production financial service, regulated accounting/audit platform, banking connection, or real transaction processor.
- Nginx Basic Auth and the new email-code login are **different checks**. The email-auth database persists when configured; uploaded financial results remain session memory and reset on logout/restart.
- Python's built-in `http.server` is lightweight and should not be treated as an independently hardened commercial production server.
- Reports and Q&A should cite actual records; FINOVA does not assert causes it cannot verify, guarantee forecast accuracy, or classify suspected fraud.
- The existing deployment guide flags a credential-shaped value in early Git history. Rotate any real exposed key with the provider. Run `python3 tools/check_secrets.py` **in a real Git checkout**; the downloaded ZIP alone does not include historical Git objects.
- Future work: train/test forecasting if evidence supports it, improve input validation and multi-user isolation, move SQLite state outside `/opt/finova`, improve production hosting and monitoring, and quantify business benefit.

**FINOVA — Finance Innovation. From financial records to clearer decisions.**


## Team

Built by:

- Chukwunonyelum Rosalyn Ezeako
- Afsana Airin
- Odunayo Juliana Owokade
- Ruyi Gai
- Md Shakiful Islam Khan
