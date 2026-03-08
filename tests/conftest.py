"""Shared pytest configuration.

Stubs out `taskw` so tests can import cli.py without a real Taskwarrior
installation or the taskw package.
"""
import sys
from unittest.mock import MagicMock

# Stub the taskw package before any test module imports cli.py.
# The real taskw is a git dependency and may not be present in CI.
taskw_stub = MagicMock()
taskw_stub.TaskWarrior = MagicMock
sys.modules.setdefault('taskw', taskw_stub)
