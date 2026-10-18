FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-inference.txt ./

RUN pip install --no-cache-dir -r requirements-inference.txt \
    && pip check

COPY src/anomaly_detection/run_cloud_batch_inference.py ./run_cloud_batch_inference.py

RUN python -c "import run_cloud_batch_inference"

CMD ["python", "/app/run_cloud_batch_inference.py"]