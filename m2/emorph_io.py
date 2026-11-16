# Everwood Classic fork: .emorph (morph target) support - load as Blender shape keys, save back.
#
# FORMAT: custom/model-pipeline/morphs/CONTRACT-Morphs.md (file v2, section 3g negative shapes, 3h texture sliders).
# The reader / writer is a port of custom/model-pipeline/everwood_sliders/monkey_everwood_sliders/emorph.py.
#
# Mapping: a morph entry (idx = ORIGINAL M2 vertex indices, delta = offset at weight +1, M2 axes = the Blender mesh
# axes, the importer copies positions 1:1) becomes a shape key named after the entry key on every imported geoset mesh
# that holds at least one affected vertex (found through the `wbs_m2_vid` point attribute). A section 3g negative shape
# becomes a key `<key>.neg`. Geometry-less entries (texture sliders) and every entry's id / category / EN + RU labels
# live in the Text datablock META_TEXT (JSON) so a save round-trips them.
# Save: delta = shape key - Basis per vid (|delta| < 1e-6 dropped). To make an UNEDITED file come back byte-identical the
# saver snaps every delta that is within 1e-6 of the same vertex's delta in the source file (path kept in the metadata)
# onto the source value (float32 basis + delta - basis would otherwise lose the last bits).
import os
import re
import json
import struct

import bpy
import numpy as np
from bpy.props import StringProperty, BoolProperty, IntProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper

from .safe_export import VID_ATTR, find_meshes, _mesh_arrays

META_TEXT = 'wbs_emorph_meta.json'
NEG_SUFFIX = '.neg'
ID_MIN, ID_MAX, ID_FIRST_FREE = 26, 126, 100
KEY_RE = re.compile(r'^[a-z0-9_]{1,64}$')
DROP_EPS = 1e-6
SNAP_EPS = 1e-6
V1_IDS = {'chin_forward': 26, 'nose_size': 27, 'face_width': 28}
DEFAULT_LABELS = {
    'chin_forward': ('Chin forward', u'Подбородок вперёд'),
    'nose_size': ('Nose size', u'Размер носа'),
    'face_width': ('Face width', u'Ширина лица'),
}


class EmorphError(Exception):
    pass


# ------------------------------------------------------------------------------------------------ file format

def has_neg_block(cat):
    """Section 3g: bit 5 brings a negative-shape block only on a vertex morph (on a texture slider it means down-only)."""
    return bool(cat & 0x20) and not cat & 0x40


def parse(data):
    """bytes -> dict(version, n_model_v, morphs=[dict(key,pid,cat,en,ru,idx,delta,neg_idx,neg_delta)])."""
    d = data
    try:
        if d[:4] != b'EMRF':
            raise EmorphError('bad magic')
        ver, nv, nm = struct.unpack_from('<III', d, 4)
        if ver not in (1, 2):
            raise EmorphError('bad version %d' % ver)
        o = 16
        out = []
        for _ in range(nm):
            kl = d[o]; o += 1
            key = d[o:o + kl].decode('ascii'); o += kl
            if ver == 2:
                pid, cat = d[o], d[o + 1]; o += 2
                ll = d[o]; o += 1
                en = d[o:o + ll].decode('utf-8'); o += ll
                ll = d[o]; o += 1
                ru = d[o:o + ll].decode('utf-8'); o += ll
            else:
                pid, cat = V1_IDS.get(key), 1
                en, ru = DEFAULT_LABELS.get(key, (key, key))
            blocks = []
            for _b in range(2 if (ver == 2 and has_neg_block(cat)) else 1):
                n = struct.unpack_from('<I', d, o)[0]; o += 4
                if o + 16 * n > len(d):
                    raise EmorphError('truncated')
                idx = np.frombuffer(d, '<u4', n, o).copy(); o += 4 * n
                dl = np.frombuffer(d, '<f4', n * 3, o).reshape(n, 3).copy(); o += 12 * n
                blocks.append((idx, dl))
            (idx, dl), (ni, nd) = blocks[0], (blocks[1] if len(blocks) > 1 else (None, None))
            out.append(dict(key=key, pid=pid, cat=cat, en=en, ru=ru, idx=idx, delta=dl, neg_idx=ni, neg_delta=nd))
        if o != len(d):
            raise EmorphError('trailing bytes %d' % (len(d) - o))
    except (IndexError, struct.error, UnicodeDecodeError) as e:
        raise EmorphError('malformed .emorph: %r' % e)
    return dict(version=ver, n_model_v=nv, morphs=out)


def to_bytes(n_model_v, morphs):
    """v2 file bytes, morphs sorted by part id (as make_morphs writes them)."""
    ms = sorted(morphs, key=lambda m: m['pid'])
    out = [b'EMRF', struct.pack('<III', 2, n_model_v, len(ms))]
    for m in ms:
        kb = m['key'].encode('ascii')
        eb, rb = m['en'].encode('utf-8'), m['ru'].encode('utf-8')
        out += [struct.pack('<B', len(kb)), kb, struct.pack('<BB', m['pid'], m['cat']),
                struct.pack('<B', len(eb)), eb, struct.pack('<B', len(rb)), rb,
                struct.pack('<I', len(m['idx'])), np.asarray(m['idx'], '<u4').tobytes(),
                np.asarray(m['delta'], '<f4').reshape(-1, 3).tobytes()]
        if has_neg_block(m['cat']):
            out += [struct.pack('<I', len(m['neg_idx'])), np.asarray(m['neg_idx'], '<u4').tobytes(),
                    np.asarray(m['neg_delta'], '<f4').reshape(-1, 3).tobytes()]
    return b''.join(out)


def validate(n_model_v, morphs):
    """Structural rules of check_emorph.validate that need no geometry. -> list of error strings."""
    errs, ids, keys = [], set(), set()
    for m in morphs:
        k = m['key']
        if not KEY_RE.match(k):
            errs.append('%s: key must be lowercase [a-z0-9_]' % k)
        if k in keys:
            errs.append('%s: duplicate key' % k)
        keys.add(k)
        pid = m['pid']
        if pid is None or not ID_MIN <= pid <= ID_MAX:
            errs.append('%s: part id %r outside %d..%d' % (k, pid, ID_MIN, ID_MAX))
        if pid in ids:
            errs.append('%s: duplicate part id %r' % (k, pid))
        ids.add(pid)
        if not 0 <= (m['cat'] & 0x1f) <= 4:
            errs.append('%s: category %r outside 0..4' % (k, m['cat']))
        has_neg = m.get('neg_idx') is not None
        if m['cat'] & 0x20 and m['cat'] & 0x80:
            errs.append('%s: bit 5 with bit 7' % k)
        if has_neg_block(m['cat']) != has_neg:
            errs.append('%s: negative-shape bit and block disagree' % k)
        if has_neg:
            ni, nd = m['neg_idx'], m['neg_delta']
            if len(ni) == 0:
                errs.append('%s: empty negative shape' % k)
            if len(ni) and int(ni.max()) >= n_model_v:
                errs.append('%s: negative shape index out of range' % k)
            if len(ni) > 1 and not np.all(np.diff(ni.astype(np.int64)) > 0):
                errs.append('%s: negative shape indices not strictly increasing' % k)
            if not np.all(np.isfinite(nd)):
                errs.append('%s: NaN / inf negative delta' % k)
        if (len(m['idx']) == 0) != bool(m['cat'] & 0x40):
            errs.append('%s: n = 0 vertices requires the texture bit (0x40) and vice versa' % k)
        for lbl, name in ((m['en'], 'EN'), (m['ru'], 'RU')):
            if not lbl.strip():
                errs.append('%s: empty %s label' % (k, name))
            elif len(lbl.encode('utf-8')) > 255:
                errs.append('%s: %s label longer than 255 bytes' % (k, name))
        idx = m['idx']
        if len(idx) and int(idx.max()) >= n_model_v:
            errs.append('%s: vertex index out of range (n_model_v %d)' % (k, n_model_v))
        if len(idx) > 1 and not np.all(np.diff(idx.astype(np.int64)) > 0):
            errs.append('%s: indices not strictly increasing' % k)
        if not np.all(np.isfinite(m['delta'])):
            errs.append('%s: NaN / inf delta' % k)
    return errs


# ------------------------------------------------------------------------------------------------ metadata text

def read_meta():
    t = bpy.data.texts.get(META_TEXT)
    if t is None:
        return None
    try:
        return json.loads(t.as_string())
    except ValueError:
        return None


def write_meta(meta):
    t = bpy.data.texts.get(META_TEXT) or bpy.data.texts.new(META_TEXT)
    t.clear()
    t.write(json.dumps(meta, ensure_ascii=False, indent=1))


def _entry_meta(m):
    return dict(key=m['key'], pid=int(m['pid']), cat=int(m['cat']), en=m['en'], ru=m['ru'],
                has_geo=bool(len(m['idx'])), has_neg=m.get('neg_idx') is not None)


# ------------------------------------------------------------------------------------------------ load

def _dense(n, idx, delta):
    full = np.zeros((n, 3), np.float32)
    full[idx] = delta
    hit = np.zeros(n, bool)
    hit[idx] = True
    return full, hit


def load_emorph(objs, path):
    """Create the shape keys. -> dict(ok, errors, warnings, keys (names created), n_geo_entries, n_entries, per_mesh)."""
    res = dict(ok=False, errors=[], warnings=[], keys=[], n_geo_entries=0, n_entries=0, n_neg=0)
    if not objs:
        res['errors'].append('no imported M2 meshes (with the wbs_m2_vid attribute) found - import the model first')
        return res
    try:
        with open(path, 'rb') as f:
            em = parse(f.read())
    except (OSError, EmorphError) as e:
        res['errors'].append(str(e))
        return res
    nv = em['n_model_v']
    for o in objs:
        saved = o.get('wbs_m2_nverts')
        if saved is not None and int(saved) != nv:
            res['errors'].append('%s was built for %d vertices but the imported model has %d: wrong pair of files'
                                 % (os.path.basename(path), nv, int(saved)))
            return res

    info = []        # per mesh: obj, vid, basis co (n,3)
    for o in objs:
        vid, ok, co = _mesh_arrays(o)
        info.append((o, np.where(ok, vid, -1), co))

    def make_key(o, name, vid, co, full, hit):
        sel = (vid >= 0) & hit[np.clip(vid, 0, nv - 1)]
        if not sel.any():
            return False
        me = o.data
        if me.shape_keys is None:
            o.shape_key_add(name='Basis', from_mix=False)
        if me.shape_keys is not None and name in me.shape_keys.key_blocks:
            o.shape_key_remove(me.shape_keys.key_blocks[name])
        sk = o.shape_key_add(name=name, from_mix=False)
        new = co.copy()
        new[sel] += full[vid[sel]]
        sk.data.foreach_set('co', new.ravel())
        sk.value = 0.0
        return True

    created = []
    for m in em['morphs']:
        if len(m['idx']):
            res['n_geo_entries'] += 1
            blocks = [(m['key'], m['idx'], m['delta'])]
            if m['neg_idx'] is not None:
                blocks.append((m['key'] + NEG_SUFFIX, m['neg_idx'], m['neg_delta']))
                res['n_neg'] += 1
            for name, idx, delta in blocks:
                full, hit = _dense(nv, idx, delta)
                n_mesh = 0
                for o, vid, co in info:
                    n_mesh += make_key(o, name, vid, co, full, hit)
                if n_mesh:
                    created.append(name)
                else:
                    res['warnings'].append('%s: none of its %d vertices is in the imported meshes' % (name, len(idx)))
    res['n_entries'] = len(em['morphs'])
    res['keys'] = created
    write_meta(dict(version=2, n_model_v=nv, source_path=os.path.abspath(path),
                    entries=[_entry_meta(m) for m in em['morphs']]))
    res['ok'] = True
    return res


# ------------------------------------------------------------------------------------------------ save

def _gather(objs, nv):
    """shape-key name -> (vids sorted unique, deltas float32 (n,3)); plus warnings list."""
    parts = {}
    warns = []
    for o in objs:
        me = o.data
        sk = me.shape_keys
        if sk is None or len(sk.key_blocks) < 2:
            continue
        vid, ok, co0 = _mesh_arrays(o)
        basis = np.empty(len(me.vertices) * 3, np.float32)
        sk.reference_key.data.foreach_get('co', basis)
        basis = basis.reshape(-1, 3)
        good = ok & (vid >= 0) & (vid < nv)
        for kb in sk.key_blocks:
            if kb.name == sk.reference_key.name:
                continue
            arr = np.empty(len(me.vertices) * 3, np.float32)
            kb.data.foreach_get('co', arr)
            dl = arr.reshape(-1, 3) - basis
            parts.setdefault(kb.name, []).append((vid[good], dl[good]))
    out = {}
    for name, lst in parts.items():
        v = np.concatenate([p[0] for p in lst])
        d = np.concatenate([p[1] for p in lst])
        nrm = np.abs(d).max(axis=1)
        order = np.lexsort((-nrm, v))              # per vid: largest delta first
        v, d = v[order], d[order]
        first = np.ones(len(v), bool)
        first[1:] = v[1:] != v[:-1]
        if len(v) > 1 and not first.all():
            dup = ~first
            dd = np.abs(d[1:] - d[:-1]).max(axis=1)
            bad = int((dup[1:] & (dd > 1e-5)).sum())
            if bad:
                warns.append('%s: %d vertices differ between meshes sharing the same vertex id (largest delta used)'
                             % (name, bad))
        out[name] = (v[first], d[first])
    return out, warns


def _clean(vids, deltas, nv, orig):
    """-> (idx u32 sorted, delta f32): drop |delta| < DROP_EPS, snap onto the source file's values when within SNAP_EPS."""
    full = np.zeros((nv, 3), np.float32)
    full[vids] = deltas
    keep = np.abs(full).max(axis=1) >= DROP_EPS
    if orig is not None and len(orig[0]):
        ofull, ohit = _dense(nv, orig[0], orig[1])
        close = ohit & (np.abs(full - ofull).max(axis=1) <= SNAP_EPS)
        keep |= close
        full = np.where(close[:, None], ofull, full)
    idx = np.nonzero(keep)[0].astype('<u4')
    return idx, full[idx].astype('<f4')


def collect_morphs(objs, meta=None, default_cat=0):
    """Shape keys -> morph dicts. -> (n_model_v, morphs, warnings)."""
    warns = []
    nverts = {int(o['wbs_m2_nverts']) for o in objs if 'wbs_m2_nverts' in o}
    if meta and meta.get('n_model_v'):
        nv = int(meta['n_model_v'])
    elif len(nverts) == 1:
        nv = nverts.pop()
    else:
        raise EmorphError('cannot tell the vertex count of the model (re-import it)')
    if nverts and nv not in nverts:
        raise EmorphError('the loaded .emorph (%d vertices) does not belong to the imported model (%s vertices)'
                          % (nv, sorted(nverts)))

    orig = {}
    if meta and meta.get('source_path') and os.path.isfile(meta['source_path']):
        try:
            with open(meta['source_path'], 'rb') as f:
                e = parse(f.read())
            if e['n_model_v'] == nv:
                orig = {m['key']: m for m in e['morphs']}
        except (OSError, EmorphError):
            pass

    gathered, w = _gather(objs, nv)
    warns += w
    entries = list(meta['entries']) if meta else []
    by_key = {e['key']: e for e in entries}
    used = {e['pid'] for e in entries}

    morphs = []
    consumed = set()
    for e in entries:
        key = e['key']
        base = dict(key=key, pid=e['pid'], cat=e['cat'], en=e['en'], ru=e['ru'])
        if not e['has_geo']:                                            # texture slider: metadata only
            if key in gathered:
                warns.append('%s is a texture slider (no geometry): its shape key was ignored' % key)
                consumed.add(key)
            morphs.append(dict(base, idx=np.zeros(0, '<u4'), delta=np.zeros((0, 3), '<f4'), neg_idx=None, neg_delta=None))
            continue
        if key not in gathered:
            warns.append('%s: shape key missing - entry removed from the file' % key)
            continue
        consumed.add(key)
        o = orig.get(key)
        idx, dl = _clean(*gathered[key], nv, (o['idx'], o['delta']) if o is not None else None)
        if not len(idx):
            warns.append('%s: shape key is empty (all deltas < %g) - entry removed from the file' % (key, DROP_EPS))
            consumed.add(key + NEG_SUFFIX)
            continue
        cat = e['cat']
        neg_idx = neg_dl = None
        nk = key + NEG_SUFFIX
        if nk in gathered and not cat & 0xc0:
            consumed.add(nk)
            oi = (o['neg_idx'], o['neg_delta']) if o is not None and o['neg_idx'] is not None else None
            neg_idx, neg_dl = _clean(*gathered[nk], nv, oi)
            if len(neg_idx):
                cat |= 0x20
            else:
                neg_idx = neg_dl = None
                cat &= ~0x20
        elif cat & 0x20 and not cat & 0x40:
            warns.append('%s: its negative shape key is gone - negative shape dropped' % key)
            cat &= ~0x20
        morphs.append(dict(base, cat=cat, idx=idx, delta=dl, neg_idx=neg_idx, neg_delta=neg_dl))

    # new keys
    for name in sorted(gathered):
        if name in consumed or name.endswith(NEG_SUFFIX) or name in by_key:
            continue
        key = re.sub(r'[^a-z0-9_]', '_', name.lower())[:64] or 'morph'
        if key in by_key:
            warns.append('%s: key name clashes with an existing entry - skipped' % name)
            continue
        idx, dl = _clean(*gathered[name], nv, None)
        if not len(idx):
            warns.append('%s: new shape key is empty - skipped' % name)
            continue
        pid = next((i for i in range(ID_FIRST_FREE, ID_MAX + 1) if i not in used), None)
        if pid is None:
            raise EmorphError('no free part id left (%d..%d are all used)' % (ID_FIRST_FREE, ID_MAX))
        used.add(pid)
        by_key[key] = {}
        cat = default_cat
        neg_idx = neg_dl = None
        nk = name + NEG_SUFFIX
        if nk in gathered:
            consumed.add(nk)
            neg_idx, neg_dl = _clean(*gathered[nk], nv, None)
            if len(neg_idx):
                cat |= 0x20
            else:
                neg_idx = neg_dl = None
        morphs.append(dict(key=key, pid=pid, cat=cat, en=name, ru=name, idx=idx, delta=dl, neg_idx=neg_idx,
                           neg_delta=neg_dl))
    for name in gathered:
        if name.endswith(NEG_SUFFIX) and name not in consumed:
            warns.append('%s: negative key without a positive key - ignored' % name)
    return nv, morphs, warns


def save_emorph(objs, path, default_cat=0):
    """Write the .emorph. -> dict(ok, errors, warnings, n_entries, size)."""
    res = dict(ok=False, errors=[], warnings=[], n_entries=0, size=0)
    if not objs:
        res['errors'].append('no imported M2 meshes (with the wbs_m2_vid attribute) found')
        return res
    try:
        nv, morphs, warns = collect_morphs(objs, read_meta(), default_cat)
    except EmorphError as e:
        res['errors'].append(str(e))
        return res
    res['warnings'] += warns
    errs = validate(nv, morphs)
    if errs:
        res['errors'] += errs
        return res
    data = to_bytes(nv, morphs)
    try:
        back = parse(data)
        assert back['n_model_v'] == nv and len(back['morphs']) == len(morphs)
    except Exception as e:
        res['errors'].append('written data does not read back: %r' % e)
        return res
    tmp = path + '.tmp'
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)
    # keep the metadata in step (new keys got ids / labels)
    write_meta(dict(version=2, n_model_v=nv, source_path=os.path.abspath(path),
                    entries=[_entry_meta(m) for m in sorted(morphs, key=lambda m: m['pid'])]))
    res['ok'] = True
    res['n_entries'] = len(morphs)
    res['size'] = len(data)
    return res


# ------------------------------------------------------------------------------------------------ operators

def _report(op, context, title, res):
    lines = [title + ': ' + ('OK' if res['ok'] else 'FAILED')]
    lines += ['ERROR: ' + e for e in res['errors']] + ['warning: ' + w for w in res['warnings'][:20]]
    context.scene['wbs_char_status'] = '\n'.join(lines)
    for l in lines:
        print(l)
    for e in res['errors']:
        op.report({'ERROR'}, e)
    for w in res['warnings'][:5]:
        op.report({'WARNING'}, w)


class WBS_OT_emorph_load(bpy.types.Operator, ImportHelper):
    """Load a .emorph file as shape keys on the imported M2 meshes"""
    bl_idname = 'wbs.emorph_load'
    bl_label = 'Load .emorph'
    filename_ext = '.emorph'
    filter_glob: StringProperty(default='*.emorph', options={'HIDDEN'})
    only_selected: BoolProperty(name='Selected meshes only', default=False)

    def execute(self, context):
        res = load_emorph(find_meshes(context, self.only_selected), self.filepath)
        _report(self, context, 'Load .emorph', res)
        if res['ok']:
            context.scene['wbs_char_status'] += '\n%d entries, %d with geometry (%d negative shapes), %d shape keys' % (
                res['n_entries'], res['n_geo_entries'], res['n_neg'], len(res['keys']))
        return {'FINISHED'} if res['ok'] else {'CANCELLED'}


class WBS_OT_emorph_save(bpy.types.Operator, ExportHelper):
    """Save the shape keys of the imported M2 meshes as a .emorph file"""
    bl_idname = 'wbs.emorph_save'
    bl_label = 'Save .emorph'
    filename_ext = '.emorph'
    filter_glob: StringProperty(default='*.emorph', options={'HIDDEN'})
    only_selected: BoolProperty(name='Selected meshes only', default=False)
    default_cat: IntProperty(name='Category of new keys', default=0, min=0, max=4,
                             description='0 General, 1 Face, 2 Upper body, 3 Midsection, 4 Lower body')

    def execute(self, context):
        res = save_emorph(find_meshes(context, self.only_selected), self.filepath, self.default_cat)
        _report(self, context, 'Save .emorph', res)
        if res['ok']:
            context.scene['wbs_char_status'] += '\n%d entries, %d bytes -> %s' % (res['n_entries'], res['size'],
                                                                                self.filepath)
        return {'FINISHED'} if res['ok'] else {'CANCELLED'}
