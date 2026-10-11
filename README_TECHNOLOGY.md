# FINOVA — Technology README

**Finance Innovation | Hack Midwest 2026**  
**Live demo:** https://finova-intelligence.duckdns.org/  
**Source:** https://github.com/Afsanaairin/Finova-A-Fintech-Solution

## The business problem

Financial records contain numbers but often don't explain which cash changes matter, which invoices need follow-up, or why unusual spending deserves attention. FINOVA connects **records -> understandable evidence -> possible action**. It is a hackathon decision-support MVP, not banking infrastructure, guaranteed prediction, or audited accounting software. The sample workbook is fictional; no customer or financial impact is claimed.

## Technology decisions

| Technology | Files / layer | Why it matters |
| --- | --- | --- |
| **Python 3.10+; Python 3.11 on Debian** | `run.py`, `server.py`, processing modules | Runs APIs and auditable rules. Main app uses **Python standard library only**. |
| `http.server` / threads | `server.py`, `security.py` | Lightweight bounded demo HTTP service; not an independently production-hardened web server. |
| HTML, CSS, vanilla JavaScript | `static/index.html`, `static/styles.css`, `static/app.js` | Login screen, interactive dashboards, tables, graph rendering, scenarios, and in-page questions. |
| ZIP/XML and CSV standard libraries | `xlsx_reader.py` | Read `.xlsx`/`.csv` with bounds/validation and without pandas/openpyxl. |
| Poppler tools (optional) | `pdf_reader.py` | Extract bank-statement/invoice text from PDFs. |
| Tesseract OCR (optional) | `pdf_reader.py` | Extract text from some scanned PDFs, with required user correction/review. |
| SQLite (`sqlite3`) | `auth.py` | Persist email identities, hashed login codes, hashed session tokens and cooldown data. |
| SMTP STARTTLS | `auth.py` | Send six-digit email verification codes; needs a private configured sending account. |
| Akamai workshop API (optional) | `server.py` | `hackathon-chat` explanations and `hackathon-image` image calls via HTTPS using a server-only team key. |
| Python PDF writer | `reports.py`, `report_pdf.py` | Creates structured, shareable PDF investigation/period reports without a PDF pip package. |
| Browser Canvas / media recording | `static/wrapped.js` | Animated Business Wrapped and video export on the user's device. |
| Git + GitHub | Source collaboration, server checkout | Team version control and controlled releases. |
| Akamai Linode (Debian 12) | VPS | Runs FINOVA independently of a developer laptop. |
| systemd | `deploy/finova.service` | Runs a dedicated, restricted application account. |
| nginx | `deploy/nginx.conf`, `deploy/finova-proxy.conf` | HTTPS gateway, operator password, request limits, upstream identity/proxy token. |
| DuckDNS + Let's Encrypt / Certbot | DNS and certificate | Free subdomain, trusted HTTPS and renewal for the hosted demo. |
| Akamai Cloud Firewall | Public interface | TCP 443/80 public, SSH 22 limited; backend port 8000 not public. |

**Not used for core app:** Flask, Django, React, pandas, TensorFlow, scikit-learn, MongoDB, a local GPU, or a trained forecast/fraud model. Although the workshop taught other Akamai products, Object Storage/Kubernetes/managed databases are not mandatory FINOVA dependencies.

## Source map

| File / folder | Job |
| --- | --- |
| `run.py` | Application entry point. |
| `server.py` | HTTP routes, security checks, file uploads, sessions, financial APIs and workshop calls. |
| `security.py` | Restricted proxy/loopback and connection settings. |
| `auth.py` | Gmail SMTP codes and SQLite user/login state. |
| `finance.py` | Cash flows, invoices, subscription signals, heuristics, anomaly summaries. |
| `investigations.py` | Evidence-backed five-question investigations. |
| `reports.py` + `report_pdf.py` | Report content and PDF generation. |
| `xlsx_reader.py` | Bounded `.xlsx`/`.csv` parsing. |
| `pdf_reader.py` | PDF/OCR extraction and reviewed-record confirmation. |
| `static/index.html` | Sign-in page and workspace sections. |
| `static/app.js` | Page navigation, events, Q&A, data/forecast displays. |
| `static/pdf-upload.js` | Proposed PDF rows, review and confirm workflow. |
| `static/reports.js` | Preview/download report requests. |
| `static/wrapped.js` | Canvas story, timing, soundtrack and video export. |
| `static/styles.css`, `static/login-hero.webp` | Interface styles and sign-in asset. |
| `data/finova.xlsx`, `data/pdf_examples/` | Fictional demo inputs. |
| `tests/` | Unit, HTTP, frontend behavior, PDF/report and security checks. |
| `deploy/` | Existing restricted demo service, nginx, certificate renewal and env templates. |
| `tools/check_secrets.py` | Scans Git objects/local source for potential credentials if run in a Git checkout. |

## Financial workflow and why it matters

```text
Upload fictional data (.xlsx/.csv/PDF)
  -> Read and validate -> PDF review/confirmation where necessary
  -> Calculate cash, invoiced sales, invoices, subscription costs
  -> Identify signals and explain source evidence
  -> View dashboard and what-if estimates
  -> Ask FINOVA (offline calculated answer or optional Akamai chat)
  -> Download investigation PDF / export Business Wrapped video
```

| Financial question | FINOVA's output | Business action supported |
| --- | --- | --- |
| Where did our cash go? | Receipts, payments, category patterns and net cash movement | Investigate significant expense categories. |
| Who owes us money? | Known outstanding/overdue invoices at dataset reporting date | Prioritize invoice follow-up. |
| Which costs changed? | Spending and subscription price flags with baselines | Review vendors/services and relevant ledger evidence. |
| What happens if collections change? | Illustrative three-month outlook and scenario sliders | Discuss alternative short-term cash assumptions. |
| Can we explain a flag? | Five-question evidence narrative with downloadable PDF | Share defensible investigation notes. |
| How can we tell the financial story? | Animated business summary/video | Communicate findings to nontechnical people. |

**Accuracy boundaries:** Cash collected is not invoiced revenue; net cash movement is not profit; expense/payment sheets must not be counted twice. Anomaly alerts are deterministic checks, **not fraud proof**. Forecasts are heuristic (70% recent three-month averages, 30% same-month previous year where available), **not a trained ML model**. No claim of causal explanation, financial certainty, or realized savings.

## Backend route overview

```text
GET  /                       login + workspace HTML
GET  /api/auth/me            current email-login identity
POST /api/auth/send-code     SMTP delivery
POST /api/auth/verify-code   create secure auth session
POST /api/auth/logout        revoke login, clear finance session
GET  /api/dashboard          financial snapshot (requires login)
POST /api/upload             Excel/CSV or staged PDF
POST /api/pdf/confirm        accept reviewed PDF rows
POST /api/pdf/cancel         discard PDF draft
POST /api/reset              clear demo state
POST /api/ask                offline/optional Akamai explanation
POST /api/reports/preview   report data
POST /api/reports/download  generated PDF
POST /api/cover              optional artwork
GET  /api/akamai-test       check workshop service access
GET  /api/health            authenticated state/capabilities
```

All routes are subject to trusted-proxy checks when deployed on Akamai; workspace APIs also require the new email-login session. Some request methods have specific restrictions; refer to `server.py` for authoritative behavior.

## Runtime state and security

- Browser -> **nginx Basic Auth + TLS** -> trusted proxy token -> Python backend on `127.0.0.1:8000`. The browser never receives the proxy token or workshop API key.
- Updated `auth.py` stores **SQLite authentication state** at `data/auth.sqlite3` and uses an HttpOnly secure session cookie. For hosted mode the app additionally binds financial data to the verified operator identity and email login.
- Uploaded financial records live in bounded **server-memory sessions** rather than a cloud database; they disappear after logout/restart. The auth DB **does** persist when the filesystem is configured correctly.
- PDF extraction uses private temporary files; inputs are limited in size/format; unusual OCR formats need a user's confirmation.
- Hosted service has a **read-only filesystem restriction** by default. The new auth DB needs a carefully controlled writable exception; see configuration guide Part H.
- The app uses `http.server`, which is not an appropriate endpoint for unrestricted production financial accounts. Treat this deployment as a protected fictional-data MVP.

## Testing and deployment status

Run locally or in the server checkout:

```bash
python3 -m unittest discover -s tests -v
node tests/test_auth_ui.js        # optional Node.js
node tests/test_story_reset.js    # optional Node.js
```

**Audited updated ZIP, October 11, 2026:** **95 Python tests passed**; both JavaScript smoke tests passed. These tests do not prove live SMTP mail delivery, external Akamai access, TLS or uploaded financial-data privacy. The earlier online FINOVA version passed **28 tests** before new features were added; **the updated ZIP is not yet confirmed deployed**.

For SSH, Linode, DuckDNS, HTTPS, credential separation, the SQLite/SMTP upgrade and future code releases, use [README_CONFIGURATION.md](README_CONFIGURATION.md). For complete system/data flows, see [architecture.txt](architecture.txt).

## Next engineering priorities

1. Move the SQLite auth DB outside the release tree to a dedicated state directory (requires a small code change).
2. Review authentication UX: nginx operator sign-in is separate from FINOVA email-code sign-in.
3. Test upload parsing and financial source validation on representative formats; keep fictional data for public demos.
4. Validate forecast heuristics with time-split error metrics before marketing them as predictive modeling.
5. Introduce a suitable hardened production app server and data isolation if expanding beyond the hackathon.
6. Monitor secrets, billing, API quotas, certificate renewal and deployment rollbacks.

**FINOVA's professional value is its decisions and evidence—not merely the list of tools used.**
