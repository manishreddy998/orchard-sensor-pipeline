# Dashboard image for Cloud Run. Build after `make all` so data/orchard.duckdb and results/ exist.
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8080
CMD streamlit run app/streamlit_app.py --server.port $PORT --server.address 0.0.0.0
