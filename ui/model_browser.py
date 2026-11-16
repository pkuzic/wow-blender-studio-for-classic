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
# * Import: imports the selected model with the regular WBS importer, then applies the chosen textures.
#   "Apply Textures" re-applies the choices to the M2 already in the scene (image re-pointed + reloaded, so
#   materials and export settings keep working).

import os
import json
import time
import zlib
import struct
import tempfile
import traceback

import bpy
import bpy.utils.previews

from ..utils.misc import load_game_data
from ..utils import model_preview, blp_decode
from .preferences import get_project_preferences

MAX_RESULTS = 1000
UNREADABLE_MSG = ('the archive lists this file but holds no data for it (a broken entry in the client, '
                  'not a WBS problem) - nothing to show or import')
PREVIEW_SIZE = 256
TEXTURE_TYPE_NAMES = {
    0: 'Hardcoded', 1: 'Body skin', 2: 'Object / cape', 6: 'Hair', 8: 'Fur', 11: 'Creature skin 1',
    12: 'Creature skin 2', 13: 'Creature skin 3', 14: 'Extra skin',
}

INDEX = {'key': None, 'models': [], 'blps': {}, 'archives': [], 'patch_archives': set()}
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
    DBC[name] = out
    return out


# --------------------------------------------------------------------------------------------- index

def _archive_signature(game_data):
    sig = []
    for storage, is_archive in game_data.files:
        p = storage.paths[0] if is_archive else storage
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


def build_index(force=False):
    game_data = load_game_data()
    sig = _archive_signature(game_data)
    key = json.dumps(sig)
    if INDEX['key'] == key and not force:
        return
    cache = _index_cache_path()
    if not force and os.path.isfile(cache):
        try:
            with open(cache, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            if saved.get('key') == key:
                INDEX.update(key=key, models=[tuple(x) for x in saved['models']], blps=saved['blps'],
                             archives=saved['archives'], patch_archives=set(saved['patch_archives']))
                return
        except Exception:
            pass

    seen, models, blps, archives, patch = set(), [], {}, [], set()
    for storage, is_archive in reversed(game_data.files):           # highest priority first
        if is_archive:
            name = os.path.basename(storage.paths[0])
            try:
                names = storage.namelist()
            except Exception:
                names = []
        else:
            name = os.path.basename(storage.rstrip('\\/')) + ' (folder)'
            names = []
            for root, _dirs, files in os.walk(storage):
                for fn in files:
                    names.append(os.path.relpath(os.path.join(root, fn), storage))
        archives.append(name)
        if name.lower().startswith('patch'):
            patch.add(name)
        for n in names:
            p = _norm(n)
            low = p.lower()
            if low in seen:
                continue
            ext = low[-4:]
            if ext == '.blp':
                seen.add(low)
                blps.setdefault(_dirname(low), []).append(p)
            elif low.endswith('.m2') or ext == '.mdx':
                seen.add(low)
                models.append((p[:-4] + '.m2' if ext == '.mdx' else p, name, 'M2'))
            elif ext == '.wmo':
                base = os.path.basename(low)[:-4]
                if len(base) > 4 and base[-4] == '_' and base[-3:].isdigit():
                    continue                                          # WMO group file
                seen.add(low)
                models.append((p, name, 'WMO'))
    models.sort(key=lambda x: x[0].lower())
    INDEX.update(key=key, models=models, blps=blps, archives=archives, patch_archives=patch)
    try:
        with open(cache, 'w', encoding='utf-8') as f:
            json.dump(dict(key=key, models=models, blps=blps, archives=archives, patch_archives=sorted(patch)), f)
    except Exception as e:
        print("WBS browser: cannot write index cache:", e)


def refilter(self=None, context=None):
    st = bpy.context.window_manager.wbs_browser
    words = [w for w in st.search.lower().split() if w]
    patch_only = st.source == 'PATCH'
    out = []
    total = 0
    for path, archive, kind in INDEX['models']:
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

def _load_texture(game_data, path):
    if not path or path == 'NONE':
        return None
    key = path.lower()
    if key not in TEXTURES:
        data = _read(game_data, path)
        try:
            TEXTURES[key] = blp_decode.decode(data, 256) if data else None
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


def select_model(path):
    st = bpy.context.window_manager.wbs_browser
    st.current = path
    st.slots.clear()
    st.info = ''
    try:
        game_data, mesh = load_model(path)
    except Exception as e:
        traceback.print_exc()
        st.info = 'Cannot read model: %s' % e
        st.preview_icon = 0
        return
    _SUPPRESS[0] = True
    try:
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
        st.info = 'M2 v%d: %d vertices, %d triangles shown, %d texture slots' % (
            mesh.version, len(mesh.verts), len(mesh.tris), len(mesh.slots))
    else:
        for i, tex in enumerate(mesh.slots):
            it = st.slots.add()
            it.index, it.ttype, it.label = i, -1, 'Material %d' % i
        st.info = 'WMO: %d triangles shown, %d materials' % (len(mesh.tris), len(mesh.slots))


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
    img = model_preview.render(mesh, textures, PREVIEW_SIZE, st.yaw, st.pitch)
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


class WBS_PG_Browser(bpy.types.PropertyGroup):
    search: bpy.props.StringProperty(name='Search', description='Words to find anywhere in the file path (folders too)',
                                     update=refilter, options={'TEXTEDIT_UPDATE'})
    kind: bpy.props.EnumProperty(name='Type', items=[('ALL', 'All', ''), ('M2', 'M2', ''), ('WMO', 'WMO', '')],
                                 update=refilter)
    source: bpy.props.EnumProperty(name='Source', update=refilter, items=[
        ('PATCH', 'Patch archives', 'Only models whose winning copy is in a patch-*.mpq (custom content)'),
        ('ALL', 'All archives', 'Every archive of the client')])
    results: bpy.props.CollectionProperty(type=WBS_PG_BrowserItem)
    active: bpy.props.IntProperty(default=-1, update=_on_active)
    matches: bpy.props.IntProperty()
    current: bpy.props.StringProperty()
    info: bpy.props.StringProperty()
    slots: bpy.props.CollectionProperty(type=WBS_PG_BrowserSlot)
    yaw: bpy.props.FloatProperty(name='Turn', default=35.0, update=_on_view)
    pitch: bpy.props.FloatProperty(name='Tilt', default=12.0, min=-60.0, max=80.0, update=_on_view)
    preview_icon: bpy.props.IntProperty()
    render_ms: bpy.props.IntProperty()


# ------------------------------------------------------------------------------------------ operators

class WBS_OT_browser_index(bpy.types.Operator):
    bl_idname = 'wbs.browser_index'
    bl_label = 'Load Model List'
    bl_description = 'List every M2 / WMO in the client archives of the active WBS project'

    force: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        t0 = time.time()
        try:
            build_index(self.force)
        except Exception as e:
            traceback.print_exc()
            self.report({'ERROR'}, 'WBS browser: %s' % e)
            return {'CANCELLED'}
        refilter()
        self.report({'INFO'}, 'WBS browser: %d models in %d archives (%.1f s)' % (
            len(INDEX['models']), len(INDEX['archives']), time.time() - t0))
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
        split.label(text=os.path.basename(item.path), icon='OUTLINER_OB_ARMATURE' if item.kind == 'M2' else 'HOME')
        split.label(text=item.archive)

    def filter_items(self, context, data, propname):
        return [], []                                                  # filtering is done by the search field


class WBS_PT_model_browser(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'WBS Browser'
    bl_label = 'Model Browser'

    def draw(self, context):
        layout = self.layout
        st = context.window_manager.wbs_browser
        if not INDEX['models']:
            layout.operator(WBS_OT_browser_index.bl_idname, icon='VIEWZOOM')
            layout.label(text='This window may freeze for a little while', icon='INFO')
            return
        row = layout.row(align=True)
        row.label(text='%d models, %d archives' % (len(INDEX['models']), len(INDEX['archives'])))
        op = row.operator(WBS_OT_browser_index.bl_idname, text='', icon='FILE_REFRESH')
        op.force = True
        layout.prop(st, 'search', text='', icon='VIEWZOOM')
        row = layout.row(align=True)
        row.prop(st, 'kind', expand=True)
        layout.prop(st, 'source', text='')
        shown = len(st.results)
        layout.label(text='%d match%s%s' % (st.matches, '' if st.matches == 1 else 'es',
                                            '' if shown == st.matches else ' (first %d shown)' % shown))
        layout.template_list('WBS_UL_BrowserResults', '', st, 'results', st, 'active', rows=8)

        if not st.current:
            return
        box = layout.box()
        box.label(text=os.path.basename(st.current), icon='FILE_3D')
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


def unregister():
    global PREVIEWS
    try:
        del bpy.types.WindowManager.wbs_browser
    except Exception:
        pass
    if PREVIEWS is not None:
        bpy.utils.previews.remove(PREVIEWS)
        PREVIEWS = None
