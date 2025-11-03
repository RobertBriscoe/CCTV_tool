# Email Notification Privacy - Summary

**Date:** November 3, 2025
**Status:** IP Information Protection Enabled ✅

---

## Privacy Protection Applied

All email notifications have been configured to **exclude IP addresses and technical details** to protect sensitive network information.

---

## Reboot Notification Emails

### What IS Included ✅
```
Camera: CCTV-I10-011.4-EB
Status: ✓ SUCCESS (or ✗ FAILED)
Operator: John Doe
Reason: Poor video quality
Timestamp: 2025-11-03T12:00:00
MIMS Ticket: 57789
```

### What IS NOT Included ❌
- ❌ Camera IP addresses (e.g., 10.164.244.65)
- ❌ Port numbers (e.g., :80)
- ❌ Technical error details
- ❌ Network configuration
- ❌ ONVIF credentials

### Privacy Features

1. **IP Address Redaction**
   - Any IP addresses in error messages are automatically replaced with `[IP REDACTED]`
   - Uses regex pattern to detect: `xxx.xxx.xxx.xxx`

2. **Port Number Removal**
   - Port numbers (`:80`, `:8080`, etc.) are stripped from messages

3. **Simplified Status Messages**
   - **Success:** "Camera reboot command sent successfully."
   - **Failure:** "Camera reboot command failed. Technical details logged."
   - No technical error messages exposed

### Email Template

```
CCTV Camera Reboot Notification
================================

Camera: {camera_name}
Status: {✓ SUCCESS or ✗ FAILED}
Operator: {operator_name}
Reason: {reason_provided}
Timestamp: {iso_timestamp}

{simple_status_message}

MIMS Ticket: {ticket_id or N/A}

---
This is an automated notification from the FDOT CCTV Operations Tool.
For technical details, contact the operations team.
```

---

## Snapshot Notification Emails

### What IS Included ✅
```
Session ID: 20251103_120000
Start Time: 2025-11-03 12:00:00
End Time: 2025-11-03 12:30:00
Duration: 30 minutes
Interval: 30 seconds

Statistics:
Total Captures: 60
Successful: 58
Failed: 2
Success Rate: 96.7%

Camera Details:
CCTV-I10-011.4-EB:
  Successful: 29
  Failed: 1
CCTV-I10-012.4-EB:
  Successful: 29
  Failed: 1

Storage Location: /var/cctv-snapshots/20251103_120000/
Shared Folder: /mnt/shared/cctv-snapshots/20251103_120000/
```

### What IS NOT Included ❌
- ❌ Camera IP addresses
- ❌ Network paths beyond storage locations
- ❌ Technical failure reasons

---

## Email Recipients

**Reboot Notifications:**
- Robert.briscoe@transcore.com
- D3-NWFSGsuper@dot.state.fl.us
- D3-TMCMaint@dot.state.fl.us

**Snapshot Reports:**
- Configurable based on request

---

## Technical Details (For Operations Team)

### Code Implementation

**File:** `CCTV_OperationsTool_Fixed.py`
**Function:** `_send_reboot_email()` (Lines 431-489)

**IP Redaction Logic:**
```python
# Remove IP addresses (pattern: xxx.xxx.xxx.xxx)
message = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP REDACTED]', message)

# Remove port numbers (pattern: :80, :8080, etc)
message = re.sub(r':\d+', '', message)
```

**Simplified Status Messages:**
```python
if result['success']:
    status_detail = "Camera reboot command sent successfully."
else:
    status_detail = "Camera reboot command failed. Technical details logged."
```

### Where Technical Details ARE Logged

Full technical details (including IP addresses) are logged to:
- **System logs:** `journalctl -u cctv-tool`
- **Application logs:** `/var/cctv-tool-v2/logs/` (if configured)

**View logs:**
```bash
# View reboot logs with IP addresses
sudo journalctl -u cctv-tool | grep -i reboot | tail -20

# View all CCTV tool logs
sudo journalctl -u cctv-tool -f
```

---

## Security Benefits

### 1. Protects Network Infrastructure
- Camera IP addresses not exposed in emails
- Network topology remains confidential
- Reduces risk if emails are forwarded

### 2. Compliance
- Meets security best practices for network information
- Reduces sensitive data in email systems
- Minimizes exposure in email archives

### 3. Operational Security
- Only authorized personnel (with system access) can view IP addresses
- Email recipients get necessary information without sensitive details
- Detailed troubleshooting info available in logs for operations team

---

## Example Email Comparison

### ❌ BEFORE (Exposed IP Info)
```
Camera: CCTV-I10-011.4-EB
Status: ✗ FAILED
Details:
Reboot failed: Connection timeout to 10.164.244.65:80
ONVIFCamera error: Cannot connect to device at 10.164.244.65
```

### ✅ AFTER (Privacy Protected)
```
Camera: CCTV-I10-011.4-EB
Status: ✗ FAILED
Camera reboot command failed. Technical details logged.

MIMS Ticket: 57790

---
For technical details, contact the operations team.
```

---

## Verification

To verify IP redaction is working, test by:

1. **Reboot a camera that will fail** (e.g., incorrect credentials)
2. **Check the email notification**
3. **Confirm:**
   - ✅ No IP addresses visible
   - ✅ No port numbers visible
   - ✅ Simple status message only
   - ✅ MIMS ticket ID included

4. **Check logs for technical details:**
   ```bash
   sudo journalctl -u cctv-tool | grep reboot | tail -5
   ```
   - ✅ IP addresses visible in logs (for troubleshooting)

---

## Configuration

### Email Settings (`.env`)
```bash
EMAIL_ENABLED=true
SMTP_SERVER=mail.smtp2go.com
SMTP_PORT=25
SMTP_USERNAME=d3sunguide
SMTP_FROM_EMAIL=d3sunguide@d3sunguide.com
SMTP_PASSWORD=T@mpa.2017

MAINTENANCE_EMAILS=Robert.briscoe@transcore.com,D3-NWFSGsuper@dot.state.fl.us,D3-TMCMaint@dot.state.fl.us
```

### Disable Email Temporarily
```bash
EMAIL_ENABLED=false
```

Then restart service:
```bash
sudo systemctl restart cctv-tool
```

---

## Summary

✅ **IP addresses automatically redacted from all emails**
✅ **Technical details hidden from email recipients**
✅ **Full details available in system logs for operations team**
✅ **Simple, user-friendly status messages**
✅ **MIMS ticket tracking still included**
✅ **Privacy and security enhanced**

**Email notifications now provide necessary information without exposing sensitive network details.**

---

*Last Updated: November 3, 2025*
