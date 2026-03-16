FROM node:22-alpine

RUN npm install -g supergateway @modelcontextprotocol/server-github

USER node
EXPOSE 3000

CMD ["supergateway", \
     "--stdio", "npx @modelcontextprotocol/server-github", \
     "--outputTransport", "streamableHttp", \
     "--stateful", \
     "--port", "3000", \
     "--healthEndpoint", "/health"]
