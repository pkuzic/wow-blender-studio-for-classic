import bpy
import traceback

from ....ui.preferences import get_project_preferences

from ...import_wmo import import_wmo_to_blender_scene_gamedata
from ...utils.wmv import wmv_get_last_wmo, wow_export_get_last_wmo, noggit_red_get_last_wmo
from ....utils.misc import load_game_data


class WMO_OT_import_last_wmo_from_wmv(bpy.types.Operator):
    bl_idname = "scene.wow_import_last_wmo_from_wmv"
    bl_label = "Load last WMO from preferred import method"
    bl_description = "Load last WMO from preferred import method"
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
                wmo_path = wmv_get_last_wmo()
        elif project_preferences.import_method == 'WowExport':       
            if project_preferences.wow_export_path:
                wmo_path = wow_export_get_last_wmo()
        elif project_preferences.import_method == 'NoggitRed':       
            if project_preferences.noggit_red_path:
                wmo_path = noggit_red_get_last_wmo()

        if not wmo_path:
            self.report({'ERROR'}, """Log contains no WMO entries.
            Make sure to use compatible WMV version or WoW.Export and open a .wmo there.""")
            return {'CANCELLED'}

        try:
            import_wmo_to_blender_scene_gamedata(wmo_path, bpy.context.scene.wow_scene.version)
        except:
            traceback.print_exc()
            self.report({'ERROR'}, "Failed to import model.")
            return {'CANCELLED'}

        self.report({'INFO'}, "Done importing WMO object to scene.")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)
