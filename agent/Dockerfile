# Osir AI autopilot agent.
# AgentCore Runtime requires linux/arm64 on port 8080: build it with
#   docker buildx build --platform linux/arm64 -t osir-agent .
# Locally (docker compose --profile agent) it runs as the console command worker.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py run_local.py ./
COPY osir_agent ./osir_agent

EXPOSE 8080
CMD ["python", "main.py"]
