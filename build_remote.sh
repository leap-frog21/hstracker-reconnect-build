#!/bin/bash
set -euo pipefail
BUILD_ROOT="$(cd "$(dirname "$0")" && pwd)"
SOURCE_ROOT="$(cd "${1:?Pass the patched upstream directory}" && pwd)"
OUTPUT_ROOT="$BUILD_ROOT/out"
export CI=true

for required_tool in xcodebuild wget ditto codesign shasum plutil; do
  command -v "$required_tool" >/dev/null || { echo "Missing build tool: $required_tool" >&2; exit 2; }
done
xcodebuild -version
mkdir -p "$OUTPUT_ROOT"
plutil -lint "$SOURCE_ROOT/HSTracker.xcodeproj/project.pbxproj"

# Upstream's resolved file omits transitive dependencies declared by OAuthSwift.
# Let Xcode complete the graph, but reject any change to an existing pin.
RESOLVED="$SOURCE_ROOT/HSTracker.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved"
cp "$RESOLVED" "$OUTPUT_ROOT/upstream-Package.resolved"
xcodebuild \
  -resolvePackageDependencies \
  -project "$SOURCE_ROOT/HSTracker.xcodeproj" \
  -scheme HSTracker \
  -derivedDataPath "$OUTPUT_ROOT/DerivedData" \
  2>&1 | tee "$OUTPUT_ROOT/resolve.log"
python3 - "$OUTPUT_ROOT/upstream-Package.resolved" "$RESOLVED" "$OUTPUT_ROOT/Package.resolved" <<'PY'
from pathlib import Path
import json,shutil,sys
baseline,resolved,output=map(Path,sys.argv[1:])
before={p['identity']:p for p in json.loads(baseline.read_text())['pins']}
after={p['identity']:p for p in json.loads(resolved.read_text())['pins']}
for identity,pin in before.items():
    actual=after.get(identity)
    if actual is None or actual['state'] != pin['state'] or actual['location'] != pin['location']:
        raise SystemExit(f'Resolver changed existing upstream pin: {identity}')
shutil.copyfile(resolved,output)
print('Preserved all upstream pins; completed dependencies:', ', '.join(sorted(after.keys()-before.keys())) or '(none)')
PY

# Build only the completed lockfile. Binary downloads are not all pinned;
# record their exact digests below for review.
xcodebuild \
  -project "$SOURCE_ROOT/HSTracker.xcodeproj" \
  -scheme HSTracker -configuration Debug \
  -destination 'platform=macOS,arch=arm64' \
  -derivedDataPath "$OUTPUT_ROOT/DerivedData" \
  -onlyUsePackageVersionsFromResolvedFile \
  ARCHS=arm64 ONLY_ACTIVE_ARCH=YES CODE_SIGNING_ALLOWED=NO \
  build 2>&1 | tee "$OUTPUT_ROOT/build.log"

APP="$OUTPUT_ROOT/DerivedData/Build/Products/Debug/HSTracker.app"
test -d "$APP"

# Keep an experimental build from updating itself before acceptance testing.
/usr/libexec/PlistBuddy -c 'Set :SUEnableAutomaticChecks false' "$APP/Contents/Info.plist" \
  || /usr/libexec/PlistBuddy -c 'Add :SUEnableAutomaticChecks bool false' "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c 'Set :SUAllowsAutomaticUpdates false' "$APP/Contents/Info.plist" \
  || /usr/libexec/PlistBuddy -c 'Add :SUAllowsAutomaticUpdates bool false' "$APP/Contents/Info.plist"
codesign --force --deep --sign - --options runtime \
  --entitlements "$SOURCE_ROOT/HSTracker/HSTracker.entitlements" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$OUTPUT_ROOT/HSTracker-2.0-test-arm64.zip"

python3 - "$BUILD_ROOT" "$SOURCE_ROOT" "$OUTPUT_ROOT" <<'PY'
from pathlib import Path
import hashlib,json,subprocess,sys
root,source,out=map(Path,sys.argv[1:])
package=out/'HSTracker-2.0-test-arm64.zip'
if package.stat().st_size >= 2 * 1024**3:
    raise SystemExit('Package exceeds release asset size limit')
dependency_files=[]
downloaded=source/'downloaded-frameworks'
if downloaded.exists():
    for path in sorted(downloaded.rglob('*')):
        if path.is_file() and (path.suffix in ('.zip','.dylib','.dll') or path.name=='HearthMirror'):
            dependency_files.append({'path':str(path.relative_to(source)),
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
manifest={'upstream_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),
    'patch_sha256':hashlib.sha256((root/'reconnect.patch').read_bytes()).hexdigest(),
    'xcode':subprocess.check_output(['xcodebuild','-version'],text=True).strip(),
    'architecture':'arm64','signature':'ad-hoc; not notarized',
    'live_acceptance':'not performed','binary_dependencies':dependency_files,
    'swift_packages':json.loads((out/'Package.resolved').read_text())['pins'],
    'package_resolved_sha256':hashlib.sha256((out/'Package.resolved').read_bytes()).hexdigest(),
    'app_archive_sha256':hashlib.sha256(package.read_bytes()).hexdigest()}
(out/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n'
    for p in (package,out/'build-manifest.json',out/'Package.resolved')))
(out/'notes.md').write_text('Development build only. Ad-hoc signed and not notarized. '
    'Built from pinned HSTracker 3.7.0 plus the reconnect patch. '
    'Runtime, HearthMirror access, account features, and repeated reconnects still require acceptance testing. '
    'Do not run alongside the official HSTracker. Back up existing HSTracker data before first launch.\n')
PY
