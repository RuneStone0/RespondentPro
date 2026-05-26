FROM node:24-alpine

WORKDIR /app

# Install production dependencies only
COPY package*.json ./
RUN npm ci --omit=dev

# Copy application source and package.json (version is read at runtime)
COPY src/ ./src/
COPY package.json ./

# Bake the git SHA into the image so /health can report it without needing .git
ARG GIT_SHA=unknown
ENV GIT_SHA=${GIT_SHA}

# data/ is mounted at runtime (contains cookie, config, answers — never baked in)
VOLUME /app/data

EXPOSE 3000

CMD ["node", "src/server.js"]
