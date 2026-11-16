# Registration: enable -> disable -> enable is clean, the formerly broken operators are registered and work,
# and with NO project nothing in the UI raises "No active project" while redrawing.
import io
import os
import sys
import contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import common

T = common.Test('registration')

# (class name, bl_idname) of the three operators that used to share one bl_idname
OPERATORS = (
    ('SetDefaultTexture', 'wow_m2_texture.set_default_texture'),
    ('TexturePathDefaultButton', 'wow_m2_material.set_default_texture_path'),
    ('TexturePathDefaultButton', 'wow_m2_particle.set_default_texture_path'),
)


def rna_exists(idname):
    mod, name = idname.split('.')
    try:
        getattr(getattr(bpy.ops, mod), name).get_rna_type()
        return True
    except Exception:
        return False


def redraw_everything(frames=3):
    n = 0
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            for region in area.regions:
                with bpy.context.temp_override(window=window, area=area, region=region):
                    try:
                        bpy.ops.wm.redraw_timer(type='DRAW', iterations=frames)
                    except Exception as e:
                        print('redraw_timer failed in %s/%s: %s' % (area.type, region.type, e))
                n += 1
    return n


def body(T):
    cap = io.StringIO()
    with contextlib.redirect_stderr(cap), contextlib.redirect_stdout(cap):
        prefs = common.enable_addon()
        import addon_utils
        for i in range(2):
            addon_utils.disable(common.ADDON, default_set=True)
            addon_utils.enable(common.ADDON, default_set=True, persistent=False)
    text = cap.getvalue()
    bad = [l for l in text.splitlines()
           if 'Traceback' in l or 'missing bl_rna' in l or 'register_class' in l or 'RuntimeError' in l]
    T.check(not bad, 'enable/disable/enable x2 prints no registration errors %s' % bad[:3])
    T.check(common.ADDON in bpy.context.preferences.addons, 'add-on enabled after the cycle')

    for cls_name, idname in OPERATORS:
        T.check(rna_exists(idname), 'operator %s (%s) is registered' % (cls_name, idname))

    # the texture operator really works
    img = bpy.data.images.new('regtest', 8, 8)
    img.wow_m2_texture.path = ''
    bpy.ops.wow_m2_texture.set_default_texture(img_name=img.name)
    T.check(img.wow_m2_texture.path == 'textures\\ShaneCube.blp', 'SetDefaultTexture sets the default path')

    # no project at all: every redraw must be quiet about "No active project"
    prefs = bpy.context.preferences.addons[common.ADDON].preferences
    while len(prefs.projects):
        prefs.projects.remove(0)
    T.check(len(prefs.projects) == 0, 'fresh state: no project')
    for kind in ('M2', 'WMO'):
        bpy.context.scene.wow_scene.type = kind
        cap = io.StringIO()
        with contextlib.redirect_stderr(cap), contextlib.redirect_stdout(cap):
            n = redraw_everything()
        text = cap.getvalue()
        T.check(n > 0, 'redrew %d regions (scene type %s)' % (n, kind))
        T.check('No active project' not in text, 'no "No active project" while redrawing (%s)' % kind)
        tb = [l for l in text.splitlines() if l.startswith('Traceback') or 'Error:' in l]
        T.check(not tb, 'no Python errors while redrawing with no project (%s) %s' % (kind, tb[:3]))
        if tb:
            T.info(text[-1500:])


common.run(T, body)
