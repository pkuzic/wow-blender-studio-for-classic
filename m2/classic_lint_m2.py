"""Classic (1.12 / vanilla) M2 export lint.

Validates the WRITTEN .m2 bytes (not the Blender scene) so it also works as a standalone "Check M2 for 1.12"
tool on any file. The parser is deliberately independent of pywowlib's readers: a corrupt or wrongly-versioned
file must be reported, not crash the checker.

Observed 1.12 facts (measured over the 9504 stock v256 models of model.MPQ / patch.MPQ / patch-2.MPQ):
  * every view has boneCountMax == 256;
  * the largest model has 178 bones, the largest submesh bone palette is 176 entries
    (transportship_sails.m2); bone palette (bone lookup) sizes go up to 752;
  * vertex bone indices are u8 and address the PALETTE of the submesh the vertex belongs to.
Hard limits used for ERRORs: 256 bones / 256 palette entries per submesh (u8 index space).
Anything above the stock maxima (178 / 176) is a WARNING.

No bpy at import time (the operators are only defined when bpy is available), so the checks can be run from a
plain Python for batch scans.
"""

import os
import re
import struct

try:
    import numpy as np
except ImportError:                                   # pragma: no cover
    np = None

try:
    import bpy
except ImportError:                                   # pragma: no cover
    bpy = None


# Observed stock 1.12 maxima (see module docstring).
STOCK_MAX_BONES = 178
STOCK_MAX_SUBMESH_BONES = 176
HARD_MAX_BONES = 256
HARD_MAX_SUBMESH_BONES = 256
VANILLA_BONE_COUNT_MAX = 256
WEIGHT_SUM_TOLERANCE = 3      # four u8 weights rounded from floats legitimately sum to 252..255

GLOBAL_FLAG_TEXTURE_COMBINER = 0x08


class LintResult:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.infos = []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def info(self, msg):
        self.infos.append(msg)

    def report_lines(self):
        return (["ERROR: " + m for m in self.errors]
                + ["WARNING: " + m for m in self.warnings]
                + list(self.infos))

    @property
    def ok(self):
        return not self.errors


# ---------------------------------------------------------------------------------------------------- header

def _header_fields(vanilla_layout):
    """Ordered (name, kind, elem_min_size) of the M2 header after the version. kind: 'a' M2Array (8 bytes),
    'u' uint32, 'b' CAaBox (24), 'f' float (4). Mirrors pywowlib M2Header."""
    f = [('name', 'a', 1), ('global_flags', 'u', 0), ('global_sequences', 'a', 4), ('sequences', 'a', 64),
         ('sequence_lookup', 'a', 2)]
    if vanilla_layout:
        f.append(('playable_animation_lookup', 'a', 4))
    f += [('bones', 'a', 84), ('key_bone_lookup', 'a', 2), ('vertices', 'a', 48)]
    f.append(('skin_profiles', 'a', 44) if vanilla_layout else ('num_skin_profiles', 'u', 0))
    f += [('colors', 'a', 32), ('textures', 'a', 16), ('texture_weights', 'a', 4)]
    if vanilla_layout:
        f.append(('unknown', 'a', 2))
    f += [('texture_transforms', 'a', 4), ('replacable_texture_lookup', 'a', 2), ('materials', 'a', 4),
          ('bone_lookup_table', 'a', 2), ('texture_lookup_table', 'a', 2), ('tex_unit_lookup_table', 'a', 2),
          ('transparency_lookup_table', 'a', 2), ('texture_transforms_lookup_table', 'a', 2),
          ('bounding_box', 'b', 0), ('bounding_sphere_radius', 'f', 0), ('collision_box', 'b', 0),
          ('collision_sphere_radius', 'f', 0), ('collision_triangles', 'a', 2), ('collision_vertices', 'a', 12),
          ('collision_normals', 'a', 12), ('attachments', 'a', 40), ('attachment_lookup_table', 'a', 2),
          ('events', 'a', 20), ('lights', 'a', 40), ('cameras', 'a', 40), ('camera_lookup_table', 'a', 2),
          ('ribbon_emitters', 'a', 60), ('particle_emitters', 'a', 100)]
    if not vanilla_layout:
        f.append(('texture_combiner_combos', 'a', 2))
    return f


def parse_header(data, vanilla_layout):
    """Returns (fields dict name -> (n, ofs) | int | float, header_size)."""
    out, pos = {}, 8
    for name, kind, _sz in _header_fields(vanilla_layout):
        if kind == 'a':
            if pos + 8 > len(data):
                return out, pos
            out[name] = struct.unpack_from('<II', data, pos)
            pos += 8
        elif kind == 'u':
            out[name] = struct.unpack_from('<I', data, pos)[0]
            pos += 4
        elif kind == 'f':
            out[name] = struct.unpack_from('<f', data, pos)[0]
            pos += 4
        else:
            pos += 24
    return out, pos


def _cstr_at(data, ofs, n):
    return data[ofs:ofs + n].split(b'\0', 1)[0].decode('latin-1')


def _norm(p):
    return p.replace('/', '\\').strip()


# ---------------------------------------------------------------------------------------------------- DBC

def _read_dbc(raw):
    """Minimal WDBC reader: returns (nfields, rows(list of tuples of u32), strblock bytes) or None."""
    if not raw or raw[:4] != b'WDBC':
        return None
    nrec, nf, rs, ss = struct.unpack_from('<IIII', raw, 4)
    if rs != nf * 4 or 20 + nrec * rs + ss > len(raw):
        return None
    rows = [struct.unpack_from('<%dI' % nf, raw, 20 + r * rs) for r in range(nrec)]
    return nf, rows, raw[20 + nrec * rs:20 + nrec * rs + ss]


def _dbc_str(strs, ofs):
    if 0 < ofs < len(strs):
        return strs[ofs:].split(b'\0', 1)[0].decode('latin-1')
    return ''


_CHAR_RE = re.compile(r'^character\\([^\\]+)\\(male|female)\\([^\\]+)\.m2$', re.I)


def _race_id(read_dbc, race_folder):
    d = _read_dbc(read_dbc('DBFilesClient\\ChrRaces.dbc'))
    if not d:
        return None
    nf, rows, strs = d
    want = race_folder.lower()
    for row in rows:
        for v in row[1:]:
            if v and v < len(strs) and _dbc_str(strs, v).lower() == want:
                return row[0]
    return None


def _check_character_geosets(res, geosets, game_path, read_dbc):
    m = _CHAR_RE.match(_norm(game_path))
    if not m or read_dbc is None:
        return
    race_folder, sex_name, stem = m.group(1), m.group(2).lower(), m.group(3)
    if stem.lower() != (race_folder + sex_name).lower():
        return
    sex = 0 if sex_name == 'male' else 1
    race = _race_id(read_dbc, race_folder)
    if race is None:
        res.info("Character geoset check skipped: race '%s' not found in ChrRaces.dbc." % race_folder)
        return

    missing_hair, missing_beard = set(), set()
    hair = _read_dbc(read_dbc('DBFilesClient\\CharHairGeosets.dbc'))
    if hair:
        for row in hair[1]:
            # ID, RaceID, SexID, VariationID, GeosetID, Showscalp
            if len(row) >= 5 and row[1] == race and row[2] == sex and row[4] and row[4] not in geosets:
                missing_hair.add(row[4])
    else:
        res.info("CharHairGeosets.dbc not found: hairstyle geoset check skipped.")

    fh = _read_dbc(read_dbc('DBFilesClient\\CharacterFacialHairStyles.dbc'))
    if fh and fh[0] == 9:
        for row in fh[1]:
            # Race, Sex, Variation, <3 unknown>, Geoset100, Geoset300, Geoset200 (verified against HumanMale)
            if row[0] == race and row[1] == sex:
                for value, group in zip(row[6:9], (1, 3, 2)):
                    if value and group * 100 + value not in geosets:
                        missing_beard.add(group * 100 + value)
    elif fh:
        res.info("CharacterFacialHairStyles.dbc has %d columns (expected 9): facial hair check skipped." % fh[0])

    if missing_hair:
        res.warn("Character model lacks hairstyle geoset(s) %s that CharHairGeosets.dbc expects for race %d sex %d."
                 % (_ranges(missing_hair), race, sex))
    if missing_beard:
        res.warn("Character model lacks facial hair geoset(s) %s that CharacterFacialHairStyles.dbc expects "
                 "for race %d sex %d." % (_ranges(missing_beard), race, sex))


def _ranges(ids):
    ids = sorted(ids)
    if len(ids) > 24:
        return "%s ... %s (%d ids)" % (', '.join(map(str, ids[:10])), ', '.join(map(str, ids[-4:])), len(ids))
    return ', '.join(map(str, ids))


# ---------------------------------------------------------------------------------------------------- main

def check_m2_bytes(data, game_path='', exists=None, read_dbc=None, local_dirs=(), sibling_names=(),
                   classic=True):
    """Lint one M2.

    data         file bytes
    game_path    internal path (used for the character checks and for the .skin lookup)
    exists(p)    -> bool, is `p` (backslash game path) in the client archives; None = skip the archive lookup
    read_dbc(p)  -> bytes|None, reads 'DBFilesClient\\X.dbc' through the mount order; None = skip DBC checks
    local_dirs   folders that also count as "next to the exported file" for hardcoded textures
    sibling_names  file names found next to the exported model (to spot .skin/.anim leftovers)
    """
    res = LintResult()
    size = len(data)

    if size < 8:
        res.error("File is too small (%d bytes) to be an M2." % size)
        return res
    magic = data[:4]
    if magic == b'MD21':
        res.error("Chunked M2 (MD21, Legion+) - the 1.12 client only reads the flat MD20 layout.")
        return res
    if magic != b'MD20':
        res.error("Not an M2 file: magic is %r, expected b'MD20'." % magic)
        return res
    version = struct.unpack_from('<I', data, 4)[0]

    if classic and version not in (256, 257):
        if version in (260, 261, 262, 263):
            res.error("M2 version %d (TBC): the 1.12 client reads only v256/v257 models." % version)
        elif version >= 264:
            res.error("M2 version %d (WotLK or later): the 1.12 client reads only v256/v257 models. "
                      "Set the scene Client version to Classic before exporting." % version)
            # the WotLK layout is different: still flag the WotLK-only markers we can find at their offsets
            hdr, _hsz = parse_header(data, False)
            if hdr.get('global_flags', 0) & GLOBAL_FLAG_TEXTURE_COMBINER:
                res.error("Global flag 0x08 (texture combiner) is set - WotLK only, 1.12 ignores or misreads it.")
            if hdr.get('num_skin_profiles', 0):
                res.error("The model uses %d external .skin profile(s) - 1.12 expects skin views embedded in "
                          "the .m2." % hdr['num_skin_profiles'])
        else:
            res.error("Unsupported M2 version %d for a 1.12 model (expected 256 or 257)." % version)
        return res

    hdr, hsize = parse_header(data, True)
    if size < hsize:
        res.error("File (%d bytes) is shorter than the v%d header (%d bytes)." % (size, version, hsize))
        return res

    flags = hdr['global_flags']
    if flags & GLOBAL_FLAG_TEXTURE_COMBINER:
        res.error("Global flag 0x08 (texture combiner) is set - WotLK only, the 1.12 client misreads it.")

    # ---- every M2Array in bounds
    arrays_ok = True
    for name, kind, sz in _header_fields(True):
        if kind != 'a':
            continue
        n, ofs = hdr[name]
        if n == 0:
            continue
        if ofs < hsize or ofs > size or ofs + n * sz > size:
            res.error("Header array '%s' (count %d, offset 0x%X) points outside the file (%d bytes)."
                      % (name, n, ofs, size))
            arrays_ok = False
    if not arrays_ok:
        # later checks index into these arrays: stop at structure errors
        return res

    # ---- name
    n_name, o_name = hdr['name']
    if n_name and data[o_name + n_name - 1:o_name + n_name] != b'\0':
        res.warn("Model name string is not NUL-terminated.")

    # ---- animations
    n_seq, o_seq = hdr['sequences']
    seq_ids = []
    seq_size = 68
    for i in range(n_seq):
        if o_seq + (i + 1) * seq_size > size:
            res.error("Animation sequence table is truncated.")
            break
        sid, var, t0, t1, _ms, sflags = struct.unpack_from('<HHIIfI', data, o_seq + i * seq_size)
        seq_ids.append(sid)
        if t1 < t0:
            res.warn("Sequence %d (anim %d) ends (%d) before it starts (%d)." % (i, sid, t1, t0))
    if read_dbc is not None and seq_ids:
        d = _read_dbc(read_dbc('DBFilesClient\\AnimationData.dbc'))
        if d:
            known = set(r[0] for r in d[1])
            unknown = sorted(set(s for s in seq_ids if s not in known))
            if unknown:
                res.warn("Animation id(s) %s are not in AnimationData.dbc (the client will not play them by name)."
                         % ', '.join(map(str, unknown)))
        else:
            res.info("AnimationData.dbc not readable: animation id check skipped.")

    # ---- bones
    n_bones = hdr['bones'][0]
    if n_bones > HARD_MAX_BONES:
        res.error("Model has %d bones; the 1.12 limit is %d." % (n_bones, HARD_MAX_BONES))
    elif n_bones > STOCK_MAX_BONES:
        res.warn("Model has %d bones; the largest stock 1.12 model has %d." % (n_bones, STOCK_MAX_BONES))
    n_pal = hdr['bone_lookup_table'][0]
    pal = []
    if n_pal:
        pal = list(struct.unpack_from('<%dH' % n_pal, data, hdr['bone_lookup_table'][1]))
        bad = [p for p in pal if p >= n_bones]
        if bad:
            res.error("Bone lookup table references bone %d but the model has only %d bones (%d bad entries)."
                      % (bad[0], n_bones, len(bad)))

    # ---- vertices
    n_vert, o_vert = hdr['vertices']
    if n_vert > 65535:
        res.error("Model has %d vertices; 1.12 indexes vertices with u16 (max 65535)." % n_vert)
    verts = None
    if n_vert and np is not None:
        verts = np.frombuffer(data, np.uint8, n_vert * 48, o_vert).reshape(n_vert, 48)
        wsum = verts[:, 12:16].astype(np.int32).sum(axis=1)
        badw = np.nonzero(np.abs(wsum - 255) > WEIGHT_SUM_TOLERANCE)[0]      # 252..254 = rounding of 4 weights
        if len(badw):
            res.error("%d vertice(s) have bone weights that do not add up to 255 (first: vertex %d sums to %d)."
                      % (len(badw), int(badw[0]), int(wsum[badw[0]])))

    # ---- textures
    n_tex, o_tex = hdr['textures']
    tex_info = []
    for i in range(n_tex):
        ttype, tflags, nl, ol = struct.unpack_from('<IIII', data, o_tex + 16 * i)
        name = ''
        if nl:
            if ol + nl > size or ol < hsize:
                res.error("Texture %d: filename (offset 0x%X, %d bytes) points outside the file." % (i, ol, nl))
            else:
                name = _cstr_at(data, ol, nl)
        tex_info.append((ttype, tflags, name))
        if ttype == 0:
            if not name:
                res.warn("Texture %d is hardcoded (type 0) but has no file name." % i)
                continue
            if not name.lower().endswith('.blp'):
                res.warn("Texture %d '%s' is not a .blp - the 1.12 client only loads BLP." % (i, name))
            rel = _norm(name)
            found = bool(exists(rel)) if exists is not None else False
            if not found:
                for d in local_dirs:
                    if d and (os.path.isfile(os.path.join(d, rel)) or os.path.isfile(os.path.join(d, os.path.basename(rel)))):
                        found = True
                        break
            if not found and (exists is not None or local_dirs):
                res.warn("Texture %d '%s' is hardcoded but exists neither in the client archives nor next to the "
                         "exported file (it will render untextured)." % (i, name))

    n_tl, o_tl = hdr['texture_lookup_table']
    tex_lookup = list(struct.unpack_from('<%dH' % n_tl, data, o_tl)) if n_tl else []
    badtl = [t for t in tex_lookup if t >= n_tex]
    if badtl:
        res.error("Texture lookup table references texture %d but the model has only %d textures." % (badtl[0], n_tex))

    # ---- skin views
    n_views, o_views = hdr['skin_profiles']
    if n_views == 0:
        res.error("Model has no skin view; the 1.12 client needs at least one (embedded) view.")
    for vi in range(n_views):
        _check_view(res, data, hdr, vi, o_views + 44 * vi, verts, n_vert, n_pal, pal, tex_lookup, n_tex, size)

    # ---- character geosets
    if _CHAR_RE.match(_norm(game_path or '')) and n_views:
        geosets = _geosets(data, o_views)
        if geosets is not None:
            _check_character_geosets(res, geosets, game_path, read_dbc)

    # ---- WotLK leftovers next to the file
    leftovers = sorted(n for n in sibling_names if re.search(r'\d\d\.skin$|\.anim$', n, re.I))
    if leftovers:
        res.warn("WotLK-only sibling file(s) next to the model are ignored by 1.12: %s" % ', '.join(leftovers[:6]))

    res.info("M2 v%d: %d vertices, %d bones, %d view(s), %d textures, %d animations." % (
        version, n_vert, n_bones, n_views, n_tex, n_seq))
    return res


def _geosets(data, o_views):
    try:
        n_sub, o_sub = struct.unpack_from('<II', data, o_views + 0x18)
        return set(struct.unpack_from('<H', data, o_sub + 32 * i)[0] for i in range(n_sub))
    except struct.error:
        return None


def _check_view(res, data, hdr, vi, base, verts, n_vert, n_pal, pal, tex_lookup, n_tex, size):
    tag = "View %d: " % vi
    arrs = {}
    for k, name in enumerate(('indices', 'triangles', 'properties', 'submeshes', 'batches')):
        n, ofs = struct.unpack_from('<II', data, base + 8 * k)
        esz = {'indices': 2, 'triangles': 2, 'properties': 4, 'submeshes': 32, 'batches': 24}[name]
        if n and (ofs > size or ofs + n * esz > size):
            res.error(tag + "%s array (count %d, offset 0x%X) points outside the file." % (name, n, ofs))
            return
        arrs[name] = (n, ofs)
    bone_count_max = struct.unpack_from('<I', data, base + 40)[0]
    if vi == 0 and bone_count_max != VANILLA_BONE_COUNT_MAX:      # LOD views carry 75/53/21
        res.info(tag + "boneCountMax is %d; every stock 1.12 model uses %d (custom models may use other values "
                 "and work, so this is informational)." % (bone_count_max, VANILLA_BONE_COUNT_MAX))

    n_idx, o_idx = arrs['indices']
    n_tri, o_tri = arrs['triangles']
    n_sub, o_sub = arrs['submeshes']
    n_bat, o_bat = arrs['batches']

    if n_idx > 65535:
        res.error(tag + "%d vertex indices; submesh vertex starts are u16 (max 65535)." % n_idx)
    indices = np.frombuffer(data, np.uint16, n_idx, o_idx) if (np is not None and n_idx) else []
    if np is not None and n_idx and n_vert:
        over = np.nonzero(indices >= n_vert)[0]
        if len(over):
            res.error(tag + "vertex index list references vertex %d but the model has %d vertices."
                      % (int(indices[over[0]]), n_vert))
    if n_tri % 3:
        res.error(tag + "triangle index count %d is not a multiple of 3." % n_tri)
    if np is not None and n_tri and n_idx:
        tris = np.frombuffer(data, np.uint16, n_tri, o_tri)
        over = np.nonzero(tris >= n_idx)[0]
        if len(over):
            res.error(tag + "triangle list references index %d but the vertex index list has %d entries."
                      % (int(tris[over[0]]), n_idx))

    # submeshes
    subs = []
    expected, contiguous = 0, True
    for s in range(n_sub):
        (sid, level, vstart, vcount, istart, icount, bcount, bstart,
         _infl, _cb) = struct.unpack_from('<HHHHHHHHHH', data, o_sub + 32 * s)
        subs.append((sid, vstart, vcount, bcount, bstart))
        start = istart + (level << 16)
        if vstart + vcount > n_idx:
            res.error(tag + "submesh %d (id %d) vertex range %d..%d is outside the %d vertex indices."
                      % (s, sid, vstart, vstart + vcount, n_idx))
        if start + icount > n_tri:
            res.error(tag + "submesh %d (id %d) triangle range %d..%d is outside the %d triangle indices%s."
                      % (s, sid, start, start + icount, n_tri,
                         " (level high bits = %d)" % level if n_tri > 65535 else ""))
        if contiguous:
            if expected > 65535 and level == 0:
                res.error(tag + "submesh %d (id %d) starts at triangle index %d (> 65535) but its level (high "
                          "16 bits) is 0 - the client would read from the wrong place." % (s, sid, expected))
            if start != expected:
                contiguous = False
            expected = start + icount
        if bcount > HARD_MAX_SUBMESH_BONES:
            res.error(tag + "submesh %d (id %d) has %d bones; max %d." % (s, sid, bcount, HARD_MAX_SUBMESH_BONES))
        elif bcount > STOCK_MAX_SUBMESH_BONES:
            res.warn(tag + "submesh %d (id %d) has %d bones; the largest stock 1.12 submesh has %d."
                     % (s, sid, bcount, STOCK_MAX_SUBMESH_BONES))
        if bstart + bcount > n_pal:
            res.error(tag + "submesh %d (id %d) bone palette %d..%d is outside the bone lookup table (%d)."
                      % (s, sid, bstart, bstart + bcount, n_pal))

    # per-vertex bone indices address the submesh palette
    if verts is not None and np is not None and len(indices):
        bad_total, first = 0, None
        for s, (sid, vstart, vcount, bcount, bstart) in enumerate(subs):
            if vcount == 0 or vstart + vcount > len(indices):
                continue
            gv = indices[vstart:vstart + vcount].astype(np.int64)
            gv = gv[gv < n_vert]
            w = verts[gv, 12:16]
            # the per-view `properties` array holds the bone indices of THAT view's palette (view 0 = vertex copy)
            if arrs['properties'][0] == n_idx:
                props = np.frombuffer(data, np.uint8, n_idx * 4, arrs['properties'][1]).reshape(n_idx, 4)
                bi = props[vstart:vstart + vcount][indices[vstart:vstart + vcount] < n_vert].astype(np.int32)
            else:
                bi = verts[gv, 16:20].astype(np.int32)
            bad = (w > 0) & (bi >= bcount)
            nb = int(bad.any(axis=1).sum())
            if nb:
                bad_total += nb
                if first is None:
                    r = int(np.nonzero(bad.any(axis=1))[0][0])
                    c = int(np.nonzero(bad[r])[0][0])
                    first = (int(gv[r]), int(bi[r, c]), s, sid, bcount)
        if bad_total:
            res.error(tag + "%d vertice(s) use a bone index outside their submesh's bone palette (first: vertex %d "
                      "uses index %d, submesh %d id %d has %d bones)." % ((bad_total,) + first))

    # batches
    n_mat = hdr['materials'][0]
    n_col = hdr['colors'][0]
    n_tu = hdr['tex_unit_lookup_table'][0]
    n_tr = hdr['transparency_lookup_table'][0]
    n_tt = hdr['texture_transforms_lookup_table'][0]
    for b in range(n_bat):
        (fl, prio, shader, sidx, geo, col, mat, layer, tcount, tcombo, tcoord, tweight,
         ttrans) = struct.unpack_from('<BbHHHhHHHHHHH', data, o_bat + 24 * b)
        if sidx >= n_sub:
            res.error(tag + "batch %d references submesh %d but there are only %d." % (b, sidx, n_sub))
        if tcount and tcombo + tcount > len(tex_lookup):
            res.error(tag + "batch %d texture combo %d+%d is outside the texture lookup table (%d)."
                      % (b, tcombo, tcount, len(tex_lookup)))
        if mat >= n_mat:
            res.error(tag + "batch %d references render flag/material %d but there are only %d." % (b, mat, n_mat))
        if col != -1 and col >= n_col:
            res.error(tag + "batch %d references colour %d but there are only %d." % (b, col, n_col))
        if n_tu and tcoord >= n_tu:
            res.error(tag + "batch %d texture-unit lookup %d is outside the table (%d)." % (b, tcoord, n_tu))
        if n_tr and tweight >= n_tr:
            res.error(tag + "batch %d transparency lookup %d is outside the table (%d)." % (b, tweight, n_tr))
        if n_tt and ttrans != 0xFFFF and ttrans >= n_tt:
            res.error(tag + "batch %d texture-transform lookup %d is outside the table (%d)." % (b, ttrans, n_tt))


# ---------------------------------------------------------------------------------------------------- Blender glue

def guess_game_path(filepath, fallback=''):
    """Internal path of an exported/standalone file: everything below the first 'Character' / 'Creature' / ...
    root folder, else the scene game path."""
    parts = os.path.normpath(filepath).split(os.sep)
    for i, p in enumerate(parts):
        if p.lower() in ('character', 'creature', 'world', 'item', 'spells', 'environments', 'interface'):
            return '\\'.join(parts[i:])
    return fallback or os.path.basename(filepath)


def lint_file(filepath, game_path='', classic=True):
    """Run the lint on a file on disk using the loaded game data (when available)."""
    with open(filepath, 'rb') as f:
        data = f.read()
    exists = read_dbc = None
    local = [os.path.dirname(filepath)]
    try:
        from ..utils.misc import load_game_data
        gd = load_game_data()

        def exists(p, _gd=gd):
            return bool(_gd.has_file(p)[0])

        def read_dbc(p, _gd=gd):
            try:
                return _gd.read_file(p, no_exc=True)[0]
            except Exception:
                return None
    except Exception:
        pass
    try:
        from ..ui.preferences import get_project_preferences
        pp = get_project_preferences()
        local += [pp.export_dir_path, pp.cache_dir_path]
    except Exception:
        pass
    siblings = []
    try:
        stem = os.path.splitext(os.path.basename(filepath))[0].lower()
        siblings = [n for n in os.listdir(os.path.dirname(filepath)) if n.lower().startswith(stem)
                    and n.lower() != os.path.basename(filepath).lower()]
    except OSError:
        pass
    return check_m2_bytes(data, game_path or guess_game_path(filepath), exists, read_dbc, local, siblings, classic)


_MAX_POPUP_LINES = 40


def show_popup(res, title="M2 Classic (1.12) lint"):
    lines = res.report_lines()
    if not lines or bpy is None:
        return
    shown = lines[:_MAX_POPUP_LINES]
    if len(lines) > _MAX_POPUP_LINES:
        shown.append("... %d more line(s) - see the Info log." % (len(lines) - _MAX_POPUP_LINES))

    def draw(menu, _context):
        col = menu.layout.column()
        for line in shown:
            text = line
            while len(text) > 110:
                col.label(text=text[:110])
                text = '    ' + text[110:]
            col.label(text=text)

    try:
        bpy.context.window_manager.popup_menu(draw, title=title, icon='ERROR' if (res.errors or res.warnings) else 'INFO')
    except Exception:
        pass


def lint_after_export(operator, filepath, version):
    """Called by the M2 export operators after the file is written. Only acts for Classic scenes. Never raises.
    Returns the LintResult (or None). Errors are REPORTED, the exported file is kept (the user decides)."""
    try:
        from ..ui.deploy_panel import remember_export      # 'Send to test client' offers this file first
        remember_export(filepath)
    except Exception:
        pass
    try:
        from ..pywowlib import WoWVersions
        if int(version) != WoWVersions.CLASSIC:
            return None
        game_path = ''
        try:
            game_path = bpy.context.scene.wow_scene.game_path
        except Exception:
            pass
        res = lint_file(filepath, game_path)
    except Exception as e:                            # lint must never break an export
        operator.report({'WARNING'}, "M2 Classic lint could not run: %s" % e)
        return None
    # errors are reported as WARNING-level Info lines tagged ERROR: the file is already written, and an ERROR report
    # would make scripted callers of the export operator raise
    for m in res.errors:
        operator.report({'WARNING'}, "M2 1.12 ERROR: " + m)
    for m in res.warnings:
        operator.report({'WARNING'}, "M2 1.12: " + m)
    if not res.errors and not res.warnings:
        operator.report({'INFO'}, "M2 1.12 check passed: " + (res.infos[-1] if res.infos else ''))
    show_popup(res)
    return res


if bpy is not None:
    from bpy.props import StringProperty
    from bpy_extras.io_utils import ImportHelper

    class WBS_OT_check_m2_classic(bpy.types.Operator, ImportHelper):
        """Validate an .m2 file for the 1.12 client (versions, limits, bones, textures, geosets)"""
        bl_idname = 'wbs.check_m2_classic'
        bl_label = 'Check M2 for 1.12'
        bl_options = {'REGISTER'}

        filename_ext = '.m2'
        filter_glob: StringProperty(default='*.m2', options={'HIDDEN'})

        def execute(self, context):
            try:
                res = lint_file(self.filepath, getattr(context.scene.wow_scene, 'game_path', ''))
            except Exception as e:
                self.report({'ERROR'}, "Cannot check %s: %s" % (self.filepath, e))
                return {'CANCELLED'}
            for m in res.errors:
                self.report({'WARNING'}, 'ERROR: ' + m)
            for m in res.warnings:
                self.report({'WARNING'}, m)
            self.report({'INFO'}, "%s: %d error(s), %d warning(s)" % (os.path.basename(self.filepath),
                                                                      len(res.errors), len(res.warnings)))
            show_popup(res)
            return {'FINISHED'}

    def _menu_func(self, _context):
        self.layout.operator(WBS_OT_check_m2_classic.bl_idname, text='Check M2 for 1.12')

    def register():
        bpy.types.TOPBAR_MT_file_export.append(_menu_func)

    def unregister():
        try:
            bpy.types.TOPBAR_MT_file_export.remove(_menu_func)
        except Exception:
            pass
