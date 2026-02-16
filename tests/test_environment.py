"""Tests for the Environment setup module."""

import uuid
from Environment import getField, setTargetTemperature, setLights


class TestGetField:
    def test_returns_dict_with_field_id(self):
        field = getField()
        assert 'field_id' in field

    def test_field_id_is_valid_uuid(self):
        field = getField()
        # Should not raise ValueError
        uuid.UUID(field['field_id'])

    def test_generates_unique_ids(self):
        f1 = getField()
        f2 = getField()
        assert f1['field_id'] != f2['field_id']


class TestSetTargetTemperature:
    def test_default_temperature(self):
        result = setTargetTemperature()
        assert result == {'targetTemp': 25}

    def test_custom_temperature(self):
        result = setTargetTemperature(30)
        assert result == {'targetTemp': 30}


class TestSetLights:
    def test_default_schedule(self):
        result = setLights()
        assert result == {'On': '06:30:00', 'Off': '22:00:00'}

    def test_custom_schedule(self):
        result = setLights(on='08:00:00', off='20:00:00')
        assert result == {'On': '08:00:00', 'Off': '20:00:00'}
