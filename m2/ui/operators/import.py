import bpy
import os
import traceback
import struct

from ...import_m2 import import_m2_gamedata
from ....wmo.utils.wmv import wmv_get_last_m2, wow_export_get_last_m2, noggit_red_get_last_m2
from ....ui.preferences import get_project_preferences
from ....utils.misc import load_game_data


class M2_OT_import_last_m2_from_wmv(bpy.types.Operator):
    bl_idname = "scene.wow_import_last_m2_from_wmv"
    bl_label = "Load last M2 from preferred import method"
    bl_description = "Load last M2 from preferred import method"
    bl_options = {'UNDO', 'REGISTER'}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):

        game_data = load_game_data()

        if not game_data or not game_data.files:
            self.report({'ERROR'}, "Failed to import model. Connect to game client first.")
            return {'CANCELLED'}

        project_preferences = get_project_preferences()
        if project_preferences.import_method == 'WMV':
            if project_preferences.wmv_path:
                m2_path = wmv_get_last_m2()
        elif project_preferences.import_method == 'WowExport':       
            if project_preferences.wow_export_path:
                m2_path = wow_export_get_last_m2()
        elif project_preferences.import_method == 'NoggitRed':       
            if project_preferences.noggit_red_path:
                m2_path = noggit_red_get_last_m2()

        if not m2_path:
            self.report({'ERROR'}, """Log contains no M2 entries.
            Make sure to use compatible WMV version or WoW.Export and open an .m2 there.""")
            return {'CANCELLED'}

        try:         
            import_m2_gamedata(2, m2_path, False)
        except:
            traceback.print_exc()
            self.report({'ERROR'}, "Failed to import model.")
            return {'CANCELLED'}

        self.report({'INFO'}, "Done importing M2 object to scene.")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)
