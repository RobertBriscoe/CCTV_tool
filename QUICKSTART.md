# CCTV Tool v2 - Quick Start Guide

## 30-Second Quick Start

```bash
# 1. Install
sudo ./install.sh

# 2. Verify .env has your credentials (already configured)
cat .env

# 3. Start service
sudo systemctl enable cctv-tool
sudo systemctl start cctv-tool

# 4. Check status
./status.sh
```

## Common Commands

```bash
# Start/Stop/Restart
sudo systemctl start cctv-tool
sudo systemctl stop cctv-tool
sudo systemctl restart cctv-tool

# Check status
./status.sh
sudo systemctl status cctv-tool

# View logs
sudo journalctl -u cctv-tool -f
tail -f logs/cctv_ops_*.log

# Test API
curl http://localhost:8080/api/health
curl http://localhost:8080/api/cameras/list
```

## Key Files

- `.env` - Configuration & secrets (NEVER commit!)
- `camera_config.json` - 285 camera definitions (no passwords)
- `README.md` - Complete documentation
- `DEPLOYMENT.md` - Detailed deployment guide
- `logs/cctv_ops_*.log` - Application logs

## Port & Access

- **Port:** 8080 (configurable in .env)
- **Health Check:** http://10.175.253.33:8080/api/health
- **Camera List:** http://10.175.253.33:8080/api/cameras/list

## Troubleshooting One-Liners

```bash
# Service won't start?
sudo journalctl -u cctv-tool -n 50

# Database issue?
odbcinst -q -d

# Port conflict?
sudo lsof -i :8080

# Low disk space?
df -h /var/cctv-snapshots

# Check camera count
curl http://localhost:8080/api/cameras/list | python3 -c "import sys, json; print(json.load(sys.stdin)['total'])"
```

## Support

- **Ops:** D3-NWFSGsuper@dot.state.fl.us
- **Maint:** D3-TMCMaint@dot.state.fl.us
- **Vendor:** Robert.briscoe@transcore.com
