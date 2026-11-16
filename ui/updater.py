# Everwood Classic fork: update checker.
#
# Source (default): the latest GitHub Release of the public fork REPO below. The release must carry an
# asset named io_scene_wmo-v<X.Y.Z>.zip built by tools/make_release.py (top folder io_scene_wmo/ + a
# wbs_manifest.txt). Optional: Preferences > Add-ons > WoW Blender Studio > "Custom update URL" points to
# a JSON file on our own server instead:  {"version": "1.2.0", "url": "https://.../io_scene_wmo-v1.2.0.zip",
#                                          "notes": "what changed", "page": "https://..."}
#
# Flow: check (background thread, at most once per "Check every N days", 5 s after start-up) ->
# "Update available" in the status bar, the WoW Scene panel and the add-on preferences -> "Download update"
# downloads + unpacks it into the staging folder -> restart Blender -> updater_apply.py copies it in.
# A git checkout of the add-on is updated with `git pull --ff-only` instead (refused if it has local edits).
#
# Network: one HTTPS GET to api.github.com (or the custom URL) per check, plus the zip download when the
# user clicks. Nothing about the user or the machine is sent beyond a generic User-Agent.

import os
import re
import sys
import json
import time
import shutil
import zipfile
import threading
import subprocess
import urllib.error
import urllib.request

import bpy

from .. import updater_apply
from ..config import ADDON_MODULE_NAME

REPO = "pkuzic/wow-blender-studio-for-classic"
API_LATEST = "https://api.github.com/repos/%s/releases/latest" % REPO
RELEASES_PAGE = "https://github.com/%s/releases" % REPO
USER_AGENT = "WBS-Classic-Updater"
TIMEOUT = 10

# status: idle | checking | uptodate | available | downloading | restart | error
STATE = {
    'status': 'idle', 'latest': '', 'url': '', 'notes': '', 'page': '', 'error': '',
    'progress': 0.0, 'last_check': 0.0,
}
_thread = None


# ----------------------------------------------------------------------------------------------- helpers

def addon_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_git_checkout():
    return os.path.isdir(os.path.join(addon_dir(), '.git'))


def current_version():
    """Version from __init__.py ON DISK: right after a staged update is applied, the already-imported __init__
    module (and its bl_info) is still the old one for this session, but this module is loaded after the swap."""
    try:
        with open(os.path.join(addon_dir(), '__init__.py'), 'r', encoding='utf-8') as f:
            m = re.search(r'"version"\s*:\s*\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\)', f.read())
        if m:
            return tuple(int(x) for x in m.groups())
    except OSError:
        pass
    mod = sys.modules.get(ADDON_MODULE_NAME)
    return tuple(getattr(mod, 'bl_info', {}).get('version', (0, 0, 0)))


def parse_version(text):
    text = (text or '').strip().lstrip('vV')
    parts = []
    for p in text.split('.'):
        digits = ''.join(ch for ch in p if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def fmt_version(v):
    return '.'.join(str(x) for x in v)


def _prefs():
    addon = bpy.context.preferences.addons.get(ADDON_MODULE_NAME)
    return addon.preferences if addon else None


def _state_file():
    return os.path.join(updater_apply.staging_root(), 'state.json')


def _load_state():
    try:
        with open(_state_file(), 'r', encoding='utf-8') as f:
            saved = json.load(f)
        for k in ('latest', 'url', 'notes', 'page', 'last_check'):
            if k in saved:
                STATE[k] = saved[k]
    except Exception:
        pass
    if os.path.isfile(os.path.join(updater_apply.staging_root(), 'READY')):
        STATE['status'] = 'restart'
    elif STATE['latest'] and parse_version(STATE['latest']) > current_version():
        STATE['status'] = 'available'


def _save_state():
    try:
        with open(_state_file(), 'w', encoding='utf-8') as f:
            json.dump({k: STATE[k] for k in ('latest', 'url', 'notes', 'page', 'last_check')}, f, indent=1)
    except Exception as e:
        print("WBS updater: cannot save state:", e)


def _get(url):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def _redraw():
    wm = bpy.context.window_manager
    if not wm:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type in ('PREFERENCES', 'PROPERTIES', 'STATUSBAR'):
                area.tag_redraw()


def _start(target, *args):
    """Runs target in a worker thread; a main-thread timer saves state + redraws when it ends."""
    global _thread
    if _thread and _thread.is_alive():
        return False
    _thread = threading.Thread(target=target, args=args, daemon=True)
    _thread.start()

    def poll():
        if _thread.is_alive():
            _redraw()
            return 0.5
        _save_state()
        _redraw()
        return None

    bpy.app.timers.register(poll, first_interval=0.5)
    return True


# ------------------------------------------------------------------------------------------------- check

def _check_worker(custom_url):
    STATE['status'], STATE['error'] = 'checking', ''
    try:
        if custom_url:
            with _get(custom_url) as r:
                data = json.loads(r.read().decode('utf-8'))
            latest, url = str(data.get('version', '')), str(data.get('url', ''))
            notes, page = str(data.get('notes', '')), str(data.get('page', '') or custom_url)
        else:
            with _get(API_LATEST) as r:
                data = json.loads(r.read().decode('utf-8'))
            latest, notes, page = data.get('tag_name', ''), data.get('body') or '', data.get('html_url') or RELEASES_PAGE
            url = ''
            for asset in data.get('assets', []):
                name = asset.get('name', '')
                if name.startswith('io_scene_wmo') and name.endswith('.zip'):
                    url = asset.get('browser_download_url', '')
                    break
        if not parse_version(latest):
            raise ValueError("no version in the release info (%r)" % latest)
        STATE.update(latest=latest, url=url, notes=notes.strip(), page=page, last_check=time.time())
        if os.path.isfile(os.path.join(updater_apply.staging_root(), 'READY')):
            STATE['status'] = 'restart'
        elif parse_version(latest) > current_version():
            STATE['status'] = 'available'
            print("WBS updater: version %s is available (installed %s)" % (latest, fmt_version(current_version())))
        else:
            STATE['status'] = 'uptodate'
    except urllib.error.HTTPError as e:
        STATE['status'] = 'error'
        STATE['error'] = "no release published yet" if e.code == 404 and not custom_url else "HTTP %d" % e.code
        STATE['last_check'] = time.time()
    except Exception as e:
        STATE['status'], STATE['error'] = 'error', "%s: %s" % (type(e).__name__, e)


def check_now(force=False):
    prefs = _prefs()
    custom = prefs.update_custom_url.strip() if prefs else ''
    if not force and prefs:
        if not prefs.update_auto_check:
            return False
        if time.time() - float(STATE['last_check'] or 0) < prefs.update_interval_days * 86400:
            return False
    return _start(_check_worker, custom)


def _auto_check():
    try:
        check_now(force=False)
    except Exception as e:
        print("WBS updater: auto-check failed:", e)
    return None


# ---------------------------------------------------------------------------------------------- download

def _download_worker(url, version):
    STATE['status'], STATE['error'], STATE['progress'] = 'downloading', '', 0.0
    root = updater_apply.staging_root()
    tmp_zip = os.path.join(root, 'download.zip')
    unpack = os.path.join(root, 'unpack')
    staged = os.path.join(root, 'staged')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp_zip, 'wb') as out:
            total = int(r.headers.get('Content-Length') or 0)
            done = 0
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if total:
                    STATE['progress'] = done / total

        shutil.rmtree(unpack, ignore_errors=True)
        with zipfile.ZipFile(tmp_zip) as z:
            for name in z.namelist():                       # refuse absolute paths / '..' entries
                if name.startswith(('/', '\\')) or '..' in name.replace('\\', '/').split('/'):
                    raise ValueError("unsafe path in zip: %s" % name)
            z.extractall(unpack)

        pkg = os.path.join(unpack, 'io_scene_wmo')
        man_path = os.path.join(pkg, updater_apply.MANIFEST)
        if not os.path.isfile(os.path.join(pkg, '__init__.py')) or not os.path.isfile(man_path):
            raise ValueError("not a WBS release zip (needs io_scene_wmo/__init__.py + %s)" % updater_apply.MANIFEST)
        manifest = updater_apply.read_manifest(man_path)
        missing = [rel for rel in manifest if not os.path.isfile(os.path.join(pkg, *rel.split('/')))]
        if missing:
            raise ValueError("release zip is incomplete (%d files missing, e.g. %s)" % (len(missing), missing[0]))

        shutil.rmtree(staged, ignore_errors=True)
        os.makedirs(staged)
        shutil.move(pkg, os.path.join(staged, 'io_scene_wmo'))
        with open(os.path.join(root, 'READY'), 'w', encoding='utf-8') as f:
            f.write(version)
        STATE['status'] = 'restart'
        print("WBS updater: %s downloaded - restart Blender to finish the update" % version)
    except Exception as e:
        STATE['status'], STATE['error'] = 'error', "download failed - %s: %s" % (type(e).__name__, e)
    finally:
        shutil.rmtree(unpack, ignore_errors=True)
        try:
            os.remove(tmp_zip)
        except OSError:
            pass


def _git_pull():
    d = addon_dir()
    try:
        dirty = subprocess.run(['git', '-C', d, 'status', '--porcelain', '--untracked-files=no'],
                               capture_output=True, text=True, timeout=30)
        if dirty.returncode != 0:
            return False, "git status failed: " + (dirty.stderr.strip() or 'unknown error')
        if dirty.stdout.strip():
            return False, "the add-on folder has local edits - commit or stash them, then pull"
        pull = subprocess.run(['git', '-C', d, 'pull', '--ff-only'], capture_output=True, text=True, timeout=120)
        if pull.returncode != 0:
            return False, "git pull failed: " + (pull.stderr.strip() or pull.stdout.strip())
        return True, pull.stdout.strip().splitlines()[-1] if pull.stdout.strip() else "pulled"
    except FileNotFoundError:
        return False, "git is not on PATH"
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)


# ------------------------------------------------------------------------------------------------- UI

class WBS_OT_update_check(bpy.types.Operator):
    bl_idname = "wbs.update_check"
    bl_label = "Check for Updates"
    bl_description = "Ask GitHub (or the custom update URL) whether a newer WoW Blender Studio is available"

    def execute(self, context):
        if not check_now(force=True):
            self.report({'INFO'}, "WBS updater: a check or download is already running")
        return {'FINISHED'}


class WBS_OT_update_install(bpy.types.Operator):
    bl_idname = "wbs.update_install"
    bl_label = "Download Update"
    bl_description = "Download the new version now; it is installed the next time Blender starts"

    def execute(self, context):
        if STATE['status'] != 'available':
            self.report({'WARNING'}, "WBS updater: no update to install")
            return {'CANCELLED'}
        if is_git_checkout():
            ok, msg = _git_pull()
            if ok:
                STATE['status'] = 'restart'
                self.report({'INFO'}, "WBS updater: %s - restart Blender to load it" % msg)
            else:
                self.report({'ERROR'}, "WBS updater: " + msg)
            _redraw()
            return {'FINISHED'} if ok else {'CANCELLED'}
        if not STATE['url']:
            self.report({'ERROR'}, "WBS updater: the release has no io_scene_wmo zip - download it from the release page")
            return {'CANCELLED'}
        _start(_download_worker, STATE['url'], STATE['latest'])
        self.report({'INFO'}, "WBS updater: downloading %s ..." % STATE['latest'])
        return {'FINISHED'}


class WBS_OT_update_page(bpy.types.Operator):
    bl_idname = "wbs.update_page"
    bl_label = "Release Notes"
    bl_description = "Open the release page in the web browser"

    def execute(self, context):
        bpy.ops.wm.url_open(url=STATE['page'] or RELEASES_PAGE)
        return {'FINISHED'}


def _status_line():
    s, cur = STATE['status'], fmt_version(current_version())
    if s == 'available':
        return "Update available: %s (installed %s)" % (STATE['latest'], cur), 'IMPORT'
    if s == 'downloading':
        return "Downloading %s ... %d%%" % (STATE['latest'], int(STATE['progress'] * 100)), 'SORTTIME'
    if s == 'restart':
        return "Update ready - restart Blender to finish", 'FILE_REFRESH'
    if s == 'checking':
        return "Checking for updates ...", 'SORTTIME'
    if s == 'uptodate':
        return "Up to date (%s)" % cur, 'CHECKMARK'
    if s == 'error':
        return "Update check: %s" % STATE['error'], 'ERROR'
    return "Installed version %s" % cur, 'INFO'


def draw_prefs(prefs, layout):
    col = layout.column(align=True)
    col.label(text='Updates:', icon='URL')
    box = col.box()
    row = box.row()
    row.prop(prefs, 'update_auto_check')
    sub = row.row()
    sub.enabled = prefs.update_auto_check
    sub.prop(prefs, 'update_interval_days')
    box.prop(prefs, 'update_custom_url')
    text, icon = _status_line()
    box.label(text=text, icon=icon)
    if STATE['status'] == 'available' and STATE['notes']:
        for line in STATE['notes'].splitlines()[:8]:
            if line.strip():
                box.label(text=line.strip()[:120])
    row = box.row()
    row.operator(WBS_OT_update_check.bl_idname, icon='FILE_REFRESH')
    if STATE['status'] == 'available':
        row.operator(WBS_OT_update_install.bl_idname,
                     text="Pull Update (git)" if is_git_checkout() else "Download Update", icon='IMPORT')
    row.operator(WBS_OT_update_page.bl_idname, icon='URL')
    if is_git_checkout():
        box.label(text="This add-on is a git checkout: updates use git pull --ff-only", icon='INFO')
    if updater_apply.LAST_STATUS:
        box.label(text=updater_apply.LAST_STATUS, icon='INFO')


def draw_notice(layout):
    """Compact notice for the WoW Scene panel - only when there is something to act on."""
    if STATE['status'] not in ('available', 'downloading', 'restart'):
        return
    box = layout.box()
    text, icon = _status_line()
    box.label(text=text, icon=icon)
    if STATE['status'] == 'available':
        row = box.row()
        row.operator(WBS_OT_update_install.bl_idname,
                     text="Pull Update (git)" if is_git_checkout() else "Download Update", icon='IMPORT')
        row.operator(WBS_OT_update_page.bl_idname, icon='URL')


def _draw_statusbar(self, context):
    if STATE['status'] in ('available', 'restart'):
        text, icon = _status_line()
        self.layout.operator(WBS_OT_update_page.bl_idname if STATE['status'] == 'restart'
                             else WBS_OT_update_install.bl_idname, text="WBS: " + text, icon=icon, emboss=False)


def register():
    _load_state()
    bpy.types.STATUSBAR_HT_header.append(_draw_statusbar)
    if not bpy.app.background:
        bpy.app.timers.register(_auto_check, first_interval=5.0)


def unregister():
    try:
        bpy.types.STATUSBAR_HT_header.remove(_draw_statusbar)
    except Exception:
        pass
    if bpy.app.timers.is_registered(_auto_check):
        bpy.app.timers.unregister(_auto_check)
