"""REST API server for the MVP Food Computer dashboard.

Serves the web dashboard and provides JSON API endpoints for sensor data.
Runs in demo mode automatically when not on Raspberry Pi hardware.

Usage:
    python3 MVP/python/app.py          # from project root
    python3 app.py                     # from MVP/python/
    MVP_DEMO=1 python3 app.py          # force demo mode
    MVP_PORT=9000 python3 app.py       # custom port
"""

import json
import math
import os
import random
import sys
import time
import threading
from collections import deque
from datetime import datetime, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

# Determine the MVP root directory.  The MVP_DIR environment variable takes
# precedence; otherwise we derive it from this script's location
# (MVP/python/app.py -> two levels up is the project root, then into MVP/).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

if os.environ.get('MVP_DIR'):
    MVP_DIR = os.environ['MVP_DIR']
else:
    # SCRIPT_DIR is MVP/python, go up one level to get MVP/
    MVP_DIR = os.path.dirname(SCRIPT_DIR)

# Ensure the python directory is on the path so we can import sibling modules
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# ---------------------------------------------------------------------------
# Import project modules
# ---------------------------------------------------------------------------

from LogUtil import get_logger
from DewPoint import getDewPoint
from env import env

# ---------------------------------------------------------------------------
# Configuration from env.py
# ---------------------------------------------------------------------------

LIGHT_ON = env.get('lights', {}).get('On', '06:30:00')
LIGHT_OFF = env.get('lights', {}).get('Off', '22:00:00')
TARGET_TEMP = env.get('thermostat', {}).get('targetTemp', 25)

# Server configuration
PORT = int(os.environ.get('MVP_PORT', 8000))
WEB_DIR = os.path.join(MVP_DIR, 'web')

logger = get_logger('AppServer')

# ---------------------------------------------------------------------------
# Demo mode detection
# ---------------------------------------------------------------------------

DEMO_MODE = False
_sensor_module = None
_relay_module = None

if os.environ.get('MVP_DEMO', '').strip() == '1':
    DEMO_MODE = True
    logger.info("Demo mode forced via MVP_DEMO=1")
elif not os.path.exists('/dev/i2c-1'):
    DEMO_MODE = True
    logger.info("Demo mode enabled: /dev/i2c-1 not found (not on Pi)")
else:
    try:
        import SI7021
        _sensor_module = SI7021
        logger.info("SI7021 sensor module loaded")
    except ImportError:
        DEMO_MODE = True
        logger.warning("SI7021 import failed, falling back to demo mode")

    try:
        import Relay
        _relay_module = Relay
        logger.info("Relay module loaded")
    except ImportError:
        logger.warning("Relay import failed, relay state will be simulated")

# ---------------------------------------------------------------------------
# Data storage
# ---------------------------------------------------------------------------

# Rolling buffers for time-series data (1 reading per minute, 24h = 1440)
MAX_HISTORY = 1440

_history_lock = threading.Lock()
_timestamps = deque(maxlen=MAX_HISTORY)
_temperatures = deque(maxlen=MAX_HISTORY)
_humidities = deque(maxlen=MAX_HISTORY)

# Current readings
_current = {
    'temperature': 0.0,
    'humidity': 0.0,
    'dew_point': 0.0,
    'light': False,
    'fan': False,
}

_start_time = time.time()
_last_reading_time = 0.0

# ---------------------------------------------------------------------------
# Simulated data generation (demo mode)
# ---------------------------------------------------------------------------


def _simulate_temperature(dt):
    """Generate a realistic temperature for a given datetime.

    Uses a sinusoidal cycle: peak at 14:00, trough at 02:00.
    Center: 24C, amplitude: 3C, plus small random noise.
    """
    hour = dt.hour + dt.minute / 60.0
    # Shift so peak is at 14:00 (hour 14)
    phase = (hour - 14.0) * (2.0 * math.pi / 24.0)
    temp = 24.0 + 3.0 * math.cos(phase)
    temp += random.uniform(-0.3, 0.3)
    return round(temp, 2)


def _simulate_humidity(temperature):
    """Generate humidity inversely correlated with temperature.

    Centered around 60%, inversely proportional to temperature deviation
    from 24C.
    """
    deviation = temperature - 24.0
    humidity = 60.0 - (deviation * 4.0) + random.uniform(-1.5, 1.5)
    humidity = max(30.0, min(90.0, humidity))
    return round(humidity, 2)


def _is_light_on(dt):
    """Check if the light should be on based on env.py schedule."""
    current_time = dt.strftime('%H:%M:%S')
    return LIGHT_ON <= current_time < LIGHT_OFF


def _is_fan_on(temperature):
    """Check if the fan should be on based on thermostat logic."""
    return temperature > TARGET_TEMP


# ---------------------------------------------------------------------------
# History management
# ---------------------------------------------------------------------------


def _backfill_history():
    """Pre-fill 24 hours of history data on startup."""
    now = datetime.now()
    with _history_lock:
        for i in range(MAX_HISTORY, 0, -1):
            dt = now - timedelta(minutes=i)
            ts = dt.strftime('%Y-%m-%dT%H:%M:%S')

            if DEMO_MODE:
                temp = _simulate_temperature(dt)
                hum = _simulate_humidity(temp)
            else:
                temp = 24.0
                hum = 60.0

            _timestamps.append(ts)
            _temperatures.append(temp)
            _humidities.append(hum)

    logger.info("Backfilled %d history entries", MAX_HISTORY)


def _read_hardware():
    """Read actual sensor values from hardware modules."""
    temp = 24.0
    hum = 60.0

    if _sensor_module is not None:
        try:
            temp = _sensor_module.get_tempC()
            hum = _sensor_module.get_humidity()
            if isinstance(temp, (int, float)) and isinstance(hum, (int, float)):
                return round(float(temp), 2), round(float(hum), 2)
        except Exception as e:
            logger.warning("Sensor read error: %s", e)

    return temp, hum


def _read_relay_state():
    """Read relay/GPIO state for light and fan."""
    light = False
    fan = False

    if _relay_module is not None:
        try:
            light = bool(_relay_module.get_light_state())
        except Exception:
            light = _is_light_on(datetime.now())
        try:
            fan = bool(_relay_module.get_fan_state())
        except Exception:
            fan = False
    else:
        now = datetime.now()
        light = _is_light_on(now)
        fan = _is_fan_on(_current.get('temperature', 24.0))

    return light, fan


def _maybe_generate_reading():
    """Add a new reading if at least 60 seconds have passed since the last one."""
    global _last_reading_time

    now = time.time()
    if now - _last_reading_time < 60.0:
        return

    _last_reading_time = now
    dt = datetime.now()
    ts = dt.strftime('%Y-%m-%dT%H:%M:%S')

    if DEMO_MODE:
        temp = _simulate_temperature(dt)
        hum = _simulate_humidity(temp)
    else:
        temp, hum = _read_hardware()

    dew = round(getDewPoint(temp, hum), 2)
    light, fan = _read_relay_state()

    _current['temperature'] = temp
    _current['humidity'] = hum
    _current['dew_point'] = dew
    _current['light'] = light
    _current['fan'] = fan

    with _history_lock:
        _timestamps.append(ts)
        _temperatures.append(temp)
        _humidities.append(hum)


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------


class MVPRequestHandler(SimpleHTTPRequestHandler):
    """HTTP handler that serves static files from WEB_DIR and JSON API."""

    def translate_path(self, path):
        """Override to serve files from the web directory instead of cwd."""
        # Strip query string and fragment
        path = urlparse(path).path

        # Normalize the path
        parts = path.split('/')
        parts = [p for p in parts if p]

        # Build the filesystem path rooted at WEB_DIR
        fs_path = WEB_DIR
        for part in parts:
            if part in (os.curdir, os.pardir):
                continue
            fs_path = os.path.join(fs_path, part)

        # If path points to a directory, serve index.html
        if os.path.isdir(fs_path):
            fs_path = os.path.join(fs_path, 'index.html')

        return fs_path

    def do_GET(self):
        """Route GET requests to API endpoints or static file serving."""
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/status':
            self._handle_status()
        elif path == '/api/history':
            params = parse_qs(parsed.query)
            self._handle_history(params)
        elif path.startswith('/api/'):
            self._send_json_error(404, "Unknown API endpoint")
        else:
            # Serve static files via parent class
            super().do_GET()

    def end_headers(self):
        """Add CORS and cache-control headers."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.end_headers()

    def guess_type(self, path):
        """Override to ensure SVG files are served with correct MIME type."""
        if path.endswith('.svg'):
            return 'image/svg+xml'
        return super().guess_type(path)

    def log_message(self, format, *args):
        """Route HTTP access logs through the project logger."""
        logger.info("HTTP %s", format % args)

    # -------------------------------------------------------------------
    # API handlers
    # -------------------------------------------------------------------

    def _handle_status(self):
        """Return current sensor status as JSON."""
        _maybe_generate_reading()

        uptime_seconds = int(time.time() - _start_time)
        hours = uptime_seconds // 3600
        minutes = (uptime_seconds % 3600) // 60
        secs = uptime_seconds % 60
        uptime_str = "{}h {}m {}s".format(hours, minutes, secs)

        data = {
            'temperature': _current['temperature'],
            'humidity': _current['humidity'],
            'dew_point': _current['dew_point'],
            'light': _current['light'],
            'fan': _current['fan'],
            'uptime': uptime_str,
            'timestamp': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            'demo_mode': DEMO_MODE,
            'target_temp': TARGET_TEMP,
            'light_on': LIGHT_ON,
            'light_off': LIGHT_OFF,
        }

        self._send_json(200, data)

    def _handle_history(self, params):
        """Return time-series data as JSON arrays.

        Query parameters:
            hours (int): Number of hours of history to return (1-24, default 24)
        """
        _maybe_generate_reading()

        try:
            hours = int(params.get('hours', ['24'])[0])
            hours = max(1, min(24, hours))
        except (ValueError, IndexError):
            hours = 24

        entries = hours * 60  # 1 reading per minute

        with _history_lock:
            ts_list = list(_timestamps)
            temp_list = list(_temperatures)
            hum_list = list(_humidities)

        # Return the most recent N entries
        if len(ts_list) > entries:
            ts_list = ts_list[-entries:]
            temp_list = temp_list[-entries:]
            hum_list = hum_list[-entries:]

        data = {
            'timestamps': ts_list,
            'temperature': temp_list,
            'humidity': hum_list,
            'hours': hours,
            'count': len(ts_list),
        }

        self._send_json(200, data)

    # -------------------------------------------------------------------
    # Response helpers
    # -------------------------------------------------------------------

    def _send_json(self, status_code, data):
        """Send a JSON response with the given status code."""
        body = json.dumps(data).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json_error(self, status_code, message):
        """Send a JSON error response."""
        self._send_json(status_code, {'error': message})


# ---------------------------------------------------------------------------
# Background data generator
# ---------------------------------------------------------------------------


class DataGeneratorThread(threading.Thread):
    """Background thread that generates a reading once per minute."""

    def __init__(self):
        super().__init__(daemon=True)
        self.name = 'DataGenerator'

    def run(self):
        while True:
            try:
                _maybe_generate_reading()
            except Exception as e:
                logger.error("Data generator error: %s", e)
            time.sleep(30)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    """Start the MVP Food Computer web server."""
    # Pre-fill history so charts have data immediately
    _backfill_history()

    # Generate the first current reading
    global _last_reading_time
    _last_reading_time = 0
    _maybe_generate_reading()

    # Start background data generator
    generator = DataGeneratorThread()
    generator.start()

    # Start HTTP server
    server = HTTPServer(('0.0.0.0', PORT), MVPRequestHandler)

    mode_str = "DEMO" if DEMO_MODE else "PRODUCTION"
    logger.info("=" * 60)
    logger.info("MVP Food Computer Server v2.0")
    logger.info("Mode:      %s", mode_str)
    logger.info("Port:      %d", PORT)
    logger.info("Web dir:   %s", WEB_DIR)
    logger.info("Light ON:  %s", LIGHT_ON)
    logger.info("Light OFF: %s", LIGHT_OFF)
    logger.info("Target:    %s C", TARGET_TEMP)
    logger.info("Dashboard: http://localhost:%d/", PORT)
    logger.info("=" * 60)

    print("")
    print("  MVP Food Computer Server v2.0")
    print("  Mode:      {}".format(mode_str))
    print("  Dashboard: http://localhost:{}/".format(PORT))
    print("  API:       http://localhost:{}/api/status".format(PORT))
    print("")
    print("  Press Ctrl+C to stop.")
    print("")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
        logger.info("Server stopped")


if __name__ == '__main__':
    main()
