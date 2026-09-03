# BmPriceAgent — LLM-backed price-proposal extraction service.
# Slim image: no ML models, no downloads at boot. poppler-utils provides
# pdftotext for the text layer; scanned PDFs go to Gemini natively.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY skill ./skill

ENV PORT=5002 \
    PYTHONUNBUFFERED=1 \
    LOG_LEVEL=INFO

EXPOSE 5002

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
