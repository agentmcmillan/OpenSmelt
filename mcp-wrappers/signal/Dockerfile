FROM node:22-alpine

RUN npm install -g supergateway

WORKDIR /app
# Signal MCP server source must be mounted at /app/signal-mcp
# Set AI_SIGNALS_PATH in .env to point to your ai-signals dist directory

USER node
EXPOSE 3000

CMD ["supergateway", \
     "--stdio", "node /app/signal-mcp/dist/index.js", \
     "--outputTransport", "streamableHttp", \
     "--stateful", \
     "--port", "3000", \
     "--healthEndpoint", "/health"]
