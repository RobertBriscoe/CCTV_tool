# CCTV Tool - Web Dashboard User Guide

**URL:** http://10.175.253.33:8080

---

## Quick Start

### Search for a Camera
1. Type in the search box: name, IP, location, or highway
2. Or click highway filter buttons: **All | I-10 | I-110 | US-90 | US-98**

### Reboot a Single Camera
1. Find the camera (search if needed)
2. Click the **🔄 Reboot** button
3. Enter your name and reason
4. Click **Reboot Camera**
5. ✅ Success notification appears
6. MIMS ticket created automatically

### Capture Snapshots from One Camera
1. Find the camera
2. Click the **📸 Snapshot** button
3. Enter:
   - Your name
   - Duration (minutes) - default: 60
   - Interval (seconds) - default: 300 (= 5 min)
4. Click **Start Capture**
5. ✅ Success notification appears

### Reboot Multiple Cameras
1. Check boxes next to cameras you want to reboot
2. Click **Reboot Selected** (red button at top)
3. Enter your name when prompted
4. Enter reason when prompted
5. All selected cameras will reboot
6. Summary notification shows success/failure count

### Snapshot Multiple Cameras
1. Check boxes next to cameras
2. Click **Snapshot Selected** (green button at top)
3. Fill in the form:
   - Operator name
   - Duration (minutes)
   - Interval (seconds)
4. Click **Start Capture**
5. All cameras begin capturing

---

## Dashboard Layout

```
┌─────────────────────────────────────────────────┐
│  🎥 FDOT CCTV Operations Tool                   │
│  District 3 Camera Management System            │
└─────────────────────────────────────────────────┘

┌─────────────┬─────────────┬─────────────┐
│ Total: 285  │ Displayed   │ Selected: 0 │
└─────────────┴─────────────┴─────────────┘

┌─────────────────────────────────────────────────┐
│ 🔍 Search box                                   │
│ [All] [I-10] [I-110] [US-90] [US-98]           │
│ [Select All] [Deselect] [Reboot] [Snapshot]    │
└─────────────────────────────────────────────────┘

┌───────────────┬───────────────┬───────────────┐
│ □ Camera 1    │ □ Camera 2    │ □ Camera 3    │
│ I10 MM 0.6 EB │ I10 MM 0.7 EB │ I10 MM 1.5 EB │
│ 10.164.244.14 │ 10.164.244.20 │ 10.164.244.23 │
│ [🔄 Reboot]   │ [🔄 Reboot]   │ [🔄 Reboot]   │
│ [📸 Snapshot] │ [📸 Snapshot] │ [📸 Snapshot] │
└───────────────┴───────────────┴───────────────┘
```

---

## Button Reference

### Individual Camera Buttons
- **🔄 Reboot** - Reboot this camera (opens form)
- **📸 Snapshot** - Capture from this camera (opens form)

### Bulk Action Buttons (Top Toolbar)
- **Select All** - Check all visible cameras
- **Deselect All** - Uncheck all cameras
- **Reboot Selected** - Reboot all checked cameras (RED)
- **Snapshot Selected** - Snapshot all checked cameras (GREEN)

### Filter Buttons
- **All** - Show all 285 cameras
- **I-10** - Show only I-10 cameras (238 total)
- **I-110** - Show only I-110 cameras
- **US-90** - Show only US-90 cameras
- **US-98** - Show only US-98 cameras

---

## Form Fields Explained

### Reboot Form
**Operator Name:** *Required*
- Your full name (for tracking/accountability)
- Example: "John Smith"

**Reason for Reboot:** *Required*
- Brief explanation why reboot is needed
- Example: "Camera not responding to ping"
- Example: "Scheduled maintenance"
- Example: "Image frozen for 30+ minutes"

### Snapshot Form
**Operator Name:** *Required*
- Your full name
- Example: "Jane Doe"

**Duration (minutes):** *Required*
- How long to capture snapshots
- Default: 60 minutes (1 hour)
- Range: 1 to 1440 minutes (24 hours)
- Example: 120 = capture for 2 hours

**Interval (seconds):** *Required*
- Time between snapshots
- Default: 300 seconds (5 minutes)
- Range: 30 to 3600 seconds
- Example: 300 = one snapshot every 5 minutes

**Example:** Duration=60, Interval=300
- Captures for 60 minutes
- One snapshot every 5 minutes
- Total snapshots: 12 per camera

---

## Search Examples

### By Highway
- Type: **I10** → All I-10 cameras
- Type: **I110** → All I-110 cameras
- Type: **US90** → All US-90 cameras

### By Location
- Type: **MM 5** → All cameras at mile marker 5
- Type: **MM 10** → All cameras at mile marker 10
- Type: **EB** → All eastbound cameras
- Type: **WB** → All westbound cameras

### By Camera Name
- Type: **CCTV-I10-001** → Specific camera
- Type: **001** → All cameras with "001" in name

### By IP Address
- Type: **10.164** → All cameras on that subnet
- Type: **10.164.244.149** → Specific camera

---

## Tips & Best Practices

### For Reboots
✅ **DO:**
- Always enter a clear reason
- Use reboot for unresponsive cameras
- Check MIMS ticket was created (notification)
- Wait 2-3 minutes for camera to come back online

❌ **DON'T:**
- Reboot cameras during special events
- Reboot without documenting reason
- Reboot multiple cameras unnecessarily

### For Snapshots
✅ **DO:**
- Use for incident documentation
- Set appropriate duration (don't use 24hr unless needed)
- Use 5-minute intervals for most cases
- Check storage space before long captures

❌ **DON'T:**
- Capture from all 285 cameras simultaneously
- Use very short intervals (< 1 minute)
- Forget to document operator name

### For Bulk Operations
✅ **DO:**
- Use Select All carefully (verify filter first)
- Double-check selection count before proceeding
- Use highway filters to narrow selection
- Test with 1-2 cameras first

❌ **DON'T:**
- Select all 285 cameras for reboot
- Bulk reboot during peak traffic
- Proceed without verifying selection

---

## Troubleshooting

### "Site cannot be reached"
- Check you're on FDOT internal network
- Verify URL: http://10.175.253.33:8080 (not https)
- Try from different computer on same network

### Reboot fails
- Check camera is powered on
- Verify camera IP is correct
- Check ONVIF is enabled on camera
- Review notification error message

### Snapshot fails
- Check camera RTSP stream is accessible
- Verify disk space available
- Check camera credentials
- Try single camera first

### Cameras don't load
- Check service is running: `systemctl status cctv-tool`
- Verify 285 cameras loaded in logs
- Refresh browser (Ctrl+F5)

### Selected count doesn't update
- Refresh the page
- Clear browser cache
- Try different browser

---

## Keyboard Shortcuts

- **Ctrl+F** - Focus search box
- **Escape** - Close modal dialogs
- **Ctrl+A** - Select all (in forms)

---

## Support

**Before Contacting Support:**
1. Note camera name and IP
2. Screenshot error notification
3. Note what you were trying to do
4. Check system status: http://10.175.253.33:8080/api/health

**Contact:**
- Operations: D3-NWFSGsuper@dot.state.fl.us
- Maintenance: D3-TMCMaint@dot.state.fl.us
- Vendor: Robert.briscoe@transcore.com

---

## Frequently Asked Questions

**Q: How long does a reboot take?**
A: Typically 2-3 minutes for camera to come back online.

**Q: Can I schedule snapshots for later?**
A: Currently snapshots start immediately. Scheduling coming in future update.

**Q: Where are snapshots saved?**
A: `/var/cctv-snapshots` on the server, accessible via network share.

**Q: What creates the MIMS ticket?**
A: Reboot action automatically creates ticket with your operator name and reason.

**Q: Can I cancel a running snapshot?**
A: Yes, contact support with camera name to stop active capture.

**Q: How many cameras can I select at once?**
A: No limit, but be cautious with bulk operations (test with few cameras first).

**Q: Why is my search not finding anything?**
A: Search requires minimum 2 characters. Try broader terms.

**Q: Can I reboot cameras remotely?**
A: Yes, if you can access http://10.175.253.33:8080 from your location.

---

## Version Information

- **Tool Version:** 6.0
- **Dashboard:** Enhanced with operator actions
- **Last Updated:** 2025-11-03
- **Total Cameras:** 285
- **Features:** Search, Filter, Reboot, Snapshot, Bulk Operations
