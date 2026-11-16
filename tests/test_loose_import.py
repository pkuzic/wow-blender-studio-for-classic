# Import of a loose .m2 (File > Import > WoW M2) with NO WoW client configured, and again WITH the client.
# Needs G:\mangos\ogre_female_extract (OgreMage.m2 + .anim + textures); the test is skipped (info) without it.
import os
import sys
import glob
import shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import common

T = common.Test('loose_import')
SRC = r"G:\mangos\ogre_female_extract"


def stage():
    d = os.path.join(common.TMP, 'loose')
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    shutil.copy(os.path.join(SRC, 'model', 'OgreMage.m2'), d)
    for a in glob.glob(os.path.join(SRC, 'model', 'OgreMage*.anim')):
        shutil.copy(a, d)
    # textures next to the model: some as PNG, one only as BLP (exercises the BLP -> PNG conversion)
    for n in ('MonkeyOgressFaceLower.png', 'MonkeyOgressFaceUpper.png', 'MonkeyOgressNakedTorso.png'):
        p = os.path.join(SRC, 'png', n)
        if os.path.isfile(p):
            shutil.copy(p, d)
    p = os.path.join(SRC, 'blp', 'MonkeyOgressNakedPelvis.blp')
    if os.path.isfile(p):
        shutil.copy(p, d)
    return d


def summarize(tag):
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    arms = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']
    real = [i for i in bpy.data.images if i.wow_m2_texture.enabled and i.source == 'FILE' and i.has_data]
    T.check(len(meshes) > 10, '%s: %d mesh objects imported' % (tag, len(meshes)))
    T.check(len(arms) >= 1, '%s: armature present' % tag)
    T.info('%s: %d M2 textures, %d of them loaded from a real file' % (tag, sum(
        1 for i in bpy.data.images if i.wow_m2_texture.enabled), len(real)))
    for i in bpy.data.images:
        if i.wow_m2_texture.enabled:
            T.info('  image %r type=%s path=%r source=%s' % (i.name, i.wow_m2_texture.texture_type,
                                                         i.wow_m2_texture.path, i.source))
    return len(real)


def texture_lookup(d, cache_dir):
    # OgreMage only uses DBC (character-skin) textures, so test the loose texture lookup directly
    imp = common.module('m2.import_m2')
    names = ['textures\\MonkeyOgressFaceLower.blp', 'MonkeyOgressNakedPelvis.blp', 'nothere\\Missing.blp']
    res = imp._local_texture_map(d, names, cache_dir)
    T.check(names[0] in res and os.path.isfile(os.path.splitext(res[names[0]])[0] + '.png'), 'PNG next to the model found')
    T.check(names[1] in res and os.path.isfile(os.path.splitext(res[names[1]])[0] + '.png'),
            'BLP next to the model converted to PNG (%s)' % res.get(names[1]))
    T.check(names[2] not in res, 'missing texture left out (placeholder)')
    if names[1] in res:
        img = bpy.data.images.load(os.path.splitext(res[names[1]])[0] + '.png')
        T.check(img.size[0] > 0 and img.size[1] > 0, 'converted BLP PNG is a valid image %dx%d' % tuple(img.size))


def body(T):
    if not os.path.isfile(os.path.join(SRC, 'model', 'OgreMage.m2')):
        T.info('SKIPPED: %s not present' % SRC)
        return
    d = stage()
    m2 = os.path.join(d, 'OgreMage.m2')

    # 1) no client at all: project with an EMPTY wow path
    prefs = common.enable_addon()
    if not len(prefs.projects):
        bpy.ops.wbs.project_list_action('INVOKE_DEFAULT', action='ADD')
    pp = common.module('ui.preferences').get_project_preferences()
    pp.wow_path = ''
    pp.cache_dir_path = os.path.join(common.TMP, 'cache')
    os.makedirs(pp.cache_dir_path, exist_ok=True)
    common.new_scene('M2')
    err = None
    try:
        r = bpy.ops.import_mesh.m2(filepath=m2)
        T.check('FINISHED' in r, 'no client: bpy.ops.import_mesh.m2 -> %s' % r)
    except Exception as e:
        err = e
        T.check(False, 'no client: import raised %s' % str(e).strip().splitlines()[-1:])
    if not err:
        summarize('no client')
        T.check(len([i for i in bpy.data.images if i.name.startswith('DBC ')]) >= 1,
                'no client: DBC texture slots became placeholder images')
        texture_lookup(d, pp.cache_dir_path)

    # 2) the same file WITH the client still works (regular path)
    if os.path.isdir(common.CLIENT):
        pp.wow_path = common.CLIENT
        if hasattr(bpy, 'wow_game_data'):
            del bpy.wow_game_data
        common.new_scene('M2')
        try:
            r = bpy.ops.import_mesh.m2(filepath=m2)
            T.check('FINISHED' in r, 'with client: bpy.ops.import_mesh.m2 -> %s' % r)
            summarize('with client')
        except Exception as e:
            T.check(False, 'with client: import raised %s' % str(e).strip().splitlines()[-1:])
    else:
        T.info('client %s not found: skipped the with-client import' % common.CLIENT)


common.run(T, body)
