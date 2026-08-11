FROM python:3.11-slim

WORKDIR /app

# libs de sistema pro opencv headless + OpenMP
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV MPLBACKEND=Agg

# requirements primeiro (cache de layer); o -r do vendor precisa existir no pip time
COPY requirements.txt .
COPY vendor/omrchecker/requirements.txt vendor/omrchecker/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY templates ./templates
COPY vendor ./vendor

ENV OMR_PORT=8000
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
