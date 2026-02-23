FROM python:3.11-slim
WORKDIR /app
COPY services/memory_svc/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY factory ./factory
COPY services/memory_svc/app ./app
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8008}"]
