# Changes - Reviving the Open Source Food Computer

## Summary

This document records all changes made to revive the MVP Food Computer project
after an extended period of inactivity. The project was last actively developed
around 2020, with some cleanup PRs merged in 2024-2025. The goal of this effort
is to make the codebase testable, maintainable, and runnable on modern Python 3
without requiring Raspberry Pi hardware for development.

---

## Assessment Findings

### What was working
- Basic project structure was sound with clear separation of concerns
- One unit test (`tests/test_env.py`) existed and passed
- `QuickTest.py` had been refactored to gracefully skip missing modules
- Python 3 print-function compatibility was already addressed in a prior PR

### Critical issues found
1. **No dependency management** - No `requirements.txt`, `setup.py`, or `pyproject.toml`
2. **Hardcoded paths** - `/home/pi/MVP/...` hardcoded in 7 files, preventing
   development on any machine other than the target Pi
3. **Module-level side effects** - `CouchUtil.py` connected to CouchDB at
   import time (lines 46-59), making it impossible to import or test without a
   running database
4. **Heavy dependency for trivial use** - `DewPoint.py` imported `numpy` solely
   for `numpy.log()`, which is identical to `math.log()` from the standard library
5. **Bug in DewpointChart.py** - `test()` function on line 115 passed the
   function object `test` instead of the boolean `True` to `cleanData()` and
   `buildChart()`
6. **LogUtil.py crashes without Pi** - Hardcoded log path
   `/home/pi/MVP/logs/mvp.log` caused `FileNotFoundError` on any non-Pi system
7. **Duplicate log handlers** - Repeated calls to `get_logger()` with the same
   name kept appending handlers, causing duplicate log messages
8. **No CI/CD** - No automated testing configured
9. **Minimal test coverage** - Only 1 test for the `env` config module

---

## Changes Made

### 1. Dependency Management (new files)

**`requirements.txt`** - Core runtime dependencies:
- `CouchDB>=1.2,<2.0` - Database client
- `tenacity>=6.0` - Retry logic
- `pygal>=3.0` - SVG charting
- `pandas>=1.0` - Data analysis for dew point charts
- Hardware deps (`RPi.GPIO`, `python-periphery`) listed as comments since they
  can only be installed on a Pi

**`requirements-dev.txt`** - Development/test dependencies (extends requirements.txt):
- `pytest>=7.0`

**`pyproject.toml`** - Modern Python project metadata:
- Project name, version (bumped to 3.2.0), description
- Optional dependency groups: `[hardware]`, `[charts]`, `[dev]`
- pytest configuration: sets `testpaths` and `pythonpath` so tests find modules

**Reasoning:** Without dependency files, anyone cloning the repo had to
reverse-engineer which packages to install by reading import statements across
23 Python files.

### 2. Hardcoded Path Elimination

All `/home/pi/MVP/...` paths replaced with configurable paths using the
`MVP_DIR` environment variable, falling back to `/home/pi/MVP` for
backwards-compatibility on actual Pi hardware.

**Files changed:**
- `MVP/python/LogUtil.py` - Log file path now uses `MVP_DIR/logs/mvp.log`
- `MVP/python/Environment.py` - env.py output path now configurable
- `MVP/python/TempChart.py` - SVG output path now uses `MVP_DIR/web/`
- `MVP/python/HumidityChart.py` - SVG output path now uses `MVP_DIR/web/`
- `MVP/python/DewpointChart.py` - SVG output path now uses `MVP_DIR/web/`
- `MVP/python/Img2Gif.py` - Pictures directory now uses `MVP_DIR/pictures_R/`

**Reasoning:** Hardcoded paths tied the entire project to a specific Raspberry
Pi directory structure. Using `os.environ.get('MVP_DIR', '/home/pi/MVP')`
allows development on any machine while preserving Pi compatibility.

### 3. CouchUtil.py - Lazy Database Connection

**Before:** Lines 46-59 executed at import time, immediately connecting to
CouchDB. Any module that imported CouchUtil (Light, Fan, LogSensors, etc.)
would crash without a running database.

**After:** Database connection wrapped in `_get_db()` function that connects
only when `saveRec()` is actually called. The `couchdb` package import is also
deferred into `_get_db()`.

**Additional fix:** The `tenacity` import is now wrapped in a try/except so the
module can load even without tenacity installed (for testing/CI environments).

**Reasoning:** This is the single most impactful change. It decouples all
record-building logic (`buildCore`, `processEnv`, `processState`, `processAgro`,
`processPheno`) from the database, making them independently testable.

### 4. DewPoint.py - Removed numpy Dependency

**Before:** `import numpy as np` ... `np.log(RH/100.0)`

**After:** `import math` ... `math.log(RH/100.0)`

**Reasoning:** numpy is a 25+ MB package. The only function used was
`numpy.log()` which is mathematically identical to Python's built-in
`math.log()`. Verified that calculations produce identical results.

### 5. DewpointChart.py - Fixed test() Function Bug

**Before (line 115):**
```python
def test():
    ...
    data = cleanData(data, test)   # 'test' is the function, not True!
    buildChart(data, test)
```

**After:**
```python
def test():
    ...
    data = cleanData(data, True)
    buildChart(data, True)
```

**Reasoning:** Python treats function objects as truthy, so this bug was
masked - the test flag would always evaluate to True, but the actual value
passed would be a function object rather than a boolean. This could cause
unexpected behavior in any code that checks `if test == True` vs `if test`.

### 6. LogUtil.py - Robust Logger

Three fixes applied:
1. **Configurable log directory** via `MVP_DIR` environment variable
2. **Graceful degradation** - File handler is only added when the log directory
   exists. On non-Pi systems, only the screen handler is used.
3. **Duplicate handler prevention** - If `get_logger()` is called multiple
   times with the same name, it returns the existing logger without adding
   duplicate handlers.

### 7. HumidityChart.py - Fixed Comment

Changed misleading module comment from "Temperature chart" to "Humidity chart".

### 8. Test Suite (new files)

**`tests/conftest.py`** - Pytest configuration that adds `MVP/python` to
`sys.path` so all test files can import modules without path manipulation.

**`tests/test_env.py`** - Expanded from 1 test to 5 tests:
- Key presence, field_id structure, thermostat type, lights structure, time format

**`tests/test_couch_util.py`** - 16 tests covering all record-building functions:
- `buildCore` - device/person participants, timestamps, status with/without comments
- `processEnv` - activity type, subject structure, location
- `processState` - activity type, device participant
- `processAgro` - activity type, empty/present subjects, trial in location
- `processPheno` - activity type, plot and trial in location

**`tests/test_dew_point.py`** - 8 tests:
- `gamma` - return type, known value calculation
- `getDewPoint` - return type, known values, 100% RH edge case, always ≤ temperature
- `getDewPointAprox` - return type, reasonable approximation

**`tests/test_mvp_util.py`** - 6 tests:
- `UTCtoLocal` - return type, offset applied
- `UTCStrToLocal` - return type, ISO format, microsecond handling
- `UTCStrToLDT` - return type

**`tests/test_environment.py`** - 7 tests:
- `getField` - returns dict, valid UUID, unique IDs
- `setTargetTemperature` - default and custom values
- `setLights` - default and custom schedules

**`tests/test_log_util.py`** - 5 tests:
- Return type, name prefix, default name, screen handler, no duplicate handlers

**`tests/test_startup.py`** - 4 tests (with RPi.GPIO mocking):
- Lights on during day, off at night, off before dawn, night-light wrap-around

**Total: 51 tests, all passing**

### 9. GitHub Actions CI (new file)

**`.github/workflows/ci.yml`** - Runs tests on push/PR to master/main:
- Tests against Python 3.8, 3.9, 3.10, 3.11, 3.12
- Installs dev dependencies from `requirements-dev.txt`
- Runs `pytest tests/ -v`

---

## What Still Needs Attention

### On Raspberry Pi Hardware
- The shell scripts in `MVP/scripts/` still have hardcoded `/home/pi/MVP` paths
- The setup scripts in `MVP/setup/` reference `/home/pi/MVP` and would need
  updating for a different installation location
- Cron job paths in `MVP/scripts/MVP_cron.txt` are hardcoded

### Future Improvements
- The `Img2Gif.py` module references `env["trials"]` which doesn't exist in
  the current `env.py` configuration - this feature appears broken
- The web CGI scripts in `MVP/web/cgi-bin/` have not been reviewed
- Consider adding integration tests that run against a CouchDB Docker container
- Consider migrating from CouchDB to a lighter database (SQLite) for simpler
  deployment

---

## Phase 2: Modern Dashboard & Working Server

### 10. Modern Web Dashboard (replaced file)

**`MVP/web/index.html`** - Complete rewrite from 134-line bare-bones tabbed page
to 830-line modern responsive dashboard.

**Layout** (CSS Grid/Flexbox):
- Gradient header with project name and live connection status indicator
  (green dot = online, yellow = connecting, red = disconnected)
- 4 stat cards: Temperature, Humidity, Dew Point, Light Status - each with
  colored left-border accent, large value display, and update timestamp
- Two Chart.js interactive line charts (Temperature + Humidity over 24h) with
  smooth curves, area fill, and tooltips
- Camera feed panel with overlay timestamp
- System Info panel showing uptime, fan state, light schedule, last update,
  and links to Wiki/Forum/GitHub
- Footer with version info

**Styling**:
- Nature/agriculture color scheme via CSS custom properties (greens, earth tones,
  orange for temp, blue for humidity)
- Card-based design with subtle shadows (`box-shadow`) and rounded corners (12px)
- Responsive: 3 breakpoints (4-col / 2-col / 1-col stat cards, side-by-side /
  stacked charts)
- System font stack only - no external font loads
- Loading overlay with spinner on startup

**Interactivity** (vanilla JS, no frameworks):
- Fetches `/api/status` and `/api/history?hours=24` every 30 seconds
- Updates stat card values and Chart.js datasets dynamically
- Camera image auto-refreshes with cache-busting query string
- Graceful degradation: if Chart.js CDN fails, falls back to existing pygal SVG
  charts; if API unreachable, shows "Disconnected" state (not a broken page)

**Only external dependency**: Chart.js from CDN (loaded via `<script>` tag)

### 11. REST API Server with Demo Mode (new file)

**`MVP/python/app.py`** - New web server replacing `Server_8000.py` (which is
kept as fallback).

**Architecture** (Python stdlib only - no Flask/Django):
- Extends `http.server.SimpleHTTPRequestHandler` with API routing
- Serves static files from `MVP/web/` with proper MIME types
- JSON API endpoints at `/api/status` and `/api/history`
- CORS headers for development flexibility
- Proper error responses (JSON 404 for unknown API endpoints)

**API endpoints**:
- `GET /api/status` - Current temperature, humidity, dew point, light/fan state,
  uptime, timestamp, and demo_mode flag
- `GET /api/history?hours=N` - Time series arrays (timestamps, temperature,
  humidity) for chart rendering (1-24 hours, 1 reading per minute)

**Demo mode** (automatic when not on Pi):
- Detects hardware via `/dev/i2c-1` existence or `MVP_DEMO=1` env var
- Generates realistic simulated data:
  - Temperature: 24h sinusoidal cycle centered on 24C with +/- 3C swing and
    random noise (peak at 14:00, coolest at 02:00)
  - Humidity: inversely correlated with temperature, centered around 60%
  - Light: follows env.py schedule (06:30 on, 22:00 off)
  - Fan: follows thermostat logic (on when temp > target)
- Pre-fills 24 hours of history (1440 entries) on startup
- Adds one new reading per minute while running

**Production mode** (on Pi with hardware):
- Imports `SI7021` for real sensor readings
- Imports `Relay` for actual light/fan GPIO state
- Falls back gracefully to demo mode if hardware imports fail

**Integration**: Uses `env.py` config, `DewPoint.getDewPoint`, `LogUtil.get_logger`,
and `MVP_DIR` environment variable for path resolution.

**Usage**: `python3 MVP/python/app.py` from project root (or `python3 app.py`
from `MVP/python/`). Dashboard accessible at `http://localhost:8000/`.
