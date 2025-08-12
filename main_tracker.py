# main_tracker.py
import asyncio
import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import configparser

from rich.table import Table
from rich.text import Text
from rich.panel import Panel

from logger_setup import setup_logger, console
from n2yo_api import get_tle, get_visual_passes
from sky_utils import parse_tle, calculate_trajectory_for_pass, get_observer_location, MIN_ELEVATION_DEG
from celestron_ws_client import CelestronWsClient

logger = setup_logger("main_tracker")

CONFIG_FILE = "config.ini"
COOLDOWN_SECONDS = 2 * 60  # 2 minutes
PRE_POSITION_LEAD_TIME_SECONDS = 45 
MAX_N2YO_REQUESTS_PER_HOUR = 950 
N2YO_REQUEST_DELAY_SECONDS = 3600 / MAX_N2YO_REQUESTS_PER_HOUR + 0.1

# --- Configuration Loading --- (Same as before)
config = configparser.ConfigParser()
if not Path(CONFIG_FILE).exists():
    logger.critical(f"[bold red]Configuration file '{CONFIG_FILE}' not found. Please create it.[/]")
    exit(1)
config.read(CONFIG_FILE)

try:
    OBSERVER_LAT = config.getfloat('OBSERVER', 'latitude')
    OBSERVER_LON = config.getfloat('OBSERVER', 'longitude')
    OBSERVER_ALT_M = config.getfloat('OBSERVER', 'altitude_m')
    N2YO_API_KEY = config.get('N2YO', 'api_key')
    ORIGIN_WEBSOCKET_URI_BASE = config.get('CELESTRON', 'origin_ip').split(';')[0].strip()
    NORAD_FILE_PATH = Path(config.get('CELESTRON', 'norad_file_path'))
    TLE_PLAN_FILE = Path(config.get('CELESTRON', 'tle_plan_file'))
    TRAJECTORY_FILE = Path(config.get('CELESTRON', 'trajectory_file'))
    
    CAM_EXPOSURE_SEC = config.getfloat('CAMERA', 'exposure_seconds')
    CAM_ISO = config.getint('CAMERA', 'iso')
    CAM_BINNING = config.getint('CAMERA', 'binning')
    CAM_BIT_DEPTH = config.getint('CAMERA', 'bit_depth')
    CAM_IMAGE_COOLDOWN_SEC = config.getint('CAMERA', 'image_cooldown_seconds')

except (configparser.NoSectionError, configparser.NoOptionError) as e:
    logger.critical(f"[bold red]Error in configuration file '{CONFIG_FILE}': {e}[/]")
    exit(1)

ORIGIN_WEBSOCKET_URI = f"ws://{ORIGIN_WEBSOCKET_URI_BASE}/SmartScope-1.0/mountControlEndpoint"
OBSERVATIONS_DIR = Path("observations")
OBSERVATIONS_DIR.mkdir(exist_ok=True)
OBSERVER_SKYFIELD_LOCATION = get_observer_location(OBSERVER_LAT, OBSERVER_LON, OBSERVER_ALT_M)

# --- Schedule Generation ---
def generate_pass_schedule():
    logger.info(f"Generating new pass schedule using '{NORAD_FILE_PATH}'.")
    if not NORAD_FILE_PATH.exists():
        logger.error(f"[bold red]NORAD ID file not found: {NORAD_FILE_PATH}[/]")
        return None, None

    with open(NORAD_FILE_PATH, 'r') as f:
        norad_ids_str = f.read().strip()
    if not norad_ids_str:
        logger.error(f"[bold red]NORAD ID file is empty: {NORAD_FILE_PATH}[/]")
        return None, None
        
    norad_ids = [int(nid.strip()) for nid in norad_ids_str.split(',') if nid.strip()]
    
    # Calculate the number of days to query based on time until 5 AM next morning
    now = datetime.now(timezone.utc)
    
    # Determine target 5 AM:
    # If current hour is < 5, target is 5 AM today.
    # Otherwise, target is 5 AM tomorrow.
    target_5_am = now.replace(hour=5, minute=0, second=0, microsecond=0)
    if now.hour >= 5:
        target_5_am += timedelta(days=1)

    duration_to_target_5_am = target_5_am - now
    
    # Convert duration to days for the API call, rounding up, minimum 1 day
    # N2YO API takes an integer number of days.
    # Add a small buffer (e.g., 1 hour) to ensure we capture passes around 5 AM.
    days_to_query = (duration_to_target_5_am.total_seconds() + 3600) / (24 * 3600)
    days_to_query = max(1, int(days_to_query) + (1 if days_to_query % 1 > 0.01 else 0)) # round up
    
    logger.info(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info(f"Targeting passes until: {target_5_am.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info(f"Calculated query window: {duration_to_target_5_am}, requesting {days_to_query} day(s) from N2YO.")

    all_passes_raw = []
    for i, norad_id in enumerate(norad_ids):
        logger.info(f"Fetching passes for NORAD ID: {norad_id} ({i+1}/{len(norad_ids)})")
        passes = get_visual_passes(norad_id, OBSERVER_LAT, OBSERVER_LON, OBSERVER_ALT_M, 
                                   days=days_to_query, min_visibility_seconds=0, api_key=N2YO_API_KEY)
        all_passes_raw.extend(passes)
        time.sleep(N2YO_REQUEST_DELAY_SECONDS) 

    if not all_passes_raw:
        logger.warning("No passes found for any NORAD ID.")
        return [], []

    all_passes_raw.sort(key=lambda p: p['startUTC'])
    
    scheduled_plan = []
    trajectories_data = {} 
    last_pass_end_time = 0
    now_utc_ts = int(datetime.now(timezone.utc).timestamp())

    for p_raw in all_passes_raw:
        # Filter out passes that end after our target 5 AM or have already ended
        if p_raw['endUTC'] < now_utc_ts or p_raw['startUTC'] > int(target_5_am.timestamp()):
            if p_raw['startUTC'] > int(target_5_am.timestamp()):
                logger.debug(f"Skipping pass for {p_raw.get('satname', 'N/A')} (NORAD {p_raw['norad_id']}) as it starts after target 5 AM ({target_5_am.strftime('%H:%M:%S %Z')}).")
            continue

        if not scheduled_plan or (p_raw['startUTC'] > last_pass_end_time + COOLDOWN_SECONDS):
            logger.info(f"Fetching TLE for {p_raw['satname']} (NORAD {p_raw['norad_id']}) for pass starting at {datetime.fromtimestamp(p_raw['startUTC'], timezone.utc)}")
            tle_info = get_tle(p_raw['norad_id'], N2YO_API_KEY)
            time.sleep(N2YO_REQUEST_DELAY_SECONDS)
            if not tle_info:
                logger.warning(f"Could not get TLE for NORAD {p_raw['norad_id']}, skipping pass.")
                continue
            
            satellite = parse_tle(tle_info)
            if not satellite:
                logger.warning(f"Could not parse TLE for NORAD {p_raw['norad_id']}, skipping pass.")
                continue

            pass_trajectory = calculate_trajectory_for_pass(satellite, OBSERVER_SKYFIELD_LOCATION, 
                                                            p_raw['startUTC'], p_raw['endUTC'])
            
            if not pass_trajectory:
                logger.info(f"Pass for {satellite.name} (NORAD {p_raw['norad_id']}) has no points above {MIN_ELEVATION_DEG} deg. Skipping.")
                continue

            actual_start_utc = pass_trajectory[0]['timestamp']
            actual_end_utc = pass_trajectory[-1]['timestamp']
            max_el_in_traj = max(pt['elevation_deg'] for pt in pass_trajectory)

            if scheduled_plan and (actual_start_utc <= last_pass_end_time + COOLDOWN_SECONDS):
                 logger.info(f"Pass for {satellite.name} (refined) overlaps with previous. Skipping.")
                 continue

            pass_details = {
                "norad_id": p_raw['norad_id'], "satname": satellite.name,
                "startUTC_n2yo": p_raw['startUTC'], "endUTC_n2yo": p_raw['endUTC'],
                "startUTC_actual": actual_start_utc, "endUTC_actual": actual_end_utc,
                "maxElevation_n2yo": p_raw['maxEl'], "maxElevation_actual": max_el_in_traj,
                "tle": tle_info['tle'] 
            }
            scheduled_plan.append(pass_details)
            
            pass_id = f"{p_raw['norad_id']}_{actual_start_utc}"
            trajectories_data[pass_id] = pass_trajectory
            last_pass_end_time = actual_end_utc
            logger.info(f"[bold green]Scheduled pass for {satellite.name}[/] (NORAD {p_raw['norad_id']}) from {datetime.fromtimestamp(actual_start_utc, timezone.utc)} to {datetime.fromtimestamp(actual_end_utc, timezone.utc)}")
        else:
            logger.info(f"Skipping overlapping/too-close pass for NORAD {p_raw['norad_id']} (satname: {p_raw.get('satname', 'N/A')})")

    with open(TLE_PLAN_FILE, 'w') as f:
        json.dump(scheduled_plan, f, indent=4)
    logger.info(f"TLE plan schedule saved to {TLE_PLAN_FILE}")
    
    with open(TRAJECTORY_FILE, 'w') as f:
        json.dump(trajectories_data, f, indent=4)
    logger.info(f"Trajectory points saved to {TRAJECTORY_FILE}")
    
    return scheduled_plan, trajectories_data

# --- System Health Check ---
async def perform_system_health_check(ws_client: CelestronWsClient):
    logger.info("Performing System Health Check...")
    table = Table(title="Celestron Origin System Health Check", show_lines=True)
    table.add_column("Component", style="cyan", no_wrap=True)
    table.add_column("Check", style="magenta")
    table.add_column("Status/Value", style="green")

    async def check_and_add(component, check_name, awaitable_func, *args, value_keys=None, status_key=None, error_val="Error/N/A"):
        status_text = Text(error_val, style="bold red")
        try:
            response = await awaitable_func(*args)
            if response and response.get("ErrorCode", -1) == 0:
                if value_keys: # Display specific values
                    val_str = ""
                    if isinstance(value_keys, str): value_keys = [value_keys]
                    for key in value_keys:
                        val = response.get(key)
                        if isinstance(val, float): val_str += f"{key}: {val:.2f} "
                        elif isinstance(val, bool): val_str += f"{key}: {'Yes' if val else 'No'} "
                        else: val_str += f"{key}: {val} "
                    status_text = Text(val_str.strip(), style="green")
                elif status_key: # Check a boolean status key
                    if response.get(status_key, False):
                        status_text = Text("OK / True", style="green")
                    else:
                        status_text = Text(f"Check Failed / False ({status_key})", style="yellow")
                else:
                    status_text = Text("OK", style="green")
            elif response:
                 status_text = Text(f"Error Code: {response.get('ErrorCode')}", style="red")

        except Exception as e:
            logger.error(f"Exception during health check for {component} - {check_name}: {e}")
            status_text = Text(f"Exception: {str(e)[:30]}...", style="bold red")
        table.add_row(component, check_name, status_text)

    # System
    await check_and_add("System", "Version", ws_client.get_system_version, value_keys="Version")
    await check_and_add("System", "Model", ws_client.get_system_model, value_keys="Value")
    
    # Disk
    disk_resp = await ws_client.get_disk_status()
    if disk_resp and disk_resp.get("ErrorCode", -1) == 0:
        free_gb = disk_resp.get("FreeBytes", 0) / (1024**3)
        capacity_gb = disk_resp.get("Capacity", 0) / (1024**3)
        level = disk_resp.get("Level", "Unknown")
        status_text = Text(f"{free_gb:.2f} GB free of {capacity_gb:.2f} GB ({level})", style="green" if level == "OK" else "yellow")
        table.add_row("Disk", "Storage", status_text)
    else:
        table.add_row("Disk", "Storage", Text("Error fetching", style="red"))

    # Factory Calibration
    await check_and_add("System", "Factory Calibrated", ws_client.get_factory_calibration_status, status_key="IsCalibrated")

    # Mount
    mount_resp = await ws_client.get_mount_status()
    if mount_resp and mount_resp.get("ErrorCode", -1) == 0:
        battery = mount_resp.get("BatteryLevel", "N/A")
        voltage = mount_resp.get("BatteryVoltage", 0.0)
        is_aligned = "Yes" if mount_resp.get("IsAligned") else "No"
        is_tracking = "Yes" if mount_resp.get("IsTracking") else "No"
        dt_str = f"{mount_resp.get('Date', '')} {mount_resp.get('Time', '')} {mount_resp.get('TimeZone', '')}"
        status_text = Text(f"Battery: {battery} ({voltage:.2f}V), Aligned: {is_aligned}, Tracking: {is_tracking}\nTime: {dt_str.strip()}", style="green")
        table.add_row("Mount", "Main Status", status_text)
    else:
        table.add_row("Mount", "Main Status", Text("Error fetching", style="red"))
    
    # Camera
    await check_and_add("Camera", "Info", ws_client.get_camera_info, value_keys=["CameraName", "IsColor"])
    await check_and_add("Camera", "Filter", ws_client.get_camera_filter, value_keys="Filter")

    # Focuser
    await check_and_add("Focuser", "Status", ws_client.get_focuser_status, value_keys=["Position", "IsCalibrationComplete"])

    # Environment
    env_resp = await ws_client.get_environment_status()
    if env_resp and env_resp.get("ErrorCode", -1) == 0:
        amb_temp = env_resp.get("AmbientTemperature")
        humidity = env_resp.get("Humidity")
        dew_pt = env_resp.get("DewPoint")
        
        # Handle potential None values
        if amb_temp is not None and humidity is not None and dew_pt is not None:
            status_text = Text(f"Ambient: {amb_temp:.1f}°C, Humidity: {humidity:.1f}%, DewPt: {dew_pt:.1f}°C", style="green")
        else:
            status_text = Text("Some environment values not available", style="yellow")
        
        table.add_row("Environment", "Sensors", status_text)
    else:
        table.add_row("Environment", "Sensors", Text("Error fetching", style="red"))
    await check_and_add("Environment", "Fans", ws_client.get_environment_fans, value_keys=["CpuFanOn", "OtaFanOn"])
    
    # Dew Heater
    await check_and_add("DewHeater", "Status", ws_client.get_dew_heater_status, value_keys=["Mode", "HeaterLevel"])

    # Orientation Sensor
    orient_resp = await ws_client.get_orientation_sensor_status()
    if orient_resp and orient_resp.get("ErrorCode", -1) == 0:
        altitude = orient_resp.get("Altitude")
        status_text = Text(f"OTA Angle: {altitude}°", style="green")
        table.add_row("Orientation", "Sensor", status_text)
    else:
        table.add_row("Orientation", "Sensor", Text("Error fetching", style="red"))

    console.print(Panel(table, title="[bold]System Health Report[/bold]", border_style="blue", expand=False))
    logger.info("System Health Check Complete.")
    return True # Assuming if it runs through, it's "healthy enough" to proceed. Add more checks if needed.

# --- Main Tracking Logic --- (Same as before, but with el_rad_celestron, az_rad_celestron)
async def track_satellite_pass(ws_client: CelestronWsClient, pass_info: dict, trajectory: list):
    satname = pass_info['satname']
    norad_id = pass_info['norad_id']
    pass_start_dt = datetime.fromtimestamp(trajectory[0]['timestamp'], timezone.utc)
    pass_end_dt = datetime.fromtimestamp(trajectory[-1]['timestamp'], timezone.utc)

    logger.info(f"Preparing to track [bold yellow]{satname}[/] (NORAD {norad_id})")
    logger.info(f"Pass duration: {pass_start_dt.strftime('%H:%M:%S')} to {pass_end_dt.strftime('%H:%M:%S')} UTC")

    obs_time_str = pass_start_dt.strftime("%Y%m%d_%H%M%S")
    current_obs_dir_name = f"{satname.replace(' ', '_')}_{norad_id}_{obs_time_str}"
    current_obs_dir = OBSERVATIONS_DIR / current_obs_dir_name
    current_obs_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Observation images will be saved to: {current_obs_dir}")

    first_point = trajectory[0]
    pre_position_target_time = datetime.fromtimestamp(first_point['timestamp'], timezone.utc) - timedelta(seconds=PRE_POSITION_LEAD_TIME_SECONDS)
    
    wait_time_for_pre_pos = (pre_position_target_time - datetime.now(timezone.utc)).total_seconds()
    if wait_time_for_pre_pos > 0:
        logger.info(f"Waiting {wait_time_for_pre_pos:.1f}s for pre-positioning slew to {satname} at Az: {first_point['azimuth_deg']:.1f}, El: {first_point['elevation_deg']:.1f}")
        await asyncio.sleep(wait_time_for_pre_pos)
    
    logger.info(f"Executing pre-positioning slew for {satname} to start point (Alt/Az).")
    slew_response = await ws_client.goto_alt_azm(first_point['el_rad_celestron'], first_point['az_rad_celestron'])
    if not slew_response or slew_response.get("ErrorCode", -1) != 0:
        logger.error(f"Pre-positioning slew failed for {satname}. Aborting this pass.")
        return

    logger.info("Waiting for pre-positioning slew to complete...")
    slew_start_time = time.monotonic()
    while True:
        status = await ws_client.get_mount_status()
        if status and status.get("IsGotoOver", False):
            logger.info("Pre-positioning slew complete.")
            break
        if time.monotonic() - slew_start_time > 120: 
            logger.error("Timeout waiting for pre-positioning slew to complete. Aborting pass.")
            return
        await asyncio.sleep(1)

    wait_time_for_pass_start = (datetime.fromtimestamp(first_point['timestamp'], timezone.utc) - datetime.now(timezone.utc)).total_seconds()
    if wait_time_for_pass_start > 0:
        logger.info(f"Waiting {wait_time_for_pass_start:.1f}s for actual pass start of {satname}.")
        await asyncio.sleep(wait_time_for_pass_start)

    logger.info(f"Setting camera parameters: Exp={CAM_EXPOSURE_SEC}s, ISO={CAM_ISO}, Bin={CAM_BINNING}, Depth={CAM_BIT_DEPTH}")
    cam_param_resp = await ws_client.set_camera_parameters(CAM_EXPOSURE_SEC, CAM_ISO, CAM_BINNING, CAM_BIT_DEPTH)
    if not cam_param_resp or cam_param_resp.get("ErrorCode", -1) != 0:
        logger.error(f"Failed to set camera parameters for {satname}. Aborting this pass.")
        return

    logger.info(f"[bold cyan]Starting tracking and imaging for {satname}...[/]")
    image_counter = 0
    last_image_time = 0
    image_download_tasks = []

    for point in trajectory:
        current_time_utc = datetime.now(timezone.utc)
        point_time_utc = datetime.fromtimestamp(point['timestamp'], timezone.utc)

        if current_time_utc > point_time_utc + timedelta(seconds=5):
            logger.warning(f"Falling behind schedule for {satname}, skipping point {point_time_utc.strftime('%H:%M:%S')}")
            continue
        
        sleep_duration = (point_time_utc - current_time_utc).total_seconds()
        if sleep_duration > 0:
            await asyncio.sleep(sleep_duration)
        
        logger.debug(f"Tracking {satname}: Az={point['azimuth_deg']:.1f}, El={point['elevation_deg']:.1f}")
        await ws_client.goto_alt_azm(point['el_rad_celestron'], point['az_rad_celestron'])

        if time.monotonic() - last_image_time >= CAM_IMAGE_COOLDOWN_SEC:
            logger.info(f"Requesting image capture #{image_counter + 1} for {satname}")
            capture_resp = await ws_client.run_sample_capture(CAM_EXPOSURE_SEC, CAM_ISO, CAM_BINNING)
            if capture_resp and capture_resp.get("ErrorCode", -1) == 0:
                logger.info(f"Image capture #{image_counter + 1} initiated.")
                last_image_time = time.monotonic()
                image_counter += 1
            else:
                logger.warning(f"Failed to initiate image capture #{image_counter + 1}.")
        
        try:
            notification = ws_client.notification_queue.get_nowait()
            if notification.get("Source") == "ImageServer" and notification.get("Command") == "NewImageReady":
                img_loc = notification.get("FileLocation")
                img_type = notification.get("ImageType")
                logger.info(f"Received NewImageReady: Location='{img_loc}', Type='{img_type}'")
                if img_loc and img_type == "SAMPLE_CAPTURE": 
                    img_filename = Path(img_loc).name
                    save_img_path = current_obs_dir / f"{obs_time_str}_{img_filename}"
                    task = asyncio.create_task(ws_client.download_image(img_loc, str(save_img_path)))
                    image_download_tasks.append(task)
            else: 
                await ws_client.notification_queue.put(notification)
        except asyncio.QueueEmpty:
            pass 

    logger.info(f"[bold green]Finished tracking {satname}.[/]")
    
    if image_download_tasks:
        logger.info(f"Waiting for {len(image_download_tasks)} image downloads to complete...")
        results = await asyncio.gather(*image_download_tasks, return_exceptions=True)
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error(f"Download task {i} failed: {res}")
        logger.info("All image downloads attempted.")

# --- Main Application ---
async def main():
    logger.info("Satellite Tracking Application Started.")
    logger.info(f"Observer Location: Lat={OBSERVER_LAT}, Lon={OBSERVER_LON}, Alt={OBSERVER_ALT_M}m")

    plan = []
    trajectories = {}

    if TLE_PLAN_FILE.exists() and TRAJECTORY_FILE.exists():
        regen_choice = console.input(f"Found existing schedule files ('{TLE_PLAN_FILE}', '{TRAJECTORY_FILE}').\n"
                                     "Generate new satellite pass schedule? ([bold green]y[/bold green]/[bold red]N[/bold red]): ").strip().lower()
        if regen_choice == 'y':
            plan, trajectories = generate_pass_schedule()
        else:
            logger.info("Loading existing schedule...")
            try:
                with open(TLE_PLAN_FILE, 'r') as f:
                    plan = json.load(f)
                with open(TRAJECTORY_FILE, 'r') as f:
                    trajectories = json.load(f)
                logger.info(f"Loaded {len(plan)} passes from existing schedule.")
            except Exception as e:
                logger.error(f"Failed to load existing schedule: {e}. Please generate a new one.")
                plan, trajectories = generate_pass_schedule()
    else:
        logger.info("No existing schedule found. Generating new one.")
        plan, trajectories = generate_pass_schedule()

    if not plan or not trajectories:
        logger.critical("[bold red]No valid schedule to execute. Exiting.[/]")
        return

    now_utc_ts = int(datetime.now(timezone.utc).timestamp())
    upcoming_plan = [p for p in plan if p['endUTC_actual'] > now_utc_ts]
    upcoming_plan.sort(key=lambda p: p['startUTC_actual'])

    if not upcoming_plan:
        logger.info("[bold yellow]No upcoming passes in the loaded/generated schedule for tonight. Exiting.[/]")
        return
    
    logger.info(f"Found {len(upcoming_plan)} upcoming passes in the schedule.")
    for i, p_info in enumerate(upcoming_plan):
         start_dt = datetime.fromtimestamp(p_info['startUTC_actual'], timezone.utc)
         end_dt = datetime.fromtimestamp(p_info['endUTC_actual'], timezone.utc)
         logger.info(f"  {i+1}. {p_info['satname']} (NORAD {p_info['norad_id']}): {start_dt.strftime('%Y-%m-%d %H:%M:%S')} to {end_dt.strftime('%Y-%M-%S')} UTC, MaxEl: {p_info['maxElevation_actual']:.1f}°")

    ws_client = CelestronWsClient(ORIGIN_WEBSOCKET_URI)
    if not await ws_client.connect():
        logger.critical("[bold red]Could not connect to Celestron Origin. Check IP/hostname ('{ORIGIN_WEBSOCKET_URI_BASE}') and telescope status. Exiting.[/]")
        return

    # Perform System Health Check
    if not await perform_system_health_check(ws_client):
        logger.error("[bold red]System health check indicated issues. Please review. Exiting.[/]")
        await ws_client.close()
        return

    logger.info("Ensuring sidereal tracking is disabled for satellite operations.")
    tracking_off_resp = await ws_client.send_command("Mount", "EnableTracking", {"Value": False})
    if not tracking_off_resp or tracking_off_resp.get("ErrorCode", -1) != 0:
        logger.warning("Could not explicitly disable mount tracking. Proceeding with caution.")
    else:
        logger.info("Mount sidereal tracking confirmed disabled.")

    try:
        for i, pass_to_track in enumerate(upcoming_plan):
            pass_id = f"{pass_to_track['norad_id']}_{pass_to_track['startUTC_actual']}"
            trajectory_for_pass = trajectories.get(pass_id)

            if not trajectory_for_pass:
                logger.error(f"Trajectory not found for pass ID {pass_id} ({pass_to_track['satname']}). Skipping.")
                continue

            first_point_time = datetime.fromtimestamp(trajectory_for_pass[0]['timestamp'], timezone.utc)
            # Adjust wait_until_target_time to be relative to the current loop iteration
            # This means if the first pass took long, we don't oversleep for the next.
            prep_start_target_time = first_point_time - timedelta(seconds=PRE_POSITION_LEAD_TIME_SECONDS + 10) # +10s buffer
            current_wait_seconds = (prep_start_target_time - datetime.now(timezone.utc)).total_seconds()
            
            if current_wait_seconds > 0:
                logger.info(f"Next pass for [bold yellow]{pass_to_track['satname']}[/] starts tracking prep in {timedelta(seconds=int(current_wait_seconds))}.")
                logger.info(f"Sleeping for {current_wait_seconds:.0f} seconds...")
                await asyncio.sleep(current_wait_seconds)
            
            await track_satellite_pass(ws_client, pass_to_track, trajectory_for_pass)
            
            if i < len(upcoming_plan) - 1:
                logger.info(f"Cooldown period of {COOLDOWN_SECONDS // 60} minutes before next pass.")
                await asyncio.sleep(COOLDOWN_SECONDS)
            
    except KeyboardInterrupt:
        logger.info("User interrupted. Shutting down...")
    except Exception as e:
        logger.critical(f"An unhandled error occurred: {e}", exc_info=True)
    finally:
        if ws_client.is_connected:
            logger.info("Closing connection to Celestron Origin.")
            await ws_client.close()
        logger.info("Application finished.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user.")