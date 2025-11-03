# MIMS Ticket Creation - FIX APPLIED ✅

**Date:** November 3, 2025
**Status:** **RESOLVED**

---

## Problem

MIMS tickets were not being created when operators rebooted cameras:
- Reboots worked successfully
- But no tickets appeared in MIMS system
- Error in logs: `401 Authorization has been denied for this request`

---

## Root Cause

**Two issues discovered:**

### 1. Expired JWT Token
The `MIMS_TOKEN` in `.env` file expired on **October 7, 2025** (26 days ago).
- Token expiration: `1759867098` (Oct 7, 2025)
- Current date: November 3, 2025
- MIMS API was rejecting all requests with 401 Unauthorized

### 2. Incorrect Username Format
Original `.env` had:
```bash
MIMS_USERNAME=KNTRN RB  # ✗ WRONG (with space)
```

Should be:
```bash
MIMS_USERNAME=KNTRNRB   # ✓ CORRECT (no space)
```

The JWT token payload showed username as "KNTRNRB" (no space), but config had space.

---

## Solution Applied

### Step 1: Updated `.env` File
Changed from token-based auth to username/password:

**Before:**
```bash
# MIMS_USERNAME=KNTRN RB
# MIMS_PASSWORD=your_mims_password_here
MIMS_TOKEN=eyJ0eXAiOiJKV1Qi...  # EXPIRED
```

**After:**
```bash
MIMS_USERNAME=KNTRNRB
MIMS_PASSWORD=Lifeisgood@1
# MIMS_TOKEN=eyJ0eXAiOiJKV1Qi...  # EXPIRED Oct 7, 2025
```

### Step 2: Restarted Service
```bash
systemctl restart cctv-tool
```

System now:
- Authenticates with username/password
- Automatically gets fresh tokens (expires in 24 hours)
- Auto-refreshes tokens before expiration
- No manual token renewal needed

---

## Verification Tests

### Test 1: Authentication ✅
```
Username: KNTRNRB
Status: ✓ Authentication successful
Token expires: 86399 seconds (24 hours)
```

### Test 2: Device Lookup ✅
```
MIMS Devices: 947 cameras found
Sample: CCTV-I10-059.7-WB (ID: 7972)
Note: Most devices have "Unknown" IP addresses in MIMS
```

### Test 3: Asset Lookup ✅
```
Camera: CCTV-I10-000.7-EB
Asset ID: 118
Method: Lookup by NAME (IP addresses mostly "Unknown" in MIMS)
```

### Test 4: Ticket Creation ✅
```
Camera: CCTV-I10-000.7-EB (10.164.244.20)
Asset ID: 118
Ticket ID: 57788
Outcome: success
Reason: Testing MIMS ticket creation after authentication fix
Result: ✓ Ticket created successfully!
```

---

## How It Works Now

When an operator reboots a camera:

1. **Camera Reboot** via ONVIF protocol
2. **Asset Lookup** in MIMS:
   - First tries IP address match
   - Falls back to camera NAME match (most reliable)
3. **Ticket Creation**:
   - If asset found: Links ticket to asset ID
   - If asset not found: Creates unlinked ticket with camera info in description
4. **Operator Feedback**: Returns ticket ID in dashboard response

---

## Important Notes

### Camera Matching
- **Most cameras in MIMS have "Unknown" IP addresses**
- System primarily matches by **camera name**
- 947 CCTV devices registered in MIMS
- Camera names are case-insensitive (e.g., "CCTV-I10-000.7-EB" = "cctv-i10-000.7-eb")

### Token Auto-Refresh
- New tokens valid for **24 hours**
- System automatically refreshes before expiration
- No manual intervention needed

### Username Format
- Username must be: **KNTRNRB** (no spaces)
- Password: Stored securely in .env (chmod 600)

---

## Testing Recommendations

### Test Reboot with MIMS Ticket
1. Go to: http://10.175.253.33:8080
2. Select any camera from list
3. Click **🔄 Reboot** button
4. Fill in form:
   - Operator: (your name)
   - Reason: "Testing MIMS integration"
5. Click **Reboot Camera**
6. **Check response includes ticket ID**
7. Verify ticket appears in MIMS system: http://172.60.1.42:8080

### Monitor Tickets
```bash
# Watch for MIMS ticket creation in logs
sudo journalctl -u cctv-tool -f | grep "MIMS ticket"

# Should see:
# ✓ MIMS ticket created for CCTV-I10-XXX.X-XX: {'id': 57788}
```

---

## Service Status

```bash
# Check service
systemctl status cctv-tool

# View logs
journalctl -u cctv-tool -f

# Restart if needed
systemctl restart cctv-tool
```

Current status:
- ✅ Service: Running
- ✅ MIMS: Authenticated
- ✅ Tickets: Working
- ✅ Token: Auto-refreshing

---

## Troubleshooting

### If authentication fails again:
1. Check username/password in .env
2. Verify MIMS API is accessible:
   ```bash
   curl -v http://172.60.1.42:8080/oauth2/token
   ```
3. Check service logs:
   ```bash
   journalctl -u cctv-tool | grep -i mims | tail -20
   ```

### If tickets not appearing:
1. Check MIMS system at http://172.60.1.42:8080
2. Verify ticket ID from dashboard response
3. Search tickets by ID in MIMS
4. Check camera is registered in MIMS (947 cameras total)

---

## Files Modified

1. **`.env`** - Updated MIMS credentials
   - Line 29: `MIMS_USERNAME=KNTRNRB`
   - Line 30: `MIMS_PASSWORD=Lifeisgood@1`
   - Line 31: Commented out expired token

2. **Service** - Restarted to load new config
   - `systemctl restart cctv-tool`

No code changes were needed - the system already supported username/password authentication!

---

## Summary

✅ **MIMS ticket creation is now fully operational**
✅ **Automatic token refresh every 24 hours**
✅ **947 cameras available for asset linking**
✅ **Fallback for cameras not in MIMS database**

**Next Steps:**
- Monitor tickets being created via dashboard
- Verify tickets appear in MIMS system
- Ensure operators can see ticket IDs in responses

---

**Support Contacts:**
- Operations: D3-NWFSGsuper@dot.state.fl.us
- Maintenance: D3-TMCMaint@dot.state.fl.us
- Vendor: Robert.briscoe@transcore.com
