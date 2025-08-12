import asyncio
import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import configparser
import signal
import uvicorn
import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import pytz

from logger_setup import setup_logger
from celestron_ws_client import CelestronWsClient
from n2yo_api import get_tle, get_visual_passes
from sky_utils import parse_tle, calculate_trajectory_for_pass, get_observer_location

# Setup
logger = setup_logger("dashboard")

# Lifespan manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    logger.info("Starting up dashboard server...")
    # Start client update loop
    asyncio.create_task(update_websocket_clients())
    # Connect to telescope on startup
    asyncio.create_task(connect_telescope())
    yield
    # Shutdown logic
    logger.info("Shutting down dashboard server...")
    if telescope_client:
        await telescope_client.close()
        logger.info("Closed telescope connection.")

app = FastAPI(title="Celestron Satellite Tracker Dashboard", lifespan=lifespan)
CONFIG_FILE = "config.ini"
TLE_PLAN_FILE = Path("tle_plan_schedule.json")
TRAJECTORY_FILE = Path("trajectory_points.json")

# Load config
config = configparser.ConfigParser()
if not Path(CONFIG_FILE).exists():
    logger.critical(f"Configuration file '{CONFIG_FILE}' not found.")
    exit(1)
config.read(CONFIG_FILE)

# Observer location
OBSERVER_LAT = config.getfloat('OBSERVER', 'latitude')
OBSERVER_LON = config.getfloat('OBSERVER', 'longitude')
OBSERVER_ALT_M = config.getfloat('OBSERVER', 'altitude_m')
N2YO_API_KEY = config.get('N2YO', 'api_key')
ORIGIN_WEBSOCKET_URI_BASE = config.get('CELESTRON', 'origin_ip').split(';')[0].strip()
ORIGIN_WEBSOCKET_URI = f"ws://{ORIGIN_WEBSOCKET_URI_BASE}/SmartScope-1.0/mountControlEndpoint"

# Static files and templates
templates = Jinja2Templates(directory="templates")
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("static/js", exist_ok=True)
os.makedirs("static/css", exist_ok=True)
os.makedirs("static/data", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Global state
telescope_client = None
connection_stats = {
    "connection_attempts": 0,
    "successful_connections": 0,
    "disconnections": 0,
    "last_connected": None,
    "last_disconnected": None,
    "current_status": "Disconnected",
    "uptime_seconds": 0,
    "connection_start_time": None,
    "ping_responses": [],
    "error_log": []
}

# Active client websockets for updating the dashboard
active_dashboard_clients = set()

# Weather data cache
weather_data_cache = {
    "last_updated": None,
    "forecast": None
}

# WeatherAPI.com API Key (Hardcoded as requested)
WEATHERAPI_COM_KEY = "486a7baaf9ab4c0586e212440251405"

async def get_weather_data():
    """Fetch weather data from WeatherAPI.com for telescope location"""
    if (weather_data_cache["last_updated"] is not None and
        (datetime.now() - weather_data_cache["last_updated"]).total_seconds() < 1800): # Cache for 30 minutes
        return weather_data_cache["forecast"]

    if not WEATHERAPI_COM_KEY:
        logger.warning("WeatherAPI.com API key not set.")
        return {"error": "WeatherAPI.com API key not configured."}

    url = "http://api.weatherapi.com/v1/forecast.json"
    params = {
        "key": WEATHERAPI_COM_KEY,
        "q": f"{OBSERVER_LAT},{OBSERVER_LON}",
        "days": 2,  # Fetch for today and tomorrow to ensure we can get next 12 hours
        "aqi": "no",
        "alerts": "no"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            processed_data = []
            if "forecast" in data and "forecastday" in data["forecast"] and len(data["forecast"]["forecastday"]) > 0:
                all_hourly_forecast = []
                for day_forecast in data["forecast"]["forecastday"]:
                    all_hourly_forecast.extend(day_forecast.get("hour", []))
                
                current_time_epoch = int(time.time())
                
                # Filter for the next 12 hours from the current time
                future_hourly_forecast = [
                    h for h in all_hourly_forecast
                    if h["time_epoch"] >= current_time_epoch
                ][:12] # Get up to 12 future hours

                if not future_hourly_forecast and len(all_hourly_forecast) > 0:
                    # Fallback if no future hours (e.g., very end of the second day data)
                    # Take the last available hour as a current snapshot
                    future_hourly_forecast = [all_hourly_forecast[-1]]

                for hour_data in future_hourly_forecast:
                    dt_utc = datetime.fromtimestamp(hour_data["time_epoch"], tz=timezone.utc)
                    # Convert to Pacific Time
                    pacific_tz = pytz.timezone('America/Los_Angeles')
                    dt_pacific = dt_utc.astimezone(pacific_tz)

                    clouds = hour_data.get("cloud", 0) # Percentage
                    visibility_km = hour_data.get("vis_km", 0)
                    humidity = hour_data.get("humidity", 0)
                    wind_kph = hour_data.get("wind_kph", 0)
                    temp_c = hour_data.get("temp_c")
                    condition_text = hour_data.get("condition", {}).get("text", "N/A")

                    # Determine sky conditions (simplified)
                    if clouds < 20:
                        sky_condition = "Clear"
                    elif clouds < 60:
                        sky_condition = "Partly Cloudy"
                    else:
                        sky_condition = "Cloudy"

                    # Assess observation conditions (simplified)
                    # WeatherAPI free plan might not have detailed visibility for "Excellent" rating often
                    if clouds < 30 and visibility_km >= 10 and wind_kph < 20: # visibility in km
                        observation_rating = "Excellent"
                    elif clouds < 60 and visibility_km >= 5 and wind_kph < 30:
                        observation_rating = "Good"
                    elif clouds < 80 and visibility_km >= 1:
                        observation_rating = "Fair"
                    else:
                        observation_rating = "Poor"

                    processed_data.append({
                        "time": dt_pacific.strftime("%H:%M PST"),
                        "clouds": clouds,
                        "visibility_km": visibility_km,
                        "humidity": humidity,
                        "wind_speed": round(wind_kph / 3.6, 1), # Convert kph to m/s approx
                        "temperature": temp_c,
                        "sky_condition": sky_condition,
                        "observation_rating": observation_rating,
                        "condition_text": condition_text
                    })
            
            if not processed_data: # Handle case where no future hours are available for today
                processed_data = [{"error": "Hourly forecast data not available for the next 6 hours."}]


            weather_data_cache["forecast"] = processed_data
            weather_data_cache["last_updated"] = datetime.now()
            return processed_data

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching weather data from WeatherAPI.com: {e.response.status_code} - {e.response.text}")
        return {"error": f"HTTP error {e.response.status_code} fetching weather data. Check API key and location."}
    except Exception as e:
        logger.error(f"Error fetching weather data from WeatherAPI.com: {e}")
        return {"error": str(e)}

async def update_websocket_clients():
    """Send updates to all connected dashboard clients"""
    while True:
        if active_dashboard_clients:
            data = {
                "connection_stats": connection_stats,
                "telescope_status": await get_telescope_status() if telescope_client and telescope_client.is_connected else None,
                "upcoming_passes": await get_upcoming_passes(),
                "current_time": datetime.now().isoformat(),
                "weather": await get_weather_data()
            }
            
            clients_to_remove = set()
            for ws in active_dashboard_clients:
                try:
                    await ws.send_json(data)
                except Exception:
                    clients_to_remove.add(ws)
            
            # Remove disconnected clients
            active_dashboard_clients.difference_update(clients_to_remove)
            
        # Update every second
        await asyncio.sleep(1)

async def get_telescope_status():
    """Get current telescope status"""
    if not telescope_client or not telescope_client.is_connected:
        return None
    
    try:
        system_version = await telescope_client.get_system_version()
        mount_status = await telescope_client.get_mount_status()
        env_status = await telescope_client.get_environment_status()
        
        # Update connection uptime
        if connection_stats["connection_start_time"]:
            connection_stats["uptime_seconds"] = (datetime.now() - connection_stats["connection_start_time"]).total_seconds()
        
        return {
            "system_version": system_version.get("Version") if system_version else "Unknown",
            "mount": {
                "battery_level": mount_status.get("BatteryLevel") if mount_status else "Unknown",
                "battery_voltage": mount_status.get("BatteryVoltage") if mount_status else 0.0,
                "is_aligned": mount_status.get("IsAligned", False) if mount_status else False,
                "is_tracking": mount_status.get("IsTracking", False) if mount_status else False,
                "timestamp": f"{mount_status.get('Date', '')} {mount_status.get('Time', '')}" if mount_status else "Unknown"
            },
            "environment": {
                "ambient_temp": env_status.get("AmbientTemperature") if env_status else "Unknown",
                "humidity": env_status.get("Humidity") if env_status else "Unknown",
                "dew_point": env_status.get("DewPoint") if env_status else "Unknown"
            }
        }
    except Exception as e:
        logger.error(f"Error getting telescope status: {e}")
        return {"error": str(e)}

async def get_upcoming_passes():
    """Get upcoming satellite passes"""
    if not TLE_PLAN_FILE.exists():
        return []
    
    try:
        with open(TLE_PLAN_FILE, 'r') as f:
            passes = json.load(f)
        
        now_utc_ts = int(datetime.now(timezone.utc).timestamp())
        upcoming = [p for p in passes if p['startUTC_actual'] > now_utc_ts]
        upcoming.sort(key=lambda p: p['startUTC_actual'])
        
        # Add countdown
        for p in upcoming:
            seconds_to_start = p['startUTC_actual'] - now_utc_ts
            countdown = str(timedelta(seconds=max(0, seconds_to_start)))
            p['countdown'] = countdown
        
        return upcoming[:5]  # Return next 5 passes
    except Exception as e:
        logger.error(f"Error loading upcoming passes: {e}")
        return []

async def connect_telescope():
    """Connect to the telescope"""
    global telescope_client
    
    # Initialize client if not already done
    if telescope_client is None:
        telescope_client = CelestronWsClient(ORIGIN_WEBSOCKET_URI)
    
    # Update stats
    connection_stats["connection_attempts"] += 1
    
    # Attempt connection
    success = await telescope_client.connect()
    
    if success:
        connection_stats["successful_connections"] += 1
        connection_stats["last_connected"] = datetime.now()
        connection_stats["current_status"] = "Connected"
        connection_stats["connection_start_time"] = datetime.now()
        logger.info("Successfully connected to telescope")
    else:
        connection_stats["error_log"].append({
            "timestamp": datetime.now().isoformat(),
            "error": "Failed to connect to telescope"
        })
        connection_stats["current_status"] = "Connection Failed"
        logger.error("Failed to connect to telescope")
    
    return success

# Event handlers for telescope connection
async def handle_telescope_disconnect():
    """Update stats when telescope disconnects"""
    connection_stats["disconnections"] += 1
    connection_stats["last_disconnected"] = datetime.now()
    connection_stats["current_status"] = "Disconnected"
    connection_stats["connection_start_time"] = None
    logger.warning("Telescope disconnected")

# Routes
@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """Serve the main dashboard"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time dashboard updates"""
    await websocket.accept()
    active_dashboard_clients.add(websocket)
    
    try:
        while True:
            # Wait for messages from the client
            message = await websocket.receive_text()
            data = json.loads(message)
            
            # Handle client commands
            if data.get("command") == "connect_telescope":
                success = await connect_telescope()
                await websocket.send_json({"command_result": "connect_telescope", "success": success})
            
            elif data.get("command") == "disconnect_telescope":
                if telescope_client:
                    await telescope_client.close()
                    await handle_telescope_disconnect()
                await websocket.send_json({"command_result": "disconnect_telescope", "success": True})
                
    except WebSocketDisconnect:
        active_dashboard_clients.remove(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in active_dashboard_clients:
            active_dashboard_clients.remove(websocket)

@app.get("/api/connection-stats")
async def get_connection_stats():
    """Get connection statistics"""
    return JSONResponse(connection_stats)

@app.get("/api/telescope-status")
async def api_telescope_status():
    """Get current telescope status"""
    return JSONResponse(await get_telescope_status())

@app.get("/api/upcoming-passes")
async def api_upcoming_passes():
    """Get upcoming satellite passes"""
    return JSONResponse(await get_upcoming_passes())

@app.get("/api/weather")
async def api_weather():
    """Get weather forecast"""
    return JSONResponse(await get_weather_data())

if __name__ == "__main__":
    # Register shutdown handler
    def handle_exit(signum, frame):
        if telescope_client:
            asyncio.run(telescope_client.close())
            print("Closed telescope connection")
        print("Exiting dashboard server")
    
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    # Start the server
    uvicorn.run(app, host="0.0.0.0", port=8000) 