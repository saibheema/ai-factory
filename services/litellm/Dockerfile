FROM python:3.11-slim

WORKDIR /app

COPY services/litellm/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY litellm_config.yaml /app/litellm_config.yaml

EXPOSE 4000
CMD ["litellm", "--port", "4000", "--host", "0.0.0.0", "--config", "/app/litellm_config.yaml"]
