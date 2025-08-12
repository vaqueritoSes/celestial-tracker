# n2yo_api.py
import requests
import time
from logger_setup import setup_logger

logger = setup_logger(__name__)

N2YO_BASE_URL = "https://api.n2yo.com/rest/v1/satellite"
# N2YO API allows 1000 transactions per hour. Be mindful.

def get_tle(norad_id: int, api_key: str) -> dict | None:
    url = f"{N2YO_BASE_URL}/tle/{norad_id}&apiKey={api_key}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("info", {}).get("transactioncount", 0) > 900:
            logger.warning(f"N2YO API transaction count nearing limit: {data['info']['transactioncount']}")
        if "tle" in data and data["tle"]:
            return data
        else:
            logger.error(f"No TLE data found for NORAD ID {norad_id}. Response: {data}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching TLE for {norad_id}: {e}")
        return None
    except ValueError as e: # JSONDecodeError
        logger.error(f"Error decoding JSON for TLE {norad_id}: {e}. Response text: {response.text if 'response' in locals() else 'N/A'}")
        return None


def get_visual_passes(norad_id: int, lat: float, lon: float, alt_m: float,
                        days: int, min_visibility_seconds: int, api_key: str) -> list:
    # min_visibility is actually min_elevation for radiopasses, 
    # but for visualpasses it's minimum duration of optical visibility.
    # For this project, we use radiopasses endpoint to get all passes above a certain elevation.
    # The "visualpasses" endpoint is more for human eye visibility.
    # We'll use "radiopasses" and set min_elevation to 0 to get all passes,
    # then filter elevation later with skyfield.
    
    # For this project, we'll use the 'radiopasses' endpoint for better control over min_elevation.
    # The N2YO doc mentions 'min_elevation' for radiopasses.
    # Let's assume we want all passes above horizon initially, then filter.
    min_elevation_for_pass = 0 # Degrees
    
    url = (f"{N2YO_BASE_URL}/radiopasses/{norad_id}/{lat}/{lon}/{alt_m}/"
           f"{days}/{min_elevation_for_pass}&apiKey={api_key}")
    try:
        logger.debug(f"Requesting passes for NORAD {norad_id} from URL: {url.replace(api_key, '***')}")
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

        if data.get("info", {}).get("transactioncount", 0) > 900:
            logger.warning(f"N2YO API transaction count nearing limit: {data['info']['transactioncount']}")

        if "passes" in data:
            logger.info(f"Found {len(data['passes'])} raw passes for NORAD {norad_id}.")
            # Add NORAD ID to each pass for later reference
            for p_data in data['passes']:
                p_data['norad_id'] = norad_id
                p_data['satname'] = data.get('info', {}).get('satname', 'Unknown')
            return data["passes"]
        else:
            logger.warning(f"No passes found for NORAD ID {norad_id}. Response: {data}")
            return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching passes for {norad_id}: {e}")
        return []
    except ValueError as e: # JSONDecodeError
        logger.error(f"Error decoding JSON for passes {norad_id}: {e}. Response text: {response.text if 'response' in locals() else 'N/A'}")
        return []