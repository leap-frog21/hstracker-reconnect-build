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


class ConnectionSelection(unittest.TestCase):
    def selected(self, connections, server=None):
        with patch.object(backend, 'clash_connections', return_value=connections), \
             patch.object(backend, 'last_server_ip', return_value=server):
            return backend.hs_connections()

    def test_preserves_login_and_unrelated_connections(self):
        game = connection('game')
        self.assertEqual(self.selected([connection('login', host='login.invalid'),
                         connection('other', process='/Applications/Other.app/Contents/MacOS/Other'), game]), [game])

    def test_ambiguous_without_server_does_nothing(self):
        self.assertEqual(self.selected([connection('one'), connection('two', ip='192.0.2.2')]), [])

    def test_known_server_selects_only_that_server(self):
        game = connection('wanted', ip='192.0.2.2')
        self.assertEqual(self.selected([connection('old'), game], '192.0.2.2'), [game])

    def test_missing_known_server_does_nothing(self):
        self.assertEqual(self.selected([connection('wrong')], '192.0.2.9'), [])

    def test_zero_second_cut_closes_only_selected_connection(self):
        with patch.object(backend, 'hs_connections', return_value=[connection('wanted')]), \
             patch.object(backend, 'clash_request') as request:
            self.assertEqual(backend.cut_once(0), 1)
            request.assert_called_once_with('DELETE', '/connections/wanted')


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
