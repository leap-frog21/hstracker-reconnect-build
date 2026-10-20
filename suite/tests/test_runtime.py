"""Synthetic regression cases; no live game, logs, accounts, or socket calls."""
from pathlib import Path
import importlib.util
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backend = load('hsd', ROOT / 'helper/hsd.py')
manager = load('manager', ROOT / 'session_manager.py')


def connection(identity, ip='192.0.2.1', host='', process='/Applications/Hearthstone/Hearthstone.app/Contents/MacOS/Hearthstone', port='1119'):
    return {'id': identity, 'metadata': {'network': 'tcp', 'destinationPort': port,
            'processPath': process, 'destinationIP': ip, 'host': host}}


class Lifecycle(unittest.TestCase):
    def test_start_stop_and_relaunch(self):
        state = manager.Session()
        self.assertIsNone(state.transition(False, 0))
        self.assertEqual(state.transition(True, 1), 'start')
        self.assertIsNone(state.transition(True, 2))
        self.assertIsNone(state.transition(False, 3))
        self.assertIsNone(state.transition(False, 4))
        self.assertEqual(state.transition(False, 5), 'stop')
        self.assertIsNone(state.transition(False, 6))
        self.assertEqual(state.transition(True, 7), 'start')

    def test_brief_game_process_gap_is_debounced(self):
        state = manager.Session()
        state.transition(True, 0)
        self.assertIsNone(state.transition(False, 1))
        self.assertIsNone(state.transition(True, 2))
        self.assertTrue(state.active)


if __name__ == '__main__':
    unittest.main()
