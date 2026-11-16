# Import sweep: a seeded random sample of patch-archive models (spread over folders and M2 versions) plus a fixed
# regression list are imported through the Model Browser's Import; every failure is a test failure, except models
# that are broken IN THE CLIENT (expected: the browser's UNREADABLE_MSG, or a WotLK-format model whose skin file
# is not in the client). Models of the regression list that the client does not have are skipped.
# Env: WBS_SWEEP_MAX (sample size, default 40), WBS_SWEEP_SEED (default 7).
import os
import sys
import time
import random
import struct
import collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import common

T = common.Test('import_sweep')

REGRESSION = (r"CREATURE\Serpent\SerpentRuby.m2; CREATURE\panda\Jadepandacub.M2; PARTICLES\LootFX.m2; "
              r"SPELLS\Enchantments\SkullBalls.m2; CREATURE\Flyingmachinecreature_vehicle\flyingmachinecreature_vehicle.m2; "
              r"world\expansion05\doodads\human\doodads\6hu_townhall_architect_scrollbarrel02.m2; "
              r"Interface\GLUES\MODELS\UI_Goblin\UI_Goblin.m2; Creature\Cupid\Cupid.m2; Creature\Ragnaros\Ragnaros.m2; "
              r"Character\Ogre\Female\OgreMage.m2; Creature\Brutallus\Brutallus.m2; "
              r"PARTICLES\BloodSpurts\BloodSpurtBlue.m2; SPELLS\Missile_Light.M2; "
              r"world\wmo\forever_port\buildings\draenei\fp_outland_draeni_hut_1\fp_outland_draeni_hut_1.wmo")


def norm(p):
    return p.replace('/', '\\').lower()


def body(T):
    pp = common.setup_project()
    MB = common.module('ui.model_browser')
    # the operator indexes in a background thread; the test wants the blocking build
    MB.build_index()
    gd = MB.load_game_data()
    index = MB.INDEX
    T.check(len(index['models']) > 100, 'index built: %d models, %d patch archives'
            % (len(index['models']), len(index['patch_archives'])))

    # sample: up to 2 models per (kind, M2 version, top folder) bucket, from the patch archives
    rng = random.Random(int(os.environ.get('WBS_SWEEP_SEED', '7')))
    models = [m for m in index['models'] if m[1] in index['patch_archives']]
    rng.shuffle(models)
    buckets = collections.defaultdict(list)
    for path, arch, kind in models:
        top = path.split('\\')[0].lower()
        if kind == 'M2':
            head = MB._read(gd, path)
            key = ('M2', 'unreadable' if not head or len(head) < 8 else 'v%d' % struct.unpack_from('<I', head, 4)[0], top)
        else:
            key = ('WMO', '', top)
        if len(buckets[key]) < 2:
            buckets[key].append((path, arch))
    sample = [(k, p) for k, v in sorted(buckets.items()) for p, a in v][:int(os.environ.get('WBS_SWEEP_MAX', '40'))]

    lookup = {norm(m[0]): m[0] for m in index['models']}
    absent = 0
    for extra in filter(None, (e.strip() for e in REGRESSION.split(';'))):
        real = lookup.get(norm(extra))
        if real:
            sample.append((('REGRESSION', '', ''), real))
        else:
            absent += 1
    T.info('sample: %d models (%d regression-list models are not in this client and were skipped)' % (len(sample), absent))

    ok = expected = bad = 0
    for key, path in sample:
        # every model gets a fresh scene; the previous one (and its orphaned collections/objects) is purged, so a
        # leftover collection of an earlier import (e.g. 'Set_$DefaultGlobal') can't leak into the next WMO import
        prev = bpy.context.scene
        bpy.ops.scene.new(type='NEW')
        bpy.context.scene.wow_scene.version = '0'
        if prev != bpy.context.scene and prev.name != 'Scene':
            for obj in list(prev.objects):
                bpy.data.objects.remove(obj)
            bpy.data.scenes.remove(prev)
            bpy.data.orphans_purge(do_recursive=True)
        t = time.time()
        try:
            MB.select_model(path)
            bpy.ops.wbs.browser_import()
            n = len([o for o in bpy.context.scene.objects if o.type in {'MESH', 'ARMATURE', 'EMPTY'}])
            ok += 1
            T.info('[OK]  %s %s (%d objects, %.1fs)' % (key, path, n, time.time() - t))
        except Exception as e:
            msg = ' '.join(str(e).split())
            if MB.UNREADABLE_MSG[:40] in msg or ('WotLK-format model' in msg and 'is not in the client' in msg):
                expected += 1
                T.info('[EXPECTED] broken in the client: %s' % path)
            else:
                bad += 1
                T.check(False, 'import of %s %s failed: %s' % (key, path, msg[-300:]))
    T.check(bad == 0, 'sweep done: %d imported, %d broken-in-client (expected), %d failed' % (ok, expected, bad))
    T.check(ok > 0, 'at least one model imported')


common.run(T, body)
