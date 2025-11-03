#!/bin/bash
# ==============================================================================
# CCTV Tool v2 - Status Check Script
# ==============================================================================

echo "=========================================="
echo "CCTV Tool v2 - Status"
echo "=========================================="
echo ""

# Check systemd service status
if systemctl list-unit-files | grep -q cctv-tool.service; then
    echo "Systemd Service Status:"
    systemctl status cctv-tool --no-pager
    echo ""
fi

# Check if process is running
PID=$(pgrep -f "CCTV_OperationsTool_Fixed.py")
if [ -n "$PID" ]; then
    echo "Process: Running (PID: $PID)"
else
    echo "Process: Not running"
fi

echo ""

# Check port 8080
if netstat -tln 2>/dev/null | grep -q ":8080 "; then
    echo "Port 8080: Listening"
elif ss -tln 2>/dev/null | grep -q ":8080 "; then
    echo "Port 8080: Listening"
else
    echo "Port 8080: Not listening"
fi

echo ""

# Test health endpoint
if command -v curl > /dev/null; then
    echo "Health Check:"
    curl -s http://localhost:8080/api/health | python3 -m json.tool 2>/dev/null || echo "  Not responding"
fi

echo ""
echo "=========================================="
