#!/bin/bash
# ==============================================================================
# CCTV Tool v2 - Manual Start Script
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "CCTV Tool v2 - Starting"
echo "=========================================="

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found!"
    echo "Please copy .env.example to .env and configure it"
    exit 1
fi

# Activate virtual environment
if [ ! -d "venv" ]; then
    echo "ERROR: Virtual environment not found!"
    echo "Please run ./install.sh first"
    exit 1
fi

source venv/bin/activate

# Start the application
echo "Starting CCTV Tool..."
echo "Access the API at: http://$(hostname -I | awk '{print $1}'):8080"
echo "Press Ctrl+C to stop"
echo ""

python3 CCTV_OperationsTool_Fixed.py
