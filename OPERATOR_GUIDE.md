# CCTV Tool v2 - Operator Guide

## Quick Access

**Web Dashboard:** http://10.175.253.33:8080
**API Base URL:** http://10.175.253.33:8080/api

## For Operators - Easy Camera Search

### Option 1: Web Dashboard (Easiest!)

Just open your web browser and go to:
```
http://10.175.253.33:8080
```

**Features:**
- 🔍 **Live Search** - Type anything: camera name, IP, location, highway
- 🛣️ **Highway Filters** - Quick buttons for I-10, I-110, US-90, US-98
- 📊 **Real-time Stats** - See total and filtered camera counts
- 🎯 **Click Cameras** - Click any camera to see details and RTSP URL

**Search Examples:**
- Type "I10" → See all I-10 cameras (238 total)
- Type "MM 5" → See all cameras at mile marker 5
- Type "10.164" → Search by IP address
- Type "EB" → See all eastbound cameras

---

## For Advanced Users - API Reference

### 1. Search Cameras (Quick)

```bash
# Search for cameras matching "I10"
curl "http://10.175.253.33:8080/api/cameras/search?q=I10&limit=20"
```

**Parameters:**
- `q` - Search query (minimum 2 characters)
- `limit` - Max results (default: 20)

**Response:**
```json
{
  "query": "i10",
  "count": 20,
  "results": [
    {
      "id": "CCTV_I10_000_6_EB",
      "name": "CCTV-I10-000.6-EB",
      "ip": "10.164.244.149",
      "location": "I10 MM 000.6 EB",
      "rtsp_url": "rtsp://10.164.244.149:554/stream1"
    },
    ...
  ]
}
```

### 2. List Cameras (With Filters)

```bash
# List all cameras
curl "http://10.175.253.33:8080/api/cameras/list"

# Search with filtering
curl "http://10.175.253.33:8080/api/cameras/list?search=001"

# Sort by location
curl "http://10.175.253.33:8080/api/cameras/list?sort=location&order=asc"

# Pagination
curl "http://10.175.253.33:8080/api/cameras/list?limit=50&offset=0"
```

**Parameters:**
- `search` - Search term (name, IP, location)
- `sort` - Sort field: name, ip, location
- `order` - Sort order: asc, desc
- `limit` - Page size
- `offset` - Starting position

### 3. Group by Highway

```bash
# Get all cameras grouped by highway
curl "http://10.175.253.33:8080/api/cameras/by-highway"

# Filter specific highway
curl "http://10.175.253.33:8080/api/cameras/by-highway?highway=I10"
```

**Response:**
```json
{
  "highways": ["I10"],
  "total_cameras": 238,
  "data": {
    "I10": [
      {
        "id": "CCTV_I10_000_6_EB",
        "name": "CCTV-I10-000.6-EB",
        "ip": "10.164.244.149",
        "location": "I10 MM 000.6 EB"
      },
      ...
    ]
  }
}
```

### 4. Bulk Camera Information

```bash
# Get info for multiple cameras at once
curl -X POST http://10.175.253.33:8080/api/cameras/bulk-info \
  -H "Content-Type: application/json" \
  -d '{
    "camera_ips": ["10.164.244.149", "10.164.244.20", "10.164.244.23"]
  }'
```

---

## Common Search Scenarios

### Scenario 1: Find cameras on I-10 near mile marker 5

**Web Dashboard:**
- Type "I10 MM 5" in search box

**API:**
```bash
curl "http://10.175.253.33:8080/api/cameras/search?q=I10%20MM%205"
```

### Scenario 2: Find all eastbound cameras

**Web Dashboard:**
- Type "EB" in search box

**API:**
```bash
curl "http://10.175.253.33:8080/api/cameras/list?search=EB"
```

### Scenario 3: Find camera by IP address

**Web Dashboard:**
- Type IP address (e.g., "10.164.244.149")

**API:**
```bash
curl "http://10.175.253.33:8080/api/cameras/search?q=10.164.244"
```

### Scenario 4: List all I-110 cameras sorted by location

**API:**
```bash
curl "http://10.175.253.33:8080/api/cameras/list?search=I110&sort=location&order=asc"
```

### Scenario 5: Get cameras for specific IPs

**API:**
```bash
curl -X POST http://10.175.253.33:8080/api/cameras/bulk-info \
  -H "Content-Type: application/json" \
  -d '{"camera_ips": ["10.164.244.149", "10.164.244.20"]}'
```

---

## Camera Counts by Highway

| Highway | Camera Count |
|---------|-------------|
| I-10    | 238         |
| I-110   | ~40         |
| US-90   | ~5          |
| US-98   | ~2          |
| **Total** | **285**   |

---

## Reboot a Camera

```bash
curl -X POST http://10.175.253.33:8080/api/camera/reboot \
  -H "Content-Type: application/json" \
  -d '{
    "camera_ip": "10.164.244.149",
    "camera_name": "CCTV-I10-000.6-EB",
    "operator": "John Doe",
    "reason": "Camera not responding"
  }'
```

---

## Capture Snapshots

```bash
curl -X POST http://10.175.253.33:8080/api/snapshot/capture \
  -H "Content-Type: application/json" \
  -d '{
    "cameras": [
      {"ip": "10.164.244.149", "name": "CCTV-I10-000.6-EB"}
    ],
    "duration_minutes": 60,
    "interval_seconds": 300,
    "operator": "John Doe"
  }'
```

---

## Tips for Operators

1. **Use the Web Dashboard** - It's the easiest way to find cameras
2. **Bookmark it** - Save http://10.175.253.33:8080 in your browser
3. **Search is Flexible** - Type anything: names, IPs, mile markers, directions
4. **Highway Buttons** - Click I-10, I-110, etc. for quick filtering
5. **Case Insensitive** - Search works with upper or lowercase

---

## Support

**Having trouble finding a camera?**
- Check spelling (I10 vs I-10)
- Try partial matches (type "001" to find MM 001.x)
- Use IP address if you know it
- Try highway filter buttons

**Need Help?**
- Operations: D3-NWFSGsuper@dot.state.fl.us
- Maintenance: D3-TMCMaint@dot.state.fl.us
- Vendor: Robert.briscoe@transcore.com
