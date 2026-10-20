#!/usr/bin/env python3
"""Package two apps and a reinstaller; never include the user's live data."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hstracker-app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    package = output / 'Hearthstone-Disconnect-Suite-3.0.1-arm64'
    if package.exists():
        raise RuntimeError('Package directory already exists')
    source = args.hstracker_app.resolve()
    provenance = json.loads((ROOT / 'hstracker-build.json').read_text())
    assert digest(source / 'Contents/MacOS/HSTracker') == provenance['executable_sha256']
    subprocess.run([sys.executable, str(ROOT / 'build.py'), '--output', str(package / 'payload')], check=True)
    subprocess.run(['/usr/bin/ditto', str(source), str(package / 'payload/HSTracker.app')], check=True)
    for source_name, dest_name in [('install.py', 'install.py'), ('安装3.0.command', '安装3.0.command'),
                                   ('helper/config.default.json', 'config.default.json'),
                                   ('INSTALL-README.md', 'README.md')]:
        shutil.copyfile(ROOT / source_name, package / dest_name)
    (package / '安装3.0.command').chmod(0o755)
    shutil.copyfile(ROOT.parent / 'LICENSE', package / 'LICENSE')
    shutil.copyfile(ROOT / 'hstracker-build.json', package / 'hstracker-build.json')
    manifest = {'suite_version': '3.0.1', 'architecture': 'arm64',
                'python_bundled': False, 'signature': 'ad-hoc; not notarized',
                'hstracker_build_run': 39111059922, 'files': {}, 'symlinks': {}}
    for path in sorted(package.rglob('*')):
        relative = str(path.relative_to(package))
        if path.is_symlink():
            manifest['symlinks'][relative] = os.readlink(path)
        elif path.is_file():
            manifest['files'][relative] = digest(path)
    (package / 'package-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    subprocess.run([sys.executable, str(package / 'install.py'), '--check'], check=True)
    archive = output / (package.name + '.zip')
    subprocess.run(['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(package), str(archive)], check=True)
    shutil.copyfile(package / 'package-manifest.json', output / 'package-manifest.json')
    (output / 'SHA256SUMS').write_text(''.join(f'{digest(path)}  {path.name}\n'
                                            for path in (archive, output / 'package-manifest.json')))
    print(json.dumps({'package': archive.name, 'bytes': archive.stat().st_size,
                      'manifest_files': len(manifest['files'])}))


if __name__ == '__main__':
    main()
