#!/bin/bash
set -e

# oncell runtime entrypoint
# Detects whether the agent is Python or TypeScript and starts the runtime.

AGENT_DIR="${ONCELL_AGENT_DIR:-/app}"
CELL_ID="${ONCELL_CELL_ID:-default}"
PORT="${ONCELL_PORT:-8080}"
CELLS_DIR="${ONCELL_CELLS_DIR:-/cells}"

# Detect agent language
if [ -f "$AGENT_DIR/agent.py" ]; then
    echo "detected Python agent"

    # Install deps if requirements.txt exists
    if [ -f "$AGENT_DIR/requirements.txt" ]; then
        pip install --quiet -r "$AGENT_DIR/requirements.txt"
    fi

    exec python -m oncell.runtime \
        --agent "$AGENT_DIR/agent.py" \
        --cell-id "$CELL_ID" \
        --port "$PORT" \
        --cells-dir "$CELLS_DIR"

elif [ -f "$AGENT_DIR/agent.ts" ]; then
    echo "detected TypeScript agent"

    # Install deps if package.json exists
    if [ -f "$AGENT_DIR/package.json" ]; then
        cd "$AGENT_DIR" && npm install --quiet 2>/dev/null
    fi

    exec npx tsx /usr/local/lib/oncell/runtime.ts \
        --agent "$AGENT_DIR/agent.ts" \
        --cell-id "$CELL_ID" \
        --port "$PORT" \
        --cells-dir "$CELLS_DIR"

else
    echo "error: no agent.py or agent.ts found in $AGENT_DIR"
    exit 1
fi
