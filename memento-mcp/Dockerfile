FROM node:22-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY . .

RUN mkdir -p /var/log/mcp

EXPOSE 56332

HEALTHCHECK --interval=15s --timeout=10s --start-period=60s --retries=5 \
    CMD node -e "const http=require('http');http.get('http://localhost:56332/health',r=>{process.exit(r.statusCode===200?0:1)}).on('error',()=>process.exit(1))"

CMD ["node", "server.js"]
