# Plan: Health Dashboard — Technical Architecture

## Stack

- **Language:** Python 3.10+
- **Dashboard:** Streamlit
- **Data processing:** Pandas
- **Visualization:** Plotly Express + Plotly Graph Objects
- **ETL:** SAX streaming XML parser (for Apple Health), openpyxl (for Strong .xlsx)
- **Storage:** Flat CSV files (no database in production)
- **Deploy:** Streamlit Cloud (auto-deploy on push to main)

## Architecture

```
Apple Health (XML 5GB)    Strong App (.xlsx)     Claude Coach (chat)
     ↓                         ↓                       ↓
etl_apple_health.py       parse_strong.py         training_plan.csv
     ↓                         ↓                       ↓
   health.db              strong_log.csv                |
     ↓                         ↓                       ↓
export_csvs.py ─────────────── + ──────────────────── + ──→ data/
                                                              ↓
                                                         GitHub repo (private)
                                                              ↓
                                                      Streamlit Cloud
```

## Data Pipeline

1. `scripts/etl_apple_health.py` — Parses 5 GB XML using SAX streaming into SQLite (65 sec). Creates 8 tables with deduplication and source priority.
2. `scripts/export_csvs.py` — Exports SQLite → 8 CSVs (~1 MB total) for Streamlit Cloud.
3. `scripts/parse_strong.py` — Parses Strong .xlsx → `strong_log.csv` with normalized columns.

## Why no Docker

Streamlit Cloud manages the full runtime (Python install, dependency install, server). ETL scripts run locally on Mac. There are no external services (no PostgreSQL, no Redis, no APIs). Docker would add complexity without benefit.

## Why no .env

No environment variables are needed. Streamlit Cloud runs the app directly from repo files. If API tokens are needed in the future, `.env.example` will be created at that time.

## Weekly Update Flow

```
MANUAL (every Sunday):
1. iPhone: Settings > Health > Export All Health Data → AirDrop to Mac
2. Strong App: Export data → save .xlsx
3. Claude Coach: Generate weekly plan → save as training_plan.csv

PIPELINE (terminal):
cd health-dashboard
python3 scripts/etl_apple_health.py ../apple_health_export/exportar.xml health.db
python3 scripts/export_csvs.py
python3 scripts/parse_strong.py "../Strong YYYYMMDD-YYYYMMDD.xlsx"
cp ../training_plan.csv data/
git add data/ && git commit -m "chore: update data $(date +%Y-%m-%d)" && git push

AUTOMATIC:
Streamlit Cloud re-deploys in ~2 min after detecting push
```
