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
- The `Server_8000.py` web server creates a TCP server at module level - could
  benefit from the same lazy-initialization pattern applied to CouchUtil
- Consider migrating from CouchDB to a lighter database (SQLite) for simpler
  deployment
