.PHONY: all data land dbt eval labels test app
all: data dbt eval labels test
data:
	python -m src.fetch_weather
	python -m src.synth_sensors
land:
	python -m src.land --reset
dbt: land
	python -m src.warehouse build
eval:
	python -m src.evaluate_pipeline
labels:
	python -m src.evaluate_labels
test:
	pytest -q
app:
	streamlit run app/streamlit_app.py
