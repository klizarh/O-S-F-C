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
import sqlite3
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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

if os.environ.get('MVP_DIR'):
    MVP_DIR = os.environ['MVP_DIR']
else:
    MVP_DIR = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# ---------------------------------------------------------------------------
# Import project modules
# ---------------------------------------------------------------------------

from LogUtil import get_logger
from DewPoint import getDewPoint
from env import env

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LIGHT_ON = env.get('lights', {}).get('On', '06:30:00')
LIGHT_OFF = env.get('lights', {}).get('Off', '22:00:00')
TARGET_TEMP = env.get('thermostat', {}).get('targetTemp', 25)

PORT = int(os.environ.get('MVP_PORT', 8000))
WEB_DIR = os.path.join(MVP_DIR, 'web')
DATA_DIR = os.path.join(MVP_DIR, 'data')
DB_PATH = os.environ.get('MVP_DB', os.path.join(DATA_DIR, 'readings.db'))

logger = get_logger('AppServer')

# ---------------------------------------------------------------------------
# Alert thresholds (configurable via environment)
# ---------------------------------------------------------------------------

ALERTS = {
    'temp_min': float(os.environ.get('MVP_TEMP_MIN', 18.0)),
    'temp_max': float(os.environ.get('MVP_TEMP_MAX', 30.0)),
    'humidity_min': float(os.environ.get('MVP_HUM_MIN', 30.0)),
    'humidity_max': float(os.environ.get('MVP_HUM_MAX', 80.0)),
}

def _check_alerts(temp, humidity):
    """Return a list of active alert dicts for current readings."""
    alerts = []
    if temp is not None:
        if temp < ALERTS['temp_min']:
            alerts.append({
                'sensor': 'temperature', 'level': 'warning',
                'message': 'Temperature too low ({:.1f}°C < {:.0f}°C)'.format(temp, ALERTS['temp_min']),
            })
        elif temp > ALERTS['temp_max']:
            alerts.append({
                'sensor': 'temperature', 'level': 'critical',
                'message': 'Temperature too high ({:.1f}°C > {:.0f}°C)'.format(temp, ALERTS['temp_max']),
            })
    if humidity is not None:
        if humidity < ALERTS['humidity_min']:
            alerts.append({
                'sensor': 'humidity', 'level': 'warning',
                'message': 'Humidity too low ({:.1f}% < {:.0f}%)'.format(humidity, ALERTS['humidity_min']),
            })
        elif humidity > ALERTS['humidity_max']:
            alerts.append({
                'sensor': 'humidity', 'level': 'critical',
                'message': 'Humidity too high ({:.1f}% > {:.0f}%)'.format(humidity, ALERTS['humidity_max']),
            })
    return alerts

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
# SQLite persistence
# ---------------------------------------------------------------------------

_db_lock = threading.Lock()

def _init_db():
    """Create the readings table if it doesn't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                temperature REAL,
                humidity REAL,
                dew_point REAL,
                light INTEGER,
                fan INTEGER
            )
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings(timestamp)
        ''')
    logger.info("Database initialized at %s", DB_PATH)


def _store_reading(ts, temp, hum, dew, light, fan):
    """Persist a single reading to SQLite."""
    with _db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                'INSERT INTO readings (timestamp, temperature, humidity, dew_point, light, fan) VALUES (?, ?, ?, ?, ?, ?)',
                (ts, temp, hum, dew, 1 if light else 0, 1 if fan else 0)
            )


def _query_history(hours):
    """Retrieve readings for the last N hours from SQLite."""
    cutoff = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%dT%H:%M:%S')
    with _db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                'SELECT timestamp, temperature, humidity FROM readings WHERE timestamp >= ? ORDER BY timestamp',
                (cutoff,)
            ).fetchall()
    return rows


def _query_recent(hours):
    """Retrieve recent readings as separate lists for the API."""
    rows = _query_history(hours)
    if not rows:
        return {'timestamps': [], 'temperature': [], 'humidity': []}
    timestamps = [r[0] for r in rows]
    temperatures = [r[1] for r in rows]
    humidities = [r[2] for r in rows]
    # Thin out data for very long ranges to keep response size reasonable
    max_points = 2000
    if len(timestamps) > max_points:
        step = len(timestamps) // max_points
        timestamps = timestamps[::step]
        temperatures = temperatures[::step]
        humidities = humidities[::step]
    return {
        'timestamps': timestamps,
        'temperature': temperatures,
        'humidity': humidities,
    }


def _prune_old_data(max_days=90):
    """Remove readings older than max_days to keep the database from growing indefinitely."""
    cutoff = (datetime.now() - timedelta(days=max_days)).strftime('%Y-%m-%dT%H:%M:%S')
    with _db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute('DELETE FROM readings WHERE timestamp < ?', (cutoff,))


# ---------------------------------------------------------------------------
# Current state
# ---------------------------------------------------------------------------

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
    """Sinusoidal cycle: peak at 14:00, trough at 02:00. Center 24C, amplitude 3C."""
    hour = dt.hour + dt.minute / 60.0
    phase = (hour - 14.0) * (2.0 * math.pi / 24.0)
    temp = 24.0 + 3.0 * math.cos(phase)
    temp += random.uniform(-0.3, 0.3)
    return round(temp, 2)


def _simulate_humidity(temperature):
    """Humidity inversely correlated with temperature, centered around 60%."""
    deviation = temperature - 24.0
    humidity = 60.0 - (deviation * 4.0) + random.uniform(-1.5, 1.5)
    humidity = max(30.0, min(90.0, humidity))
    return round(humidity, 2)


def _is_light_on(dt):
    current_time = dt.strftime('%H:%M:%S')
    return LIGHT_ON <= current_time < LIGHT_OFF


def _is_fan_on(temperature):
    return temperature > TARGET_TEMP


# ---------------------------------------------------------------------------
# Reading generation
# ---------------------------------------------------------------------------


def _read_hardware():
    temp, hum = 24.0, 60.0
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
    light, fan = False, False
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


def _backfill_history():
    """Pre-fill history if the database is empty (first run or demo mode)."""
    with _db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            count = conn.execute('SELECT COUNT(*) FROM readings').fetchone()[0]
    if count > 0:
        logger.info("Database has %d existing readings, skipping backfill", count)
        return

    logger.info("Backfilling 24 hours of history...")
    now = datetime.now()
    batch = []
    for i in range(1440, 0, -1):
        dt = now - timedelta(minutes=i)
        ts = dt.strftime('%Y-%m-%dT%H:%M:%S')
        temp = _simulate_temperature(dt)
        hum = _simulate_humidity(temp)
        dew = round(getDewPoint(temp, hum), 2)
        light = 1 if _is_light_on(dt) else 0
        fan = 1 if _is_fan_on(temp) else 0
        batch.append((ts, temp, hum, dew, light, fan))

    with _db_lock:
        with sqlite3.connect(DB_PATH) as conn:
            conn.executemany(
                'INSERT INTO readings (timestamp, temperature, humidity, dew_point, light, fan) VALUES (?, ?, ?, ?, ?, ?)',
                batch
            )
    logger.info("Backfilled %d readings", len(batch))


def _maybe_generate_reading():
    """Add a new reading if at least 60 seconds have passed."""
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

    _store_reading(ts, temp, hum, dew, light, fan)


# ---------------------------------------------------------------------------
# Grow Advisor (rule-based)
# ---------------------------------------------------------------------------

def _get_advice():
    """Analyze recent sensor data and return grow recommendations."""
    rows = _query_history(6)
    if not rows:
        return []

    temps = [r[1] for r in rows if r[1] is not None]
    hums = [r[2] for r in rows if r[2] is not None]

    if not temps or not hums:
        return []

    advice = []
    avg_temp = sum(temps) / len(temps)
    avg_hum = sum(hums) / len(hums)
    min_temp = min(temps)
    max_temp = max(temps)
    temp_range = max_temp - min_temp

    # Count consecutive high/low readings (using last 3 hours = ~180 readings)
    recent_hums = hums[-180:] if len(hums) > 180 else hums
    recent_temps = temps[-180:] if len(temps) > 180 else temps
    high_hum_count = sum(1 for h in recent_hums if h > 80)
    low_hum_count = sum(1 for h in recent_hums if h < 35)
    high_temp_count = sum(1 for t in recent_temps if t > 30)
    low_temp_count = sum(1 for t in recent_temps if t < 18)

    # High humidity sustained — mold risk
    if high_hum_count > len(recent_hums) * 0.5:
        advice.append({
            'severity': 'critical',
            'title': 'Mold Risk — High Humidity',
            'message': 'Humidity has been above 80% for an extended period ({:.0f}% of recent readings). '
                       'Increase ventilation or reduce watering to prevent fungal growth.'.format(
                           100.0 * high_hum_count / len(recent_hums)),
            'metric': 'Avg humidity: {:.1f}%'.format(avg_hum),
        })

    # Low humidity sustained — plant stress
    if low_hum_count > len(recent_hums) * 0.5:
        advice.append({
            'severity': 'warning',
            'title': 'Low Humidity Stress',
            'message': 'Humidity has been below 35% for an extended period. '
                       'Plants may show wilting or leaf curl. Consider adding a humidifier or misting.',
            'metric': 'Avg humidity: {:.1f}%'.format(avg_hum),
        })

    # High temperature sustained
    if high_temp_count > len(recent_temps) * 0.3:
        advice.append({
            'severity': 'critical',
            'title': 'Heat Stress Risk',
            'message': 'Temperature has frequently exceeded 30°C. '
                       'Most leafy greens and herbs suffer above this threshold. '
                       'Ensure the fan is running and consider reducing light duration.',
            'metric': 'Max temp: {:.1f}°C'.format(max_temp),
        })

    # Low temperature sustained
    if low_temp_count > len(recent_temps) * 0.3:
        advice.append({
            'severity': 'warning',
            'title': 'Cold Stress Risk',
            'message': 'Temperature has frequently dropped below 18°C. '
                       'Growth slows significantly at low temperatures. '
                       'Consider insulation or a small heater.',
            'metric': 'Min temp: {:.1f}°C'.format(min_temp),
        })

    # Large temperature swings
    if temp_range > 10:
        advice.append({
            'severity': 'warning',
            'title': 'Large Temperature Swings',
            'message': 'Temperature varied by {:.1f}°C over the last 6 hours. '
                       'Rapid swings can stress plants. Check for drafts or thermostat issues.'.format(temp_range),
            'metric': '{:.1f}°C – {:.1f}°C'.format(min_temp, max_temp),
        })

    # Dew point proximity — condensation risk
    if avg_temp - getDewPoint(avg_temp, avg_hum) < 2.0:
        advice.append({
            'severity': 'warning',
            'title': 'Condensation Risk',
            'message': 'The dew point is very close to the air temperature. '
                       'Condensation on leaves promotes disease. Increase airflow.',
            'metric': 'Dew point spread: {:.1f}°C'.format(avg_temp - getDewPoint(avg_temp, avg_hum)),
        })

    # Optimal conditions
    if not advice:
        advice.append({
            'severity': 'ok',
            'title': 'Conditions Look Good',
            'message': 'Temperature and humidity are within healthy ranges. '
                       'Keep monitoring — consistency is key for strong growth.',
            'metric': '{:.1f}°C / {:.1f}% RH'.format(avg_temp, avg_hum),
        })

    return advice


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------


class MVPRequestHandler(SimpleHTTPRequestHandler):

    def translate_path(self, path):
        path = urlparse(path).path
        parts = [p for p in path.split('/') if p and p not in (os.curdir, os.pardir)]
        fs_path = WEB_DIR
        for part in parts:
            fs_path = os.path.join(fs_path, part)
        if os.path.isdir(fs_path):
            fs_path = os.path.join(fs_path, 'index.html')
        return fs_path

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/status':
            self._handle_status()
        elif path == '/api/history':
            params = parse_qs(parsed.query)
            self._handle_history(params)
        elif path == '/api/advisor':
            self._handle_advisor()
        elif path.startswith('/api/'):
            self._send_json_error(404, "Unknown API endpoint")
        else:
            super().do_GET()

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def guess_type(self, path):
        if path.endswith('.svg'):
            return 'image/svg+xml'
        return super().guess_type(path)

    def log_message(self, format, *args):
        logger.info("HTTP %s", format % args)

    # -------------------------------------------------------------------
    # API handlers
    # -------------------------------------------------------------------

    def _handle_status(self):
        _maybe_generate_reading()

        uptime_seconds = int(time.time() - _start_time)
        hours = uptime_seconds // 3600
        minutes = (uptime_seconds % 3600) // 60
        secs = uptime_seconds % 60
        uptime_str = "{}h {}m {}s".format(hours, minutes, secs)

        temp = _current['temperature']
        hum = _current['humidity']

        data = {
            'temperature': temp,
            'humidity': hum,
            'dew_point': _current['dew_point'],
            'light': _current['light'],
            'fan': _current['fan'],
            'uptime': uptime_str,
            'timestamp': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            'demo_mode': DEMO_MODE,
            'target_temp': TARGET_TEMP,
            'light_on': LIGHT_ON,
            'light_off': LIGHT_OFF,
            'alerts': _check_alerts(temp, hum),
            'thresholds': ALERTS,
        }

        self._send_json(200, data)

    def _handle_history(self, params):
        _maybe_generate_reading()

        try:
            hours = int(params.get('hours', ['24'])[0])
            hours = max(1, min(24 * 90, hours))  # up to 90 days
        except (ValueError, IndexError):
            hours = 24

        data = _query_recent(hours)
        data['hours'] = hours
        data['count'] = len(data['timestamps'])

        self._send_json(200, data)

    def _handle_advisor(self):
        _maybe_generate_reading()
        advice = _get_advice()
        self._send_json(200, {
            'advice': advice,
            'analyzed_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        })

    # -------------------------------------------------------------------
    # Response helpers
    # -------------------------------------------------------------------

    def _send_json(self, status_code, data):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json_error(self, status_code, message):
        self._send_json(status_code, {'error': message})


# ---------------------------------------------------------------------------
# Background data generator
# ---------------------------------------------------------------------------


class DataGeneratorThread(threading.Thread):

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
    _init_db()

    if DEMO_MODE:
        _backfill_history()

    global _last_reading_time
    _last_reading_time = 0
    _maybe_generate_reading()

    generator = DataGeneratorThread()
    generator.start()

    server = HTTPServer(('0.0.0.0', PORT), MVPRequestHandler)

    mode_str = "DEMO" if DEMO_MODE else "PRODUCTION"
    logger.info("=" * 60)
    logger.info("MVP Food Computer Server v3.0")
    logger.info("Mode:      %s", mode_str)
    logger.info("Port:      %d", PORT)
    logger.info("Web dir:   %s", WEB_DIR)
    logger.info("Database:  %s", DB_PATH)
    logger.info("Light ON:  %s", LIGHT_ON)
    logger.info("Light OFF: %s", LIGHT_OFF)
    logger.info("Target:    %s C", TARGET_TEMP)
    logger.info("Alerts:    temp %s-%s C, humidity %s-%s %%",
                ALERTS['temp_min'], ALERTS['temp_max'],
                ALERTS['humidity_min'], ALERTS['humidity_max'])
    logger.info("Dashboard: http://localhost:%d/", PORT)
    logger.info("=" * 60)

    print("")
    print("  MVP Food Computer Server v3.0")
    print("  Mode:      {}".format(mode_str))
    print("  Database:  {}".format(DB_PATH))
    print("  Dashboard: http://localhost:{}/".format(PORT))
    print("  API:       http://localhost:{}/api/status".format(PORT))
    print("  Advisor:   http://localhost:{}/api/advisor".format(PORT))
    print("")
    print("  Press Ctrl+C to stop.")
    print("")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        _prune_old_data()
        server.shutdown()
        logger.info("Server stopped")


if __name__ == '__main__':
    main()
