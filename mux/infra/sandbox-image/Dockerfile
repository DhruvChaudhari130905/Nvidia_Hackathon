# Starter image for Nebius sandboxes: Node, the full-stack template, and the approved packages preinstalled.
FROM node:20-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# TODO: copy the full-stack template and preinstall the approved packages, e.g.
#   COPY template/ /workspace/
#   RUN npm ci

# Run as the unprivileged user that ships with the node image
RUN chown node:node /workspace
USER node

# Keep the container alive; the backend execs commands into it
CMD ["sleep", "infinity"]
