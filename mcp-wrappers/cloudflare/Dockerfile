FROM node:22-alpine

RUN npm install -g supergateway @cloudflare/mcp-server-cloudflare

USER node
EXPOSE 3000

CMD ["supergateway", \
     "--stdio", "npx @cloudflare/mcp-server-cloudflare", \
     "--outputTransport", "streamableHttp", \
     "--stateful", \
     "--port", "3000", \
     "--healthEndpoint", "/health"]
