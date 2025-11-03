# FDOT CCTV Operations Tool v2

A production-ready Flask application for managing FDOT District 3 CCTV cameras with reboot capabilities, snapshot capture, MIMS ticket integration, and email notifications.

## Features

- **Camera Management**: Manage 285+ CCTV cameras across FDOT District 3
- **Remote Reboot**: ONVIF-based camera reboots with automatic MIMS ticket creation
- **Snapshot Capture**: Multi-camera snapshot capture with configurable duration and intervals
- **MIMS Integration**: Automatic trouble ticket creation for maintenance tracking
- **Email Notifications**: Automated notifications to maintenance team and stakeholders
- **Health Monitoring**: Comprehensive health checks for LibreNMS integration
- **24/7 Operation**: Systemd service for reliable continuous operation

## System Requirements

- **OS**: Red Hat Enterprise Linux 8+ / CentOS 8+
- **Python**: 3.9+
- **Database**: Microsoft SQL Server (ODBC Driver 17)
- **Network**: Internal network access to cameras and MIMS API
- **Storage**: Minimum 50GB for snapshots

## Quick Start

### 1. Installation

```bash
cd /var/cctv-tool-v2
sudo ./install.sh
```

This will:
- Install system dependencies (Python, ODBC drivers)
- Create Python virtual environment
- Install Python packages
- Set up systemd service
- Create necessary directories

### 2. Configuration

Edit the `.env` file with your credentials:

```bash
nano .env
```

**Required settings:**
- `DB_SERVER`, `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD` - Database connection
- `SMTP_USERNAME`, `SMTP_PASSWORD` - Email credentials
- `MIMS_USERNAME`, `MIMS_PASSWORD` or `MIMS_TOKEN` - MIMS API access
- `CAMERA_DEFAULT_USERNAME`, `CAMERA_DEFAULT_PASSWORD` - Camera credentials
- `MAINTENANCE_EMAILS`, `STAKEHOLDER_EMAILS` - Email recipients

**See `.env.example` for all available options.**

### 3. Start the Service

**Option A: Manual start (for testing)**
```bash
./start.sh
```

**Option B: Systemd service (for production)**
```bash
sudo systemctl enable cctv-tool
sudo systemctl start cctv-tool
```

### 4. Verify Installation

```bash
./status.sh
```

Or check the health endpoint:
```bash
curl http://localhost:8080/api/health
```

## API Endpoints

### Health & Status

- `GET /api/health` - Comprehensive health check (for LibreNMS)
- `GET /api/metrics` - Metrics endpoint
- `GET /api/config` - Current configuration (no secrets)

### Camera Operations

- `GET /api/cameras/list` - List all configured cameras (285 total)
- `POST /api/camera/reboot` - Reboot a camera with MIMS ticket
- `POST /api/camera/snapshots` - Capture snapshots from cameras
- `GET /api/sessions/list` - List active snapshot sessions

### Example: Reboot Camera

```bash
curl -X POST http://localhost:8080/api/camera/reboot \
  -H "Content-Type: application/json" \
  -d '{
    "camera_ip": "10.164.244.149",
    "camera_name": "CCTV-I10-000.6-EB",
    "operator": "John Doe",
    "reason": "Camera not responding"
  }'
```

### Example: Capture Snapshots

```bash
curl -X POST http://localhost:8080/api/camera/snapshots \
  -H "Content-Type: application/json" \
  -d '{
    "camera_ips": ["10.164.244.149", "10.164.244.20"],
    "duration": 3600,
    "interval": 300,
    "operator": "John Doe"
  }'
```

## Service Management

### Start/Stop/Restart

```bash
sudo systemctl start cctv-tool    # Start service
sudo systemctl stop cctv-tool     # Stop service
sudo systemctl restart cctv-tool  # Restart service
sudo systemctl status cctv-tool   # Check status
```

### View Logs

```bash
# Systemd journal logs
sudo journalctl -u cctv-tool -f

# Application logs
tail -f logs/cctv_ops_*.log
```

### Enable Auto-Start on Boot

```bash
sudo systemctl enable cctv-tool
```

## LibreNMS Monitoring Setup

### HTTP Check Configuration

1. Add HTTP check in LibreNMS:
   - URL: `http://10.175.253.33:8080/api/health`
   - Method: GET
   - Expected Status: 200
   - Check Interval: 60 seconds

2. Alert on status code 503 (degraded health)

### Health Check Indicators

The `/api/health` endpoint monitors:
- ✅ MIMS API connectivity
- ✅ ONVIF availability
- ✅ Database connectivity
- ✅ Disk space (alerts if < 5GB free)
- ✅ Camera configuration loaded
- ✅ Email service status

**Response when healthy (200):**
```json
{
  "status": "healthy",
  "timestamp": "2025-11-03T10:00:00",
  "version": "6.0",
  "services": {
    "mims_available": true,
    "mims_authenticated": true,
    "onvif_available": true,
    "opencv_available": true,
    "email_enabled": true
  },
  "cameras": {
    "total_cameras": 285,
    "config_loaded": true
  },
  "database": {
    "connected": true,
    "server": "SG-8-Test-SQL",
    "database": "FDOT_CCTV_System"
  },
  "storage": {
    "path": "/var/cctv-snapshots",
    "free_gb": 45.2,
    "total_gb": 50.0,
    "used_percent": 9.6
  }
}
```

**Response when degraded (503):**
```json
{
  "status": "degraded",
  "issues": [
    "Database connection failed: timeout",
    "Low disk space: 3.2 GB free"
  ],
  ...
}
```

## Directory Structure

```
/var/cctv-tool-v2/
├── CCTV_OperationsTool_Fixed.py  # Main application
├── mims_client.py                # MIMS API client
├── scheduler_init.py             # Scheduler and utilities
├── camera_config.json            # Camera definitions (no secrets)
├── .env                          # Environment variables (secrets)
├── .env.example                  # Configuration template
├── requirements.txt              # Python dependencies
├── cctv-tool.service            # Systemd service file
├── install.sh                    # Installation script
├── start.sh                      # Manual start script
├── stop.sh                       # Stop script
├── status.sh                     # Status check script
├── logs/                         # Application logs
├── snapshots/                    # Temporary snapshot storage
└── venv/                         # Python virtual environment
```

## Troubleshooting

### Service Won't Start

1. Check logs:
   ```bash
   sudo journalctl -u cctv-tool -n 50
   ```

2. Verify .env configuration:
   ```bash
   grep -v "^#" .env | grep -v "^$"
   ```

3. Test database connection:
   ```bash
   source venv/bin/activate
   python3 -c "import pyodbc; print(pyodbc.drivers())"
   ```

### Database Connection Issues

- Verify ODBC Driver 17 is installed:
  ```bash
  odbcinst -q -d
  ```

- Test SQL Server connectivity:
  ```bash
  sqlcmd -S SG-8-Test-SQL -U RTMCSNAP -P 'SunGuide1!' -Q "SELECT @@VERSION"
  ```

### Port 8080 Already in Use

- Find process using port:
  ```bash
  sudo lsof -i :8080
  ```

- Change port in `.env`:
  ```bash
  FLASK_PORT=8081
  ```

### Camera Reboot Fails

- Verify ONVIF availability:
  ```bash
  curl http://localhost:8080/api/health | grep onvif
  ```

- Check camera credentials in `.env`
- Verify camera IP is reachable:
  ```bash
  ping 10.164.244.149
  ```

### Low Disk Space Warnings

- Check current usage:
  ```bash
  df -h /var/cctv-snapshots
  ```

- Clean old snapshots:
  ```bash
  find /var/cctv-snapshots -type f -mtime +7 -delete
  ```

- Increase `MAX_STORAGE_GB` in `.env`

## Security Considerations

### Internal Network Only

This application is designed for internal network use behind a firewall:
- No HTTPS required (but recommended with internal CA)
- Basic authentication can be added via API keys
- All secrets stored in `.env` (never commit to git)

### File Permissions

```bash
chmod 600 .env                    # Secrets file
chmod 755 *.sh                    # Scripts
chmod 644 camera_config.json      # Camera metadata (no secrets)
```

### Backup Recommendations

1. **Configuration**: Backup `.env` file securely
2. **Camera List**: Backup `camera_config.json`
3. **Database**: Regular SQL Server backups
4. **Snapshots**: Archive to network storage

## Maintenance

### Update Python Dependencies

```bash
source venv/bin/activate
pip install --upgrade -r requirements.txt
sudo systemctl restart cctv-tool
```

### Add New Cameras

1. Edit `camera_config.json`:
   ```json
   "CCTV_NEW_CAMERA": {
       "name": "CCTV-I10-999.9-EB",
       "ip": "10.164.244.999",
       "reboot_url": "/api/reboot",
       "snapshot_url": "/api/snapshot"
   }
   ```

2. Restart service:
   ```bash
   sudo systemctl restart cctv-tool
   ```

### Log Rotation

Logs are stored in `logs/cctv_ops_YYYYMMDD.log`

To set up automatic rotation:
```bash
sudo nano /etc/logrotate.d/cctv-tool
```

Add:
```
/var/cctv-tool-v2/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    missingok
}
```

## Support & Contact

- **Maintenance Team**: D3-TMCMaint@dot.state.fl.us
- **Operations**: D3-NWFSGsuper@dot.state.fl.us
- **Vendor Support**: Robert.briscoe@transcore.com

## Version History

- **v6.0** (2025-11-03) - Production release
  - Environment variable configuration
  - Security hardening (removed hardcoded credentials)
  - Enhanced health checks for LibreNMS
  - Systemd service for 24/7 operation
  - Database integration for snapshot scheduling
  - 285 camera support

## License

Copyright © 2025 FDOT District 3. Internal use only.
