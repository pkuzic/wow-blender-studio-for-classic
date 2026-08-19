from ..pywowlib.m2_file import M2File
from . import m2_scene
from .operations import m2_export_warnings
import importlib

import os
import bpy
import time

from ..utils.misc import resolve_outside_model_path
from ..ui.preferences import get_project_preferences

def create_m2(version, filepath, selected_only, fill_textures, forward_axis, scale, merge_vertices):
    proj_prefs = get_project_preferences()
    time_import_method = proj_prefs.time_import_method
    m2 = M2File(version)
    importlib.reload(m2_scene)
    importlib.reload(m2_export_warnings)
    bl_m2 = m2_scene.BlenderM2Scene(m2, proj_prefs)

    export_path = resolve_outside_model_path(filepath)
    if export_path:
        bpy.context.scene.wow_scene.game_path = export_path

    print("\n\n##########################")
    print("### Exporting M2 model ###")
    print("##########################")
    print("\n")

    start_time = time.time()

    bl_m2.prepare_export_axis(forward_axis, scale)
    bl_m2.prepare_pose(selected_only)
    bl_m2.save_properties(filepath, selected_only)
    bl_m2.save_bones(selected_only)
    bl_m2.save_cameras()
    bl_m2.save_attachments()
    bl_m2.save_events()
    bl_m2.save_lights()
    bl_m2.save_ribbons()
    bl_m2.save_particles(time_import_method)
    bl_m2.save_animations(time_import_method)
    bl_m2.save_geosets(selected_only, fill_textures, merge_vertices)
    bl_m2.save_collision(selected_only)
    bl_m2.restore_pose()

    warnings = m2_export_warnings.print_warnings()

    if warnings:
        bpy.ops.wbs.viewport_text_display('INVOKE_DEFAULT', message="Info: M2 Exported with Warnings, check console!!", font_size=32, y_offset=100, color=(1,0.15,0.15,1))
    else:
        bpy.ops.wbs.viewport_text_display('INVOKE_DEFAULT', message="Info: Successfully exported M2!", font_size=24, y_offset=67)    

    print("\nSuccessfully Exported M2 to " + filepath +
          "\nTotal export time: ", time.strftime("%M minutes %S seconds", time.gmtime(time.time() - start_time)))

    return m2


def export_m2(version, filepath, selected_only, fill_textures, forward_axis, scale, merge_vertices):
    if os.path.exists(filepath):
        os.remove(filepath)    
    create_m2(version,filepath,selected_only,fill_textures,forward_axis, scale, merge_vertices).write(filepath)