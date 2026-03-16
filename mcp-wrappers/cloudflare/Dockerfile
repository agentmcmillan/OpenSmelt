FROM node:22-alpine

RUN npm install -g supergateway @cloudflare/mcp-server-cloudflare

USER node
EXPOSE 3000

# CLOUDFLARE_ACCOUNT_ID must be set via docker-compose environment
CMD sh -c 'if [ -z "$CLOUDFLARE_ACCOUNT_ID" ]; then echo "CLOUDFLARE_ACCOUNT_ID not set, sleeping"; sleep infinity; else exec supergateway --stdio "npx @cloudflare/mcp-server-cloudflare run ${CLOUDFLARE_ACCOUNT_ID}" --outputTransport streamableHttp --stateful --port 3000 --healthEndpoint /health; fi'
