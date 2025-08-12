# Celestron Origin Satellite Tracker - Quick Reference

## 🚀 Quick Start

```bash
# 1. Configure your location and API keys
vim config.ini

# 2. Add satellite NORAD IDs to track
echo "25544,45344,48274" > norad_ids.txt  # ISS, Starlink satellites

# 3. Run the tracker
python main_tracker.py
```

## 📡 Key API Calls Used

### Mount Control
```python
# Move telescope to Alt/Az position (RADIANS!)
await ws_client.goto_alt_azm(alt_rad, az_rad)

# Disable sidereal tracking for satellites
await ws_client.send_command("Mount", "EnableTracking", {"Value": False})

# Check mount status
status = await ws_client.get_mount_status()
is_aligned = status.get("IsAligned")
is_goto_complete = status.get("IsGotoOver")
```

### Camera & Imaging
```python
# Set camera parameters
await ws_client.set_camera_parameters(
    exposure_sec=0.5,   # Short for fast satellites
    iso=800,            # Moderate sensitivity
    binning=2,          # 2x2 binning for sensitivity
    bit_depth=16        # 16-bit for dynamic range
)

# Trigger image capture
await ws_client.run_sample_capture(exposure_sec, iso, binning)

# Download captured image
await ws_client.download_image(origin_file_path, local_save_path)
```

## 🌍 Coordinate Conversions

```python
# Skyfield → Celestron Origin
from skyfield.api import Topos, load, EarthSatellite

# Create observer location
observer = Topos(latitude_degrees=34.05, 
                 longitude_degrees=-118.24,
                 elevation_m=71)

# Calculate satellite position
difference = satellite - observer
apparent_pos = difference.at(time)
el, az, _ = apparent_pos.altaz()

# Convert to Celestron format (RADIANS!)
celestron_alt = el.radians
celestron_azm = az.radians
```

## 📂 File Structure

```
celestron_satellite_tracker/
├── config.ini              # Configuration
├── norad_ids.txt          # Satellites to track
├── main_tracker.py        # Main application
├── n2yo_api.py           # Satellite data fetching
├── sky_utils.py          # Position calculations
├── celestron_ws_client.py # Telescope control
├── tle_plan.json         # Generated schedule
├── trajectory.json       # Calculated paths
└── observations/         # Captured images
    └── SATNAME_NORAD_TIMESTAMP/
        └── *.fits
```

## ⚙️ Configuration Parameters

```ini
[OBSERVER]
latitude = 34.0522        # Decimal degrees
longitude = -118.2437     # Decimal degrees
altitude_m = 71           # Meters above sea level

[CELESTRON]
origin_ip = origin.local  # Or IP address like 192.168.1.100

[CAMERA]
exposure_seconds = 0.5    # Short for satellites
iso = 800                 # 100-6400 range
binning = 2               # 1, 2, 3, or 4
bit_depth = 16            # 8, 16, or 24
image_cooldown_seconds = 5
```

## 🔧 Common Operations

### Generate New Schedule
```python
plan, trajectories = generate_pass_schedule()
# Automatically saves to tle_plan.json and trajectory.json
```

### Track Single Pass
```python
await track_satellite_pass(ws_client, pass_info, trajectory)
# Handles pre-positioning, tracking, and imaging
```

### System Health Check
```python
await perform_system_health_check(ws_client)
# Displays comprehensive status table
```

## 📊 Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| MIN_ELEVATION_DEG | 20° | Minimum satellite elevation |
| COOLDOWN_SECONDS | 120s | Time between passes |
| PRE_POSITION_LEAD_TIME | 45s | Pre-slew buffer |
| N2YO_REQUEST_DELAY | 3.8s | API rate limiting |
| WATCHDOG_INTERVAL | 5s | Connection monitoring |

## 🐛 Troubleshooting

### Connection Issues
```python
# Check WebSocket URI format
ws://origin.local/SmartScope-1.0/mountControlEndpoint

# Verify telescope is on same network
ping origin.local
```

### Tracking Problems
```python
# Verify mount is aligned
status = await ws_client.get_mount_status()
if not status.get("IsAligned"):
    print("Mount needs alignment!")

# Check coordinates are in RADIANS
assert 0 <= alt_rad <= math.pi/2  # 0-90° in radians
assert 0 <= az_rad <= 2*math.pi   # 0-360° in radians
```

### Image Issues
```python
# Verify storage location exists
Path("observations").mkdir(exist_ok=True)

# Check Origin's internal storage
disk_status = await ws_client.get_disk_status()
free_gb = disk_status.get("FreeBytes", 0) / (1024**3)
```

## 📚 API Documentation Structure

### Command Format
```json
{
    "Source": "External",
    "Command": "Mount.GotoAltAzm",
    "Payload": {
        "Alt": 0.785398,  // radians
        "Azm": 3.141592   // radians
    },
    "SequenceID": 1234
}
```

### Response Format
```json
{
    "Source": "Mount",
    "Command": "GotoAltAzm",
    "Payload": {
        "ErrorCode": 0,
        "ErrorMessage": null
    },
    "SequenceID": 1234
}
```

### Notification Format
```json
{
    "Source": "ImageServer",
    "Command": "NewImageReady",
    "Payload": {
        "FileLocation": "/images/capture_001.fits",
        "ImageType": "SAMPLE_CAPTURE"
    }
}
```

## 🎯 Performance Tips

1. **Reduce API Calls**: Use dynamic time windows
2. **Batch Operations**: Download images asynchronously
3. **Pre-position Early**: Start slewing 45s before pass
4. **Short Exposures**: 0.5-1s for moving satellites
5. **Higher ISO**: 800-1600 for dim satellites
6. **Binning**: 2x2 improves sensitivity
7. **Skip Low Passes**: Filter < 20° elevation

## 🔗 External Resources

- [Celestron Origin Product Page](https://www.celestron.com/products/celestron-origin)
- [N2YO Satellite Tracker](https://www.n2yo.com)
- [Skyfield Documentation](https://rhodesmill.org/skyfield/)
- [NORAD Catalog Numbers](https://celestrak.com/satcat/search.php)

## 💡 Pro Tips

1. **Test with ISS First**: NORAD 25544, bright and predictable
2. **Check StarSense**: Ensure auto-alignment completed
3. **Monitor Environment**: Watch humidity vs dew point
4. **Use High Elevation**: Better seeing above 40°
5. **Plan for Weather**: Check cloud cover forecasts
6. **Regular Calibration**: Re-align after equipment changes

---
*Quick Reference v1.0 - For detailed information, see SYSTEM_DOCUMENTATION.md*
