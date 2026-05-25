FROM node:24-alpine

WORKDIR /app

# Install production dependencies only
COPY package*.json ./
RUN npm ci --omit=dev

# Copy application source
COPY src/ ./src/

# data/ is mounted at runtime (contains cookie, config, answers — never baked in)
VOLUME /app/data

EXPOSE 3000

CMD ["node", "src/server.js"]
