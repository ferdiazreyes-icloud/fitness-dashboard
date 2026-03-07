# Health Dashboard

Personal health and fitness dashboard. Consolidates data from Apple Health, Strong App, and Claude Coach training plans into interactive Streamlit visualizations.

**Version:** V1.2 — Functional dashboard with 8 pages
**Status:** Production-ready for Streamlit Cloud
**Data range:** 2018 – present (~8 years of history)

## Implemented Features

- [x] ETL pipeline: Apple Health XML (5 GB) → SQLite → CSVs (65 sec)
- [x] Strong App parser: Excel → normalized CSV
- [x] Training plan integration (Claude Coach CSV)
- [x] Page: Resumen Semanal (KPIs, trends, activity distribution)
- [x] Page: Running Analytics (pace, power, distance, recent runs)
- [x] Page: Fuerza Analytics (weight progression, volume, RPE, HR, personal records)
- [x] Page: Mi Plan (compact weekly training plan viewer with block/circuit support)
- [x] Page: Adherencia (plan vs reality comparison — uses ALL plan days for semáforo)
- [x] Page: Tendencias de Salud (VO2Max, RHR, HRV, sleep, SpO2)
- [x] Page: Composición Corporal (weight, BMI, body fat, lean mass)
- [x] Page: Métricas Acumuladas (lifetime/YTD totals, monthly breakdown)

## Pending

- [ ] Alerts (HRV drop, inactivity)
- [ ] Historical plan accumulation
- [ ] Pipeline automation

## Run Locally

```bash
make run
# or
streamlit run app.py
```

## Run Tests

```bash
make test
# or
python -m pytest tests/ -v
```

## Update Data (weekly)

1. Export Apple Health from iPhone → AirDrop to Mac
2. Export Strong App → save `.xlsx`
3. Generate training plan in Claude Coach → save as `training_plan.csv`
4. Run pipeline:

```bash
python3 scripts/etl_apple_health.py ../apple_health_export/exportar.xml health.db
python3 scripts/export_csvs.py
python3 scripts/parse_strong.py "../Strong YYYYMMDD-YYYYMMDD.xlsx"
cp ../training_plan.csv data/
git add data/ && git commit -m "chore: update data $(date +%Y-%m-%d)" && git push
```

Streamlit Cloud re-deploys automatically in ~2 minutes.

## Project Structure

```
health-dashboard/
├── app.py                  # Streamlit dashboard (8 pages)
├── requirements.txt        # Production dependencies
├── data/                   # CSVs for Streamlit (committed to repo)
├── scripts/                # ETL scripts (run locally only)
│   ├── etl_apple_health.py
│   ├── export_csvs.py
│   └── parse_strong.py
├── tests/                  # Data integrity and parser tests
├── .specify/               # Project documentation
├── .streamlit/             # Streamlit theme config
├── Makefile                # Standard commands
└── README.md               # This file
```
