# FINOVA v3 — Interactive anomaly evidence and resilient financial Q&A

Version 3 is a targeted update to an existing FINOVA v2 installation. The data workbook, cash-flow math outside the anomaly evidence additions, and animated Business Wrapped (`static/wrapped.js`) remain unchanged.

## Features

- **Anomaly Explorer** sidebar page: selectable expense spikes, price increases, and overdue customer invoices with historical baseline, threshold, associated ledger records, and a suggested investigation step.
- **Overview investigation buttons:** Select a FINOVA intelligence alert and open the relevant evidence directly.
- **Graceful AI fallback:** If Akamai returns `401`, `403`, `429`, networking errors, or another upstream failure, `/api/ask` returns a verified local calculation-based response, with the failure explained in the interface. The local response is **not** represented as Akamai-generated.
- **Akamai key configuration fix:** The values in the project's `.env` override inherited shell variables. This follows the workshop's `load_dotenv(override=True)` convention.
- **Smaller AI context:** Sends selected computed metrics and anomaly summaries, not every underlying transaction, to the workshop chat service.
- **Pre-existing features preserved:** 3-month estimates, what-if simulator, subscriptions, Excel upload, transaction search, Business Wrapped animation and downloadable video.

## Windows CMD

From the existing folder containing `run.py`:

```bat
py -3 run.py
```

Then open http://127.0.0.1:8000 and use **Ctrl+Shift+R** to reload the updated JavaScript. Stop the old server with `Ctrl+C` first.

## macOS and Linux

```bash
python3 run.py
```

Refresh with **Cmd+Shift+R** on macOS or **Ctrl+Shift+R** on Linux.

## Diagnose Akamai HTTP 401

1. Open **your existing** `finova/.env` file; do not replace it with `.env.example`.
2. Verify the exact values, without exposing the real key:
   ```ini
   OPENAI_BASE_URL=https://ws.akamai-workshops.com/v1
   OPENAI_API_KEY=hk_YOUR_REAL_TEAM_KEY
   ```
3. Save `.env`, restart FINOVA, open **Business Wrapped → Test Akamai connection**.
4. `HTTP 401` means the Akamai workshop endpoint rejected your credential. Verify with hackathon staff that the key is activated and assigned to your team. Don't send the actual key in chat or commit it to Git.
5. A key appearing in the sidebar means it was *loaded*, not that authentication succeeded. FINOVA still offers local financial analysis until the issue is resolved.

## Quick demo walkthrough

1. **Overview:** Click the Electricity or Adobe alert card.
2. **Anomaly Explorer:** Select the **Spending spikes** filter and the **Electricity / June 2026** finding. View the flagged **$1,166.39** versus typical recent **$716.43**, supporting ledger transaction(s), and the recommended review.
3. **Invoice filter:** Look at the overdue customer invoice table.
4. **Ask FINOVA:** Try `Why have our expenses changed?`, `What subscriptions should we review?`, `What invoices are overdue?`, or click **Ask FINOVA about this** on an anomaly.
5. **Business Wrapped:** The v2 video playback/export is unchanged and works without a team key. Generating new Akamai artwork still needs verified credentials.

## Limitations

- Historical spike checks compare a month's category spending to the median of up to six *previous months with activity* for that category. They are deterministic statistical rules, not a trained fraud model or causal proof. These rules can miss irregular, nonrecurring spending and should be tuned per business.
- Overdue dates are evaluated **as of the Excel workbook's latest reporting month**, not live current time.
- The local assistant is a grounded rule-based fallback, not an LLM. It intentionally handles a limited set of common financial questions. The hosted Akamai model remains necessary for open-ended AI explanations.
- Neither this release nor the previous releases should be exposed publicly with real financial data without authentication, per-tenant data isolation, HTTPS, input and upload security review, and an appropriate production server.

## Run regression tests

```bash
python3 -m unittest discover -s tests -v
```

On Windows CMD, replace `python3` with `py -3`.
