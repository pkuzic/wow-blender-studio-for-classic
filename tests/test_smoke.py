# Smoke test: the add-on enables, a project on the client loads, and one 1.12 character imports.
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import common

T = common.Test('smoke')


def body(T):
    common.setup_project()
    T.check(hasattr(bpy.ops.wbs, 'browser_index'), 'add-on registered (browser operator present)')
    common.new_scene('M2')
    common.import_game_model(r"Character\Ogre\Female\OgreMage.m2")
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    T.check(len(meshes) > 10, 'ogress imported: %d mesh objects' % len(meshes))


common.run(T, body)
