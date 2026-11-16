# Everwood Classic fork: geometry-only readers for M2 (v256 vanilla, v260-264 TBC/WotLK) and WMO (root +
# groups), plus a small numpy software rasterizer for the model browser preview. No bpy here.
#
# read_m2(data, read_file)  -> Mesh   (read_file(path) -> bytes|None, used for the WotLK .skin)
# read_wmo(data, read_file, path) -> Mesh
# render(mesh, textures, size, yaw, pitch) -> (size, size, 4) uint8 RGBA
#
# A Mesh holds world-space vertices, per-vertex UVs, triangles and, per triangle, a "texture key" naming
# which texture slot it samples. The caller resolves keys to decoded images (dict key -> RGBA array).

import struct
import numpy as np


class Mesh:
    def __init__(self):
        self.verts = np.zeros((0, 3), np.float32)
        self.uvs = np.zeros((0, 2), np.float32)
        self.normals = None         # optional (N, 3) per-vertex normals for smooth shading
        self.tris = np.zeros((0, 3), np.int64)
        self.tri_key = []           # per triangle: texture slot key (int for M2 texture index, str for WMO)
        self.slots = []             # M2: list of dict(index, type, flags, filename) ; WMO: texture filenames
        self.kind = ''
        self.version = 0
        self.geosets = []           # M2: every geoset id the model has


def _arr(data, off):
    return struct.unpack_from('<II', data, off)


def _cstr(data, n, o):
    return data[o:o + n].split(b'\0', 1)[0].decode('latin-1')


# ---------------------------------------------------------------------------------------------------- M2

def default_geosets(ids, is_character):
    """Character models stack every hairstyle / beard / face / gear piece: keep one per group - id 0 plus the
    lowest id present in every other group (x01 when the model has it, else e.g. 302 for an ogre face)."""
    ids = set(ids)
    if not is_character:
        return ids
    keep = {0} if 0 in ids else set()
    groups = {}
    for g in ids:
        if g and g // 100 in BODY_GROUPS:
            groups.setdefault(g // 100, []).append(g)
    for members in groups.values():
        keep.add(min(members))
    return keep


# Character geoset groups that make up the bare body: 0 hair/scalp, 1-3 facial, 4 hands, 5 feet, 7 ears,
# 13 legs. Everything else is gear (8 sleeves, 9 leg cuffs, 10 chest, 11 pants, 12 tabard, 15 cloak, 18 belt)
# or optional extras (6 tail, 17 eye glow) and stays hidden in the preview.
BODY_GROUPS = {0, 1, 2, 3, 4, 5, 7, 13}


def read_m2(data, read_file=None, path=''):
    if data[:4] != b'MD20':
        raise ValueError("not an MD20 M2 (MD21/legion files are not supported by the preview)")
    ver = struct.unpack_from('<I', data, 4)[0]
    m = Mesh()
    m.kind, m.version = 'M2', ver
    vanilla = ver <= 256
    legacy = ver < 264      # <= TBC: extra playable_animation_lookup array and EMBEDDED skin views (an M2Array)
    o_verts, o_views, o_tex, o_texlookup = (0x44, 0x4C, 0x5C, 0x94) if legacy else (0x3C, 0x44, 0x50, 0x80)

    n_v, o_v = _arr(data, o_verts)
    raw = np.frombuffer(data, np.uint8, n_v * 48, o_v).reshape(n_v, 48)
    m.verts = raw[:, 0:12].copy().view(np.float32).reshape(n_v, 3)
    m.uvs = raw[:, 32:40].copy().view(np.float32).reshape(n_v, 2)
    m.normals = raw[:, 20:32].copy().view(np.float32).reshape(n_v, 3)

    n_tex, o_tex = _arr(data, o_tex)
    for i in range(n_tex):
        ttype, tflags, nl, ol = struct.unpack_from('<IIII', data, o_tex + 16 * i)
        m.slots.append(dict(index=i, type=ttype, flags=tflags, filename=_cstr(data, nl, ol) if nl else ''))
    n_tl, o_tl = _arr(data, o_texlookup)
    tex_lookup = list(struct.unpack_from('<%dH' % n_tl, data, o_tl)) if n_tl else []

    # skin profile 0: embedded (<= 263) or <name>00.skin (>= 264)
    if legacy:
        n_views, o_view = _arr(data, o_views)
        if not n_views:
            raise ValueError("M2 has no skin profiles")
        sk, base, sub_size = data, o_view, 32 if vanilla else 48
    else:
        sk = read_file(path[:-3] + '00.skin') if read_file else None
        if not sk or sk[:4] != b'SKIN':
            raise ValueError("missing %s00.skin" % path[:-3])
        base, sub_size = 4, 48
    n_idx, o_idx = _arr(sk, base)
    n_tri, o_tri = _arr(sk, base + 8)
    n_sub, o_sub = _arr(sk, base + 24)
    n_bat, o_bat = _arr(sk, base + 32)
    indices = np.frombuffer(sk, np.uint16, n_idx, o_idx).astype(np.int64)
    tri_idx = np.frombuffer(sk, np.uint16, n_tri, o_tri).astype(np.int64)

    # first texture of the first batch of each submesh
    sub_tex = {}
    for b in range(n_bat):
        _fl, _pr, _sh, sub, _geo, _col, _mat, _lay, tcount, tcombo = struct.unpack_from('<BbHHHhHHHH', sk, o_bat + 24 * b)
        if sub not in sub_tex and tcount and tcombo < len(tex_lookup):
            sub_tex[sub] = tex_lookup[tcombo]

    is_char = path.lower().replace('/', '\\').startswith('character\\')
    subs = [struct.unpack_from('<HHHHHH', sk, o_sub + sub_size * i) for i in range(n_sub)]
    m.geosets = sorted(set(x[0] for x in subs))
    show = default_geosets(m.geosets, is_char)
    tris, keys = [], []
    for s, (geo, level, _vs, _vc, istart, icount) in enumerate(subs):
        if geo not in show:
            continue
        start = istart + (level << 16)       # big models overflow the u16 index start into `level`
        t = tri_idx[start:start + icount]
        t = t[:len(t) // 3 * 3].reshape(-1, 3)
        if not len(t):
            continue
        tris.append(indices[np.clip(t, 0, len(indices) - 1)])
        keys.extend([sub_tex.get(s, -1)] * len(t))
    if tris:
        m.tris = np.concatenate(tris)
        m.tri_key = keys
    return m


# --------------------------------------------------------------------------------------------------- WMO

def _chunks(data, start=0, end=None):
    end = len(data) if end is None else end
    o = start
    while o + 8 <= end:
        cid = data[o:o + 4][::-1].decode('latin-1')
        size = struct.unpack_from('<I', data, o + 4)[0]
        yield cid, o + 8, size
        o += 8 + size


def read_wmo(data, read_file, path, max_tris=60000):
    m = Mesh()
    m.kind = 'WMO'
    motx, momt, n_groups = b'', [], 0
    for cid, o, size in _chunks(data):
        if cid == 'MOHD':
            n_groups = struct.unpack_from('<I', data, o + 4)[0]
        elif cid == 'MOTX':
            motx = data[o:o + size]
        elif cid == 'MOMT':
            for i in range(size // 64):
                tex1_ofs = struct.unpack_from('<I', data, o + 64 * i + 12)[0]
                momt.append(motx[tex1_ofs:].split(b'\0', 1)[0].decode('latin-1') if tex1_ofs < len(motx) else '')
    m.slots = momt

    verts, uvs, nrms, tris, keys = [], [], [], [], []
    vbase = 0
    for g in range(n_groups):
        gd = read_file('%s_%03d.wmo' % (path[:-4], g))
        if not gd:
            continue
        mogp = next(((o, s) for cid, o, s in _chunks(gd) if cid == 'MOGP'), None)
        if not mogp:
            continue
        o, s = mogp
        mopy = movi = movt = motv = monr = None
        for cid, co, cs in _chunks(gd, o + 68, o + s):
            if cid == 'MOPY' and mopy is None:
                mopy = np.frombuffer(gd, np.uint8, cs, co).reshape(-1, 2)
            elif cid == 'MOVI' and movi is None:
                movi = np.frombuffer(gd, np.uint16, cs // 2, co).astype(np.int64)
            elif cid == 'MOVT' and movt is None:
                movt = np.frombuffer(gd, np.float32, cs // 4, co).reshape(-1, 3)
            elif cid == 'MONR' and monr is None:
                monr = np.frombuffer(gd, np.float32, cs // 4, co).reshape(-1, 3)
            elif cid == 'MOTV' and motv is None:
                motv = np.frombuffer(gd, np.float32, cs // 4, co).reshape(-1, 2)
        if movi is None or movt is None:
            continue
        t = movi[:len(movi) // 3 * 3].reshape(-1, 3)
        mat = mopy[:len(t), 1] if mopy is not None and len(mopy) >= len(t) else np.zeros(len(t), np.uint8)
        keep = mat != 0xFF                                       # 0xFF = collision-only triangle
        t, mat = t[keep], mat[keep]
        verts.append(movt)
        uvs.append(motv if motv is not None and len(motv) == len(movt) else np.zeros((len(movt), 2), np.float32))
        nrms.append(monr if monr is not None and len(monr) == len(movt) else np.zeros((len(movt), 3), np.float32))
        tris.append(t + vbase)
        keys.extend(int(x) for x in mat)
        vbase += len(movt)
    if verts:
        m.verts = np.concatenate(verts)
        m.uvs = np.concatenate(uvs)
        m.normals = np.concatenate(nrms)
        m.tris = np.concatenate(tris)
        m.tri_key = keys
        if len(m.tris) > max_tris:                               # keep previews of huge WMOs fast
            pick = np.sort(np.random.default_rng(0).choice(len(m.tris), max_tris, replace=False))
            m.tris = m.tris[pick]
            m.tri_key = [m.tri_key[i] for i in pick]
    return m


# ---------------------------------------------------------------------------------------------- raster
#
# Vectorized "sample splatting": every triangle is covered by ~SAMPLES_PER_PIXEL stratified sample points
# per screen pixel of its area (at least one), all samples of all triangles are shaded at once, and a
# z-buffer is resolved with one lexsort. No per-triangle Python loop, so a 25k-triangle character renders
# in a fraction of a second. A final 3x3 pass fills the rare pin-holes.

SAMPLES_PER_PIXEL = 3.0
MAX_SAMPLES = 2500000


def _halton(n, base):
    i = np.arange(1, n + 1, dtype=np.float64)
    out = np.zeros(n)
    f = 1.0
    while i.any():
        f /= base
        out += f * (i % base)
        i = np.floor(i / base)
    return out


def _vertex_normals(mesh):
    n = np.zeros(mesh.verts.shape, np.float64)
    v = mesh.verts.astype(np.float64)
    t = mesh.tris
    fn = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
    for k in range(3):
        np.add.at(n, t[:, k], fn)
    return n


def render(mesh, textures, size=256, yaw=35.0, pitch=15.0, background=(0, 0, 0, 0)):
    """textures: {tri_key: (H, W, 4) uint8}. Missing keys render a neutral grey."""
    bg = np.array(background, np.float32) / 255.0
    img = np.empty((size, size, 4), np.float32)
    img[:] = bg
    if not len(mesh.tris):
        return (img * 255).astype(np.uint8)

    tris = mesh.tris
    used = np.unique(tris)
    v = mesh.verts.astype(np.float64)
    cy, sy = np.cos(np.radians(yaw)), np.sin(np.radians(yaw))
    cp, sp = np.cos(np.radians(pitch)), np.sin(np.radians(pitch))
    # WoW: X forward, Y left, Z up. Camera orbits around Z (yaw) and tilts down (pitch).
    x1 = v[:, 0] * cy - v[:, 1] * sy
    y1 = v[:, 0] * sy + v[:, 1] * cy
    z1 = v[:, 2]
    depth = x1 * cp + z1 * sp                                    # larger = closer
    sxw, syw = -y1, -x1 * sp + z1 * cp
    lo = np.array([sxw[used].min(), syw[used].min()])
    hi = np.array([sxw[used].max(), syw[used].max()])
    scale = size * 0.9 / (max(hi - lo) or 1.0)
    mid = (lo + hi) / 2
    px = (sxw - mid[0]) * scale + size / 2
    py = size / 2 - (syw - mid[1]) * scale

    nrm = mesh.normals.astype(np.float64) if mesh.normals is not None and len(mesh.normals) == len(v) else None
    if nrm is None or not np.isfinite(nrm).all() or (np.abs(nrm).sum(axis=1) < 1e-6).mean() > 0.5:
        nrm = _vertex_normals(mesh)
    nrm /= (np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12)
    view_dir = np.array([cy * cp, -sy * cp, sp])
    light = view_dir * 0.7 + np.array([0.0, 0.0, 0.7])
    light /= np.linalg.norm(light)

    # samples per triangle from its screen area
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    area = 0.5 * np.abs((px[b] - px[a]) * (py[c] - py[a]) - (px[c] - px[a]) * (py[b] - py[a]))
    cnt = np.maximum(1, np.ceil(area * SAMPLES_PER_PIXEL)).astype(np.int64)
    total = int(cnt.sum())
    if total > MAX_SAMPLES:
        cnt = np.maximum(1, (cnt * (MAX_SAMPLES / total)).astype(np.int64))
        total = int(cnt.sum())
    tri_of = np.repeat(np.arange(len(tris)), cnt)
    r1, r2 = _halton(total, 2), _halton(total, 3)
    s1 = np.sqrt(r1)
    w0, w1, w2 = 1.0 - s1, s1 * (1.0 - r2), s1 * r2
    single = cnt[tri_of] == 1                                    # one-sample triangles use the centroid
    w0[single] = w1[single] = w2[single] = 1.0 / 3.0
    ia, ib, ic = a[tri_of], b[tri_of], c[tri_of]
    sx = w0 * px[ia] + w1 * px[ib] + w2 * px[ic]
    syy = w0 * py[ia] + w1 * py[ib] + w2 * py[ic]
    ix, iy = np.floor(sx).astype(np.int64), np.floor(syy).astype(np.int64)
    ok = (ix >= 0) & (ix < size) & (iy >= 0) & (iy < size)
    z = w0 * depth[ia] + w1 * depth[ib] + w2 * depth[ic]

    # colour: texture lookup per key group (alpha-tested), otherwise grey
    col = np.empty((total, 4), np.float32)
    col[:] = (0.62, 0.62, 0.62, 1.0)
    keys = list(mesh.tri_key) if len(mesh.tri_key) == len(tris) else [-1] * len(tris)
    uniq = list(dict.fromkeys(keys))
    code = {k: i for i, k in enumerate(uniq)}
    key_arr = np.array([code[k] for k in keys], dtype=np.int64)
    skey = key_arr[tri_of]
    for k in uniq:
        tex = textures.get(k)
        if tex is None:
            continue
        sel = skey == code[k]
        if not sel.any():
            continue
        u = w0[sel] * mesh.uvs[ia[sel], 0] + w1[sel] * mesh.uvs[ib[sel], 0] + w2[sel] * mesh.uvs[ic[sel], 0]
        vv = w0[sel] * mesh.uvs[ia[sel], 1] + w1[sel] * mesh.uvs[ib[sel], 1] + w2[sel] * mesh.uvs[ic[sel], 1]
        th, tw = tex.shape[:2]
        tx = (np.mod(u, 1.0) * tw).astype(np.int64).clip(0, tw - 1)
        ty = (np.mod(vv, 1.0) * th).astype(np.int64).clip(0, th - 1)
        col[sel] = tex[ty, tx].astype(np.float32) / 255.0
    ok &= col[:, 3] > 0.45                                        # alpha-tested cut-outs

    n_s = w0[:, None] * nrm[ia] + w1[:, None] * nrm[ib] + w2[:, None] * nrm[ic]
    n_s /= (np.linalg.norm(n_s, axis=1, keepdims=True) + 1e-12)
    shade = (0.38 + 0.62 * np.abs(n_s @ light)).astype(np.float32)

    ix, iy, z, col, shade = ix[ok], iy[ok], z[ok], col[ok], shade[ok]
    if len(ix):
        pix = iy * size + ix
        order = np.lexsort((z, pix))                             # per pixel, nearest sample last
        pix_s = pix[order]
        last = np.ones(len(pix_s), bool)
        last[:-1] = pix_s[1:] != pix_s[:-1]
        win = order[last]
        flat = img.reshape(-1, 4)
        flat[pix[win], :3] = col[win, :3] * shade[win, None]
        flat[pix[win], 3] = 1.0

    # fill isolated pin-holes: an empty pixel with >= 6 of 8 neighbours filled takes their mean
    filled = img[..., 3] > 0.5
    pad = np.pad(img, ((1, 1), (1, 1), (0, 0)))
    pf = np.pad(filled, 1).astype(np.float32)
    nsum = np.zeros((size, size, 3), np.float32)
    ncnt = np.zeros((size, size), np.float32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx or dy:
                w = pf[1 + dy:1 + dy + size, 1 + dx:1 + dx + size]
                ncnt += w
                nsum += pad[1 + dy:1 + dy + size, 1 + dx:1 + dx + size, :3] * w[..., None]
    hole = (~filled) & (ncnt >= 6)
    img[hole, :3] = nsum[hole] / ncnt[hole, None]
    img[hole, 3] = 1.0
    return (img.clip(0, 1) * 255).astype(np.uint8)
