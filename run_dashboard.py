#!/usr/bin/env python3
# Run dashboard server
import os
import uvicorn
from dashboard_server import app

if __name__ == "__main__":
    print("Starting Celestron Satellite Tracker Dashboard")
    print("Dashboard will be available at http://localhost:8000")
    print("Press Ctrl+C to stop")
    
    # Uncomment and set this if you want to enable weather data
    # os.environ["OPENWEATHER_API_KEY"] = "your_api_key_here"
    
    uvicorn.run(app, host="0.0.0.0", port=8000) 