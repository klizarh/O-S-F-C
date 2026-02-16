"""Tests for the StartUp module's determineState logic.

StartUp.py imports Light which imports Relay which requires RPi.GPIO.
We mock out the hardware modules before importing so the pure-logic
determineState function can be tested without Raspberry Pi hardware.
"""

import sys
from types import ModuleType
from unittest.mock import patch, MagicMock
from datetime import datetime

# Provide mock modules for hardware dependencies so StartUp can be imported
_gpio_mock = MagicMock()
_rpi_mock = MagicMock()
_rpi_mock.GPIO = _gpio_mock
sys.modules.setdefault('RPi', _rpi_mock)
sys.modules.setdefault('RPi.GPIO', _gpio_mock)

from StartUp import determineState


class TestDetermineState:
    def test_lights_on_during_day(self):
        """During the middle of the light period, lights should be on."""
        with patch('StartUp.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2024, 6, 15, 12, 0, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = determineState('06:30:00', '22:00:00')
        assert result is True

    def test_lights_off_at_night(self):
        """After the light period, lights should be off."""
        with patch('StartUp.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2024, 6, 15, 23, 0, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = determineState('06:30:00', '22:00:00')
        assert result is False

    def test_lights_off_before_dawn(self):
        """Before the light period starts, lights should be off."""
        with patch('StartUp.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2024, 6, 15, 5, 0, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = determineState('06:30:00', '22:00:00')
        assert result is False

    def test_night_light_schedule(self):
        """When start > end (night lights), should wrap around midnight."""
        with patch('StartUp.datetime') as mock_dt:
            # 23:00 is between 15:30 and next day 08:30
            mock_dt.now.return_value = datetime(2024, 6, 15, 23, 0, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = determineState('15:30:00', '08:30:00')
        assert result is True
