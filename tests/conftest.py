"""Pytest configuration for the MVP Food Computer test suite."""

import os
import sys

# Ensure MVP/python is on the import path so tests can import modules
# the same way the production code does (e.g. ``from env import env``).
MVP_PYTHON_DIR = os.path.join(
    os.path.dirname(__file__), os.pardir, "MVP", "python"
)
sys.path.insert(0, os.path.abspath(MVP_PYTHON_DIR))
