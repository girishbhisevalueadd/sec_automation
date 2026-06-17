# edgar_pipeline

Fully automated SEC EDGAR financial data pipeline. Pulls 10-K / 10-Q filings via the free [`edgartools`](https://pypi.org/project/edgartools/) library, stores history in SQLite, and emits styled Excel workbooks plus Word / PDF research reports. No paid APIs required (Anthropic API key is optional for narrative commentary).

## Install

```bash
python -m venv secenv
secenv\Scripts\activate         # Windows
# source secenv/bin/activate    # macOS / Linux

pip install -r requirements.txt
```

## Quick start (zero -> Excel model in 3 commands)

```bash
python main.py fetch --ticker MSFT --form 10-K --limit 5
python main.py build --ticker MSFT
python main.py report --ticker MSFT --format both
```

Or run the entire pipeline in one go:

```bash
python main.py run --ticker MSFT
```

Outputs land in `outputs/excel/`, `outputs/reports/`, and `outputs/db/financials.db`.

## CLI command reference

| Command                                                  | What it does                                                |
| -------------------------------------------------------- | ----------------------------------------------------------- |
| `python main.py fetch --ticker X --form 10-K --limit 5`  | Fetch and store filings for one ticker                      |
| `python main.py fetch-all`                               | Fetch every ticker in `WATCHLIST` for every form            |
| `python main.py build --ticker X`                        | Build Excel model from stored data                          |
| `python main.py report --ticker X --format word\|pdf\|both` | Generate Word and/or PDF research report                    |
| `python main.py run --ticker X`                          | Full pipeline: fetch -> store -> Excel -> report            |
| `python main.py run-all`                                 | Full pipeline for the entire watchlist                      |
| `python main.py history --ticker X`                      | Show filing history stored in SQLite                        |
| `python main.py status`                                  | Show DB contents and output file counts                     |
| `python main.py schedule`                                | Start the weekly scheduler (Mon 07:00 local time)           |

All commands log to console **and** to `outputs/pipeline.log`.

## Configuration

Edit [`config.py`](./config.py):

- `WATCHLIST` — list of tickers processed by `fetch-all` / `run-all`. Default: `["AAPL", "MSFT", "INFY"]`.
- `EDGAR_IDENTITY` — name + email sent in the SEC User-Agent header. **The SEC requires this** — update it to your own identity. The pipeline calls `set_identity()` from `edgartools` automatically before any request.
- `FORMS` — filing types to fetch (default `["10-K", "10-Q"]`).
- `FILING_LIMIT` — number of recent filings per form (default `5`).

## SEC rate limits

The SEC enforces 10 requests/sec per identity. The pipeline:

- Calls `set_identity()` once before any `Company()` call (required).
- Sleeps `0.5s` between filings (`SEC_RATE_LIMIT_SLEEP` in `config.py`).
- Retries network errors up to 3 times with a 5s backoff.

## Optional: Claude narrative commentary

If you set `ANTHROPIC_API_KEY`, the report generator calls Claude (`claude-sonnet-4-6`) to produce a 600–800 word research note with the standard sections (Executive Summary, Revenue Trend, Margins, Balance Sheet, Cash Flow, Risks, Outlook). Without an API key it falls back to placeholder text.

```bash
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# bash / zsh
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Folder structure

```
edgar_pipeline/
├── main.py             # click-based CLI entry point
├── config.py           # watchlist, paths, SEC identity, styling
├── fetcher.py          # edgartools data pull + XBRL debt facts
├── storage.py          # SQLite read/write
├── processor.py        # normalization, summary tables, ratios
├── model_builder.py    # openpyxl multi-sheet Excel workbook
├── report_writer.py    # python-docx Word report + PDF converter
├── narrative.py        # Claude-powered narrative (optional)
├── scheduler.py        # weekly schedule runner
├── requirements.txt
├── README.md
└── outputs/            # auto-created at runtime
    ├── excel/          # TICKER_FORM_YYYYMMDD.xlsx
    ├── reports/        # TICKER_FORM_YYYYMMDD.docx / .pdf
    ├── db/financials.db
    └── pipeline.log
```

## PDF generation notes

PDFs are produced either via `docx2pdf` (uses MS Word on Windows / LibreOffice elsewhere) or via a `reportlab` fallback that re-renders the `.docx`. On Windows the `docx2pdf` path requires Microsoft Word installed. If neither is available, generation falls through to the ReportLab path which always works.

> The original spec mentioned WeasyPrint. We opted for `docx2pdf` + ReportLab on Windows because WeasyPrint needs the GTK runtime, which makes onboarding fragile. The fallback chain delivers the same PDF deliverable without that system dependency.
