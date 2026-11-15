# Build the release zip the in-Blender updater installs:  py -3 tools/make_release.py  [out_dir]
#   -> dist/io_scene_wmo-v<version>.zip   (version = bl_info["version"] in __init__.py)
# Contents = every file git tracks or would track (git ls-files --cached --others --exclude-standard), so
# .gitignored data (pywowlib/archives/listfile.csv, caches) is never shipped and a user's local copy of it
# survives updates. The zip has one top folder io_scene_wmo/ and a wbs_manifest.txt ("sha1  relpath" per
# line) that updater_apply.py uses to copy only changed files and delete files a release dropped.
# Publish:  gh release create v<version> dist/io_scene_wmo-v<version>.zip --title "v<version>" --notes "..."
import os, re, sys, hashlib, zipfile, subprocess

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(here, '__init__.py'), encoding='utf-8').read()
m = re.search(r'"version"\s*:\s*\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\)', src)
if not m:
    sys.exit("bl_info version not found in __init__.py")
version = '.'.join(m.groups())
out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, 'dist')
os.makedirs(out_dir, exist_ok=True)
out = os.path.join(out_dir, 'io_scene_wmo-v%s.zip' % version)

files = subprocess.run(['git', '-C', here, 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                       capture_output=True, check=True).stdout.decode('utf-8').split('\0')
files = sorted(f for f in files if f and f != 'wbs_manifest.txt' and not f.startswith('dist/')
               and os.path.isfile(os.path.join(here, f)))

def sha1(p):
    h = hashlib.sha1()
    with open(p, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

lines = ['# WoW Blender Studio (Classic fork) v%s - sha1  relpath' % version]
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in files:
        p = os.path.join(here, f)
        lines.append('%s  %s' % (sha1(p), f))
        z.write(p, 'io_scene_wmo/' + f)
    z.writestr('io_scene_wmo/wbs_manifest.txt', '\n'.join(lines) + '\n')
print("wrote %s  (%d files, %.1f MB)" % (out, len(files), os.path.getsize(out) / 1048576.0))
