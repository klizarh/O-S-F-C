import os
import sys
import unittest

# Add MVP/python to the import path so we can import env
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'MVP', 'python'))

from env import env

class TestEnv(unittest.TestCase):
    def test_expected_keys_present(self):
        for key in ('field', 'thermostat', 'lights'):
            self.assertIn(key, env)

if __name__ == '__main__':
    unittest.main()
