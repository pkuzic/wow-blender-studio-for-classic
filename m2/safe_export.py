# Everwood Classic fork: SAFE character export.
#
# WBS's normal M2 export is not safe for character models (hidden submeshes are dropped, vertices reordered, geoset
# selection and sliders break). This operator instead takes the ORIGINAL .m2 bytes and replaces ONLY the vertex
# positions (and optionally the normals of the moved vertices) from the Blender meshes. Every other byte stays
# identical: same size, same offsets, same vertex order.
#
# Vertex identity: m2_scene.load_geosets stores an INT point attribute `wbs_m2_vid` (original M2 vertex index) and
# `wbs_m2_ok` (1 on every imported vertex, 0 on vertices created later) on every imported geoset mesh.
# Coordinates: the importer copies M2 positions into the mesh 1:1 (no axis swap), so the transform is the identity in
# MESH-LOCAL space (verified: exporting an unchanged import is byte-identical, tests/test_safe_export.py).
import os
import struct

import bpy
import numpy as np
from bpy.props import StringProperty, BoolProperty
from bpy_extras.io_utils import ExportHelper

VID_ATTR = 'wbs_m2_vid'
OK_ATTR = 'wbs_m2_ok'
MOVE_EPS = 1e-7        # a vertex counts as moved when any coordinate differs from the original by more than this

VERTEX_DTYPE = np.dtype([('pos', '<f4', 3), ('bw', 'u1', 4), ('bi', 'u1', 4), ('nrm', '<f4', 3), ('uv', '<f4', 4)])
assert VERTEX_DTYPE.itemsize == 48


def m2_vertex_block(data):
    """(count, offset) of the 48-byte vertex records of an MD20 v256-v264 M2."""
    if data[:4] != b'MD20':
        raise ValueError('not an MD20 M2 (MD21 / Legion files are not supported)')
    ver = struct.unpack_from('<I', data, 4)[0]
    if not 256 <= ver <= 264:
        raise ValueError('unsupported M2 version %d (supported: 256-264)' % ver)
    hdr = 0x44 if ver < 264 else 0x3C
    n, o = struct.unpack_from('<II', data, hdr)
    if o + n * 48 > len(data):
        raise ValueError('vertex block lies outside the file')
    return n, o


def read_vertices(data):
    n, o = m2_vertex_block(data)
    return np.frombuffer(data, VERTEX_DTYPE, n, o)


def has_vid(obj):
    return obj.type == 'MESH' and VID_ATTR in obj.data.attributes


def find_meshes(context, only_selected=False):
    objs = context.selected_objects if only_selected else context.scene.objects
    return [o for o in objs if has_vid(o)]


def _mesh_arrays(obj):
    """-> (vid[int64], ok[bool], co[float32 (n,3)]) of an M2 mesh object, mesh-local coordinates."""
    if obj.mode == 'EDIT':
        obj.update_from_editmode()
    me = obj.data
    n = len(me.vertices)
    vid = np.empty(n, np.int32)
    me.attributes[VID_ATTR].data.foreach_get('value', vid)
    ok = np.ones(n, np.int32)
    if OK_ATTR in me.attributes:
        me.attributes[OK_ATTR].data.foreach_get('value', ok)
    co = np.empty(n * 3, np.float32)
    me.vertices.foreach_get('co', co)
    return vid.astype(np.int64), ok != 0, co.reshape(n, 3)


def _face_normal_sums(obj, co, vid, acc):
    """Add the area-weighted triangle normals of the mesh (new positions `co`) into acc[vid]."""
    me = obj.data
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    if not nt:
        return
    tri = np.empty(nt * 3, np.int32)
    me.loop_triangles.foreach_get('vertices', tri)
    tri = tri.reshape(nt, 3)
    p0, p1, p2 = co[tri[:, 0]].astype(np.float64), co[tri[:, 1]].astype(np.float64), co[tri[:, 2]].astype(np.float64)
    fn = np.cross(p1 - p0, p2 - p0)
    for k in range(3):
        np.add.at(acc, vid[tri[:, k]], fn)


def original_source(objs):
    """(game_path, local_path) shared by the meshes. Raises ValueError when they come from different models."""
    srcs = set()
    for o in objs:
        srcs.add((str(o.get('wbs_m2_game_path', '')), str(o.get('wbs_m2_local_path', ''))))
    if len(srcs) > 1:
        raise ValueError('the meshes come from different models: %s' % '; '.join(sorted(s[0] or s[1] for s in srcs)))
    return next(iter(srcs)) if srcs else ('', '')


def load_original_bytes(objs, original_path=''):
    """Original .m2 bytes: an explicit local file, else the client's game data, else the import's local file."""
    if original_path:
        with open(bpy.path.abspath(original_path), 'rb') as f:
            return f.read(), original_path
    game_path, local_path = original_source(objs)
    if game_path:
        try:
            from ..utils.misc import load_game_data
            res = load_game_data().read_file(game_path.replace('/', '\\').lstrip('\\'), no_exc=True)
            if res:
                return res[0], 'client:' + game_path
        except Exception as e:
            print('safe export: client read failed:', e)
    if local_path and os.path.isfile(local_path):
        with open(local_path, 'rb') as f:
            return f.read(), local_path
    raise ValueError('cannot find the original .m2 (game path %r, local path %r): choose it with "Original M2"'
                     % (game_path, local_path))


def build_safe_m2(objs, original, update_normals=True, ignore_new=False):
    """Pure core. -> dict(ok, data (bytes or None), errors, warnings, moved (sorted vids), n_vertices).
    Replaces only position (+ normal of moved vertices) of the vertex records `original` holds."""
    res = dict(ok=False, data=None, errors=[], warnings=[], moved=[], n_vertices=0)
    try:
        n_orig, off = m2_vertex_block(original)
    except ValueError as e:
        res['errors'].append(str(e))
        return res
    res['n_vertices'] = n_orig
    if not objs:
        res['errors'].append('no imported M2 meshes (with the wbs_m2_vid attribute) found')
        return res

    orig = np.frombuffer(original, VERTEX_DTYPE, n_orig, off)
    orig_pos = orig['pos']

    for o in objs:
        n_saved = o.get('wbs_m2_nverts')
        if n_saved is not None and int(n_saved) != n_orig:
            res['errors'].append('%s: imported from a model with %d vertices but the original has %d - wrong original file'
                                 % (o.name, int(n_saved), n_orig))
        m = o.matrix_basis
        ident = all(abs(m[i][j] - (1.0 if i == j else 0.0)) < 1e-6 for i in range(4) for j in range(4))
        if not ident:
            res['warnings'].append('%s has a non-identity object transform; positions are exported in MESH-LOCAL '
                                   'space (apply the transform to the mesh or reset it)' % o.name)
    if res['errors']:
        return res

    parts = []          # (obj, vid, co, ok)
    bad_new, bad_range = [], []
    for o in objs:
        vid, ok, co = _mesh_arrays(o)
        in_range = (vid >= 0) & (vid < n_orig)
        newv = ~ok
        if newv.any():
            bad_new.append((o.name, int(newv.sum())))
        rng = ok & ~in_range
        if rng.any():
            bad_range.append((o.name, int(rng.sum())))
        parts.append((o, vid, co, ok & in_range))
    if (bad_new or bad_range) and not ignore_new:
        for name, c in bad_new:
            res['errors'].append('%s: %d vertices without a vertex id (new geometry; M2 vertices cannot be added by the '
                                 'safe export - enable "Ignore new vertices" to skip them)' % (name, c))
        for name, c in bad_range:
            res['errors'].append('%s: %d vertices with an out-of-range vertex id' % (name, c))
        return res
    for name, c in bad_new + bad_range:
        res['warnings'].append('%s: %d new / invalid vertices ignored' % (name, c))

    # moved entries per mesh
    mv_vid, mv_pos, mv_name = [], [], []
    seen_unmoved = []
    for o, vid, co, good in parts:
        v, c = vid[good], co[good]
        moved = np.any(np.abs(c.astype(np.float64) - orig_pos[v].astype(np.float64)) > MOVE_EPS, axis=1)
        mv_vid.append(v[moved]); mv_pos.append(c[moved]); mv_name.append(np.full(int(moved.sum()), len(mv_name)))
        seen_unmoved.append(v[~moved])
    mvv = np.concatenate(mv_vid) if mv_vid else np.zeros(0, np.int64)
    mvp = np.concatenate(mv_pos) if mv_pos else np.zeros((0, 3), np.float32)
    mvm = np.concatenate(mv_name) if mv_name else np.zeros(0, np.int64)

    order = np.argsort(mvv, kind='stable')
    mvv, mvp, mvm = mvv[order], mvp[order], mvm[order]
    first = np.ones(len(mvv), bool)
    first[1:] = mvv[1:] != mvv[:-1]
    # same vid moved to different places in several meshes
    if len(mvv) > 1:
        same = ~first
        diff = np.zeros(len(mvv), bool)
        diff[1:] = same[1:] & np.any(np.abs(mvp[1:].astype(np.float64) - mvp[:-1].astype(np.float64)) > 1e-5, axis=1)
        if diff.any():
            bad = np.unique(mvv[diff])
            res['warnings'].append('%d vertex ids appear in several meshes at DIFFERENT positions (the first mesh wins), '
                                   'e.g. vid %s in %s vs %s' % (len(bad), int(bad[0]),
                                   objs[int(mvm[np.where(mvv == bad[0])[0][0]])].name,
                                   objs[int(mvm[np.where(mvv == bad[0])[0][1]])].name))
    uv_, up_ = mvv[first], mvp[first]
    # a moved vertex whose twin copy in another mesh stayed in place
    if len(uv_) and seen_unmoved:
        still = np.unique(np.concatenate(seen_unmoved))
        both = np.intersect1d(uv_, still)
        if len(both):
            res['warnings'].append('%d moved vertices have a copy in another mesh that did not move (the moved copy is '
                                   'exported; move both copies to keep the seam closed)' % len(both))

    buf = bytearray(original)
    recs = np.frombuffer(buf, VERTEX_DTYPE, n_orig, off)       # writable view into buf
    if len(uv_):
        recs['pos'][uv_] = up_
        if update_normals:
            acc = np.zeros((n_orig, 3), np.float64)
            for o, vid, co, good in parts:
                _face_normal_sums(o, co, vid, acc)
            nn = acc[uv_]
            ln = np.linalg.norm(nn, axis=1)
            good_n = ln > 1e-12
            sel = uv_[good_n]
            recs['nrm'][sel] = (nn[good_n] / ln[good_n, None]).astype(np.float32)
    res['moved'] = [int(x) for x in uv_]
    res['data'] = bytes(buf)
    res['ok'] = True
    return res


def safe_export(objs, out_path, original_path='', update_normals=True, ignore_new=False, original_bytes=None):
    """Write the safe M2. -> result dict of build_safe_m2 plus 'source' and 'path'."""
    try:
        if original_bytes is None:
            original_bytes, src = load_original_bytes(objs, original_path)
        else:
            src = 'bytes'
    except (ValueError, OSError) as e:
        return dict(ok=False, data=None, errors=[str(e)], warnings=[], moved=[], n_vertices=0, source='', path='')
    res = build_safe_m2(objs, original_bytes, update_normals, ignore_new)
    res['source'] = src
    res['path'] = out_path
    if res['ok']:
        d = os.path.dirname(os.path.abspath(out_path))
        os.makedirs(d, exist_ok=True)
        with open(out_path, 'wb') as f:
            f.write(res['data'])
    return res


class WBS_OT_m2_safe_export(bpy.types.Operator, ExportHelper):
    """Write the ORIGINAL .m2 with only the vertex positions replaced from the Blender meshes (character-safe)"""
    bl_idname = 'wbs.m2_safe_export'
    bl_label = 'Safe Export (positions only)'
    filename_ext = '.m2'
    filter_glob: StringProperty(default='*.m2', options={'HIDDEN'})
    update_normals: BoolProperty(name='Update normals', default=True,
                                 description='Recompute the normals of the moved vertices from the new geometry')
    ignore_new: BoolProperty(name='Ignore new vertices', default=False,
                             description='Skip vertices that have no M2 vertex id instead of refusing')
    only_selected: BoolProperty(name='Selected meshes only', default=False)
    original_path: StringProperty(name='Original M2', subtype='FILE_PATH', default='',
                                  description='Optional: a local original .m2. Empty = read it from the client')

    def execute(self, context):
        objs = find_meshes(context, self.only_selected)
        res = safe_export(objs, self.filepath, self.original_path, self.update_normals, self.ignore_new)
        lines = ['Safe export: ' + ('OK' if res['ok'] else 'REFUSED')]
        if res['ok']:
            lines.append('%d of %d vertices changed -> %s' % (len(res['moved']), res['n_vertices'], self.filepath))
        lines += ['ERROR: ' + e for e in res['errors']] + ['warning: ' + w for w in res['warnings']]
        context.scene['wbs_char_status'] = '\n'.join(lines)
        for l in lines:
            print(l)
        for e in res['errors']:
            self.report({'ERROR'}, e)
        for w in res['warnings']:
            self.report({'WARNING'}, w)
        if res['ok']:
            self.report({'INFO'}, '%d vertices changed' % len(res['moved']))
            # same follow-up as a normal export: 1.12 checks (only for a 1.12 original) and offer the file to
            # 'Send to test client'
            try:
                from .classic_lint_m2 import lint_after_export
                ver = max((int(o.get('wbs_m2_version', 0) or 0) for o in objs), default=0)
                lint_after_export(self, self.filepath, 0 if ver <= 257 else 2)
            except Exception as e:
                self.report({'WARNING'}, 'post-export checks skipped: %s' % e)
        return {'FINISHED'} if res['ok'] else {'CANCELLED'}
