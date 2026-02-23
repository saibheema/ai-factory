FROM python:3.11-slim
WORKDIR /app
COPY services/hitl_svc/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY factory ./factory
COPY services/hitl_svc/app ./app
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8007}"]
