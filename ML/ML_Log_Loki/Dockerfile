
FROM python:3.12-slim

# Metadata
LABEL maintainer="monitoring-ia"
LABEL description="Collecte les logs depuis Loki et génère un dataset CSV pour ML"

WORKDIR /app


COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY Log_collection/log_collector.py .

RUN mkdir -p /app/datasets

ENV LOKI_URL=http://loki:3100
ENV LOKI_QUERY={job="dummy-app"}
ENV LOG_DATASET_PATH=/app/datasets/log_dataset.csv

ENTRYPOINT ["python", "log_collector.py"]
CMD ["--mode", "stream", "--interval", "60"]
