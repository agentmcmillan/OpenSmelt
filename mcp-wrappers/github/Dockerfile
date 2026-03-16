FROM node:22-alpine

RUN npm install -g supergateway @modelcontextprotocol/server-github

USER node
EXPOSE 3000

CMD sh -c 'if [ -z "$GITHUB_PERSONAL_ACCESS_TOKEN" ]; then echo "GITHUB_PERSONAL_ACCESS_TOKEN not set, sleeping"; sleep infinity; else exec supergateway --stdio "npx @modelcontextprotocol/server-github" --outputTransport streamableHttp --stateful --port 3000 --healthEndpoint /health; fi'
