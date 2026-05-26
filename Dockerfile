FROM node:24-alpine

WORKDIR /app

# Install production dependencies only
COPY package*.json ./
RUN npm ci --omit=dev

# Copy application source
COPY src/ ./src/

# Bake the git SHA at build time so /health can report it
ARG GIT_SHA=unknown
ENV GIT_SHA=${GIT_SHA}

# data/ is mounted at runtime (contains cookie, config, answers — never baked in)
VOLUME /app/data

EXPOSE 3000

CMD ["node", "src/server.js"]
