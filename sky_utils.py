# sky_utils.py
from skyfield.api import Topos, load, EarthSatellite
from skyfield.framelib import ecliptic_frame
import numpy as np
from datetime import datetime, timezone, timedelta
from logger_setup import setup_logger

logger = setup_logger(__name__)
ts = load.timescale()

MIN_ELEVATION_DEG = 20.0

def parse_tle(tle_data: dict) -> EarthSatellite | None:
    if not tle_data or "tle" not in tle_data or not tle_data["tle"]:
        logger.error("Invalid TLE data provided for parsing.")
        return None
    tle_lines = tle_data["tle"].splitlines()
    # N2YO TLE format might have \r\n, ensure clean lines
    line1 = tle_lines[0].strip()
    line2 = tle_lines[1].strip()
    sat_name = tle_data.get("info", {}).get("satname", "Unknown Satellite")
    try:
        return EarthSatellite(line1, line2, sat_name, ts)
    except Exception as e:
        logger.error(f"Skyfield error parsing TLE for {sat_name}: {e}\nL1: '{line1}'\nL2: '{line2}'")
        return None

def calculate_trajectory_for_pass(satellite: EarthSatellite, observer_location: Topos,
                                  start_utc: int, end_utc: int) -> list:
    """
    Calculates trajectory (timestamp, az, el, ra, dec) every second for the given pass.
    Filters for elevation >= MIN_ELEVATION_DEG.
    RA/Dec are astrometric J2000.
    """
    trajectory = []
    current_time = datetime.fromtimestamp(start_utc, timezone.utc)
    end_time_dt = datetime.fromtimestamp(end_utc, timezone.utc)

    # This is the Skyfield object representing the difference in position
    # between the satellite and the observer's location.
    difference = satellite - observer_location

    while current_time <= end_time_dt:
        t = ts.utc(current_time)
        
        # Now, evaluate this difference at time t to get the apparent position
        # of the satellite as seen from the observer_location.
        apparent_pos = difference.at(t)
        
        el, az, _ = apparent_pos.altaz()
        # For RA/Dec, you still observe the satellite from the Earth's center (geocentric)
        # and then transform to the observer's location for Alt/Az,
        # or get the apparent RA/Dec directly from the topocentric position.
        # The radec() method on a topocentric position gives apparent RA/Dec.
        ra, dec, _ = apparent_pos.radec() # Apparent Astrometric J2000, defaults to ICRS

        if el.degrees >= MIN_ELEVATION_DEG:
            trajectory.append({
                "timestamp": int(current_time.timestamp()),
                "azimuth_deg": az.degrees,
                "elevation_deg": el.degrees,
                "az_rad_celestron": az.radians, 
                "el_rad_celestron": el.radians, 
                "ra_hours": ra.hours,
                "dec_deg_sky": dec.degrees,
            })
        current_time += timedelta(seconds=1)
    
    logger.debug(f"Calculated {len(trajectory)} points above {MIN_ELEVATION_DEG} deg for {satellite.name}")
    return trajectory
def get_observer_location(lat: float, lon: float, alt_m: float) -> Topos:
    return Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=alt_m)