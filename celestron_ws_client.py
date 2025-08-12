# celestron_ws_client.py
import asyncio
import aiohttp
import websockets
import json
import time
import random
from logger_setup import setup_logger
import ssl # For wss if needed, though origin.local is likely ws

logger = setup_logger(__name__)

class CelestronWsClient:
    def __init__(self, uri):
        self.uri = uri # e.g., "ws://origin.local/SmartScope-1.0/mountControlEndpoint"
        self.websocket = None
        self.sequence_id = 0
        self._is_connected = False # Socket connection established
        self._is_verified = False  # Verified by receiving a GetVersion response
        self.response_futures = {} # To match responses to commands by SequenceID
        self.notification_queue = asyncio.Queue()
        self.watchdog_task = None
        self.ping_counter = 0
        self.watchdog_interval = 5  # seconds
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.reconnect_backoff_min = 1  # seconds
        self.reconnect_backoff_max = 30  # seconds
        self.reconnect_in_progress = False
        
        # Connection metrics for dashboard
        self.connection_metrics = {
            "connection_attempts": 0,
            "successful_connections": 0,
            "disconnections": 0,
            "last_connected": None,
            "last_disconnected": None,
            "connection_start_time": None,
            "uptime_seconds": 0,
            "ping_responses": [],  # List of ping response time measurements
            "error_log": []  # List of connection-related errors
        }
        self.max_ping_history = 50  # Maximum number of ping responses to keep

    async def connect(self):
        if self.reconnect_in_progress:
            logger.info("Reconnection already in progress, not starting another.")
            return False
            
        # Reset connection state for clean start
        self.reconnect_in_progress = True
        self._is_verified = False
        
        # For the initial connection, we just check if websocket is None
        if self.websocket:
            logger.info("WebSocket object exists, closing it before reconnecting.")
            try:
                await self.websocket.close()
            except Exception as e:
                logger.debug(f"Error closing existing websocket: {e}")
            self.websocket = None
            
        # Update metrics
        self.connection_metrics["connection_attempts"] += 1
        
        try:
            logger.info(f"Attempting to connect to {self.uri}...")
            # For local 'origin.local', SSL context might not be needed or might need to be permissive
            # If 'wss://' and self-signed cert, you might need:
            # ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            # ssl_context.check_hostname = False
            # ssl_context.verify_mode = ssl.CERT_NONE
            # self.websocket = await websockets.connect(self.uri, ssl=ssl_context)
            
            connect_start_time = time.time()
            self.websocket = await websockets.connect(self.uri)
            connect_time_ms = (time.time() - connect_start_time) * 1000
            
            # DEBUG: Inspect the websocket object
            logger.info(f"WebSocket object type: {type(self.websocket)}")
            logger.info(f"WebSocket state: {self.websocket.state}")
            logger.info(f"Connection established in {connect_time_ms:.2f}ms")
            
            self._is_connected = True # Socket is connected
            logger.info(f"[bold green]Socket connected to {self.uri}[/]")
            
            # Start the listener task
            self._listen_task = asyncio.create_task(self._listen())
            
            # Initial command to verify connection
            version_response = await self.send_command("System", "GetVersion", {}, log_payload=False)
            if version_response and version_response.get("ErrorCode", -1) == 0:
                logger.info(f"Initial GetVersion successful: {version_response.get('Version')}")
                self._is_verified = True
                self.reconnect_attempts = 0  # Reset on successful connection
                
                # Update metrics
                self.connection_metrics["successful_connections"] += 1
                self.connection_metrics["last_connected"] = time.time()
                self.connection_metrics["connection_start_time"] = time.time()
                
                # Start the watchdog task after successful verification
                if self.watchdog_task is None or self.watchdog_task.done():
                    self.watchdog_task = asyncio.create_task(self._connection_watchdog())
                    logger.info("Started connection watchdog task")
                
                self.reconnect_in_progress = False
                return True
            else:
                logger.error("Initial GetVersion command failed after connection.")
                # Update error log
                self.connection_metrics["error_log"].append({
                    "timestamp": time.time(),
                    "error": "Initial GetVersion command failed after connecting to WebSocket"
                })
                # Keep only the last 50 errors
                if len(self.connection_metrics["error_log"]) > 50:
                    self.connection_metrics["error_log"] = self.connection_metrics["error_log"][-50:]
                
                await self.close() # Clean up if initial command fails
                self.reconnect_in_progress = False
                return False

        except (websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.InvalidURI,
                ConnectionRefusedError, OSError, websockets.exceptions.InvalidStatusCode) as e:
            logger.error(f"Connection to {self.uri} failed: {e}")
            # Update error log
            self.connection_metrics["error_log"].append({
                "timestamp": time.time(),
                "error": f"Connection failed: {str(e)}"
            })
            # Keep only the last 50 errors
            if len(self.connection_metrics["error_log"]) > 50:
                self.connection_metrics["error_log"] = self.connection_metrics["error_log"][-50:]
                
            self.websocket = None
            self._is_connected = False
            self._is_verified = False
            self.reconnect_in_progress = False
            return False
        except Exception as e: # Catch any other unexpected errors during connect
            logger.error(f"Unexpected error during connect: {e}")
            # Update error log
            self.connection_metrics["error_log"].append({
                "timestamp": time.time(),
                "error": f"Unexpected error: {str(e)}"
            })
            # Keep only the last 50 errors
            if len(self.connection_metrics["error_log"]) > 50:
                self.connection_metrics["error_log"] = self.connection_metrics["error_log"][-50:]
                
            self.websocket = None
            self._is_connected = False
            self._is_verified = False
            self.reconnect_in_progress = False
            return False

    async def reconnect(self):
        """Attempt to reconnect with exponential backoff"""
        if self.reconnect_in_progress:
            logger.info("Reconnection already in progress, not starting another.")
            return False
            
        self.reconnect_in_progress = True
        self.reconnect_attempts += 1
        
        if self.reconnect_attempts > self.max_reconnect_attempts:
            logger.error(f"Maximum reconnection attempts ({self.max_reconnect_attempts}) reached. Giving up.")
            # Update error log
            self.connection_metrics["error_log"].append({
                "timestamp": time.time(),
                "error": f"Maximum reconnection attempts ({self.max_reconnect_attempts}) reached"
            })
            # Keep only the last 50 errors
            if len(self.connection_metrics["error_log"]) > 50:
                self.connection_metrics["error_log"] = self.connection_metrics["error_log"][-50:]
                
            self.reconnect_in_progress = False
            return False
            
        # Calculate backoff with jitter to avoid reconnection storms
        backoff = min(
            self.reconnect_backoff_max,
            self.reconnect_backoff_min * (2 ** (self.reconnect_attempts - 1))
        )
        jitter = random.uniform(0.8, 1.2)  # Add ±20% jitter
        wait_time = backoff * jitter
        
        logger.info(f"Reconnection attempt {self.reconnect_attempts}/{self.max_reconnect_attempts} "
                   f"will start in {wait_time:.1f} seconds...")
        
        # Wait before reconnection attempt
        await asyncio.sleep(wait_time)
        
        # Clear notification queue to avoid processing stale notifications after reconnect
        try:
            while not self.notification_queue.empty():
                self.notification_queue.get_nowait()
                self.notification_queue.task_done()
            logger.info("Cleared notification queue before reconnection")
        except Exception as e:
            logger.error(f"Error clearing notification queue: {e}")
            
        # Attempt to reconnect
        success = await self.connect()
        self.reconnect_in_progress = False
        return success

    async def _connection_watchdog(self):
        """Watchdog task that periodically checks the connection health"""
        logger.info("Connection watchdog started")
        try:
            while self._is_connected:
                await asyncio.sleep(self.watchdog_interval)
                
                if not self._is_connected:
                    logger.warning("Watchdog detected connection is already marked as closed")
                    break
                    
                # Store current counter value
                current_ping = self.ping_counter
                
                try:
                    # Send GetVersion as a ping/heartbeat
                    logger.debug("Watchdog sending GetVersion heartbeat")
                    ping_start_time = time.time()
                    version_response = await self.send_command("System", "GetVersion", {}, log_payload=False, timeout=5.0)
                    ping_time_ms = (time.time() - ping_start_time) * 1000
                    
                    if version_response and version_response.get("ErrorCode", -1) == 0:
                        # Successful ping, increment counter
                        self.ping_counter += 1
                        logger.debug(f"Watchdog received response, ping counter: {self.ping_counter}, time: {ping_time_ms:.2f}ms")
                        self._is_verified = True
                        
                        # Record ping time for metrics
                        self.connection_metrics["ping_responses"].append({
                            "timestamp": time.time(),
                            "response_time": ping_time_ms
                        })
                        # Keep only the last N ping responses
                        if len(self.connection_metrics["ping_responses"]) > self.max_ping_history:
                            self.connection_metrics["ping_responses"] = self.connection_metrics["ping_responses"][-self.max_ping_history:]
                        
                        # Update uptime
                        if self.connection_metrics["connection_start_time"]:
                            self.connection_metrics["uptime_seconds"] = time.time() - self.connection_metrics["connection_start_time"]
                    else:
                        # Command sent but response was error or None
                        logger.warning("Watchdog heartbeat received error response or None")
                        # Update error log
                        self.connection_metrics["error_log"].append({
                            "timestamp": time.time(),
                            "error": "Watchdog heartbeat failed: No response or error response"
                        })
                        # Keep only the last 50 errors
                        if len(self.connection_metrics["error_log"]) > 50:
                            self.connection_metrics["error_log"] = self.connection_metrics["error_log"][-50:]
                            
                        if self._is_connected:  # Double-check we're still connected
                            await self.close()
                            asyncio.create_task(self.reconnect())
                        break
                except Exception as e:
                    logger.error(f"Watchdog heartbeat failed with exception: {e}")
                    # Update error log
                    self.connection_metrics["error_log"].append({
                        "timestamp": time.time(),
                        "error": f"Watchdog heartbeat exception: {str(e)}"
                    })
                    # Keep only the last 50 errors
                    if len(self.connection_metrics["error_log"]) > 50:
                        self.connection_metrics["error_log"] = self.connection_metrics["error_log"][-50:]
                        
                    if self._is_connected:  # Only try to reconnect if we think we're connected
                        await self.close()
                        asyncio.create_task(self.reconnect())
                    break
                    
        except asyncio.CancelledError:
            logger.info("Connection watchdog task cancelled")
        except Exception as e:
            logger.error(f"Unexpected error in connection watchdog: {e}")
            # Update error log
            self.connection_metrics["error_log"].append({
                "timestamp": time.time(),
                "error": f"Watchdog unexpected error: {str(e)}"
            })
            # Keep only the last 50 errors
            if len(self.connection_metrics["error_log"]) > 50:
                self.connection_metrics["error_log"] = self.connection_metrics["error_log"][-50:]
                
            if self._is_connected:
                await self.close()
                asyncio.create_task(self.reconnect())
        finally:
            logger.info("Connection watchdog stopped")

    async def _listen(self):
        try:
            # Ensure websocket is not None before entering loop
            if not self.websocket:
                logger.error("Listener started with no WebSocket object.")
                self._is_connected = False
                self._is_verified = False
                return

            async for message_str in self.websocket:
                try:
                    message = json.loads(message_str)
                    # logger.debug(f"RAW <RECV>: {message}")
                    
                    seq_id = message.get("SequenceID")
                    msg_type = message.get("Type")
                    source = message.get("Source")
                    command = message.get("Command")

                    log_msg_detail = f"Type: {msg_type}, Src: {source}, Cmd: {command}, SeqID: {seq_id}"
                    
                    # Check if this is a response to a GetVersion (our heartbeat)
                    if source == "System" and command == "GetVersion":
                        self.ping_counter += 1
                        self._is_verified = True
                        logger.debug(f"Received GetVersion response, ping counter: {self.ping_counter}")
                    
                    if msg_type == "Response":
                        if seq_id in self.response_futures and not self.response_futures[seq_id].done():
                            self.response_futures[seq_id].set_result(message)
                        else:
                            logger.warning(f"Received unmatched/late response: {log_msg_detail} - Payload: {json.dumps(message, indent=2)}")
                    elif msg_type == "Notification":
                        # Less verbose logging for frequent notifications if needed
                        if command not in ["GetStatus"]: # Example: mute frequent status notifications
                             logger.info(f"[cyan]<NOTIFY>[/] {log_msg_detail} - Payload: {json.dumps(message, indent=2)}")
                        else:
                             logger.debug(f"[cyan]<NOTIFY>[/] {log_msg_detail}") # Log frequent ones as debug
                        await self.notification_queue.put(message)
                    else:
                        logger.warning(f"Received unknown message type: {message}")

                except json.JSONDecodeError:
                    logger.error(f"Failed to decode JSON message: {message_str}")
                except Exception as e:
                    logger.error(f"Error processing incoming message: {e} - Message: {message_str}")
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"WebSocket connection closed by server/network: {e.code} {e.reason}")
            # Update metrics
            self.connection_metrics["disconnections"] += 1
            self.connection_metrics["last_disconnected"] = time.time()
            self.connection_metrics["error_log"].append({
                "timestamp": time.time(),
                "error": f"Connection closed: {e.code} {e.reason}"
            })
            # Keep only the last 50 errors
            if len(self.connection_metrics["error_log"]) > 50:
                self.connection_metrics["error_log"] = self.connection_metrics["error_log"][-50:]
        except Exception as e:
            logger.error(f"Exception in listener: {e}")
            # Update error log
            self.connection_metrics["error_log"].append({
                "timestamp": time.time(),
                "error": f"Listener exception: {str(e)}"
            })
            # Keep only the last 50 errors
            if len(self.connection_metrics["error_log"]) > 50:
                self.connection_metrics["error_log"] = self.connection_metrics["error_log"][-50:]
        finally:
            logger.info("Listener stopped. Initiating reconnection...")
            self._is_connected = False # Connection is definitively lost if listener exits
            self._is_verified = False
            
            # Update metrics
            self.connection_metrics["disconnections"] += 1
            self.connection_metrics["last_disconnected"] = time.time()
            
            if self.websocket: # Simplified check
                try:
                    await self.websocket.close()
                except Exception as e_close:
                    logger.debug(f"Exception while trying to close websocket in listener finally: {e_close}")
            self.websocket = None
            
            # Start reconnection unless this was an intentional close
            # This helps prevent reconnection storms when we deliberately close
            if not self.reconnect_in_progress:
                asyncio.create_task(self.reconnect())


    async def send_command(self, destination: str, command: str, payload: dict, timeout: float = 10.0, log_payload: bool = True):
        if not self.websocket:
            logger.error(f"WebSocket is not connected. Cannot send command {destination}:{command}.")
            return None

        self.sequence_id += 1
        current_seq_id = self.sequence_id
        
        message = {
            "Source": "WebApp", 
            "Destination": destination,
            "Command": command,
            "Type": "Command",
            "SequenceID": current_seq_id,
            **payload
        }
        
        try:
            log_entry = f"Dest: {destination}, Cmd: {command}, SeqID: {current_seq_id}"
            if log_payload:
                logger.info(f"[magenta]<SEND>[/] {log_entry}, Payload: {json.dumps(payload)}")
            else:
                logger.debug(f"<SEND> {log_entry}")

            command_start_time = time.time()
            await self.websocket.send(json.dumps(message))
            
            fut = asyncio.get_event_loop().create_future()
            self.response_futures[current_seq_id] = fut
            
            try:
                response = await asyncio.wait_for(fut, timeout=timeout)
                command_time_ms = (time.time() - command_start_time) * 1000
                
                log_response_detail = f"Src: {response.get('Source')}, Cmd: {response.get('Command')}, SeqID: {response.get('SequenceID')}"
                error_code = response.get("ErrorCode", 0)
                error_message = response.get("ErrorMessage", "")

                if error_code != 0:
                    logger.error(f"[bold red]<RESP_ERR>[/] {log_response_detail} - Code: {error_code}, Msg: '{error_message}' Payload: {json.dumps(response, indent=2)}")
                    # Update error log for non-GetVersion commands (to avoid spam from heartbeats)
                    if command != "GetVersion":
                        self.connection_metrics["error_log"].append({
                            "timestamp": time.time(),
                            "error": f"Command error: {destination}.{command} - Code: {error_code}, Message: {error_message}"
                        })
                        # Keep only the last 50 errors
                        if len(self.connection_metrics["error_log"]) > 50:
                            self.connection_metrics["error_log"] = self.connection_metrics["error_log"][-50:]
                else:
                    # Log successful responses, but be less verbose for frequent ones
                    if log_payload or command not in ["GetStatus", "GetVersion"]: 
                         logger.info(f"[green]<RESP_OK>[/] {log_response_detail} - Payload: {json.dumps(response, indent=2)}")
                    else:
                         logger.debug(f"<RESP_OK> {log_response_detail}")
                         
                    # Record response time for GetVersion commands (our heartbeats)
                    if command == "GetVersion" and destination == "System":
                        self.connection_metrics["ping_responses"].append({
                            "timestamp": time.time(),
                            "response_time": command_time_ms
                        })
                        # Keep only the last N ping responses
                        if len(self.connection_metrics["ping_responses"]) > self.max_ping_history:
                            self.connection_metrics["ping_responses"] = self.connection_metrics["ping_responses"][-self.max_ping_history:]
                
                return response
            except asyncio.TimeoutError:
                logger.error(f"Timeout waiting for response to SeqID {current_seq_id} ({destination}:{command})")
                # Update error log for non-GetVersion commands (to avoid spam from heartbeats)
                if command != "GetVersion":
                    self.connection_metrics["error_log"].append({
                        "timestamp": time.time(),
                        "error": f"Command timeout: {destination}.{command} (SeqID: {current_seq_id})"
                    })
                    # Keep only the last 50 errors
                    if len(self.connection_metrics["error_log"]) > 50:
                        self.connection_metrics["error_log"] = self.connection_metrics["error_log"][-50:]
                return None
            finally:
                if current_seq_id in self.response_futures: # Check if key exists before deleting
                    del self.response_futures[current_seq_id]

        except websockets.exceptions.ConnectionClosed:
            logger.error(f"Failed to send command {destination}:{command}: WebSocket connection closed.")
            self._is_connected = False # Update state
            self._is_verified = False
            self.websocket = None
            # Don't initiate reconnect here - the listener will detect the closed connection
            return None
        except Exception as e:
            logger.error(f"Error sending command {destination}:{command}: {e}")
            # Update error log for non-GetVersion commands (to avoid spam from heartbeats)
            if command != "GetVersion":
                self.connection_metrics["error_log"].append({
                    "timestamp": time.time(),
                    "error": f"Command error: {destination}.{command} - Exception: {str(e)}"
                })
                # Keep only the last 50 errors
                if len(self.connection_metrics["error_log"]) > 50:
                    self.connection_metrics["error_log"] = self.connection_metrics["error_log"][-50:]
            return None

    @property
    def is_connected(self):
        # Return true only if both socket is connected AND we've received a successful response
        return self._is_connected and self._is_verified
        
    def get_connection_metrics(self):
        """Return a copy of the connection metrics for dashboard display"""
        # Update uptime if connected
        if self._is_connected and self._is_verified and self.connection_metrics["connection_start_time"]:
            self.connection_metrics["uptime_seconds"] = time.time() - self.connection_metrics["connection_start_time"]
            
        # Return a copy to avoid external modification
        return dict(self.connection_metrics)

    async def close(self):
        # Cancel watchdog task
        if self.watchdog_task and not self.watchdog_task.done():
            self.watchdog_task.cancel()
            try:
                await self.watchdog_task
            except asyncio.CancelledError:
                pass
            self.watchdog_task = None
            
        if self.websocket:
            logger.info("Closing WebSocket connection.")
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error(f"Error during explicit websocket close: {e}")
        self.websocket = None
        self._is_connected = False
        self._is_verified = False
        
        # Update metrics
        if self.connection_metrics["connection_start_time"]:
            self.connection_metrics["disconnections"] += 1
            self.connection_metrics["last_disconnected"] = time.time()
            self.connection_metrics["connection_start_time"] = None

    # --- Specific Celestron Commands --- (rest of the methods are the same)
    async def get_system_version(self):
        return await self.send_command("System", "GetVersion", {}, log_payload=False)

    async def get_system_model(self):
        return await self.send_command("System", "GetModel", {})

    async def get_disk_status(self):
        return await self.send_command("Disk", "GetStatus", {})

    async def get_factory_calibration_status(self):
        return await self.send_command("FactoryCalibrationController", "GetStatus", {}, log_payload=False)

    async def get_mount_status(self):
        return await self.send_command("Mount", "GetStatus", {}, log_payload=False)

    async def get_camera_info(self):
        return await self.send_command("Camera", "GetCameraInfo", {})

    async def get_camera_filter(self):
        return await self.send_command("Camera", "GetFilter", {})

    async def get_focuser_status(self):
        return await self.send_command("Focuser", "GetStatus", {}, log_payload=False)

    async def get_environment_status(self):
        return await self.send_command("Environment", "GetStatus", {}, log_payload=False)
    
    async def get_environment_fans(self):
        return await self.send_command("Environment", "GetFans", {})

    async def get_dew_heater_status(self):
        return await self.send_command("DewHeater", "GetStatus", {})

    async def get_orientation_sensor_status(self):
        return await self.send_command("OrientationSensor", "GetStatus", {}, log_payload=False)

    async def goto_alt_azm(self, alt_rad: float, az_rad: float):
        payload = {"Alt": alt_rad, "Azm": az_rad}
        return await self.send_command("Mount", "GotoAltAzm", payload)

    async def set_camera_parameters(self, exposure_sec: float, iso: int, binning: int, bit_depth: int):
        payload = {
            "Exposure": exposure_sec,
            "ISO": iso,
            "Binning": binning,
            "BitDepth": bit_depth
        }
        return await self.send_command("Camera", "SetCaptureParameters", payload)

    async def run_sample_capture(self, exposure_sec: float, iso: int, binning: int):
        payload = {
            "ExposureTime": exposure_sec,
            "ISO": iso,
            "Binning": binning
        }
        return await self.send_command("TaskController", "RunSampleCapture", payload)
        
    async def download_image(self, file_location_on_origin: str, save_path: str):
        import aiohttp
        base_url = f"http://{self.uri.split('//')[1].split('/')[0]}"
        image_url = f"{base_url}/{file_location_on_origin.lstrip('/')}?t={int(time.time())}"
        logger.info(f"Attempting to download image from: {image_url}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    resp.raise_for_status()
                    with open(save_path, 'wb') as f:
                        while True:
                            chunk = await resp.content.read(1024)
                            if not chunk:
                                break
                            f.write(chunk)
                    logger.info(f"Image successfully downloaded to [cyan]{save_path}[/]")
                    return True
        except aiohttp.ClientError as e:
            logger.error(f"Error downloading image {image_url}: {e}")
            return False
        except IOError as e:
            logger.error(f"Error saving image to {save_path}: {e}")
            return False