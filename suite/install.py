#!/usr/bin/env python3
"""Install the self-use 3.0 suite without an old source directory or Xcode."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
SUPPORT = HOME / 'Library/Application Support/HSDisconnect'
LABEL = 'com.leap.hsautostart'
AGENT = HOME / f'Library/LaunchAgents/{LABEL}.plist'
DOMAIN = f'gui/{os.getuid()}'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(app):
    entries = {}
    for path in sorted(app.rglob('*')):
        if path.is_symlink():
            entries[str(path.relative_to(app))] = {'link': os.readlink(path)}
        elif path.is_file():
            entries[str(path.relative_to(app))] = {'sha256': digest(path)}
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()


def verify_package():
    manifest = json.loads((ROOT / 'package-manifest.json').read_text())
    if manifest['suite_version'] != '3.0.0':
        raise RuntimeError('不是预期的 3.0 安装包')
    for relative, expected in manifest['files'].items():
        path = ROOT / relative
        if not path.resolve().is_relative_to(ROOT) or not path.is_file() or digest(path) != expected:
            raise RuntimeError(f'安装文件校验失败：{relative}')
    for relative, target in manifest['symlinks'].items():
        path = ROOT / relative
        if not path.is_symlink() or os.readlink(path) != target or not path.resolve().is_relative_to(ROOT):
            raise RuntimeError(f'安装链接校验失败：{relative}')
    for name in ('HSDisconnect', 'HSTracker'):
        subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict',
                        str(ROOT / 'payload' / f'{name}.app')], check=True, capture_output=True)
    return manifest


def quit_app_processes(name):
    result = subprocess.run(['/usr/bin/pgrep', '-x', name], capture_output=True, text=True)
    for pid in result.stdout.split():
        executable = subprocess.run(['/bin/ps', '-p', pid, '-o', 'comm='],
                                    capture_output=True, text=True).stdout.strip()
        if not executable:
            continue
        app = Path(executable).parent.parent.parent
        info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
        expected = {'HSDisconnect': 'com.leap.hsdisconnect', 'HSTracker': 'net.hearthsim.hstracker'}[name]
        if info.get('CFBundleIdentifier') != expected:
            raise RuntimeError(f'发现同名但身份不同的程序：{name}，请手动退出')
        subprocess.run(['/usr/bin/osascript', '-e', f'tell application {json.dumps(str(app), ensure_ascii=False)} to quit'],
                       check=True, timeout=15, capture_output=True)
    for _ in range(30):
        if subprocess.run(['/usr/bin/pgrep', '-x', name], stdout=subprocess.DEVNULL).returncode == 1:
            return
        time.sleep(.2)
    raise RuntimeError(f'{name} 尚未退出，请稍后重试')


def service_bootout():
    subprocess.run(['/bin/launchctl', 'bootout', f'{DOMAIN}/{LABEL}'], capture_output=True)


def service_bootstrap():
    subprocess.run(['/bin/launchctl', 'bootstrap', DOMAIN, str(AGENT)], check=True, capture_output=True)
    subprocess.run(['/bin/launchctl', 'print', f'{DOMAIN}/{LABEL}'], check=True, capture_output=True)


def install():
    if subprocess.run(['/usr/bin/pgrep', '-x', 'Hearthstone'], stdout=subprocess.DEVNULL).returncode == 0:
        raise RuntimeError('请先正常退出炉石，再运行安装；安装不会中断正在进行的对局')
    timestamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = SUPPORT / 'install-backups' / timestamp
    backup.mkdir(parents=True, mode=0o700)
    os.chmod(backup, 0o700)
    changed_apps = []
    saved_files = {}
    config = SUPPORT / 'config.json'
    config_existed = config.exists()
    for path in (AGENT, SUPPORT / 'runtime.json'):
        saved_files[path] = path.read_bytes() if path.exists() else None
        if path.exists():
            (backup / path.name).write_bytes(path.read_bytes())
    temp_root = Path(tempfile.gettempdir()) / 'agent-tasks'
    temp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='hs-suite-install-', dir=temp_root) as temporary:
        staging = Path(temporary)
        # Complete all copies and signature checks before replacing anything.
        for name in ('HSDisconnect', 'HSTracker'):
            staged = staging / f'{name}.app'
            subprocess.run(['/usr/bin/ditto', str(ROOT / 'payload' / f'{name}.app'), str(staged)], check=True)
            subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(staged)], check=True, capture_output=True)
        service_bootout()
        try:
            for name in ('HSDisconnect', 'HSTracker'):
                quit_app_processes(name)
            for name in ('HSDisconnect', 'HSTracker'):
                staged = staging / f'{name}.app'
                destination = Path('/Applications') / staged.name
                if destination.exists() and fingerprint(destination) == fingerprint(staged):
                    continue
                old = backup / staged.name
                had_old = destination.exists()
                if had_old:
                    os.rename(destination, old)
                changed_apps.append((destination, old if had_old else None))
                os.rename(staged, destination)
            SUPPORT.mkdir(parents=True, exist_ok=True)
            if not config_existed:
                shutil.copyfile(ROOT / 'config.default.json', config)
            runtime = {'python': sys.executable}
            (SUPPORT / 'runtime.json').write_text(json.dumps(runtime, indent=2) + '\n')
            logs = HOME / 'Library/Logs/HSDisconnect'
            logs.mkdir(parents=True, exist_ok=True)
            AGENT.parent.mkdir(parents=True, exist_ok=True)
            resources = Path('/Applications/HSDisconnect.app/Contents/Resources')
            agent = {'Label': LABEL,
                     'ProgramArguments': [sys.executable, str(resources / 'session_manager.py')],
                     'WorkingDirectory': str(resources), 'RunAtLoad': True, 'KeepAlive': True,
                     'StandardOutPath': str(logs / 'session-3.stdout.log'),
                     'StandardErrorPath': str(logs / 'session-3.stderr.log')}
            AGENT.write_bytes(plistlib.dumps(agent))
            subprocess.run(['/Applications/HSDisconnect.app/Contents/MacOS/HSDisconnect', '--diagnose'],
                           check=True, capture_output=True, timeout=15)
            service_bootstrap()
        except BaseException:
            service_bootout()
            for destination, old in reversed(changed_apps):
                if destination.exists():
                    shutil.rmtree(destination)
                if old is not None:
                    os.rename(old, destination)
            for path, content in saved_files.items():
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(content)
            if not config_existed:
                config.unlink(missing_ok=True)
            if AGENT.exists():
                service_bootstrap()
            raise
    for name in ('HSDisconnect', 'HSTracker'):
        subprocess.run(['/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister',
                        '-f', f'/Applications/{name}.app'], check=True, capture_output=True)
    record = {'suite_version': '3.0.0', 'installed_at': timestamp,
              'python': sys.executable, 'agent': str(AGENT), 'backup': str(backup),
              'old_project_directory_required': False, 'hstracker_build_run': 39111059922}
    (SUPPORT / 'installation-3.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print('3.0 安装完成。炉石启动时自动打开拔线按钮和 HSTracker，退出时一起关闭。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--install', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine() != 'arm64' or sys.version_info < (3, 10):
        raise RuntimeError('此包面向 Apple 芯片 Mac，需要现有 Python 3.10 或更高版本')
    manifest = verify_package()
    if args.check:
        print(json.dumps({'suite_version': manifest['suite_version'], 'package_verified': True,
                          'python_compatible': True, 'game_running': subprocess.run(
                              ['/usr/bin/pgrep', '-x', 'Hearthstone'], stdout=subprocess.DEVNULL).returncode == 0}))
    else:
        install()


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(f'安装未完成：{error}', file=sys.stderr)
        sys.exit(1)
