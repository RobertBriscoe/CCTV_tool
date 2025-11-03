#!/bin/bash
# ==============================================================================
# CCTV Tool v2 - Stop Script
# ==============================================================================

echo "Stopping CCTV Tool service..."

if systemctl is-active --quiet cctv-tool; then
    systemctl stop cctv-tool
    echo "Service stopped"
else
    # Try to find and kill the process
    PID=$(pgrep -f "CCTV_OperationsTool_Fixed.py")
    if [ -n "$PID" ]; then
        kill $PID
        echo "Process $PID terminated"
    else
        echo "CCTV Tool is not running"
    fi
fi
