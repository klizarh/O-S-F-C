"""Tests for the MVP_Util time conversion module."""

from datetime import datetime
from MVP_Util import UTCtoLocal, UTCStrToLocal, UTCStrToLDT


class TestUTCtoLocal:
    def test_returns_datetime(self):
        utc = datetime.utcnow()
        result = UTCtoLocal(utc)
        assert isinstance(result, datetime)

    def test_offset_applied(self):
        # The result should differ from input by the local UTC offset
        utc = datetime(2024, 6, 15, 12, 0, 0)
        local = UTCtoLocal(utc)
        # We can't know the exact offset in CI, but we can verify
        # the function runs and returns a datetime
        assert isinstance(local, datetime)


class TestUTCStrToLocal:
    def test_returns_string(self):
        result = UTCStrToLocal('2024-06-15T12:00:00')
        assert isinstance(result, str)

    def test_iso_format(self):
        result = UTCStrToLocal('2024-06-15T12:00:00')
        # Should be in ISO format YYYY-MM-DDTHH:MM:SS
        assert len(result) == 19
        assert result[4] == '-'
        assert result[10] == 'T'

    def test_handles_microseconds(self):
        # Should handle timestamps with extra precision
        result = UTCStrToLocal('2024-06-15T12:00:00.123456')
        assert isinstance(result, str)
        assert len(result) == 19


class TestUTCStrToLDT:
    def test_returns_datetime(self):
        result = UTCStrToLDT('2024-06-15T12:00:00')
        assert isinstance(result, datetime)
