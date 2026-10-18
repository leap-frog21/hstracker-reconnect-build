#!/usr/bin/env python3
"""Start/stop the installed apps with Hearthstone; never disconnect anything."""
from pathlib import Path
import argparse
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import time

APPS = (Path('/Applications/HSDisconnect.app'), Path('/Applications/HSTracker.app'))
LOG = logging.getLogger('suite-session')


class Session:
    def __init__(self):
        self.active = False
        self.absent_since = None

    def transition(self, game_running, now):
        if game_running:
            self.absent_since = None
            if not self.active:
                self.active = True
                return 'start'
        elif self.active:
            if self.absent_since is None:
                self.absent_since = now
            elif now - self.absent_since >= 2:
                self.active = False
                self.absent_since = None
                return 'stop'
        return None


def game_running():
    return subprocess.run(['/usr/bin/pgrep', '-x', 'Hearthstone'],
                          stdout=subprocess.DEVNULL).returncode == 0


def running_executables(name):
    result = subprocess.run(['/usr/bin/pgrep', '-x', name], capture_output=True, text=True)
    paths = []
    for pid in result.stdout.split():
        value = subprocess.run(['/bin/ps', '-p', pid, '-o', 'comm='],
                               capture_output=True, text=True).stdout.strip()
        if value:
            paths.append(value)
    return paths


def start_app(app):
    if not app.is_dir():
        LOG.error('Installed app missing: %s', app.name)
        return
    current = running_executables(app.stem)
    if current:
        expected = str(app / 'Contents/MacOS' / app.stem)
        if any(path != expected for path in current):
            LOG.warning('Another copy of %s is running; not opening a duplicate', app.stem)
        return
    subprocess.run(['/usr/bin/open', '-n', str(app)], check=True, timeout=10)
    LOG.info('Opened %s', app.name)


def stop_app(app):
    expected = str(app / 'Contents/MacOS' / app.stem)
    current = running_executables(app.stem)
    if expected not in current:
        return
    # Only address the installed copy, never a project or backup copy.
    subprocess.run(['/usr/bin/osascript', '-e', f'tell application "{app}" to quit'],
                   check=True, timeout=15, capture_output=True)
    LOG.info('Quit %s', app.name)


def apply_action(action):
    if action is None:
        return
    for app in APPS:
        try:
            (start_app if action == 'start' else stop_app)(app)
        except (OSError, subprocess.SubprocessError) as error:
            LOG.error('%s %s failed: %s', action, app.name, type(error).__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only process check')
    args = parser.parse_args()
    if args.check:
        import json
        print(json.dumps({'game_running': game_running(),
                          'installed_apps': {app.name: app.is_dir() for app in APPS},
                          'running_apps': {app.name: len(running_executables(app.stem)) for app in APPS}}))
        return
    directory = Path.home() / 'Library/Logs/HSDisconnect'
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(directory / 'session-3.log', maxBytes=1_000_000,
                                  backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    LOG.info('Session manager 3.0 started')
    session = Session()
    while True:
        apply_action(session.transition(game_running(), time.monotonic()))
        time.sleep(1)


if __name__ == '__main__':
    main()
