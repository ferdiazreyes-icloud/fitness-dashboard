.PHONY: run test lint update

run:
	streamlit run app.py

test:
	python -m pytest tests/ -v

lint:
	python -m py_compile app.py
	python -m py_compile scripts/etl_apple_health.py
	python -m py_compile scripts/export_csvs.py
	python -m py_compile scripts/parse_strong.py

update:
	@echo "Weekly data update pipeline:"
	@echo "1. python3 scripts/etl_apple_health.py ../apple_health_export/exportar.xml health.db"
	@echo "2. python3 scripts/export_csvs.py"
	@echo "3. python3 scripts/parse_strong.py '../Strong YYYYMMDD-YYYYMMDD.xlsx'"
	@echo "4. cp ../training_plan.csv data/"
	@echo "5. git add data/ && git commit -m 'chore: update data' && git push"
