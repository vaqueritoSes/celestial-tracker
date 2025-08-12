# 🛰️ Celestial Tracker - Autonomous Satellite Tracking for Celestron Origin

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Celestron Origin](https://img.shields.io/badge/Celestron-Origin-red.svg)](https://www.celestron.com/products/celestron-origin)
[![API Version](https://img.shields.io/badge/API-v1.0-green.svg)](https://www.celestron.com)

An advanced autonomous satellite tracking system designed specifically for the **Celestron Origin Intelligent Home Observatory**. Track and image satellites automatically using the telescope's built-in AI capabilities and WebSocket API.

![Satellite Tracking](https://img.shields.io/badge/Status-Production_Ready-success)

## ✨ Features

- 🚀 **Autonomous Satellite Tracking** - Automatically tracks satellites across the sky
- 📸 **Intelligent Imaging** - Captures high-quality images during satellite passes
- 🌙 **Smart Scheduling** - Optimized for single-night observation windows
- 🔭 **Full API Integration** - Complete integration with Celestron Origin WebSocket API
- 📊 **Real-time Dashboard** - Web-based monitoring and control interface
- 🌐 **Multi-Satellite Support** - Track ISS, Starlink, and any NORAD-cataloged satellite
- ⚡ **Performance Optimized** - Dynamic scheduling reduces API calls by 50%
- 🔄 **Auto-Recovery** - Robust error handling with automatic reconnection

## 🎯 Key Capabilities

### Telescope Control
- Precise Alt/Az positioning with sub-degree accuracy
- Pre-positioning 45 seconds before pass start
- 1Hz position updates during tracking
- Automatic sidereal tracking disable for satellites

### Imaging System
- Configurable exposure times (0.1-30 seconds)
- ISO range 100-6400
- Binning support (1x1 to 4x4)
- 8/16/24-bit depth options
- AI-powered real-time image stacking

### Data Management
- Organized observation storage by satellite and timestamp
- Automatic image download from telescope
- JSON-based schedule persistence
- Comprehensive logging with Rich formatting

## 📋 Prerequisites

### Hardware
- **Celestron Origin Intelligent Home Observatory** (6" RASA telescope)
- Network connection to telescope (WiFi or Ethernet)
- Computer running Python 3.8+

### Software
- Python 3.8 or higher
- N2YO API key (free from [n2yo.com](https://www.n2yo.com/api/))

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/celestial-tracker.git
cd celestial-tracker
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Settings
```bash
# Copy sample configuration
cp config.ini.sample config.ini

# Edit with your settings
nano config.ini
```

Update these key settings:
- `latitude`, `longitude`, `altitude_m` - Your observation location
- `api_key` - Your N2YO API key
- `origin_ip` - Your telescope's IP address or hostname

### 4. Add Satellites to Track
```bash
# Copy sample NORAD IDs
cp norad_ids.txt.sample norad_ids.txt

# Or create your own list
echo "25544,20580" > norad_ids.txt  # ISS and Hubble
```

### 5. Run the Tracker
```bash
python main_tracker.py
```

## 📁 Project Structure

```
celestial-tracker/
├── main_tracker.py           # Main application entry point
├── celestron_ws_client.py    # WebSocket client for telescope control
├── n2yo_api.py              # Satellite pass prediction API
├── sky_utils.py             # Astronomical calculations
├── dashboard_server.py      # Web dashboard (optional)
├── config.ini.sample        # Configuration template
├── requirements.txt         # Python dependencies
├── observations/            # Captured images directory
├── docs/                    # Documentation
│   ├── SYSTEM_DOCUMENTATION.md
│   ├── QUICK_REFERENCE.md
│   └── API_ALIGNMENT.md
└── templates/              # Web dashboard templates
```

## 🔧 Configuration

### Basic Configuration (`config.ini`)

```ini
[OBSERVER]
latitude = 34.0522        # Decimal degrees
longitude = -118.2437     # Decimal degrees  
altitude_m = 71          # Meters above sea level

[N2YO]
api_key = YOUR_KEY_HERE  # From n2yo.com/api

[CELESTRON]
origin_ip = origin.local # Or IP like 192.168.1.100

[CAMERA]
exposure_seconds = 0.5   # Short for fast satellites
iso = 800               # Moderate sensitivity
binning = 2             # 2x2 for better sensitivity
```

## 📊 Web Dashboard (Optional)

Launch the monitoring dashboard:

```bash
python dashboard_server.py
```

Access at `http://localhost:5000` to view:
- Real-time tracking status
- Upcoming satellite passes
- System health metrics
- Live connection status
- Captured images gallery

## 🛰️ Supported Satellites

Track any satellite with a NORAD catalog number:

| Satellite | NORAD ID | Brightness | Speed |
|-----------|----------|------------|-------|
| ISS | 25544 | Very Bright | Medium |
| Hubble | 20580 | Moderate | Slow |
| Starlink | Various | Bright | Fast |
| Tiangong | 48274 | Bright | Medium |

Find more at [celestrak.com](https://celestrak.com/satcat/search.php)

## 📈 Performance

- **Schedule Generation**: < 30 seconds for 10 satellites
- **API Efficiency**: ~200 calls/hour (limit: 950)
- **Tracking Accuracy**: < 0.5° pointing error
- **Image Capture Rate**: Up to 12 per minute
- **Position Updates**: 1 Hz during tracking

## 🔬 Technical Details

### Coordinate System
- Uses Skyfield for precise astronomical calculations
- Converts topocentric Alt/Az to radians for mount control
- J2000 epoch for RA/Dec coordinates
- WGS84 for observer location

### API Integration
- WebSocket connection on port 80
- JSON-RPC style messaging
- Automatic reconnection with exponential backoff
- Comprehensive error handling

### Image Processing
- Onboard AI stacking and enhancement
- FITS format support
- Automatic dark frame subtraction
- Real-time image optimization

## 📚 Documentation

Comprehensive documentation is available:

- [System Documentation](docs/SYSTEM_DOCUMENTATION.md) - Full technical details
- [Quick Reference](docs/QUICK_REFERENCE.md) - Common operations
- [API Alignment](docs/VALIDATION_SUMMARY.md) - API compliance details
- [Improvements Roadmap](docs/IMPROVEMENTS_AND_GAPS.md) - Future enhancements

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 🐛 Troubleshooting

### Common Issues

**Connection Failed**
- Verify telescope is on same network
- Check firewall settings
- Try IP address instead of hostname

**No Satellites Scheduled**
- Verify location settings are correct
- Check N2YO API key is valid
- Ensure observation time window is appropriate

**Tracking Errors**
- Confirm mount is aligned (StarSense)
- Check coordinates are in correct format
- Verify telescope has clear view of sky

See [Quick Reference](docs/QUICK_REFERENCE.md#-troubleshooting) for more solutions.

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Celestron](https://www.celestron.com) for the Origin telescope and API
- [N2YO.com](https://www.n2yo.com) for satellite tracking data
- [Skyfield](https://rhodesmill.org/skyfield/) for astronomical calculations
- [Rich](https://github.com/Textualize/rich) for beautiful terminal output

## 📞 Support

- 📖 [Documentation](docs/)
- 🐛 [Issue Tracker](https://github.com/yourusername/celestial-tracker/issues)
- 💬 [Discussions](https://github.com/yourusername/celestial-tracker/discussions)

## ⚠️ Disclaimer

This is an independent project and is not affiliated with, endorsed by, or sponsored by Celestron, LLC. Celestron Origin is a trademark of Celestron, LLC.

---

<p align="center">
  Made with ❤️ for the astronomy community
  <br>
  🌟 Star this repository if you find it useful! 🌟
</p>
