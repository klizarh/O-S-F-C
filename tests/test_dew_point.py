"""Tests for the DewPoint calculation module."""

import math
from DewPoint import getDewPoint, getDewPointAprox, gamma


class TestGamma:
    def test_returns_float(self):
        g = gamma(20, 50)
        assert isinstance(g, float)

    def test_known_value(self):
        # gamma(20, 50) = (17.271 * 20 / (237.7 + 20)) + ln(0.5)
        expected = (17.271 * 20 / (237.7 + 20)) + math.log(0.5)
        assert abs(gamma(20, 50) - expected) < 1e-10


class TestGetDewPoint:
    def test_returns_float(self):
        dp = getDewPoint(20, 50)
        assert isinstance(dp, float)

    def test_known_dew_point(self):
        # At 20C and 50% RH, dew point is approximately 9.3C
        dp = getDewPoint(20, 50)
        assert 8.5 < dp < 10.0

    def test_high_humidity(self):
        # At 100% RH, dew point should equal the temperature
        dp = getDewPoint(25, 100)
        assert abs(dp - 25) < 0.5

    def test_dew_point_below_temp(self):
        # Dew point should always be at or below the actual temperature
        for temp in [10, 20, 30, 40]:
            for rh in [20, 40, 60, 80]:
                dp = getDewPoint(temp, rh)
                assert dp <= temp + 0.1


class TestGetDewPointAprox:
    def test_returns_number(self):
        dp = getDewPointAprox(20, 50)
        assert isinstance(dp, (int, float))

    def test_approximation_reasonable(self):
        # Approximation should be in the right ballpark
        dp = getDewPointAprox(20, 50)
        assert 5 < dp < 15
