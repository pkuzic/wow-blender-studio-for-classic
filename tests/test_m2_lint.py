# 1.12 M2 lint: a stock model and a WBS-exported model pass; deliberately broken copies are caught with the right
# message; a real character model's geoset check behaves; a sample of stock models gives no errors.
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import common

T = common.Test('m2_lint')

MODEL = 'World\\Azeroth\\Elwynn\\PassiveDoodads\\Haystacks\\haystack01.m2'
CHAR = 'Character\\Human\\Male\\HumanMale.m2'


def body(T):
    from importlib import import_module as _im
    L = _im(common.ADDON + '.m2.classic_lint_m2')
    common.setup_project()
    common.new_scene('M2')
    misc = _im(common.ADDON + '.utils.misc')
    gd = misc.load_game_data()

    def exists(p):
        return bool(gd.has_file(p)[0])

    def read_dbc(p):
        try:
            return gd.read_file(p, no_exc=True)[0]
        except Exception:
            return None

    def lint(data, path=MODEL, local=()):
        return L.check_m2_bytes(data, path, exists, read_dbc, list(local), [])

    def has(msgs, *words):
        return any(all(w.lower() in m.lower() for w in words) for m in msgs)

    orig = gd.read_file(MODEL)[0]
    r = lint(orig)
    T.check(not r.errors and not r.warnings, 'stock haystack01.m2 (v256) passes clean: %s' % (r.errors + r.warnings))
    T.check(has(r.infos, 'M2 v256'), 'info line: ' + (r.infos[-1] if r.infos else ''))

    # ---- WBS export round trip (Classic)
    common.import_game_model(MODEL)
    out = os.path.join(common.TMP, 'export', MODEL)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    exp = _im(common.ADDON + '.m2.export_m2')
    exported = None
    try:
        exp.export_m2(0, out, False, True, 'X+', 1.0, True)
        with open(out, 'rb') as f:
            exported = f.read()
    except Exception as e:
        T.check(False, 'WBS Classic export of haystack01 works: %r' % e)
    if exported:
        ver = struct.unpack_from('<I', exported, 4)[0]
        T.check(ver == 256, 'WBS Classic export writes M2 v256 (got %d)' % ver)
        r = L.lint_file(out, MODEL)
        T.check(not r.errors, 'WBS-exported haystack01 has no lint errors: %s' % r.errors)
        for w in r.warnings:
            T.info('exported warning: ' + w)

        # operator wiring: the real export operator lints a Classic export and keeps the file
        out2 = os.path.join(common.TMP, 'export2', MODEL)
        os.makedirs(os.path.dirname(out2), exist_ok=True)
        try:
            res = bpy.ops.export_mesh.m2('EXEC_DEFAULT', filepath=out2)
            T.check('FINISHED' in res and os.path.isfile(out2), 'export operator finished and wrote the file: %s' % res)
        except Exception as e:
            T.check(False, 'export operator ran: %r' % e)
        try:
            res = bpy.ops.wbs.check_m2_classic('EXEC_DEFAULT', filepath=out)
            T.check('FINISHED' in res, 'standalone operator wbs.check_m2_classic runs: %s' % res)
        except Exception as e:
            T.check(False, 'standalone operator ran: %r' % e)

    hdr, hsize = L.parse_header(orig, True)

    # ---- broken copies
    # a. bad array offset
    b = bytearray(orig)
    ofs_pos = 0x44 + 4                                   # vertices.ofs
    struct.pack_into('<I', b, ofs_pos, len(b) + 4096)
    r = lint(bytes(b))
    T.check(has(r.errors, "'vertices'", 'outside the file'), 'bad vertex array offset caught: %s' % r.errors[:1])

    # b. bone index >= palette size
    b = bytearray(orig)
    n_v, o_v = hdr['vertices']
    for i in range(n_v):
        b[o_v + 48 * i + 12] = 255                       # weight 0 = 255
        b[o_v + 48 * i + 13:o_v + 48 * i + 16] = b'\0\0\0'
        b[o_v + 48 * i + 16] = 250                       # bone index 0 = 250
    # the view's per-vertex `properties` copy
    n_views, o_views = hdr['skin_profiles']
    n_pr, o_pr = struct.unpack_from('<II', orig, o_views + 16)
    for i in range(n_pr):
        b[o_pr + 4 * i] = 250
    r = lint(bytes(b))
    T.check(has(r.errors, 'bone index', 'palette'), 'vertex bone index beyond the submesh palette caught: %s' % r.errors[:1])

    # b2. weights not 255
    b = bytearray(orig)
    b[o_v + 12] = 1
    b[o_v + 13] = 1
    r = lint(bytes(b))
    T.check(has(r.errors, 'weights', '255'), 'bone weights not summing to 255 caught: %s' % r.errors[:1])

    # c. version 264 + texture combiner flag + external skin
    b = bytearray(orig)
    struct.pack_into('<I', b, 4, 264)
    struct.pack_into('<I', b, 0x10, struct.unpack_from('<I', orig, 0x10)[0] | 0x08)
    r = lint(bytes(b))
    T.check(has(r.errors, 'version 264'), 'M2 version 264 caught: %s' % r.errors[:1])
    T.check(has(r.errors, 'texture combiner'), 'global flag 0x08 caught')
    T.check(has(r.errors, 'external .skin'), 'external .skin profiles caught')
    b = bytearray(orig)
    struct.pack_into('<I', b, 0x10, struct.unpack_from('<I', orig, 0x10)[0] | 0x08)
    r = lint(bytes(b))
    T.check(has(r.errors, 'texture combiner'), 'global flag 0x08 caught on a v256 file too')
    b = bytearray(orig[:4] + b'MD21' + orig[8:])
    b = bytearray(b'MD21' + orig[4:])
    r = lint(bytes(b))
    T.check(has(r.errors, 'MD21', 'chunked'), 'chunked MD21 caught')

    # d. missing hardcoded texture
    n_t, o_t = hdr['textures']
    patched = None
    for i in range(n_t):
        ttype, tflags, nl, ol = struct.unpack_from('<IIII', orig, o_t + 16 * i)
        if ttype == 0 and nl > 6:
            b = bytearray(orig)
            b[ol:ol + nl - 1] = (b'zz_missing_' + b'q' * nl)[:nl - 1]
            b[ol + nl - 5:ol + nl - 1] = b'.blp'
            patched = bytes(b)
            break
    if patched is None:
        T.check(False, 'test model has a hardcoded texture to break')
    else:
        r = lint(patched)
        T.check(has(r.warnings, 'zz_missing_', 'hardcoded', 'archives'), 'missing hardcoded texture caught: %s' % r.warnings[:1])
        # ... unless it sits next to the exported file
        d = os.path.join(common.TMP, 'texdir')
        os.makedirs(d, exist_ok=True)
        name = (b'zz_missing_' + b'q' * nl)[:nl - 1]
        name = name[:-4] + b'.blp'
        with open(os.path.join(d, name.decode().split('\\')[-1]), 'wb') as f:
            f.write(b'BLP2')
        r = lint(patched, local=[d])
        T.check(not has(r.warnings, 'zz_missing_'), 'a texture found next to the exported file is accepted')

    # e. texture lookup index out of range
    b = bytearray(orig)
    n_tl, o_tl = hdr['texture_lookup_table']
    if n_tl:
        struct.pack_into('<H', b, o_tl, 99)
        r = lint(bytes(b))
        T.check(has(r.errors, 'texture lookup'), 'texture lookup index out of range caught: %s' % r.errors[:1])

    # f. too many bones / bone count max
    b = bytearray(orig)
    struct.pack_into('<I', b, 0x34, 300)
    r = lint(bytes(b))
    T.check(r.errors, 'impossible bone count is reported as an error: %s' % r.errors[:1])

    # g. animation id unknown to AnimationData.dbc
    b = bytearray(orig)
    n_s, o_s = hdr['sequences']
    if n_s:
        struct.pack_into('<H', b, o_s, 9999)
        r = lint(bytes(b))
        T.check(has(r.warnings, 'AnimationData.dbc', '9999'), 'unknown animation id caught: %s' % r.warnings[:1])

    # ---- real character model
    ch = gd.read_file(CHAR)[0]
    r = lint(ch, CHAR)
    T.check(not r.errors, 'stock HumanMale.m2 has no errors: %s' % r.errors[:2])
    for w in r.warnings + r.infos[:-1]:
        T.info('HumanMale: ' + w)
    T.check(all(('geoset' in w.lower() or 'dbc' in w.lower()) for w in r.warnings),
            'HumanMale warnings (if any) are geoset/DBC related only')
    # strip the hairstyle geosets (ids 1..18) -> the hairstyle warning must appear
    ch_h, _ = L.parse_header(ch, True)
    n_vw, o_vw = ch_h['skin_profiles']
    n_sub, o_sub = struct.unpack_from('<II', ch, o_vw + 0x18)
    b = bytearray(ch)
    for s in range(n_sub):
        gid = struct.unpack_from('<H', b, o_sub + 32 * s)[0]
        if 1 <= gid <= 18:
            struct.pack_into('<H', b, o_sub + 32 * s, 5000 + gid)
    r = lint(bytes(b), CHAR)
    T.check(has(r.warnings, 'hairstyle geoset'), 'missing hairstyle geosets reported: %s' % [w[:90] for w in r.warnings[:2]])

    # ---- sample of stock models: no false positives
    MPQ = _im(common.ADDON + '.pywowlib.archives.mpq').MPQFile
    mm = MPQ(os.path.join(common.CLIENT, 'Data', 'model.MPQ'), 0x100)
    names = [n for n in mm.namelist() if n.lower().endswith('.m2')]
    sample = names[::max(1, len(names) // 400)]
    bad = []
    for n in sample:
        try:
            data = mm.read(n.replace('/', '\\'))
        except Exception:
            continue
        if data[:4] != b'MD20' or struct.unpack_from('<I', data, 4)[0] != 256:
            continue
        rr = L.check_m2_bytes(data, n.replace('/', '\\'))
        if rr.errors:
            bad.append((n, rr.errors[0]))
    mm.close()
    T.check(not bad, 'stock model sample (%d files): no lint errors %s' % (len(sample), bad[:2]))


common.run(T, body)
