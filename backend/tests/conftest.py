"""Pytest config to ensure project root is on sys.path during test collection.

Some environments run pytest with a different working directory which can
lead to "No module named 'backend'" import errors. This file ensures the
repository root is available to the test process.
"""
import os
import sys

_HERE = os.path.dirname(__file__)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))  # backend/
PROJECT_ROOT = os.path.abspath(os.path.join(_ROOT, ".."))  # repo root

# Insert project root at front of sys.path if not already present
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
