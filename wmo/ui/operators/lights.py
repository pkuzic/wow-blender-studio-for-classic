import bpy

from ...ui.collections import get_wmo_collection, SpecialCollections


class WMO_OT_add_light(bpy.types.Operator):
    bl_idname = 'scene.wow_add_light'
    bl_label = 'Add light'
    bl_description = 'Add a WoW light object to the scene'

    def execute(self, context):
        
        scn = context.scene
        light_collection = get_wmo_collection(scn, SpecialCollections.Lights)
        if not light_collection:
            self.report({'WARNING'}, "Can't add WMO Light: No WMO Object Collection found in the scene.")
            return {'FINISHED'}
        
        light = bpy.data.lights.new(name='WoW Light', type='POINT')
        obj = bpy.data.objects.new('WoW Light', light)

        light.color = (1.0, 0.565, 0.0)
        light.energy = 1.0

        obj.wow_wmo_light.enabled = True
        obj.wow_wmo_light.use_attenuation = True
        obj.wow_wmo_light.color = light.color # set yellow as default
        obj.wow_wmo_light.color_alpha = 1.0
        obj.wow_wmo_light.intensity = light.energy
        # light.falloff_type = 'INVERSE_LINEAR'
        
        # move lights to collection
        light_collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        bpy.data.objects[obj.name].select_set(True)

        obj.location = bpy.context.scene.cursor.location

        self.report({'INFO'}, "Successfully created WoW light: " + obj.name)
        return {'FINISHED'}