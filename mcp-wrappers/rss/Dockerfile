FROM node:22-alpine

RUN apk add --no-cache ca-certificates && update-ca-certificates
RUN npm install -g supergateway rss-reader-mcp

# Patch: disable roots/list callback that causes gateway proxy incompatibility.
# The fastmcp (Node) library auto-requests roots/list from the client on connect.
# When proxied through the FastMCP (Python) gateway, this bidirectional callback
# is unsupported and causes "Not connected" errors + GET stream disconnect loops.
# fastmcp checks rootsConfig.enabled !== false before calling listRoots().
RUN if grep -q 'new FastMCP({' /usr/local/lib/node_modules/rss-reader-mcp/build/index.js; then \
      sed -i 's|new FastMCP({|new FastMCP({ roots: { enabled: false },|' \
        /usr/local/lib/node_modules/rss-reader-mcp/build/index.js; \
      echo "Patched: roots/list disabled"; \
    else \
      echo "WARNING: FastMCP constructor pattern not found — patch skipped"; \
    fi

USER node
EXPOSE 3000

CMD ["supergateway", \
     "--stdio", "rss-mcp", \
     "--outputTransport", "streamableHttp", \
     "--stateful", \
     "--port", "3000", \
     "--healthEndpoint", "/health"]
