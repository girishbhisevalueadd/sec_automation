# SEC EDGAR Financial Data Pipeline

> **A complete tool that downloads US-listed company financial data from the
> SEC, stores it in a database, and produces ready-to-use Excel models,
> Word research reports, and PDFs — all through a clean web dashboard.**

Built by **ValueAdd Research And Analytics Solutions LLP**.

This guide is written for someone who has never touched the project before.
Follow it top to bottom and you'll have the web app running in about 10 minutes.

> 📁 **All application code lives in the [`edgar_pipeline/`](./edgar_pipeline)
> subfolder.** Every command in this guide assumes you have a terminal open
> *inside* `edgar_pipeline/`. The setup section below tells you exactly how.

---

## Table of contents

1. [What this app does](#1-what-this-app-does)
2. [What you need before you start](#2-what-you-need-before-you-start)
3. [First-time setup (one time only)](#3-first-time-setup-one-time-only)
4. [Starting the web app](#4-starting-the-web-app)
5. [Using the web app — page by page](#5-using-the-web-app--page-by-page)
6. [Common tasks — step by step](#6-common-tasks--step-by-step)
7. [Where things are saved](#7-where-things-are-saved)
8. [Command-line usage (optional)](#8-command-line-usage-optional)
9. [Troubleshooting](#9-troubleshooting)
10. [Configuration](#10-configuration)
11. [How the cache works (save time, save money)](#11-how-the-cache-works)
12. [Folder structure](#12-folder-structure)

---

## 1. What this app does

You give it a company ticker (e.g. **AAPL**, **MSFT**, **NVDA**) and the app
will:

1. **Fetch** the company's recent annual (10-K) or quarterly (10-Q) filings
   directly from the SEC's free EDGAR website — no API key, no payment.
2. **Store** the financial statements (Income Statement, Balance Sheet,
   Cash Flow, Debt info) in a small SQLite database on your machine.
3. **Build** an Excel financial model with 7 styled sheets — Cover, Income
   Statement, Balance Sheet, Cash Flow, Debt Schedule, Key Ratios, raw Data.
4. **Generate** a Word research report (and a PDF version) with cover page,
   tables, and commentary sections.
5. **(Optional)** Use Claude AI to write a 600–800 word narrative for the
   report — but only if you set an Anthropic API key.

Everything is browsable from a dark-themed web dashboard.

---

## 2. What you need before you start

| Requirement | Why |
| --- | --- |
| **Python 3.10, 3.11, or 3.12** | The app's runtime. Python 3.14 is too new for some dependencies. |
| **About 1 GB of free disk space** | For Python packages and downloaded filings. |
| **Internet connection** | To download filings the first time. After that the cache works offline. |
| **Microsoft Word installed** (Windows only) | Needed for the highest-quality PDF output. If you don't have it the app falls back to a basic PDF — still works. |
| **A modern browser** (Chrome / Edge / Firefox) | To use the dashboard. |

**Optional:**

- An **Anthropic API key** if you want AI-written commentary in your reports.
  Get one at https://console.anthropic.com. Without it, reports use
  placeholder text — everything else still works.

### Check your Python version

Open a terminal (PowerShell on Windows, Terminal on Mac) and type:

```
python --version
```

If you see `Python 3.10.x`, `3.11.x`, or `3.12.x` → you're good.
If not, install one from https://www.python.org/downloads/.

---

## 3. First-time setup (one time only)

You only do this **once** per machine.

### Step 3.1 — Open a terminal in the project folder

The project lives in a folder called `edgar_pipeline`. Inside the terminal,
navigate there:

```bash
cd path/to/edgar_pipeline
```

(Replace `path/to/edgar_pipeline` with the real location on your computer.)

### Step 3.2 — Create the virtual environment named `secenv`

A virtual environment is a private box for the project's Python packages
so they don't conflict with anything else on your machine.

**Windows (PowerShell or Command Prompt):**
```
py -3.12 -m venv secenv
```

**Mac / Linux:**
```
python3.12 -m venv secenv
```

You should see a new folder called `secenv/` appear next to `main.py`.

### Step 3.3 — Activate the virtual environment

**Windows PowerShell:**
```
.\secenv\Scripts\Activate.ps1
```

**Windows Command Prompt (cmd.exe):**
```
secenv\Scripts\activate.bat
```

**Mac / Linux:**
```
source secenv/bin/activate
```

Your terminal prompt should now show `(secenv)` at the front.

### Step 3.4 — Install all the required packages

With `(secenv)` active in your terminal, run:

```
pip install -r requirements.txt
```

This downloads about 30 packages (Streamlit, Plotly, edgartools, pandas,
openpyxl, python-docx, anthropic, etc.) into the virtual environment.
**Expect this to take 2–5 minutes** depending on your internet speed.

When it finishes, you're done with setup.

---

## 4. Starting the web app

There are two ways: **a one-line launcher** (easy) or the raw streamlit
command (manual).

### Easy way — use the launcher

Make sure you're inside the `edgar_pipeline/` folder.

**Windows (any terminal):**
```
.\run_app.bat
```

**Mac / Linux / Git Bash:**
```
bash run_app.sh
```

The launcher will:

1. Find the `secenv/` Python automatically.
2. Verify Streamlit is installed.
3. Print the URL `http://localhost:8501`.
4. Start the server.

A browser tab should open automatically. If it doesn't, copy
**http://localhost:8501** into your browser address bar.

### Manual way — direct streamlit command

If you prefer to type the command yourself:

```
streamlit run app/streamlit_app.py
```

**Do NOT type `streamlit run main.py`** — that's the command-line tool, not
the web app. (This is the most common confusion.)

### Stopping the app

In the terminal where the app is running, press **`Ctrl + C`**.

---

## 5. Using the web app — page by page

Once the app is open in your browser, you'll see a **left sidebar** with
navigation, and a **main area** with content.

### The sidebar (always visible)

- **Top:** Your company name — *ValueAdd Research And Analytics Solutions LLP*.
- **Navigation:** Click any page to switch (Home, Dashboard, Run Pipeline,
  Financials, Charts, Downloads, Logs).
- **Pipeline:** Shows whether a pipeline run is currently happening.
  A green pulsing dot means *Running*. A gray dot means *Idle*.
- **Watchlist:** The list of company tickers you track. Add new tickers
  by typing them in the *Add Ticker* box and pressing *Add*. Remove
  tickers via the *Remove ticker* dropdown.
- **Quick Stats:** A one-line summary of how much data you have.

### 🏠 Home (landing page)

The first page you see. Shows:
- A **hero banner** with the platform name.
- **4 KPI cards** — Companies Tracked, Filings Stored, Reports Generated,
  Last Pipeline Run.
- A **Quick Run** box — type a ticker and click **▶ Run Full Pipeline**
  to jump to the Run Pipeline page with your ticker prefilled.
- A **Watchlist Snapshot** table with the tickers you track.
- A **Recent Activity** feed showing the last few log lines.

### 📊 Dashboard

A wider overview:
- The same 4 KPI cards at the top.
- An **Auto-refresh every 30 seconds** toggle for live monitoring.
- **Watchlist Status** table — for each ticker you see when it was last
  fetched, how many periods are stored, and whether an Excel file is ready.
  Rows are colored: green (fresh, ≤ 1 day), amber (≤ 7 days), red (stale).
- **Recent Outputs** — links to the 10 newest files you can download
  immediately.
- **Revenue sparklines** — one tiny chart per watchlist ticker showing
  the multi-year revenue trend.

### 🚀 Run Pipeline

This is where you trigger data fetches and report generation.

**Left panel — Run Configuration:**
- Pick **Single ticker** or **Watchlist** (multi-select).
- Choose **Form type**: 10-K (annual), 10-Q (quarterly), or both.
- Set the **Filings per form** slider (1–10).
- Check the **Steps** you want:
  - Fetch from SEC EDGAR
  - Store in SQLite
  - Build Excel Model
  - Generate Word Report
  - Generate PDF Report
  - Generate AI Narrative *(only works if Anthropic API key is set)*
- **Force refresh from EDGAR** checkbox — leave it OFF to reuse cached
  data; turn it ON only when you suspect the cache is stale.
- Click **▶ Run Pipeline** (or **▶ Run Whole Watchlist**).

**Right panel — Live Console:**
- Shows real-time progress: `[OK]` lines in green, `[INFO]` in blue,
  `[WARN]` in amber, `[ERROR]` in red.
- Progress bar at the bottom.
- When the run finishes, the **Files Created** cards appear with
  download buttons.

### 📋 Financials

Browse stored financial statements interactively:
- Pick a **Ticker** from the dropdown.
- Pick a **Number format**: Standard (M / B) or Indian (Cr / L).
- Use the **tabs** to switch between Income Statement / Balance Sheet
  / Cash Flow / Key Ratios / Debt Schedule.
- For each statement you can **multi-select periods** and optionally
  toggle **Compare two periods side-by-side** (adds Variance + Variance %).
- Click **⬇ Export this view as CSV** to download the table.
- **Quick Insights** cards show Revenue CAGR, Avg Net Margin, and FCF
  Conversion for the selected ticker.

### 📈 Charts

Six interactive Plotly charts in a grid:
1. Revenue & Net Income (bar)
2. Margin Trends — Gross / Operating / Net (line)
3. Cash Flow Components — Operating / Investing / Financing (bar)
4. Debt vs Equity (stacked bar)
5. Key Ratios Radar (latest period)
6. Peer Revenue Comparison (select up to 4 tickers)

Plus a **Multi-Company Overlay** section at the bottom for overlaying up
to 4 revenue trends on one chart.

Hover any chart for a formatted tooltip. The toolbar (top-right of each
chart on hover) lets you zoom, pan, and export as PNG.

### ⬇️ Downloads

Three tabs — Excel Models, Word Reports, PDFs.

Each tab shows a table of files with **Ticker**, **Form**, **Size**, and
**Age** ("2 hours ago", "Yesterday"). The **⬇ Download** button on each
row downloads that single file.

Tick **Enable multi-select for ZIP download** to add checkboxes — pick
multiple files and the **⬇ Download Selected as ZIP** button at the bottom
bundles them into one ZIP file.

Bottom of the page: storage statistics (number of files + total size by
type, plus a bar chart).

### 📜 Logs

Two sections:
- **Run History** — past pipeline runs with status badges (Success /
  Failed / Running). Toggle **Detail** on any row to see its full output.
  Filter by status, ticker, or date.
- **Live Log Tail** — pick which log to view (`pipeline.log` for backend,
  `streamlit_ui.log` for the web app) and how many lines (50 / 100 / 200
  / 500). Color-coded: green for OK, amber for WARN, red for ERROR.
  Click **⬇ Download full log** to save the entire file.

---

## 6. Common tasks — step by step

### A. I want financial data for one new company (e.g. Tesla)

1. Open the app (see [§4](#4-starting-the-web-app)).
2. Click **🚀 Run Pipeline** in the sidebar.
3. In *Single ticker*, type `TSLA`.
4. Leave the defaults checked (Fetch, Store, Build Excel, Word, PDF).
5. Click **▶ Run Pipeline**.
6. Watch the Live Console. Takes about 30–60 seconds.
7. When the *Files Created* cards appear, click **⬇ Download** on each.
   Or visit the **Downloads** page anytime to grab them later.

### B. I want to see Tesla's income statement without re-downloading

1. Click **📋 Financials** in the sidebar.
2. Pick **TSLA** from the Ticker dropdown.
3. Click the **📈 Income Statement** tab — done. No fetch, no waiting.

### C. I want to add Tesla to my permanent watchlist

1. In the sidebar, find the **Watchlist** section.
2. Type `TSLA` in the *Add Ticker* box.
3. Click **Add**. The app validates the ticker with EDGAR before adding.

Now TSLA shows up everywhere watchlist is referenced, and *Run Whole
Watchlist* will include it.

### D. I want one ZIP file with all 5 watchlist companies' Excel models

1. Click **⬇️ Downloads** in the sidebar.
2. Pick the **📊 Excel Models** tab.
3. Tick **Enable multi-select for ZIP download**.
4. Tick the rows for the 5 companies.
5. Scroll to **Bulk Download** and click **⬇ Download Selected as ZIP**.

### E. I want the report to include AI-written commentary

1. Set your Anthropic API key as an environment variable before launching:

   **Windows PowerShell:**
   ```
   $env:ANTHROPIC_API_KEY = "sk-ant-..."
   ```
   **Mac / Linux:**
   ```
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```

2. Launch the app from the **same** terminal: `bash run_app.sh` (or
   `.\run_app.bat`).
3. On the **Run Pipeline** page, tick **Generate AI Narrative**.
4. Click **▶ Run Pipeline**.

The generated Word/PDF will now have a 600–800 word professional research
note instead of placeholder text.

### F. The data looks outdated — I want fresh filings

1. On **Run Pipeline**, tick the **Force refresh from EDGAR** checkbox.
2. Run the pipeline normally. This bypasses the cache and re-downloads.

---

## 7. Where things are saved

Everything lives under `edgar_pipeline/outputs/`:

| Folder / file | What's inside |
| --- | --- |
| `outputs/db/financials.db` | SQLite database — every filing line item you've fetched. |
| `outputs/excel/` | Excel models. Filenames like `AAPL_10K_20260617.xlsx`. |
| `outputs/reports/` | Word + PDF research reports. `AAPL_10K_20260617.docx` + `.pdf`. |
| `outputs/pipeline.log` | Backend log file. |
| `outputs/streamlit_ui.log` | Web app log file (rotated at 2 MB). |

You can open any Excel file by double-clicking it in Windows Explorer /
Finder. You can also access them via the **Downloads** page in the app.

---

## 8. Command-line usage (optional)

If you prefer the terminal over the web app, you can use the CLI directly.
Make sure your virtual environment is active first.

| Command | What it does |
| --- | --- |
| `python main.py fetch --ticker AAPL --form 10-K --limit 5` | Fetch one ticker's filings into SQLite. |
| `python main.py fetch-all` | Fetch every ticker in the watchlist. |
| `python main.py build --ticker AAPL` | Build the Excel model from already-stored data. |
| `python main.py report --ticker AAPL --format both` | Generate Word + PDF report. |
| `python main.py run --ticker AAPL` | Full pipeline for one ticker. |
| `python main.py run-all` | Full pipeline for the entire watchlist. |
| `python main.py history --ticker AAPL` | Show what's stored for this ticker. |
| `python main.py status` | Summary of database contents. |
| `python main.py schedule` | Run a background scheduler (Monday 7 AM). |

---

## 9. Troubleshooting

### "The browser tab is blank / loading forever"

You probably ran `streamlit run main.py` by mistake. Stop it (Ctrl+C) and
use **`streamlit run app/streamlit_app.py`** instead, or just run the
launcher (`bash run_app.sh` / `.\run_app.bat`).

### "Port 8501 already in use"

Another Streamlit is already running. Either:

- Close the other one, or
- Launch on a different port:
  ```
  PORT=8600 bash run_app.sh
  ```
  (On Windows cmd: `set PORT=8600 && run_app.bat`)

### "streamlit: command not found" or "module not found"

Your virtual environment isn't active. Run:

```
.\secenv\Scripts\Activate.ps1   # Windows PowerShell
secenv\Scripts\activate.bat     # Windows cmd
source secenv/bin/activate      # Mac / Linux
```

Then `pip install -r requirements.txt` again.

### "I see raw HTML like `<div class=...>` on the page"

Hard refresh your browser: **Ctrl + Shift + R** (Windows / Linux) or
**Cmd + Shift + R** (Mac). Streamlit aggressively caches styles.

### "PDF generation failed"

On Windows, PDFs are generated via Microsoft Word. If Word isn't installed
the app falls back to a basic PDF generator (ReportLab). Either way you
still get a PDF — it just looks a little simpler in the fallback case.

### "EDGAR returned an error / connection timed out"

The SEC enforces a rate limit. The app already waits 0.5s between requests
and retries up to 3 times. If you still fail, wait a minute and try again,
or reduce the *Filings per form* slider to a smaller number.

### "I can't add a ticker — it says 'not found on EDGAR'"

The ticker validator looks up the exact symbol. Try:
- Exact uppercase (e.g. `BRK-B`, not `brk.b`).
- For ADRs and foreign companies, sometimes the ticker differs from the
  stock exchange. Check on https://www.sec.gov/cgi-bin/browse-edgar.

### "Where do I see what's happening in the background?"

Open the **📜 Logs** page in the app. Or open
`outputs/streamlit_ui.log` and `outputs/pipeline.log` in a text editor.

For more verbose logs, launch with:
```
EDGAR_UI_LOG_LEVEL=DEBUG bash run_app.sh
```

---

## 10. Configuration

Most settings live in `config.py`. You can edit it with any text editor.

| Setting | Default | What it does |
| --- | --- | --- |
| `WATCHLIST` | `["AAPL", "MSFT", "INFY"]` | The initial set of tracked tickers. |
| `EDGAR_IDENTITY` | `ValueAdd Research / analytics@valueadd.com` | Required by SEC. Update with your own name + email. |
| `FORMS` | `["10-K", "10-Q"]` | Which filing types to fetch by default. |
| `FILING_LIMIT` | `5` | How many recent filings per form. |
| `SEC_RATE_LIMIT_SLEEP` | `0.5s` | Politeness delay between requests. |

After editing `config.py`, restart the app for the changes to take effect.

> Tickers added via the sidebar are stored separately in
> `app/watchlist_overrides.json` and survive restarts. They take effect
> immediately.

---

## 11. How the cache works

The first time you run the pipeline for a ticker, it downloads from EDGAR
(~10 seconds per filing) and stores everything in
`outputs/db/financials.db`.

Every subsequent run **reads from the database** rather than re-downloading.
This means:

- **Building Excel and reports later → no internet needed.**
- **Browsing the Financials and Charts pages → no internet needed.**
- **Switching number formats, periods, or running ratios → instant.**

When you click **▶ Run Pipeline** without ticking *Force refresh*, the
runner first checks how many filings are already stored. If the count
already meets the limit, you'll see this in the live console:

```
[CACHE] Using cached SQLite data: 5 10-K filings already stored for AAPL (limit=5). Skipping fetch.
```

And the pipeline jumps straight to building the Excel and reports —
typically under 5 seconds instead of 30+ seconds.

To force a fresh download, tick **Force refresh from EDGAR**.

---

## 12. Folder structure

```
edgar_pipeline/
│
├── main.py                  ← CLI entry point (click)
├── config.py                ← Watchlist, paths, EDGAR identity, settings
│
├── fetcher.py               ← Downloads filings via edgartools
├── storage.py               ← SQLite read / write
├── processor.py             ← Normalization, summaries, ratios
├── model_builder.py         ← Excel workbook builder (openpyxl)
├── report_writer.py         ← Word + PDF report generator
├── narrative.py             ← Optional Claude AI commentary
├── scheduler.py             ← Weekly Monday-7am runner
│
├── requirements.txt         ← All Python package dependencies
├── run_app.sh               ← Web app launcher (POSIX / Git Bash)
├── run_app.bat              ← Web app launcher (Windows)
│
├── .streamlit/
│   └── config.toml          ← Streamlit theme + server settings
│
├── app/                     ← Streamlit web UI (this layer)
│   ├── streamlit_app.py     ← Landing page (entry)
│   ├── app_utils.py         ← Shared helpers (CSS, watchlist, log tail)
│   ├── pipeline_runner.py   ← Threaded pipeline executor for the UI
│   ├── logging_config.py    ← Centralized UI logging
│   ├── assets/
│   │   └── style.css        ← Custom dark-theme CSS + animations
│   ├── components/
│   │   ├── sidebar.py       ← Sidebar (branding, nav, watchlist, status)
│   │   ├── status_badge.py  ← Animated status pills
│   │   ├── metric_cards.py  ← KPI metric grid
│   │   └── file_table.py    ← File browser with downloads
│   └── pages/
│       ├── 1_Dashboard.py
│       ├── 2_Run_Pipeline.py
│       ├── 3_Financials.py
│       ├── 4_Charts.py
│       ├── 5_Downloads.py
│       └── 6_Logs.py
│
├── outputs/                 ← Auto-created at runtime; gitignored
│   ├── db/
│   │   └── financials.db
│   ├── excel/
│   ├── reports/
│   ├── pipeline.log
│   └── streamlit_ui.log
│
└── secenv/                  ← Virtual environment; gitignored
```

---

## License & credits

- Data source: SEC EDGAR (public, free).
- Built on the [`edgartools`](https://pypi.org/project/edgartools/) library.
- Optional commentary by Anthropic Claude.
- Built by **ValueAdd Research And Analytics Solutions LLP**.
