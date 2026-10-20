#!/usr/bin/env python3
"""Build the small helper with Command Line Tools, not a full local Xcode."""
from pathlib import Path
import argparse
import plistlib
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent


def build(output):
    app = output / 'HSDisconnect.app'
    if app.exists():
        raise RuntimeError('Output already exists; choose a fresh build directory')
    (app / 'Contents/MacOS').mkdir(parents=True)
    resources = app / 'Contents/Resources'
    resources.mkdir()
    info = {'CFBundleIdentifier': 'com.leap.hsdisconnect', 'CFBundleName': 'HSDisconnect',
            'CFBundleDisplayName': '炉石拔线助手 3.0', 'CFBundleExecutable': 'HSDisconnect',
            'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': '3.0.1',
            'CFBundleVersion': '3.0.1', 'LSUIElement': True, 'LSMinimumSystemVersion': '14.0',
            'NSHighResolutionCapable': True}
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    for source, target in [(ROOT / 'helper/hsd.py', 'hsd.py'),
                           (ROOT / 'session_manager.py', 'session_manager.py')]:
        shutil.copyfile(source, resources / target)
    temp_root = Path(tempfile.gettempdir()) / 'agent-tasks'
    temp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='hs-suite-compiler-', dir=temp_root) as task:
        subprocess.run(['xcrun', 'swiftc', '-O', '-target', 'arm64-apple-macosx14.0',
                        '-module-cache-path', str(Path(task) / 'module-cache'),
                        '-framework', 'Cocoa', '-framework', 'Carbon',
                        str(ROOT / 'helper/main.swift'), '-o', str(app / 'Contents/MacOS/HSDisconnect')], check=True)
    subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(app)], check=True)
    subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(app)], check=True)
    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(build(args.output.resolve()))
