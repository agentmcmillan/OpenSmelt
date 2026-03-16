FROM node:22-alpine

RUN npm install -g supergateway mcp-ssh-manager

USER node
EXPOSE 3000

# The mcp-ssh-manager stdio server is the node module's index.js
CMD ["supergateway", \
     "--stdio", "node /usr/local/lib/node_modules/mcp-ssh-manager/src/index.js", \
     "--outputTransport", "streamableHttp", \
     "--stateful", \
     "--port", "3000", \
     "--healthEndpoint", "/health"]
