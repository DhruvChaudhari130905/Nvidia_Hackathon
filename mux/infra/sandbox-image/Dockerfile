# Starter image for Nebius sandboxes: Node, the starter template's packages, and the mux-report script.
#
# Build from the mux/ directory (the context needs templates/ and infra/):
#   docker build -f infra/sandbox-image/Dockerfile -t mux-starter .
#
# Only the packages are baked in. The backend uploads every room file (the template is checkpoint C0) into
# /app for each run, so a file deleted in the room is not left behind in the image.
FROM node:20-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# PROJECT_DIR in mux/server/mux/sandbox/runner.py
WORKDIR /app

# The approved packages (templates/fullstack-starter/approved-packages.json); the coder cannot install others
COPY templates/fullstack-starter/package.json templates/fullstack-starter/package-lock.json ./
RUN npm ci --no-audit --no-fund && npm cache clean --force

# Runs the build or the tests and prints the short report the backend parses
COPY infra/sandbox-image/mux-report.mjs /usr/local/bin/mux-report
RUN chmod 755 /usr/local/bin/mux-report

# tsc, vite and vitest from the project's packages
ENV PATH=/app/node_modules/.bin:$PATH \
    NODE_ENV=development

RUN chown -R node:node /app
USER node

# Keep the container alive; the backend runs commands in it
CMD ["sleep", "infinity"]
