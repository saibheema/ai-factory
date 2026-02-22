FROM python:3.11-slim
WORKDIR /app
COPY services/chat/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/chat/app ./app
CMD ["sh", "-c", "uvicorn app.app:app --host 0.0.0.0 --port ${PORT:-8001}"]
