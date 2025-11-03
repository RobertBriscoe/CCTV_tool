#!/bin/bash
# ==============================================================================
# CCTV Tool v2 - Installation Script for Red Hat/CentOS
# ==============================================================================

set -e

echo "=========================================="
echo "CCTV Tool v2 - Installation"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run as root"
    exit 1
fi

INSTALL_DIR="/var/cctv-tool-v2"
VENV_DIR="$INSTALL_DIR/venv"

echo ""
echo "Step 1: Installing system dependencies..."
yum install -y python3 python3-pip python3-devel gcc unixODBC unixODBC-devel

# Install Microsoft ODBC Driver 17 for SQL Server (if not already installed)
if ! odbcinst -q -d -n "ODBC Driver 17 for SQL Server" > /dev/null 2>&1; then
    echo "Installing Microsoft ODBC Driver 17 for SQL Server..."
    curl https://packages.microsoft.com/config/rhel/8/prod.repo > /etc/yum.repos.d/mssql-release.repo
    ACCEPT_EULA=Y yum install -y msodbcsql17
else
    echo "ODBC Driver 17 already installed"
fi

echo ""
echo "Step 2: Creating virtual environment..."
cd "$INSTALL_DIR"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv venv
fi

echo ""
echo "Step 3: Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Step 4: Creating necessary directories..."
mkdir -p logs snapshots /var/cctv-snapshots /mnt/shared/cctv-snapshots

echo ""
echo "Step 5: Setting permissions..."
chmod 600 .env
chmod +x *.sh

echo ""
echo "Step 6: Installing systemd service..."
cp cctv-tool.service /etc/systemd/system/
systemctl daemon-reload

echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env file with your credentials"
echo "2. Test the application: ./start.sh"
echo "3. Enable auto-start: systemctl enable cctv-tool"
echo "4. Start service: systemctl start cctv-tool"
echo "5. Check status: systemctl status cctv-tool"
echo ""
