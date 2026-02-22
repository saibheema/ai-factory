FROM python:3.11-slim
WORKDIR /app
COPY services/clarification_responder/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/clarification_responder/app ./app
COPY factory ./factory
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8010}"]
