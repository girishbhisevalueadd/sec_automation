# sec_automation

Fully automated SEC EDGAR financial data pipeline. Pulls 10-K / 10-Q filings via the free [`edgartools`](https://pypi.org/project/edgartools/) library, stores history in SQLite, and emits styled Excel workbooks plus Word / PDF research reports — with an optional Claude API integration for narrative commentary.

The full application lives in [`edgar_pipeline/`](./edgar_pipeline). See [`edgar_pipeline/README.md`](./edgar_pipeline/README.md) for the complete docs, CLI reference, and setup instructions.

## Quick start

```bash
cd edgar_pipeline
python -m venv secenv
secenv\Scripts\activate           # Windows
# source secenv/bin/activate      # macOS / Linux
pip install -r requirements.txt
python main.py run --ticker MSFT
```

Outputs land in `edgar_pipeline/outputs/`:

- `excel/`   — styled multi-sheet Excel models (Income, Balance, Cash Flow, Debt, Ratios)
- `reports/` — Word + PDF research reports
- `db/`      — SQLite history of every filing fetched

## Folder layout

```
sec_automation/
├── .gitignore
├── README.md
└── edgar_pipeline/
    ├── main.py             # click-based CLI
    ├── config.py           # WATCHLIST, EDGAR_IDENTITY, paths
    ├── fetcher.py          # edgartools data pull
    ├── storage.py          # SQLite read/write
    ├── processor.py        # normalization + ratios
    ├── model_builder.py    # openpyxl Excel builder
    ├── report_writer.py    # python-docx + PDF
    ├── narrative.py        # optional Claude commentary
    ├── scheduler.py        # weekly scheduler
    ├── requirements.txt
    └── README.md
```
