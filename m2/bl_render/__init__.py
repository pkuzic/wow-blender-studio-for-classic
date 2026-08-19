import os
import bpy

from pathlib import Path
from .cycles import update_m2_mat_node_tree_cycles

node_groups = [
    'EnvMapping',
    'UV Picker'
 ]

def load_m2_shader_dependencies(reload_shader=False):
    render_engine = bpy.context.scene.render.engine

    # remove old node groups
    if reload_shader:
        for ng_name in node_groups:
            if ng_name in bpy.data.node_groups:
                bpy.data.node_groups.remove(bpy.data.node_groups[ng_name])

    missing_nodes = [ng_name for ng_name in node_groups if ng_name not in bpy.data.node_groups]

    if render_engine in ('CYCLES', 'BLENDER_EEVEE'):
        lib_path = os.path.join(str(Path(__file__).parent), 'cycles', 'wotlk_m2_default.blend')
    else:
        print('\nWARNING: Failed loading shader: materials may not display correctly.'
              '\nIncompatible render engine \""{}"\"'.format(render_engine))
        return

    with bpy.data.libraries.load(lib_path) as (data_from, data_to):
        data_to.node_groups = [node_group for node_group in data_from.node_groups if node_group in missing_nodes]

def update_m2_mat_node_tree(bl_mat):

    render_engine = bpy.context.scene.render.engine

    if render_engine in ('CYCLES', 'BLENDER_EEVEE'):
        update_m2_mat_node_tree_cycles(bl_mat)

    else:
        print('\nWARNING: Failed generating node tree: material \"{}\" may not display correctly.'
              '\nIncompatible render engine \""{}"\"'.format(bl_mat.name, render_engine))