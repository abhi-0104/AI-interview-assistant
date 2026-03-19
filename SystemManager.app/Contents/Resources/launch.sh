#!/bin/bash
# True background launch script called by AppleScript bundle
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
LOG="$SCRIPT_DIR/.launcher.log"

echo "[$(date)] AppleScript triggered bash launcher" >> "$LOG"

PYTHON="$SCRIPT_DIR/venv/bin/SystemManagementService"
if [ ! -f "$PYTHON" ]; then
    echo "[$(date)] ERROR: $PYTHON not found" >> "$LOG"
    exit 1
fi



echo "[$(date)] Starting SystemManagementService..." >> "$LOG"

# Using nohup and disown to completely detatch from the AppleScript parent
nohup "$PYTHON" -u "$SCRIPT_DIR/syssvc.py" </dev/null >>"$LOG" 2>&1 &
disown
