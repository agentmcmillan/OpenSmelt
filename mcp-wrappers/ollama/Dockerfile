FROM node:22-alpine

RUN npm install -g supergateway ollama-mcp

USER node
EXPOSE 3000

CMD ["supergateway", \
     "--stdio", "npx ollama-mcp", \
     "--outputTransport", "streamableHttp", \
     "--stateful", \
     "--port", "3000", \
     "--healthEndpoint", "/health"]
