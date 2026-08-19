import bpy

from ...utils.fogs import create_fog_object
from ...ui.collections import get_wmo_collection, SpecialCollections


class WMO_OT_add_fog(bpy.types.Operator):
    bl_idname = 'scene.wow_add_fog'
    bl_label = 'Add fog'
    bl_description = 'Add a WoW fog object to the scene'

    def execute(self, context):
        scn = context.scene
        fog_collection = get_wmo_collection(scn, SpecialCollections.Fogs)
        if not fog_collection:
            self.report({'WARNING'}, "Can't add WMO Fog: No WMO Object Collection found in the scene.")
            return {'FINISHED'}

        fog_obj = create_fog_object()


        # applying object properties
        fog_obj.wow_wmo_fog.enabled = True
        fog_collection.objects.link(fog_obj)
        bpy.context.view_layer.objects.active = fog_obj

        fog_obj.scale = (5.0, 5.0, 5.0) # default size to 5

        fog_obj.wow_wmo_fog.color2 = (0.0, 0.0, 1.0) # set underwater color as blue

        self.report({'INFO'}, "Successfully created WoW fog: " + fog_obj.name)
        return {'FINISHED'}