# Everwood Classic fork: Model Browser (View3D > Sidebar > "WBS Browser").
#
# * Index: every .m2 / root .wmo in the project's client archives (default: patch-*.mpq only = custom content),
#   plus the .blp files of each folder (texture choices). The archive that WINS for each path is shown. The
#   index is cached on disk (cache folder, keyed by archive size+mtime) so reopening is instant.
# * Search: words match anywhere in the path (folder names too), M2/WMO and source filters.
# * Preview: rendered straight from the file bytes by utils/model_preview.py (no import, no scene change),
#   with the currently chosen textures; rotate with the arrows.
# * Textures: every texture slot of the selected M2 gets a choice list - character skins / hair from
#   CharSections, creature skins from CreatureModelData + CreatureDisplayInfo, plus every .blp in the model's
#   folder. WMO slots are listed read-only.
# * Background index: the archive listing runs in a worker thread (own read-only archive handles, no bpy in the
#   thread); a bpy.app.timers poll shows "archives done / total" and applies the result. The disk cache stays.
# * Geoset picker (M2): checkbox per geoset id grouped by id // 100 + Default body / All / None presets.
# * Animation (M2): sequence dropdown (AnimationData.dbc names), Play / Pause and a time slider; bones are
#   evaluated and skinned in numpy (utils/model_preview.py).
# * Item models (Item\ObjectComponents\...): ItemDisplayInfo.dbc textures are offered first for object-skin slots.
# * Archives: every archive that holds the selected path is listed (the winner marked).
# * Favourites / recent: kept per user in CONFIG/wbs_browser/browser.json.
# * HD toggle: preview textures are read from <client>\Data\Upscale\*.mpq first (read-only, separate handles).
# * Import: imports the selected model with the regular WBS importer, then applies the chosen textures.
#   "Apply Textures" re-applies the choices to the M2 already in the scene (image re-pointed + reloaded, so
#   materials and export settings keep working).

import os
import json
import time
import zlib
import struct
import sys
import shutil
import subprocess
import tempfile
import threading
import traceback

import bpy
import bpy.utils.previews

from ..utils.misc import load_game_data, everwood_mode
from ..utils import model_preview, blp_decode
from ..pywowlib.archives.mpq import MPQFile
from .preferences import get_project_preferences

MAX_RESULTS = 1000
UNREADABLE_MSG = ('the archive lists this file but holds no data for it (a broken entry in the client, '
                  'not a WBS problem) - nothing to show or import')
PREVIEW_SIZE = 256
TEXTURE_TYPE_NAMES = {
    0: 'Hardcoded', 1: 'Body skin', 2: 'Object / cape', 6: 'Hair', 8: 'Fur', 11: 'Creature skin 1',
    12: 'Creature skin 2', 13: 'Creature skin 3', 14: 'Extra skin',
}

INDEX = {'key': None, 'models': [], 'blps': {}, 'archives': [], 'patch_archives': set(), 'by_path': {}}
JOB = {'active': False, 'finished': False, 'done': 0, 'total': 0, 'name': '', 'result': None, 'error': None,
       'key': None, 'seconds': 0.0, 'mode': ''}
USER = {'fav': [], 'recent': []}      # favourite / recently opened model paths (persisted per user)
RECENT_MAX = 20
HD = {'root': None, 'archives': None}   # opened Data\Upscale archives [(name, MPQFile)]
HOLDERS = []                           # archives that hold the selected path, winner first
ANIM_ITEMS = [('NONE', '(bind pose)', 'Show the model without animation')]
ANIM_FIT = {}                          # (path, seq, geosets) -> (center, radius) so the preview keeps one scale
_ANIM = {'running': False, 't': 0.0, 'setting': False}
GEOSET_NAMES = {0: 'Hair / scalp', 1: 'Facial 1', 2: 'Facial 2', 3: 'Facial 3', 4: 'Hands', 5: 'Feet', 6: 'Tail',
                7: 'Ears', 8: 'Sleeves', 9: 'Leg cuffs', 10: 'Chest', 11: 'Pants', 12: 'Tabard', 13: 'Legs',
                15: 'Cloak', 17: 'Eye glow', 18: 'Belt'}
MESHES = {}          # path -> model_preview.Mesh (small LRU)
TEXTURES = {}        # blp path -> decoded RGBA (preview resolution)
CANDIDATES = {}      # (model path, slot index) -> [(identifier, label, description)]
PRIMARY = {}         # (model path, slot index) -> how many leading candidates come from the model / DBCs
DBC = {}             # 'CharSections' / 'CreatureModelData' / 'CreatureDisplayInfo' -> parsed rows
PREVIEWS = None
_preview_counter = [0]
_SUPPRESS = [False]   # True while select_model fills the slots (one render at the end)


# ------------------------------------------------------------------------------------------- utilities

def _norm(p):
    return p.replace('/', '\\')


def _dirname(p):
    return _norm(p).rsplit('\\', 1)[0] if '\\' in _norm(p) else ''


def _read(game_data, path):
    try:
        res = game_data.read_file(_norm(path), no_exc=True)
    except Exception:
        return None
    if not res:
        return None
    data = res[0] if isinstance(res, tuple) else res
    return data or None


def _write_png(path, rgba):
    h, w = rgba.shape[:2]
    raw = b''.join(b'\x00' + rgba[y].tobytes() for y in range(h))

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def _preview_dir():
    d = os.path.join(tempfile.gettempdir(), 'wbs_model_browser')
    os.makedirs(d, exist_ok=True)
    return d


def _redraw(context=None):
    wm = bpy.context.window_manager
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


# ----------------------------------------------------------------------------------------------- DBC

def _parse_dbc(data):
    if not data or data[:4] != b'WDBC':
        return [], b''
    _m, rc, fc, rs, ss = struct.unpack_from('<4sIIII', data, 0)
    rows = [struct.unpack_from('<%dI' % fc, data, 20 + i * rs) for i in range(rc)]
    return rows, data[20 + rc * rs:20 + rc * rs + ss]


def _s(block, off):
    if not off or off >= len(block):
        return ''
    return block[off:block.index(b'\0', off)].decode('latin-1')


def _item_name_column(rows, strings):
    """ItemDisplayInfo: first of the two ModelName columns. 1.12 and 3.3.5 both put ID, ModelName[2],
    ModelTexture[2] first, but find the column from the data (strings ending in .mdx / .m2) instead of trusting it."""
    best, best_n = 1, 0
    for c in range(1, min(6, len(rows[0]) if rows else 0)):
        n = 0
        for r in rows[:600]:
            t = _s(strings, r[c]).lower()
            if t.endswith('.mdx') or t.endswith('.m2'):
                n += 1
        if n > best_n:
            best, best_n = c, n
    return best


def _dbc(game_data, name):
    if name in DBC:
        return DBC[name]
    rows, strings = _parse_dbc(_read(game_data, 'DBFilesClient\\%s.dbc' % name))
    out = []
    if name == 'CharSections' and rows and len(rows[0]) >= 10:
        # 1.12: ID Race Sex Section Variation Color Tex1 Tex2 Tex3 Flags ; 3.3.5: ID Race Sex Section Tex1-3 Flags Var Color
        legacy = sum(1 for r in rows[:200] if '\\' in _s(strings, r[6])) >= sum(1 for r in rows[:200] if '\\' in _s(strings, r[4]))
        for r in rows:
            if legacy:
                tex, var, col = (r[6], r[7], r[8]), r[4], r[5]
            else:
                tex, var, col = (r[4], r[5], r[6]), r[8], r[9]
            out.append(dict(race=r[1], sex=r[2], section=r[3], variation=var, color=col,
                            tex=[_s(strings, t) for t in tex]))
    elif name == 'CreatureModelData':
        out = [dict(id=r[0], model=_s(strings, r[2])) for r in rows]
    elif name == 'CreatureDisplayInfo':
        out = [dict(id=r[0], model_id=r[1], tex=[_s(strings, r[6]), _s(strings, r[7]), _s(strings, r[8])]) for r in rows]
    elif name == 'AnimationData':
        out = {r[0]: _s(strings, r[1]) for r in rows if len(r) > 1}
    elif name == 'ItemDisplayInfo' and rows and len(rows[0]) >= 5:
        c = _item_name_column(rows, strings)
        if c + 3 < len(rows[0]):
            for r in rows:
                out.append(dict(id=r[0], models=[_s(strings, r[c]), _s(strings, r[c + 1])],
                                texs=[_s(strings, r[c + 2]), _s(strings, r[c + 3])]))
    DBC[name] = out
    return out


# ------------------------------------------------------------------------------------------ user data

def _user_file():
    try:
        d = bpy.utils.user_resource('CONFIG', path='wbs_browser', create=True)
    except Exception:
        d = ''
    return os.path.join(d, 'browser.json') if d else ''


def load_user():
    """(Re)read the favourites / recent list from the user's config folder."""
    USER['fav'], USER['recent'] = [], []
    try:
        f = _user_file()
        if f and os.path.isfile(f):
            with open(f, 'r', encoding='utf-8') as fh:
                saved = json.load(fh)
            USER['fav'] = [str(x) for x in saved.get('fav', [])]
            USER['recent'] = [str(x) for x in saved.get('recent', [])][:RECENT_MAX]
    except Exception as e:
        print("WBS browser: cannot read favourites:", e)


def save_user():
    try:
        f = _user_file()
        if f:
            with open(f, 'w', encoding='utf-8') as fh:
                json.dump(dict(fav=USER['fav'], recent=USER['recent'][:RECENT_MAX]), fh, indent=1)
    except Exception as e:
        print("WBS browser: cannot write favourites:", e)


def is_fav(path):
    low = path.lower()
    return any(p.lower() == low for p in USER['fav'])


def toggle_fav(path):
    low = path.lower()
    if is_fav(path):
        USER['fav'] = [p for p in USER['fav'] if p.lower() != low]
    else:
        USER['fav'].append(path)
    save_user()
    return is_fav(path)


def touch_recent(path):
    low = path.lower()
    USER['recent'] = [path] + [p for p in USER['recent'] if p.lower() != low]
    USER['recent'] = USER['recent'][:RECENT_MAX]
    save_user()


# --------------------------------------------------------------------------------------------- index
#
# The archive listing happens in a worker thread. The thread opens its OWN read-only MPQFile handles (so it never
# shares a StormLib handle with the main thread) and touches no bpy data; it only fills JOB. A bpy.app.timers
# poll on the main thread shows the progress and applies the finished result.

def _archive_signature(game_data):
    sig = []
    for storage, is_archive in game_data.files:
        try:
            p = storage.paths[0] if is_archive else storage
        except Exception:
            p = str(storage)
        try:
            st = os.stat(p)
            sig.append([p, st.st_size, int(st.st_mtime)])
        except OSError:
            sig.append([p, 0, 0])
    return sig


def _index_cache_path():
    try:
        d = get_project_preferences().cache_dir_path
    except Exception:
        d = ''
    d = d or _preview_dir()
    return os.path.join(d, 'wbs_model_index.json')


def _index_plan(game_data):
    """[(display name, path, is_archive)] highest priority first (what wins comes first)."""
    plan = []
    for storage, is_archive in reversed(game_data.files):
        if is_archive:
            try:
                p = storage.paths[0]
            except Exception:
                continue
            plan.append((os.path.basename(p), p, True))
        else:
            plan.append((os.path.basename(storage.rstrip('\\/')) + ' (folder)', storage, False))
    return plan


def _list_names(path, is_archive):
    if is_archive:
        f = MPQFile(path, 0x00000100)                        # own read-only handle
        try:
            return list(f.namelist())
        finally:
            try:
                f.close()
            except Exception:
                pass
    names = []
    for root, _dirs, files in os.walk(path):
        for fn in files:
            names.append(os.path.relpath(os.path.join(root, fn), path))
    return names


def _index_scan(plan, job=None):
    """In-process scan (fallback + blocking build_index)."""
    def progress(done, total, name):
        if job is not None:
            job['done'], job['name'] = done, name
    return model_preview.scan_plan(plan, _list_names, progress)


# The listing runs in a separate Python process: StormLib calls hold the GIL for hundreds of milliseconds each
# (opening a 1-2 GB archive), which would freeze Blender's UI even from a thread. The process only needs the
# compiled storm module and utils/model_preview.py (no bpy); it prints "P done total name" lines for the progress
# and writes its result as JSON. A supervisor thread reads that progress. If the process cannot run, the
# in-process scan is used instead.
WORKER_SRC = r'''
import sys, os, json, importlib.util
native, mp_path, plan_f, out_f = sys.argv[1:5]
sys.path.insert(0, native)
import storm
spec = importlib.util.spec_from_file_location('wbs_model_preview', mp_path)
mp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mp)
plan = json.load(open(plan_f, encoding='utf-8'))


def list_names(path, is_archive):
    names = []
    if not is_archive:
        for root, _d, files in os.walk(path):
            for fn in files:
                names.append(os.path.relpath(os.path.join(root, fn), path))
        return names
    h = storm.SFileOpenArchive(path, 0, 0x100)
    try:
        handle, f = storm.SFileFindFirstFile(h, "", "*")
        while True:
            names.append(f.replace("\\", "/"))
            try:
                f = storm.SFileFindNextFile(handle)
            except storm.NoMoreFilesError:
                break
    finally:
        storm.SFileCloseArchive(h)
    return names


def progress(done, total, name):
    sys.stdout.write("P %d %d %s\n" % (done, total, name))
    sys.stdout.flush()


res = mp.scan_plan([tuple(x) for x in plan], list_names, progress)
with open(out_f, 'w', encoding='utf-8') as fh:
    json.dump(res, fh)
sys.stdout.write("DONE\n")
sys.stdout.flush()
'''


def _python_exe():
    exe = getattr(bpy.app, 'binary_path_python', '') or ''
    if exe and os.path.isfile(exe):
        return exe
    exe = sys.executable
    return exe if exe and 'blender' not in os.path.basename(exe).lower() else ''


def _run_worker_process(plan, job):
    """Returns the scan result dict, or None when the worker process could not be used."""
    exe = _python_exe()
    native = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pywowlib', 'archives', 'mpq', 'native')
    mp_path = os.path.abspath(model_preview.__file__)
    if not exe or not os.path.isdir(native):
        return None
    work = tempfile.mkdtemp(prefix='wbs_index_')
    script, plan_f, out_f = (os.path.join(work, n) for n in ('worker.py', 'plan.json', 'out.json'))
    try:
        with open(script, 'w', encoding='utf-8') as f:
            f.write(WORKER_SRC)
        with open(plan_f, 'w', encoding='utf-8') as f:
            json.dump(plan, f)
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        proc = subprocess.Popen([exe, '-I', script, native, mp_path, plan_f, out_f], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, creationflags=flags, universal_newlines=True, encoding='utf-8')
        for line in proc.stdout:
            if line.startswith('P '):
                parts = line.rstrip('\n').split(' ', 3)
                try:
                    job['done'], job['name'] = int(parts[1]), (parts[3] if len(parts) > 3 else '')
                except (ValueError, IndexError):
                    pass
        err = proc.stderr.read()
        if proc.wait() != 0 or not os.path.isfile(out_f):
            print("WBS browser: index worker failed (%s): %s" % (proc.returncode, err[-500:]))
            return None
        with open(out_f, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print("WBS browser: cannot run the index worker process:", e)
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _apply_index(key, res, write_cache=True):
    INDEX.update(key=key, models=[tuple(x) for x in res['models']], blps=res['blps'], archives=res['archives'],
                 patch_archives=set(res['patch_archives']))
    INDEX['by_path'] = {m[0].lower(): m for m in INDEX['models']}
    if write_cache:
        try:
            with open(_index_cache_path(), 'w', encoding='utf-8') as f:
                json.dump(dict(key=key, models=INDEX['models'], blps=INDEX['blps'], archives=INDEX['archives'],
                               patch_archives=sorted(INDEX['patch_archives'])), f)
        except Exception as e:
            print("WBS browser: cannot write index cache:", e)


def _try_cache(key):
    cache = _index_cache_path()
    if os.path.isfile(cache):
        try:
            with open(cache, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            if saved.get('key') == key:
                _apply_index(key, saved, write_cache=False)
                return True
        except Exception:
            pass
    return False


def build_index(force=False):
    """Blocking build (cache first). The UI uses start_index_job instead."""
    game_data = load_game_data()
    key = json.dumps(_archive_signature(game_data))
    if INDEX['key'] == key and not force:
        return
    if not force and _try_cache(key):
        return
    _apply_index(key, _index_scan(_index_plan(game_data)))


def _job_main(plan, job):
    t0 = time.time()
    try:
        res = _run_worker_process(plan, job)
        job['mode'] = 'process' if res is not None else 'thread'
        job['result'] = res if res is not None else _index_scan(plan, job)
    except Exception:
        job['error'] = traceback.format_exc()
    job['seconds'] = time.time() - t0
    job['finished'] = True


def _poll_job():
    if not JOB['finished']:
        _redraw()
        return 0.15
    JOB['active'] = False
    if JOB['error']:
        print("WBS browser: indexing failed:\n" + JOB['error'])
    elif JOB['result'] is not None:
        _apply_index(JOB['key'], JOB['result'])
        refilter()
    JOB['result'] = None
    _redraw()
    return None


def start_index_job(force=False):
    """-> 'ready' (already indexed / cache hit), 'started' or 'running'."""
    if JOB['active']:
        return 'running'
    game_data = load_game_data()
    key = json.dumps(_archive_signature(game_data))
    if INDEX['key'] == key and not force:
        return 'ready'
    if not force and _try_cache(key):
        refilter()
        return 'ready'
    plan = _index_plan(game_data)
    JOB.update(active=True, finished=False, done=0, total=len(plan), name='', result=None, error=None, key=key,
               seconds=0.0)
    th = threading.Thread(target=_job_main, args=(plan, JOB), name='wbs-model-index', daemon=True)
    th.start()
    bpy.app.timers.register(_poll_job, first_interval=0.1)
    return 'started'


def refilter(self=None, context=None):
    st = bpy.context.window_manager.wbs_browser
    words = [w for w in st.search.lower().split() if w]
    patch_only = st.source == 'PATCH' and st.view == 'ALL'
    if st.view == 'ALL':
        source = INDEX['models']
    else:
        names = USER['fav'] if st.view == 'FAV' else USER['recent']
        source = [INDEX['by_path'][p.lower()] for p in names if p.lower() in INDEX['by_path']]
    out = []
    total = 0
    for path, archive, kind in source:
        if st.kind != 'ALL' and kind != st.kind:
            continue
        if patch_only and archive not in INDEX['patch_archives']:
            continue
        low = path.lower()
        if words and not all(w in low for w in words):
            continue
        total += 1
        if len(out) < MAX_RESULTS:
            out.append((path, archive, kind))
    st.results.clear()
    for path, archive, kind in out:
        it = st.results.add()
        it.path, it.archive, it.kind = path, archive, kind
    st.matches = total
    st['active'] = -1


def archives_holding(game_data, path):
    """Names of every archive / folder that holds `path`, highest priority (the winner) first."""
    names = [_norm(path)]
    if path.lower().endswith('.m2'):
        names.append(_norm(path)[:-3] + '.mdx')
    out = []
    for storage, is_archive in reversed(game_data.files):
        try:
            if is_archive:
                hit = any(n in storage for n in names)
                label = os.path.basename(storage.paths[0])
            else:
                hit = any(os.path.isfile(os.path.join(storage, n)) for n in names)
                label = os.path.basename(storage.rstrip('\\/')) + ' (folder)'
        except Exception:
            continue
        if hit:
            out.append(label)
    return out


# -------------------------------------------------------------------------------------------- HD textures

def _hd_archives(game_data):
    root = os.path.join(getattr(game_data, 'wow_path', '') or '', 'Data', 'Upscale')
    if HD['root'] == root and HD['archives'] is not None:
        return HD['archives']
    arcs = []
    if os.path.isdir(root):
        for fn in sorted(os.listdir(root), key=str.lower):
            if fn.lower().endswith('.mpq'):
                try:
                    arcs.append((fn, MPQFile(os.path.join(root, fn), 0x00000100)))    # read-only, separate handle
                except Exception as e:
                    print("WBS browser: cannot open %s: %s" % (fn, e))
    HD.update(root=root, archives=arcs)
    return arcs


def hd_available(game_data=None):
    try:
        return bool(_hd_archives(game_data or load_game_data()))
    except Exception:
        return False


def _read_hd(game_data, path):
    name = _norm(path)
    for _fn, mpq in reversed(_hd_archives(game_data)):          # later archives win
        try:
            if name in mpq:
                return mpq.open(name).read() or None
        except Exception:
            continue
    return None


# -------------------------------------------------------------------------------- texture candidates

def _char_race_sex(game_data, model_dir):
    """(race, sex) whose CharSections rows live in the model's folder, else None."""
    md = model_dir.lower()
    for r in _dbc(game_data, 'CharSections'):
        if r['section'] == 0 and r['tex'][0] and _dirname(r['tex'][0]).lower() == md:
            return r['race'], r['sex']
    return None


def _creature_skins(game_data, path, slot_type):
    stem = os.path.splitext(path.lower())[0]
    ids = {r['id'] for r in _dbc(game_data, 'CreatureModelData')
           if os.path.splitext(_norm(r['model']).lower())[0] == stem}
    out, seen = [], set()
    col = slot_type - 11
    for r in _dbc(game_data, 'CreatureDisplayInfo'):
        if r['model_id'] in ids and r['tex'][col]:
            p = _dirname(path) + '\\' + r['tex'][col] + '.blp'
            if p.lower() not in seen:
                seen.add(p.lower())
                out.append((p, 'Display %d: %s' % (r['id'], r['tex'][col]), 'CreatureDisplayInfo %d' % r['id']))
    return out


def _item_skins(game_data, path):
    """Textures ItemDisplayInfo.dbc pairs with this item model (ModelName[k] <-> ModelTexture[k]); they live in the
    model's own folder."""
    if not _norm(path).lower().startswith('item\\'):
        return []
    by_model = DBC.get('_item_by_model')
    if by_model is None:
        by_model = {}
        for r in _dbc(game_data, 'ItemDisplayInfo'):
            for k in (0, 1):
                mn = _norm(r['models'][k]).lower()
                if mn and r['texs'][k]:
                    by_model.setdefault(os.path.splitext(os.path.basename(mn))[0], []).append((r['id'], r['texs'][k]))
        DBC['_item_by_model'] = by_model
    stem = os.path.splitext(os.path.basename(_norm(path)))[0].lower()
    out, seen = [], set()
    for did, tex in by_model.get(stem, []):
        p = _dirname(path) + '\\' + (tex if tex.lower().endswith('.blp') else tex + '.blp')
        if p.lower() not in seen:
            seen.add(p.lower())
            out.append((p, 'Item %d: %s' % (did, tex), 'ItemDisplayInfo %d' % did))
        if len(out) >= 300:
            break
    return out


def build_candidates(game_data, path, mesh):
    model_dir = _dirname(path)
    folder = [(p, os.path.basename(p), p) for p in sorted(INDEX['blps'].get(model_dir.lower(), []), key=str.lower)]
    if mesh.kind == 'WMO':
        for i, tex in enumerate(mesh.slots):
            CANDIDATES[(path, i)] = [(_norm(tex), os.path.basename(_norm(tex)) or '(none)', tex)] if tex else [('NONE', '(none)', '')]
        return
    rs = _char_race_sex(game_data, model_dir) if path.lower().startswith('character\\') else None
    for slot in mesh.slots:
        t = slot['type']
        items = []
        if t == 0 and slot['filename']:
            fn = _norm(slot['filename'])
            items.append((fn, os.path.basename(fn) + ' (model)', fn))
        elif t == 1 and rs:
            for r in _dbc(game_data, 'CharSections'):
                if (r['race'], r['sex']) == rs and r['section'] == 0 and r['variation'] == 0 and r['tex'][0]:
                    items.append((_norm(r['tex'][0]), 'Skin %d: %s' % (r['color'], os.path.basename(_norm(r['tex'][0]))),
                                  'CharSections skin colour %d' % r['color']))
        elif t == 6 and rs:
            for r in _dbc(game_data, 'CharSections'):
                if (r['race'], r['sex']) == rs and r['section'] == 3 and r['tex'][0]:
                    items.append((_norm(r['tex'][0]), 'Hair %d.%d: %s' % (r['variation'], r['color'],
                                                                         os.path.basename(_norm(r['tex'][0]))),
                                  'CharSections hair style %d colour %d' % (r['variation'], r['color'])))
        elif t in (11, 12, 13):
            items.extend(_creature_skins(game_data, path, t))
        elif t == 2:
            items.extend(_item_skins(game_data, path))
        PRIMARY[(path, slot['index'])] = len(items)
        have = {i[0].lower() for i in items}
        items.extend(x for x in folder if x[0].lower() not in have)
        uniq, seen = [], set()
        for it in items:
            if it[0].lower() not in seen:
                seen.add(it[0].lower())
                uniq.append(it)
        CANDIDATES[(path, slot['index'])] = [('NONE', '(none)', 'No texture')] + uniq


def _slot_items(self, context):
    st = context.window_manager.wbs_browser if context else bpy.context.window_manager.wbs_browser
    items = CANDIDATES.get((st.current, self.index)) or [('NONE', '(none)', '')]
    return items


def _on_slot_change(self, context):
    if not _SUPPRESS[0]:
        render_preview()


# ------------------------------------------------------------------------------------------- preview

def _load_texture(game_data, path, hd=None):
    """Decoded RGBA of a BLP. HD (Data\\Upscale) first when `hd` (default: the panel toggle) is on."""
    if not path or path == 'NONE':
        return None
    if hd is None:
        try:
            # Data\Upscale is the Everwood HD pack: only in Everwood mode (add-on preferences)
            hd = bool(bpy.context.window_manager.wbs_browser.use_hd) and everwood_mode()
        except Exception:
            hd = False
    key = (path.lower(), bool(hd))
    if key not in TEXTURES:
        data, got_hd = None, False
        if hd:
            data = _read_hd(game_data, path)
            got_hd = data is not None
        if data is None:
            data = _read(game_data, path)
        try:
            TEXTURES[key] = blp_decode.decode(data, 1024 if got_hd else 256) if data else None
        except Exception as e:
            print("WBS browser: cannot decode %s: %s" % (path, e))
            TEXTURES[key] = None
        if len(TEXTURES) > 64:
            TEXTURES.pop(next(iter(TEXTURES)))
    return TEXTURES[key]


def load_model(path):
    game_data = load_game_data()
    if path in MESHES:
        return game_data, MESHES[path]
    data = _read(game_data, path)
    if data is None and path.lower().endswith('.m2'):
        data = _read(game_data, path[:-3] + '.mdx')
    if not data:
        raise FileNotFoundError(UNREADABLE_MSG)
    reader = lambda p: _read(game_data, p)
    mesh = model_preview.read_m2(data, reader, path) if path.lower().endswith('.m2') \
        else model_preview.read_wmo(data, reader, path)
    MESHES[path] = mesh
    if len(MESHES) > 6:
        MESHES.pop(next(iter(MESHES)))
    build_candidates(game_data, path, mesh)
    return game_data, mesh


def _anim_label(game_data, s):
    names = _dbc(game_data, 'AnimationData')
    base = names.get(s['id']) if isinstance(names, dict) else None
    base = base or 'Anim %d.%d' % (s['id'], s['var'])
    if base and s['var'] and not base.startswith('Anim '):
        base = '%s [%d]' % (base, s['var'])
    return '%s (%d ms)' % (base, s['duration'])


def _build_anim_items(game_data, mesh):
    items = [('NONE', '(bind pose)', 'Show the model without animation')]
    if mesh.kind == 'M2' and mesh.anim is not None:
        for s in sorted(mesh.anim.playable(), key=lambda x: (x['id'], x['var'])):
            if s['duration'] > 0:
                items.append((str(s['index']), _anim_label(game_data, s), 'Sequence %d.%d' % (s['id'], s['var'])))
    ANIM_ITEMS[:] = items


def select_model(path):
    st = bpy.context.window_manager.wbs_browser
    st.current = path
    st.slots.clear()
    st.geosets.clear()
    st.info = ''
    del HOLDERS[:]
    try:
        game_data, mesh = load_model(path)
    except Exception as e:
        traceback.print_exc()
        st.info = 'Cannot read model: %s' % e
        st.preview_icon = 0
        return
    touch_recent(path)
    HOLDERS.extend(archives_holding(game_data, path))
    _build_anim_items(game_data, mesh)
    _SUPPRESS[0] = True
    try:
        st.anim_playing = False
        st.anim_pos = 0.0
        st.anim_seq = 'NONE'
        _fill_slots(st, path, mesh)
    finally:
        _SUPPRESS[0] = False
    render_preview()


def _fill_slots(st, path, mesh):
    if mesh.kind == 'M2':
        for slot in mesh.slots:
            it = st.slots.add()
            it.index, it.ttype = slot['index'], slot['type']
            it.label = TEXTURE_TYPE_NAMES.get(slot['type'], 'Type %d' % slot['type'])
            items = CANDIDATES.get((path, slot['index'])) or []
            if PRIMARY.get((path, slot['index'])) and len(items) > 1:
                it.choice = items[1][0]                               # the model's own / first DBC texture
        for gid in mesh.geosets:
            g = st.geosets.add()
            g.gid, g.on = gid, gid in mesh.default_geo
        st.info = 'M2 v%d: %d vertices, %d triangles shown, %d texture slots' % (
            mesh.version, len(mesh.verts), len(mesh.tris), len(mesh.slots))
    else:
        for i, tex in enumerate(mesh.slots):
            it = st.slots.add()
            it.index, it.ttype, it.label = i, -1, 'Material %d' % i
        st.info = 'WMO: %d triangles shown, %d materials' % (len(mesh.tris), len(mesh.slots))


def selected_geosets(st):
    return {g.gid for g in st.geosets if g.on}


def current_sequence(st, mesh):
    """Index of the chosen M2 sequence or None (bind pose)."""
    if mesh.kind != 'M2' or mesh.anim is None or st.anim_seq in ('', 'NONE'):
        return None
    try:
        i = int(st.anim_seq)
    except ValueError:
        return None
    return i if 0 <= i < len(mesh.anim.sequences) else None


def build_view(st, mesh):
    """The Mesh the preview draws: chosen geosets, posed for the chosen sequence / time. -> (mesh, fit)."""
    if mesh.kind != 'M2':
        return mesh, None
    ids = selected_geosets(st)
    view = mesh.view(geosets=ids)
    seq = current_sequence(st, mesh)
    if seq is None:
        return view, None
    dur = mesh.anim.sequences[seq]['duration']
    v, n = mesh.anim.pose(mesh, seq, st.anim_pos * dur)
    key = (st.current, seq, tuple(sorted(ids)))
    if key not in ANIM_FIT:
        ANIM_FIT[key] = model_preview.pose_fit(view, seq)
        if len(ANIM_FIT) > 32:
            ANIM_FIT.pop(next(iter(ANIM_FIT)))
    return view.view(verts=v, normals=n), ANIM_FIT[key]


def render_preview():
    global PREVIEWS
    st = bpy.context.window_manager.wbs_browser
    if not st.current or st.current not in MESHES:
        return
    game_data = load_game_data()
    mesh = MESHES[st.current]
    textures = {}
    if mesh.kind == 'M2':
        for it in st.slots:
            tex = _load_texture(game_data, it.choice)
            if tex is not None:
                textures[it.index] = tex
    else:
        for i, name in enumerate(mesh.slots):
            tex = _load_texture(game_data, _norm(name)) if name else None
            if tex is not None:
                textures[i] = tex
    t0 = time.time()
    view, fit = build_view(st, mesh)
    st.tri_count = int(len(view.tris))
    img = model_preview.render(view, textures, PREVIEW_SIZE, st.yaw, st.pitch, fit=fit)
    _preview_counter[0] += 1
    key = 'wbs_prev_%d' % _preview_counter[0]
    path = os.path.join(_preview_dir(), key + '.png')
    _write_png(path, img)
    if PREVIEWS is None:
        PREVIEWS = bpy.utils.previews.new()
    old = [k for k in PREVIEWS.keys()]
    pv = PREVIEWS.load(key, path, 'IMAGE')
    pv.image_size[:]                                                   # force the load now
    st.preview_icon = pv.icon_id
    for k in old[:-2]:                                                 # keep memory bounded
        try:
            del PREVIEWS[k]
        except Exception:
            pass
    st.render_ms = int((time.time() - t0) * 1000)
    _redraw()


def _on_active(self, context):
    if 0 <= self.active < len(self.results):
        select_model(self.results[self.active].path)


def _on_view(self, context):
    render_preview()


def _on_geoset(self, context):
    if not _SUPPRESS[0]:
        render_preview()


def _on_hd(self, context):
    render_preview()


def _anim_items(self, context):
    return ANIM_ITEMS


def _on_anim_seq(self, context):
    if _SUPPRESS[0]:
        return
    _ANIM['setting'] = True
    try:
        self.anim_pos = 0.0
        if current_sequence(self, MESHES[self.current]) is None:
            self.anim_playing = False
    except Exception:
        pass
    finally:
        _ANIM['setting'] = False
    render_preview()


def _on_anim_pos(self, context):
    if not _SUPPRESS[0] and not _ANIM['setting']:
        render_preview()


def _anim_tick():
    try:
        st = bpy.context.window_manager.wbs_browser
        mesh = MESHES.get(st.current)
        if not st.anim_playing or mesh is None:
            _ANIM['running'] = False
            return None
        seq = current_sequence(st, mesh)
        if seq is None:
            st.anim_playing = False
            _ANIM['running'] = False
            return None
        now = time.time()
        dt = now - _ANIM['t']
        _ANIM['t'] = now
        dur = max(1, mesh.anim.sequences[seq]['duration'])
        _ANIM['setting'] = True
        try:
            st.anim_pos = (st.anim_pos + dt * 1000.0 / dur) % 1.0
        finally:
            _ANIM['setting'] = False
        render_preview()                      # time based: slow renders skip frames instead of slowing the motion
    except Exception:
        traceback.print_exc()
        _ANIM['running'] = False
        return None
    return 0.08


def _on_anim_playing(self, context):
    if _SUPPRESS[0] or _ANIM['setting']:
        return
    if self.anim_playing and not _ANIM['running']:
        _ANIM['running'] = True
        _ANIM['t'] = time.time()
        bpy.app.timers.register(_anim_tick, first_interval=0.05)


# ------------------------------------------------------------------------------------ property groups

class WBS_PG_BrowserItem(bpy.types.PropertyGroup):
    path: bpy.props.StringProperty()
    archive: bpy.props.StringProperty()
    kind: bpy.props.StringProperty()


class WBS_PG_BrowserSlot(bpy.types.PropertyGroup):
    index: bpy.props.IntProperty()
    ttype: bpy.props.IntProperty()
    label: bpy.props.StringProperty()
    choice: bpy.props.EnumProperty(name='Texture', items=_slot_items, update=_on_slot_change)


class WBS_PG_BrowserGeoset(bpy.types.PropertyGroup):
    gid: bpy.props.IntProperty()
    on: bpy.props.BoolProperty(name='Show', default=False, update=_on_geoset)


class WBS_PG_Browser(bpy.types.PropertyGroup):
    search: bpy.props.StringProperty(name='Search', description='Words to find anywhere in the file path (folders too)',
                                     update=refilter, options={'TEXTEDIT_UPDATE'})
    kind: bpy.props.EnumProperty(name='Type', items=[('ALL', 'All', ''), ('M2', 'M2', ''), ('WMO', 'WMO', '')],
                                 update=refilter)
    view: bpy.props.EnumProperty(name='List', update=refilter, items=[
        ('ALL', 'All', 'Every indexed model'),
        ('FAV', 'Favourites', 'Models you starred'),
        ('RECENT', 'Recent', 'The last 20 models you opened')])
    source: bpy.props.EnumProperty(name='Source', update=refilter, items=[
        ('PATCH', 'Patch archives', 'Only models whose winning copy is in a patch-*.mpq (custom content)'),
        ('ALL', 'All archives', 'Every archive of the client')])
    results: bpy.props.CollectionProperty(type=WBS_PG_BrowserItem)
    active: bpy.props.IntProperty(default=-1, update=_on_active)
    matches: bpy.props.IntProperty()
    current: bpy.props.StringProperty()
    info: bpy.props.StringProperty()
    slots: bpy.props.CollectionProperty(type=WBS_PG_BrowserSlot)
    geosets: bpy.props.CollectionProperty(type=WBS_PG_BrowserGeoset)
    show_geosets: bpy.props.BoolProperty(name='Geosets', default=False)
    yaw: bpy.props.FloatProperty(name='Turn', default=35.0, update=_on_view)
    pitch: bpy.props.FloatProperty(name='Tilt', default=12.0, min=-60.0, max=80.0, update=_on_view)
    preview_icon: bpy.props.IntProperty()
    render_ms: bpy.props.IntProperty()
    tri_count: bpy.props.IntProperty(description='Triangles in the current preview')
    use_hd: bpy.props.BoolProperty(
        name='Use HD (Upscale) textures', default=False, update=_on_hd,
        description='Read preview textures from <client>\\Data\\Upscale\\*.mpq first (2x upscaled textures)')
    anim_seq: bpy.props.EnumProperty(name='Animation', items=_anim_items, update=_on_anim_seq)
    anim_pos: bpy.props.FloatProperty(name='Time', default=0.0, min=0.0, max=1.0, subtype='FACTOR',
                                      update=_on_anim_pos)
    anim_playing: bpy.props.BoolProperty(name='Play', default=False, update=_on_anim_playing)


# ------------------------------------------------------------------------------------------ operators

class WBS_OT_browser_index(bpy.types.Operator):
    bl_idname = 'wbs.browser_index'
    bl_label = 'Load Model List'
    bl_description = 'List every M2 / WMO in the client archives of the active WBS project (runs in the background)'

    force: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        try:
            state = start_index_job(self.force)
        except Exception as e:
            traceback.print_exc()
            self.report({'ERROR'}, 'WBS browser: %s' % e)
            return {'CANCELLED'}
        if state == 'ready':
            refilter()
            self.report({'INFO'}, 'WBS browser: %d models in %d archives' % (len(INDEX['models']), len(INDEX['archives'])))
        elif state == 'started':
            self.report({'INFO'}, 'WBS browser: indexing %d archives in the background' % JOB['total'])
        return {'FINISHED'}


class WBS_OT_browser_rotate(bpy.types.Operator):
    bl_idname = 'wbs.browser_rotate'
    bl_label = 'Rotate Preview'
    bl_options = {'INTERNAL'}

    step: bpy.props.FloatProperty(default=45.0)

    def execute(self, context):
        st = context.window_manager.wbs_browser
        st.yaw = (st.yaw + self.step) % 360.0
        return {'FINISHED'}


class WBS_OT_browser_geosets(bpy.types.Operator):
    bl_idname = 'wbs.browser_geosets'
    bl_label = 'Geoset Preset'
    bl_options = {'INTERNAL'}

    mode: bpy.props.EnumProperty(items=[('DEFAULT', 'Default body', ''), ('ALL', 'All', ''), ('NONE', 'None', '')])

    def execute(self, context):
        st = context.window_manager.wbs_browser
        mesh = MESHES.get(st.current)
        if mesh is None:
            return {'CANCELLED'}
        _SUPPRESS[0] = True
        try:
            for g in st.geosets:
                g.on = (self.mode == 'ALL') or (self.mode == 'DEFAULT' and g.gid in mesh.default_geo)
        finally:
            _SUPPRESS[0] = False
        render_preview()
        return {'FINISHED'}


class WBS_OT_browser_favourite(bpy.types.Operator):
    bl_idname = 'wbs.browser_favourite'
    bl_label = 'Favourite'
    bl_description = 'Star / unstar the selected model'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        st = context.window_manager.wbs_browser
        if not st.current:
            return {'CANCELLED'}
        toggle_fav(st.current)
        if st.view == 'FAV':
            keep = st.current
            refilter()
            st.current = keep
        _redraw()
        return {'FINISHED'}


def apply_textures(context):
    """Point the scene M2's slot images at the chosen textures. Returns the number of images changed."""
    st = context.window_manager.wbs_browser
    game_data = load_game_data()
    cache_dir = get_project_preferences().cache_dir_path
    changed = 0
    images = [img for img in bpy.data.images if getattr(img, 'wow_m2_texture', None) and img.wow_m2_texture.enabled]
    mesh = MESHES.get(st.current)
    for it in st.slots:
        if it.ttype < 0 or not it.choice or it.choice == 'NONE':
            continue
        slot = mesh.slots[it.index] if mesh and it.index < len(mesh.slots) else None
        targets = []
        for img in images:
            if img.wow_m2_texture.texture_type != str(it.ttype):
                continue
            if it.ttype == 0 and slot is not None:
                want = os.path.splitext(_norm(slot['filename']).lower())[0]
                have = os.path.splitext(_norm(img.wow_m2_texture.path).lower())[0]
                if want != have and os.path.basename(want) != os.path.splitext(img.name.lower())[0]:
                    continue
            targets.append(img)
        if not targets:
            continue
        pngs = game_data.extract_textures_as_png(cache_dir, [it.choice])
        png = pngs.get(it.choice) or os.path.join(cache_dir, os.path.splitext(it.choice)[0] + '.png')
        if not os.path.isfile(png):
            continue
        for img in targets:
            img.filepath = png
            img.source = 'FILE'
            img.reload()
            if it.ttype == 0:
                img.wow_m2_texture.path = it.choice
            changed += 1
    return changed


class WBS_OT_browser_apply(bpy.types.Operator):
    bl_idname = 'wbs.browser_apply_textures'
    bl_label = 'Apply Textures'
    bl_description = 'Use the chosen textures on the M2 that is in the scene (its slot images are re-pointed)'

    def execute(self, context):
        try:
            n = apply_textures(context)
        except Exception as e:
            traceback.print_exc()
            self.report({'ERROR'}, 'WBS browser: %s' % e)
            return {'CANCELLED'}
        self.report({'INFO'} if n else {'WARNING'},
                    'WBS browser: %d texture(s) applied' % n if n else 'WBS browser: no matching texture slot in the scene')
        return {'FINISHED'}


class WBS_OT_browser_import(bpy.types.Operator):
    bl_idname = 'wbs.browser_import'
    bl_label = 'Import'
    bl_description = 'Import the selected model into the scene with WBS, then apply the chosen textures'
    bl_options = {'UNDO'}

    def execute(self, context):
        st = context.window_manager.wbs_browser
        path = st.current
        if not path:
            return {'CANCELLED'}
        if not _read(load_game_data(), path):
            self.report({'ERROR'}, 'WBS browser: ' + UNREADABLE_MSG)
            return {'CANCELLED'}
        version = int(context.scene.wow_scene.version)
        try:
            if path.lower().endswith('.m2'):
                from ..m2.import_m2 import import_m2_gamedata
                context.scene.wow_scene.type = 'M2'
                import_m2_gamedata(version, path, False)
                n = apply_textures(context)
                self.report({'INFO'}, 'WBS browser: imported %s (%d texture choice(s) applied)' % (os.path.basename(path), n))
            else:
                from ..wmo.import_wmo import import_wmo_to_blender_scene_gamedata
                context.scene.wow_scene.type = 'WMO'
                import_wmo_to_blender_scene_gamedata(path, version)
                self.report({'INFO'}, 'WBS browser: imported %s' % os.path.basename(path))
        except Exception as e:
            traceback.print_exc()
            self.report({'ERROR'}, 'WBS browser: import failed - %s' % e)
            return {'CANCELLED'}
        return {'FINISHED'}


# ---------------------------------------------------------------------------------------------------- UI

class WBS_UL_BrowserResults(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(factor=0.7)
        if is_fav(item.path):
            ic = 'SOLO_ON'
        else:
            ic = 'OUTLINER_OB_ARMATURE' if item.kind == 'M2' else 'HOME'
        split.label(text=os.path.basename(item.path), icon=ic)
        split.label(text=item.archive)

    def filter_items(self, context, data, propname):
        return [], []                                                  # filtering is done by the search field


class WBS_PT_model_browser(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'WBS Browser'
    bl_label = 'Model Browser'

    def _draw_progress(self, layout):
        total = max(1, JOB['total'])
        text = 'Indexing archives: %d / %d' % (JOB['done'], JOB['total'])
        if hasattr(layout, 'progress'):
            layout.progress(factor=JOB['done'] / float(total), text=text)
        else:
            layout.label(text=text, icon='TIME')
        if JOB['name']:
            layout.label(text=JOB['name'])

    def _draw_geosets(self, layout, st):
        box = layout.box()
        row = box.row()
        row.prop(st, 'show_geosets', icon='TRIA_DOWN' if st.show_geosets else 'TRIA_RIGHT', emboss=False,
                 text='Geosets (%d of %d shown)' % (sum(1 for g in st.geosets if g.on), len(st.geosets)))
        if not st.show_geosets:
            return
        row = box.row(align=True)
        for mode, label in (('DEFAULT', 'Default body'), ('ALL', 'All'), ('NONE', 'None')):
            row.operator(WBS_OT_browser_geosets.bl_idname, text=label).mode = mode
        groups = {}
        for g in st.geosets:
            groups.setdefault(g.gid // 100, []).append(g)
        for grp in sorted(groups):
            name = GEOSET_NAMES.get(grp, '') if st.current.lower().startswith('character\\') else ''
            box.label(text='Group %d%s' % (grp, ' - ' + name if name else ''))
            grid = box.grid_flow(row_major=True, columns=3, even_columns=True, align=True)
            for g in groups[grp]:
                grid.prop(g, 'on', text=str(g.gid), toggle=True)

    def _draw_anim(self, layout, st, mesh):
        box = layout.box()
        box.label(text='Animation', icon='ARMATURE_DATA')
        box.prop(st, 'anim_seq', text='')
        seq = current_sequence(st, mesh)
        if seq is None:
            return
        row = box.row(align=True)
        row.prop(st, 'anim_playing', text='Pause' if st.anim_playing else 'Play',
                 icon='PAUSE' if st.anim_playing else 'PLAY', toggle=True)
        row.prop(st, 'anim_pos', text='Time', slider=True)
        dur = mesh.anim.sequences[seq]['duration']
        box.label(text='%d / %d ms  (frame %d)' % (st.anim_pos * dur, dur, round(st.anim_pos * dur / 33.333)))

    def draw(self, context):
        layout = self.layout
        st = context.window_manager.wbs_browser
        if JOB['active']:
            self._draw_progress(layout)
        if not INDEX['models']:
            if not JOB['active']:
                layout.operator(WBS_OT_browser_index.bl_idname, icon='VIEWZOOM')
            layout.label(text='This window may freeze for a little while', icon='INFO')
            return
        row = layout.row(align=True)
        row.label(text='%d models, %d archives' % (len(INDEX['models']), len(INDEX['archives'])))
        op = row.operator(WBS_OT_browser_index.bl_idname, text='', icon='FILE_REFRESH')
        op.force = True
        layout.prop(st, 'search', text='', icon='VIEWZOOM')
        layout.row(align=True).prop(st, 'view', expand=True)
        row = layout.row(align=True)
        row.prop(st, 'kind', expand=True)
        if st.view == 'ALL':
            layout.prop(st, 'source', text='')
        shown = len(st.results)
        layout.label(text='%d match%s%s' % (st.matches, '' if st.matches == 1 else 'es',
                                            '' if shown == st.matches else ' (first %d shown)' % shown))
        layout.template_list('WBS_UL_BrowserResults', '', st, 'results', st, 'active', rows=8)

        if not st.current:
            return
        mesh = MESHES.get(st.current)
        box = layout.box()
        row = box.row(align=True)
        row.label(text=os.path.basename(st.current), icon='FILE_3D')
        row.operator(WBS_OT_browser_favourite.bl_idname, text='',
                     icon='SOLO_ON' if is_fav(st.current) else 'SOLO_OFF')
        box.label(text=_dirname(st.current))
        if st.preview_icon:
            box.template_icon(icon_value=st.preview_icon, scale=12.0)
        row = box.row(align=True)
        row.operator(WBS_OT_browser_rotate.bl_idname, text='', icon='TRIA_LEFT').step = -45.0
        row.prop(st, 'yaw', text='Turn')
        row.operator(WBS_OT_browser_rotate.bl_idname, text='', icon='TRIA_RIGHT').step = 45.0
        box.prop(st, 'pitch')
        for part in st.info.split(': ', 1) if st.info else []:
            box.label(text=part)
        if everwood_mode():                          # Data\Upscale = the Everwood HD pack
            if hd_available():
                box.prop(st, 'use_hd')
            else:
                box.label(text='No Data\\Upscale archives (HD off)', icon='INFO')

        if HOLDERS:
            abox = layout.box()
            abox.label(text='In %d archive%s:' % (len(HOLDERS), '' if len(HOLDERS) == 1 else 's'), icon='PACKAGE')
            for i, name in enumerate(HOLDERS[:12]):
                abox.label(text=('%s  (used)' % name) if i == 0 else name)
            if len(HOLDERS) > 12:
                abox.label(text='... and %d more' % (len(HOLDERS) - 12))

        if mesh is not None and mesh.kind == 'M2':
            if len(st.geosets):
                self._draw_geosets(layout, st)
            if mesh.anim is not None and len(ANIM_ITEMS) > 1:
                self._draw_anim(layout, st, mesh)

        if len(st.slots):
            tbox = layout.box()
            tbox.label(text='Textures', icon='TEXTURE')
            for it in st.slots:
                col = tbox.column(align=True)
                if it.ttype < 0:
                    items = CANDIDATES.get((st.current, it.index)) or []
                    col.label(text=it.label)
                    col.label(text=items[0][1] if items else '(none)', icon='IMAGE_DATA')
                else:
                    col.label(text='%d. %s' % (it.index, it.label))
                    col.prop(it, 'choice', text='')
        row = layout.row(align=True)
        row.scale_y = 1.4
        row.operator(WBS_OT_browser_import.bl_idname, icon='IMPORT')
        if st.current.lower().endswith('.m2'):
            row.operator(WBS_OT_browser_apply.bl_idname, icon='TEXTURE')


def register():
    bpy.types.WindowManager.wbs_browser = bpy.props.PointerProperty(type=WBS_PG_Browser)
    load_user()


def unregister():
    global PREVIEWS
    try:
        del bpy.types.WindowManager.wbs_browser
    except Exception:
        pass
    if PREVIEWS is not None:
        bpy.utils.previews.remove(PREVIEWS)
        PREVIEWS = None
    for _fn, mpq in (HD['archives'] or []):
        try:
            mpq.close()
        except Exception:
            pass
    HD.update(root=None, archives=None)
