# FINOVA v2 — Animated Business Wrapped + Akamai Integration

FINOVA (Finance Innovation) converts an uploaded financial workbook into a local finance dashboard and animated video. This version **preserves all v1 features** and adds an eight-scene Business Wrapped with exportable video, an original synthesized soundtrack, Akamai artwork integration, and a key-connection test.

## The fastest way to run

Open a terminal *inside the `finova` folder* (this folder contains `run.py`).

- **Windows CMD:** `py -3 run.py`
- **Windows if `py` is unavailable:** `python run.py`
- **macOS / Linux:** `python3 run.py`

Open **http://127.0.0.1:8000**. This build uses only the standard library in Python 3.10+; no pip install needed. If an old FINOVA server is using port 8000, stop it with Ctrl+C before launching v2.

The starter workbook is `data/finova.xlsx`. All new installations start with the fictional Lakeview Creative Studio LLC dataset; upload a different CSV or XLSX to switch. **Use synthetic data for the hackathon.**

## Export a Spotify-style Business Wrapped

1. Click **Business Wrapped** in the left menu.
2. Select **9:16 · Social story** or **16:9 · Judge demo**.
3. Click **Play Wrapped** for the animated experience.
4. Click **Export video**, and **keep the browser tab visible** until recording ends (about 30 seconds). Your browser downloads `FINOVA_Business_Wrapped.webm` in Chromium browsers. An original synthesizer soundtrack is included by default; uncheck Original soundtrack for silent video.
5. Chrome and Edge provide the most reliable browser recording support. Other browsers can play the story but may have different recording capabilities. If you need MP4 for judges and have FFmpeg installed, run `ffmpeg -i FINOVA_Business_Wrapped.webm -c:v libx264 -pix_fmt yuv420p -c:a aac FINOVA_Business_Wrapped.mp4` in the directory where the video was downloaded.

The video is **rendered locally in the browser**, not by an Akamai video model. The Akamai workshop supplies **image generation**, which we can use to add an original decorative background to the story. Metrics, labels and comparisons come from FINOVA's validated calculations, not from generated images.

## Connect Akamai hosted AI and images

1. In `finova`, copy `.env.example` to `.env`.
   - **Windows CMD:** `copy .env.example .env`
   - **macOS / Linux:** `cp .env.example .env`
2. Edit `.env` in a text editor. Keep the workshop endpoint:

   `OPENAI_BASE_URL=https://ws.akamai-workshops.com/v1`

   Replace the placeholder after `OPENAI_API_KEY=` with **the real `hk_...` team key provided by the event organizers**.
3. Save `.env` and restart FINOVA. The API key must never go into client-side JavaScript, screenshots, or a public GitHub repository.
4. Open **Business Wrapped → Test Akamai connection**. The screen should show either the available model aliases or an actionable failure message.
5. Click **Generate Akamai artwork**, and when it succeeds click **Play Wrapped** or **Export video**. The artwork becomes a decorative opening/closing backdrop. For AI explanations, use **Ask FINOVA** on Overview; the backend sends verified metrics to `hackathon-chat`.

If the team key isn't configured, the UI displays an explanation. The financial dashboard **and entire animation/video export still work offline**.

## Troubleshooting

- **Akamai button doesn't work:** check the inline message in the Wrapped page. `.env.example` isn't read as credentials; make a real `.env` and paste your team key. A 401 means rejected key; 403 means denied; 429 means rate-limited. Use the Test Akamai connection button.
- **Port already in use:** close the old terminal or edit `PORT=8001` in `.env` and use the new address.
- **Export button disabled:** it is temporarily disabled while a story is playing/recording; allow the current story to end.
- **Video has glitches / missing frames:** keep the tab active and visible, use current Chrome or Edge, and choose 9:16 as the default if your computer is slow.
- **Trying this on Mac/Linux:** the application runs with `python3 run.py`; no Windows path assumptions.
- **Browser upload:** other bank statement CSVs must have recognizable date, type, description, and amount columns. The multi-sheet `finova.xlsx` supports the richer invoices/payroll/subscriptions features.
- **Financial facts:** Cash receipts and billed revenue are different. Never double count related source worksheets. Forecasts are illustrative historical estimates, not trained neural-network models or guarantees.

## Project files

- `run.py` — cross-platform startup
- `server.py` — local HTTP API, security headers, Akamai calls, API test
- `finance.py` — calculations, anomaly checks and forecasting
- `xlsx_reader.py` — CSV/XLSX standard-library data import
- `static/index.html`, `static/styles.css`, `static/app.js` — dashboard and integrations
- `static/wrapped.js` — 8-scene graphics engine, browser video recorder and soundtrack
- `data/finova.xlsx` — fictional demo data
- `tests/test_finova.py` — financial reconciliation tests

## Scope, limitations, privacy

This is a **local hackathon prototype**, not a secure multi-tenant hosted accounting platform. Uploaded data is held in the demo server's session memory. Do not deploy this server directly to the public internet or upload real customer or employee financial records without authentication, HTTPS, access controls and data retention policies. The generated cover must be treated as illustration, not evidence. No subscription cancellation or payment initiation is implemented.
