"""Tests for the env configuration module."""

from env import env


class TestEnv:
    def test_expected_keys_present(self):
        for key in ('field', 'thermostat', 'lights'):
            assert key in env

    def test_field_has_field_id(self):
        assert 'field_id' in env['field']

    def test_thermostat_has_target_temp(self):
        assert 'targetTemp' in env['thermostat']
        assert isinstance(env['thermostat']['targetTemp'], (int, float))

    def test_lights_has_on_off(self):
        assert 'On' in env['lights']
        assert 'Off' in env['lights']

    def test_lights_time_format(self):
        """Light schedule times should be HH:MM:SS format."""
        for key in ('On', 'Off'):
            parts = env['lights'][key].split(':')
            assert len(parts) == 3, f"Expected HH:MM:SS, got {env['lights'][key]}"
