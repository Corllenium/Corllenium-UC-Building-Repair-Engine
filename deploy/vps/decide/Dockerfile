# Build from the repo root:  docker build -f deploy/vps/decide/Dockerfile -t ucmodelfixer-decide:vps .
# Only the question types (engine/decide) and the service go in; no geometry engine, no data.
FROM python:3.12-slim
WORKDIR /app
COPY deploy/vps/decide/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY engine/__init__.py /app/engine/__init__.py
COPY engine/decide /app/engine/decide
COPY deploy/vps/decide/decide_service /app/decide_service
COPY deploy/vps/decide/schema.sql /app/schema.sql
ENV PYTHONPATH=/app
# No port is published by the compose file: only nginx reaches it, on the internal network.
EXPOSE 8200
CMD ["uvicorn", "decide_service.main:app", "--host", "0.0.0.0", "--port", "8200"]
