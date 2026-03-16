FROM python:3.12-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -r -s /bin/false mcpuser && \
    chown -R mcpuser:mcpuser /app

USER mcpuser

EXPOSE 9000

CMD ["python", "server.py"]
