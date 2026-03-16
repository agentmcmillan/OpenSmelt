FROM python:3.12-slim

# Install Node.js, supergateway, Docker CLI, and gosu in minimal layers
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl gnupg gosu && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g supergateway && \
    pip install --no-cache-dir uv && \
    rm -rf /var/lib/apt/lists/*

# Install Docker CLI (required by python-on-whales used by docker-mcp)
RUN ARCH=$(uname -m) && \
    curl -fsSL "https://download.docker.com/linux/static/stable/${ARCH}/docker-27.5.1.tgz" | \
    tar xz --strip-components=1 -C /usr/local/bin docker/docker

# Create non-root user with writable cache
RUN useradd -r -m -s /bin/false mcpuser && \
    mkdir -p /home/mcpuser/.cache/uv && \
    chown -R mcpuser:mcpuser /home/mcpuser

# Entrypoint: detect docker socket GID and add mcpuser to matching group
RUN printf '#!/bin/sh\n\
if [ -S /var/run/docker.sock ]; then\n\
  SOCK_GID=$(stat -c "%%g" /var/run/docker.sock)\n\
  if ! getent group "$SOCK_GID" >/dev/null 2>&1; then\n\
    groupadd -g "$SOCK_GID" dockerhost\n\
  fi\n\
  GRP=$(getent group "$SOCK_GID" | cut -d: -f1)\n\
  usermod -aG "$GRP" mcpuser\n\
fi\n\
exec gosu mcpuser "$@"\n' > /usr/local/bin/entrypoint.sh && \
    chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 3000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# docker-mcp needs Docker socket access (mounted via docker-compose as :ro)
CMD ["supergateway", \
     "--stdio", "uvx docker-mcp", \
     "--outputTransport", "streamableHttp", \
     "--stateful", \
     "--port", "3000", \
     "--healthEndpoint", "/health"]
