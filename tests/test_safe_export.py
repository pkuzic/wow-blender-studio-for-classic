# Safe export: unchanged import == original bytes; moving one mesh changes only those vertex positions.
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import numpy as np
import common

T = common.Test('safe_export')
GAME_PATH = r"Character\Ogre\Female\OgreMage.m2"


def body(T):
    common.setup_project()
    common.new_scene('M2')
    common.import_game_model(GAME_PATH)
    SE = common.module('m2.safe_export')

    meshes = SE.find_meshes(bpy.context)
    T.check(len(meshes) > 10, 'ogress imported: %d meshes with wbs_m2_vid' % len(meshes))
    me0 = meshes[0].data
    T.check('wbs_m2_ok' in me0.attributes and meshes[0].get('wbs_m2_nverts') == 31274,
            'vertex-id attributes + source props present (nverts=%s)' % meshes[0].get('wbs_m2_nverts'))

    from importlib import import_module
    load_game_data = import_module(common.ADDON + '.utils.misc').load_game_data
    orig = load_game_data().read_file(GAME_PATH, no_exc=True)[0]
    T.check(len(orig) > 1000000 and orig[:4] == b'MD20', 'original read from the client: %d bytes' % len(orig))

    # 1. unchanged -> byte-identical (both with and without the normals option)
    out1 = os.path.join(common.TMP, 'unchanged.m2')
    r = SE.safe_export(meshes, out1)
    T.check(r['ok'], 'unchanged export ok; errors=%s warnings=%s' % (r['errors'], r['warnings']))
    T.check(open(out1, 'rb').read() == orig,
            'unchanged import exports BYTE-IDENTICAL to the original (moved=%d)' % len(r['moved']))
    r = SE.safe_export(meshes, out1, update_normals=False)
    T.check(open(out1, 'rb').read() == orig, 'identical with Update normals off')

    # 2. move every vertex of ONE mesh by +0.1 on Z
    target = max(meshes, key=lambda o: len(o.data.vertices))
    nverts = len(target.data.vertices)
    vid = np.empty(nverts, np.int32)
    target.data.attributes['wbs_m2_vid'].data.foreach_get('value', vid)
    co = np.empty(nverts * 3, np.float32)
    target.data.vertices.foreach_get('co', co)
    co2 = co.reshape(-1, 3).copy()
    co2[:, 2] += 0.1
    target.data.vertices.foreach_set('co', co2.ravel())
    target.data.update()
    out2 = os.path.join(common.TMP, 'moved.m2')
    r = SE.safe_export(meshes, out2)
    T.check(r['ok'], 'moved export ok; warnings=%s' % r['warnings'])
    new = open(out2, 'rb').read()
    T.check(len(new) == len(orig), 'same file size (%d)' % len(new))
    vo, vn = SE.read_vertices(orig), SE.read_vertices(new)
    changed = np.nonzero(np.any(vo['pos'] != vn['pos'], axis=1))[0]
    T.check(sorted(changed.tolist()) == sorted(set(vid.tolist())),
            'exactly the %d vertex ids of the moved mesh changed (found %d)' % (len(set(vid.tolist())), len(changed)))
    dz = (vn['pos'][changed] - vo['pos'][changed])
    T.check(np.abs(dz[:, 2] - 0.1).max() < 1e-4 and np.abs(dz[:, :2]).max() < 1e-6,
            'each moved +0.1 on Z (max err %.2e)' % np.abs(dz[:, 2] - 0.1).max())
    # all bytes outside the touched vertex records identical
    n, off = SE.m2_vertex_block(orig)
    mask = np.ones(len(orig), bool)
    for v in changed:
        mask[off + 48 * v: off + 48 * v + 48] = False
    a = np.frombuffer(orig, np.uint8)
    b = np.frombuffer(new, np.uint8)
    T.check(np.array_equal(a[mask], b[mask]), 'every byte outside the touched vertex records is identical')
    rec = np.ones(48, bool)
    rec[0:12] = False
    rec[20:32] = False
    A = a[off:off + 48 * n].reshape(n, 48)[changed][:, rec]
    B = b[off:off + 48 * n].reshape(n, 48)[changed][:, rec]
    T.check(np.array_equal(A, B), 'inside the touched records only position and normal bytes differ')
    dots = (vo['nrm'][changed] * vn['nrm'][changed]).sum(axis=1)
    T.check(float(np.median(dots)) > 0.5,
            'recomputed normals agree with the originals (median dot %.3f)' % float(np.median(dots)))
    r = SE.safe_export(meshes, out2, update_normals=False)
    vn = SE.read_vertices(open(out2, 'rb').read())
    T.check(np.array_equal(vn['nrm'], vo['nrm']), 'Update normals off keeps every normal')

    # 3. new geometry is refused unless ignored
    import bmesh
    sel = meshes[1]
    bm = bmesh.new()
    bm.from_mesh(sel.data)
    bm.verts.new((0, 0, 5))
    bm.to_mesh(sel.data)
    bm.free()
    refused = os.path.join(common.TMP, 'refused.m2')
    r = SE.safe_export(meshes, refused)
    T.check(not r['ok'] and any('vertex id' in e for e in r['errors']) and not os.path.exists(refused),
            'new vertex -> refused with a clear report: %s' % r['errors'][:1])
    r = SE.safe_export(meshes, os.path.join(common.TMP, 'ignored.m2'), ignore_new=True)
    T.check(r['ok'], 'Ignore new vertices -> export goes through')

    # 4. a wrong original is refused
    r = SE.build_safe_m2(meshes, b'MD20' + struct.pack('<I', 256) + bytes(200))
    T.check(not r['ok'], 'garbage original refused')


common.run(T, body)
