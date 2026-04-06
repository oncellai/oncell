# oncell/runtime — base image for agent cells
# Python 3.12 + Node.js 22 + oncell SDK + common tools

FROM python:3.12-slim AS base

# Install Node.js 22
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git build-essential && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install tsx globally for TypeScript runtime
RUN npm install -g tsx

# Install Python oncell SDK
COPY python/ /tmp/oncell-python/
RUN pip install --no-cache-dir /tmp/oncell-python/ && rm -rf /tmp/oncell-python/

# Install TypeScript oncell SDK
COPY typescript/ /tmp/oncell-ts/
RUN cd /tmp/oncell-ts && npm install && npm run build && \
    mkdir -p /usr/local/lib/oncell && \
    cp -r dist/* /usr/local/lib/oncell/ && \
    cp src/runtime.ts /usr/local/lib/oncell/ && \
    rm -rf /tmp/oncell-ts

# Copy entrypoint
COPY runtime/entrypoint.sh /usr/local/bin/oncell-entrypoint
RUN chmod +x /usr/local/bin/oncell-entrypoint

# Cell directories (mounted from NVMe by Host Agent)
RUN mkdir -p /cells /app

WORKDIR /app
EXPOSE 8080

ENTRYPOINT ["oncell-entrypoint"]
