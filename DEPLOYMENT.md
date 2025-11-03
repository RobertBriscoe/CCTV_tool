# CCTV Tool v2 - Production Deployment Guide

## Pre-Deployment Checklist

### Server Requirements
- [ ] Red Hat Enterprise Linux 8+ or CentOS 8+ installed
- [ ] Root or sudo access available
- [ ] Network connectivity to:
  - SQL Server (SG-8-Test-SQL)
  - MIMS API (172.60.1.42:8080)
  - SMTP server (mail.smtp2go.com)
  - All CCTV cameras (10.164.244.x network)
- [ ] Port 8080 available (or configure alternate in .env)
- [ ] Minimum 50GB disk space for snapshots

### Access Requirements
- [ ] SQL Server credentials (RTMCSNAP user)
- [ ] MIMS API credentials or token
- [ ] SMTP email credentials
- [ ] Camera admin credentials (default: admin/Tampa234)

## Deployment Steps

### Step 1: Initial Setup

1. **Login to server:**
   ```bash
   ssh root@10.175.253.33
   ```

2. **Verify current directory:**
   ```bash
   cd /var/cctv-tool-v2
   pwd
   ```

3. **Check existing files:**
   ```bash
   ls -la
   ```

### Step 2: Run Installation

1. **Execute installation script:**
   ```bash
   ./install.sh
   ```

   This will:
   - Install Python 3.9+ and dependencies
   - Install Microsoft ODBC Driver 17 for SQL Server
   - Create Python virtual environment
   - Install all required Python packages
   - Create log and snapshot directories
   - Copy systemd service file
   - Set proper permissions

2. **Verify installation:**
   ```bash
   source venv/bin/activate
   python3 --version
   pip list | grep -E "(flask|pyodbc|onvif|opencv)"
   deactivate
   ```

### Step 3: Configure Environment

1. **Review the .env file:**
   ```bash
   cat .env
   ```

   **CRITICAL: Verify these settings:**

   **Database:**
   ```bash
   DB_SERVER=SG-8-Test-SQL
   DB_DATABASE=FDOT_CCTV_System
   DB_USERNAME=RTMCSNAP
   DB_PASSWORD=SunGuide1!
   ```

   **Email:**
   ```bash
   SMTP_SERVER=mail.smtp2go.com
   SMTP_PORT=2525
   SMTP_USERNAME=d3sunguide@d3sunguide.com
   SMTP_PASSWORD=T@mpa.2017
   MAINTENANCE_EMAILS=Robert.briscoe@transcore.com,D3-NWFSGsuper@dot.state.fl.us,D3-TMCMaint@dot.state.fl.us
   ```

   **MIMS:**
   ```bash
   MIMS_BASE_URL=http://172.60.1.42:8080
   MIMS_TOKEN=<your_jwt_token>
   ```

   **Cameras:**
   ```bash
   CAMERA_DEFAULT_USERNAME=admin
   CAMERA_DEFAULT_PASSWORD=Tampa234
   ```

2. **Test configuration:**
   ```bash
   # Verify .env is readable
   chmod 600 .env

   # Check no syntax errors
   grep -v "^#" .env | grep -v "^$"
   ```

### Step 4: Test Run (Manual Start)

1. **Start application manually:**
   ```bash
   ./start.sh
   ```

2. **In another terminal, test endpoints:**
   ```bash
   # Health check
   curl http://localhost:8080/api/health | python3 -m json.tool

   # Camera list (should show 285 cameras)
   curl http://localhost:8080/api/cameras/list | python3 -m json.tool | head -30

   # Configuration (verify no secrets exposed)
   curl http://localhost:8080/api/config | python3 -m json.tool
   ```

3. **Expected health check response:**
   ```json
   {
     "status": "healthy",
     "services": {
       "mims_available": true,
       "onvif_available": true,
       "database": { "connected": true }
     },
     "cameras": {
       "total_cameras": 285,
       "config_loaded": true
     }
   }
   ```

4. **If healthy, stop manual instance:**
   ```bash
   # Press Ctrl+C in terminal running start.sh
   ```

### Step 5: Deploy as Systemd Service

1. **Enable and start service:**
   ```bash
   sudo systemctl enable cctv-tool
   sudo systemctl start cctv-tool
   ```

2. **Check status:**
   ```bash
   sudo systemctl status cctv-tool
   ```

   **Expected output:**
   ```
   ● cctv-tool.service - FDOT CCTV Operations Tool v2
      Loaded: loaded (/etc/systemd/system/cctv-tool.service; enabled)
      Active: active (running) since [timestamp]
      Main PID: [pid] (python3)
      ...
   ```

3. **Monitor startup logs:**
   ```bash
   sudo journalctl -u cctv-tool -f
   ```

   **Look for:**
   ```
   FDOT CCTV Operations Tool v6.0
   ✓ Loaded 285 cameras from configuration
   ✓ MIMS client initialized
   ✓ All managers initialized
   Running on http://0.0.0.0:8080
   ```

4. **Verify service is responding:**
   ```bash
   ./status.sh
   ```

### Step 6: Firewall Configuration (if needed)

If firewall is blocking port 8080:

```bash
# Check firewall status
sudo firewall-cmd --state

# Add port 8080
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload

# Verify
sudo firewall-cmd --list-ports
```

### Step 7: Test Core Functions

#### Test 1: Camera List
```bash
curl http://localhost:8080/api/cameras/list | python3 -m json.tool | grep total
# Expected: "total": 285
```

#### Test 2: Health Check
```bash
curl http://localhost:8080/api/health | python3 -m json.tool | grep status
# Expected: "status": "healthy"
```

#### Test 3: Database Connection
```bash
curl http://localhost:8080/api/health | python3 -m json.tool | grep -A3 database
# Expected: "connected": true
```

#### Test 4: Camera Reboot (Optional - only if safe to reboot)
```bash
curl -X POST http://localhost:8080/api/camera/reboot \
  -H "Content-Type: application/json" \
  -d '{
    "camera_ip": "10.164.244.149",
    "camera_name": "CCTV-I10-000.6-EB",
    "operator": "System Admin",
    "reason": "Deployment test - reboot verification"
  }'
```

## Post-Deployment Configuration

### Configure LibreNMS Monitoring

1. **Add HTTP Service Check:**
   - Device: 10.175.253.33
   - Service: HTTP
   - URL: http://10.175.253.33:8080/api/health
   - Method: GET
   - Check Interval: 60 seconds
   - Alert on: Status code != 200

2. **Configure Alerts:**
   - Alert when health status = "degraded" (HTTP 503)
   - Alert when database.connected = false
   - Alert when storage.free_gb < 5

### Set Up Log Rotation

Create `/etc/logrotate.d/cctv-tool`:

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
    create 0640 root root
}
```

Test:
```bash
sudo logrotate -d /etc/logrotate.d/cctv-tool
```

### Configure Snapshot Cleanup

Add cron job to clean old snapshots:

```bash
sudo crontab -e
```

Add:
```cron
# Clean snapshots older than 7 days, daily at 2 AM
0 2 * * * find /var/cctv-snapshots -type f -mtime +7 -delete
```

### Database Backup

Ensure SQL Server backups include FDOT_CCTV_System database:
```sql
BACKUP DATABASE FDOT_CCTV_System
TO DISK = 'E:\Backups\FDOT_CCTV_System.bak'
WITH FORMAT, COMPRESSION;
```

## Verification & Validation

### Functional Tests

- [ ] API responds on port 8080
- [ ] Health check returns 200 status
- [ ] 285 cameras loaded from config
- [ ] Database connection successful
- [ ] MIMS client authenticated
- [ ] Email configuration loaded
- [ ] Storage paths accessible
- [ ] Logs being written to logs/

### Integration Tests

- [ ] Camera reboot creates MIMS ticket
- [ ] Email notifications sent successfully
- [ ] Snapshots saved to correct directory
- [ ] Service auto-restarts on failure
- [ ] LibreNMS monitoring active

### Performance Baseline

Document initial metrics:
```bash
curl http://localhost:8080/api/metrics
```

Record:
- Response time for API calls
- Memory usage: `ps aux | grep CCTV_OperationsTool`
- Disk usage: `df -h /var/cctv-snapshots`

## Rollback Plan

If deployment fails:

1. **Stop service:**
   ```bash
   sudo systemctl stop cctv-tool
   sudo systemctl disable cctv-tool
   ```

2. **Restore previous version:**
   ```bash
   # If you have a backup
   cd /var
   mv cctv-tool-v2 cctv-tool-v2-failed
   tar -xzf cctv-tool-v2-backup.tar.gz
   ```

3. **Restore configuration:**
   ```bash
   cp /backup/.env /var/cctv-tool-v2/.env
   cp /backup/camera_config.json /var/cctv-tool-v2/
   ```

4. **Restart previous version:**
   ```bash
   cd /var/cctv-tool-v2
   ./start.sh
   ```

## Monitoring & Maintenance

### Daily Checks

```bash
# Quick status
./status.sh

# Check for errors
sudo journalctl -u cctv-tool --since "1 hour ago" | grep -i error

# Verify disk space
df -h /var/cctv-snapshots
```

### Weekly Checks

- Review logs for errors or warnings
- Verify MIMS ticket creation
- Check email delivery
- Monitor disk usage trends
- Review snapshot retention

### Monthly Maintenance

- Update Python dependencies if needed
- Review and archive old logs
- Verify database connectivity
- Test disaster recovery procedure
- Review camera configuration for changes

## Troubleshooting Common Issues

### Issue: Service fails to start

**Check:**
```bash
sudo journalctl -u cctv-tool -n 100
```

**Common causes:**
- Missing .env file
- Invalid database credentials
- Port 8080 already in use
- Python dependencies missing

**Fix:**
```bash
# Reinstall dependencies
cd /var/cctv-tool-v2
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart cctv-tool
```

### Issue: Database connection failed

**Test connection:**
```bash
source venv/bin/activate
python3 << EOF
import pyodbc
conn_str = "DRIVER={ODBC Driver 17 for SQL Server};SERVER=SG-8-Test-SQL;DATABASE=FDOT_CCTV_System;UID=RTMCSNAP;PWD=SunGuide1!;"
conn = pyodbc.connect(conn_str)
print("Connected successfully!")
conn.close()
EOF
```

**Check ODBC drivers:**
```bash
odbcinst -q -d
```

### Issue: Cameras not loaded

**Check config file:**
```bash
python3 -m json.tool camera_config.json | head -20
```

**Verify count:**
```bash
python3 << EOF
import json
with open('camera_config.json') as f:
    config = json.load(f)
    print(f"Cameras: {len(config.get('cameras', {}))}")
EOF
```

### Issue: MIMS tickets not created

**Check MIMS connectivity:**
```bash
curl -X POST http://172.60.1.42:8080/oauth2/token \
  -d "grant_type=password&username=YOUR_USER&password=YOUR_PASS"
```

**Verify token in .env:**
```bash
grep MIMS_TOKEN .env
```

## Contact & Support

**Before contacting support, gather:**
```bash
# System info
uname -a
cat /etc/redhat-release

# Service status
sudo systemctl status cctv-tool

# Recent logs
sudo journalctl -u cctv-tool -n 50

# Health check
curl http://localhost:8080/api/health

# Disk space
df -h

# Memory usage
free -h
```

**Support Contacts:**
- Operations: D3-NWFSGsuper@dot.state.fl.us
- Maintenance: D3-TMCMaint@dot.state.fl.us
- Vendor: Robert.briscoe@transcore.com

## Sign-off Checklist

- [ ] Installation completed successfully
- [ ] All environment variables configured
- [ ] Manual test run successful
- [ ] Systemd service enabled and running
- [ ] Health check returns healthy status
- [ ] 285 cameras loaded
- [ ] Database connection verified
- [ ] LibreNMS monitoring configured
- [ ] Log rotation configured
- [ ] Backup procedures documented
- [ ] Support contacts notified
- [ ] Documentation reviewed

**Deployed by:** ________________
**Date:** ________________
**Verified by:** ________________
**Sign-off:** ________________
