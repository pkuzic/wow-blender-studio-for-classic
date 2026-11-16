# End-to-end modeller workflow across features: import a 1.12 character -> sculpt -> Safe Export operator ->
# the 1.12 checks run on the result and "Send to test client" offers the file -> the deploy plan targets the
# archive that wins for the model (planning only; nothing is written into the real client).
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import common

T = common.Test('workflow')
PATH = r"Character\Ogre\Female\OgreMage.m2"


def body(T):
    common.setup_project()
    common.new_scene('M2')
    common.import_game_model(PATH)
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH' and 'wbs_m2_vid' in o.data.attributes]
    T.check(len(meshes) > 10, 'imported %d meshes with vertex ids' % len(meshes))

    # "sculpt": push the biggest mesh out by 2 cm
    big = max(meshes, key=lambda o: len(o.data.vertices))
    for v in big.data.vertices:
        v.co.z += 0.02
    out = os.path.join(common.TMP, 'OgreMage_sculpt.m2')
    r = bpy.ops.wbs.m2_safe_export(filepath=out)
    T.check(r == {'FINISHED'} and os.path.isfile(out), 'Safe Export operator wrote %s' % os.path.basename(out))
    status = bpy.context.scene.get('wbs_char_status', '')
    T.check('OK' in status and 'vertices changed' in status, 'status says OK: %s' % status.splitlines()[:2])

    orig = common.module('utils.misc').load_game_data().read_file(PATH)[0]
    new = open(out, 'rb').read()
    T.check(len(new) == len(orig), 'same size as the original (%d bytes)' % len(orig))
    diff = sum(1 for a, b in zip(orig, new) if a != b)
    T.check(0 < diff < len(orig) // 10, '%d bytes differ (positions/normals of the moved vertices only)' % diff)

    T.check(bpy.context.window_manager.wbs_deploy.last_export == out,
            '"Send to test client" now offers the safe-exported file')

    L = common.module('m2.classic_lint_m2')
    res = L.lint_file(out, PATH)
    T.check(not res.errors, '1.12 checks: no errors on the safe export (%d warnings)' % len(res.warnings))

    # planning only, read-only (probe_write=False: never opens the real client for writing)
    D = common.module('utils.client_deploy')
    target, _order, notes, problem = D.plan(common.CLIENT, [(out, PATH)], probe_write=False)
    T.check(target and os.path.basename(target).lower() == 'patch-z.mpq' and not problem,
            'deploy would update the winning archive: %s (%s)' % (target and os.path.basename(target), problem or 'ok'))
    T.check(not any(n.startswith('WARNING') for n in notes), 'no higher-priority archive shadows it')


common.run(T, body)
