FROM python:3.11-slim
WORKDIR /app
COPY services/groupchat/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY factory ./factory
COPY services/groupchat/app ./app
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8002}"]
