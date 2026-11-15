# Everwood Classic fork: applies a STAGED add-on update at Blender start-up.
#
# Why staged: on Windows the add-on's compiled modules (.pyd / .dll in pywowlib and third_party) are locked
# while Blender runs, so an update cannot overwrite them in place. ui/updater.py downloads + unpacks the
# release into the staging folder and writes a READY marker; this module runs at the very top of
# io_scene_wmo/__init__.py, BEFORE any compiled module is imported, and copies the staged files over the
# add-on folder.
#
# Rules:
#   * only files whose bytes differ are written (fast, and unchanged locked binaries are never touched);
#   * files listed in the OLD wbs_manifest.txt but absent from the NEW one are deleted (removed modules
#     must not linger: auto_load imports every .py it finds);
#   * files that were never in any manifest (pywowlib/archives/listfile.csv, user files) are left alone;
#   * a git checkout (.git present) is never overwritten - the updater uses `git pull` there instead;
#   * on any error the staging folder is kept and the copy is retried on the next start.
#
# Pure stdlib + bpy.utils only (this runs before the rest of the add-on is importable).

import os
import shutil
import hashlib

MANIFEST = "wbs_manifest.txt"
LAST_STATUS = None      # set by __init__.py, shown in the add-on preferences


def staging_root():
    import bpy
    return bpy.utils.user_resource('CONFIG', path='wbs_classic_update', create=True)


def read_manifest(path):
    """{relpath: sha1} from a wbs_manifest.txt ('sha1  relpath' per line, '/' separators)."""
    out = {}
    if not os.path.isfile(path):
        return out
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\r\n')
            if not line or line.startswith('#'):
                continue
            sha, _, rel = line.partition('  ')
            if rel:
                out[rel] = sha
    return out


def _sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def apply_pending(addon_dir):
    """Returns a short status string, or None when nothing was pending."""
    try:
        root = staging_root()
    except Exception:
        return None
    ready = os.path.join(root, 'READY')
    staged = os.path.join(root, 'staged', 'io_scene_wmo')
    if not (os.path.isfile(ready) and os.path.isdir(staged)):
        return None
    if os.path.isdir(os.path.join(addon_dir, '.git')):
        return "WBS updater: staged update ignored - this add-on is a git checkout (use git pull)"

    new_man = read_manifest(os.path.join(staged, MANIFEST))
    if not new_man:
        return "WBS updater: staged update has no %s - skipped" % MANIFEST
    old_man = read_manifest(os.path.join(addon_dir, MANIFEST))

    written = removed = 0
    try:
        for rel, sha in new_man.items():
            src = os.path.join(staged, *rel.split('/'))
            dst = os.path.join(addon_dir, *rel.split('/'))
            if os.path.isfile(dst) and _sha1(dst) == sha:
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            written += 1
        for rel in old_man:
            if rel in new_man:
                continue
            dst = os.path.join(addon_dir, *rel.split('/'))
            if os.path.isfile(dst):
                os.remove(dst)
                removed += 1
        shutil.copy2(os.path.join(staged, MANIFEST), os.path.join(addon_dir, MANIFEST))
    except Exception as e:
        return "WBS updater: update NOT finished (%s: %s) - will retry on next start" % (type(e).__name__, e)

    version = ''
    try:
        with open(ready, 'r', encoding='utf-8') as f:
            version = f.read().strip()
    except Exception:
        pass
    shutil.rmtree(os.path.join(root, 'staged'), ignore_errors=True)
    try:
        os.remove(ready)
    except OSError:
        pass
    return "WBS updater: updated to %s (%d files written, %d removed)" % (version or 'new version', written, removed)
