FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ship the non-sensitive config with the image. Secrets are injected at
# runtime as environment variables (see docker-compose.yml / credentials.env),
# so credentials.env is intentionally NOT copied into the image.
COPY config.yaml ./config.yaml
COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
