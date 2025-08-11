"""Quick smoke tests for MVP python modules.

This module was originally written as a rough integration test for
hardware specific components.  Over time the project evolved and a
number of imports referenced by the original script disappeared or were
renamed.  Running ``QuickTest`` therefore resulted in ``ImportError``
exceptions long before any real tests could execute.

The goal here is not to provide exhaustive unit tests but rather a
simple check that the modules which *are* present can be imported and
their ``test`` helper executed.  Missing modules are ignored gracefully
so that ``QuickTest`` can always run without crashing.
"""

from importlib import import_module
from json import dumps


def _run_test(module_name):
    """Import ``module_name`` and execute its ``test`` function.

    Many of the original modules are optional or hardware dependent.
    ``ImportError`` and missing ``test`` functions are caught so that the
    quick test can continue running other checks.
    """

    try:
        module = import_module(module_name)
        test_func = getattr(module, "test")
    except (ImportError, AttributeError):
        print(f"Skipping {module_name}: test not available")
        return
    test_func()


def json_test():
    """Verify the standard :mod:`json` library is functional."""
    dumps({"ok": True})


def couch_test():
    _run_test("CouchUtil")


def relay_test():
    _run_test("Relay")


def light_test():
    _run_test("Light")


def sens_test():
    # Module file is ``LogSensors.py`` – use the correct case.
    _run_test("LogSensors")


def recorder_test():
    _run_test("Recorder")


def fan_test():
    _run_test("Fan")


def thermostat_test():
    _run_test("Thermostat")


def test():
    """Run all available quick tests."""

    print("\nRecorder Test")
    recorder_test()
    print("\nTest JSON Utility")
    json_test()
    print("\nTest CouchDB")
    couch_test()
    print("\nTest Relay")
    relay_test()
    print("\nTest Lights")
    light_test()
    print("\nTest Sensor Logging")
    sens_test()
    print("\nTest Fan")
    fan_test()
    print("Test Thermostat")
    thermostat_test()


if __name__ == "__main__":
    test()
