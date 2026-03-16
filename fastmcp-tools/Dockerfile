FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -r -s /bin/false mcpuser && \
    mkdir -p /app/data && \
    chown -R mcpuser:mcpuser /app

USER mcpuser

EXPOSE 8090

CMD ["python", "server.py"]
