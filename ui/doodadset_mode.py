import bpy
from ..wmo.ui.custom_objects import *
from ..wmo.ui.collections import get_wmo_groups_list
from ..utils.collections import get_current_wow_model_collection

class WBS_OT_doodadset_mode(bpy.types.Operator):
    bl_idname = 'scene.doodadset_mode'
    bl_label = 'Enters into Doodadset editing mode'
    bl_description = "Enters into Doodadset editing mode, disabling some edit options."
    bl_options = {'REGISTER'}

    def execute(self, context):
        bpy.context.scene.wow_scene.doodadset_mode = not bpy.context.scene.wow_scene.doodadset_mode


        wmo_model_collection = get_current_wow_model_collection(context.scene, 'wow_wmo')
        if wmo_model_collection:
            if bpy.context.scene.wow_scene.doodadset_mode == True:    
                bpy.ops.wbs.viewport_text_display('INVOKE_DEFAULT', message="Doodadset mode enabled", font_size=24, y_offset=67)        
                for i, obj in enumerate(get_wmo_groups_list(context.scene)):
                    obj : bpy.types.Object
                    obj.lock_location = (True, True, True)
                    obj.lock_rotation = (True, True, True)
                    obj.lock_scale = (True, True, True)
                    obj.hide_select = True
                for obj in bpy.context.scene.objects:
                    if obj.type == 'MESH':
                        if WoWWMOPortal.match(obj):
                            obj.hide_select = True
                        elif WoWWMOFog.match(obj):
                            obj.hide_select = True
                        elif WoWWMOLiquid.match(obj):
                            obj.hide_select = True
                        elif WoWWMOCollision.match(obj):
                            obj.hide_select = True                            
                    elif obj.type == 'LIGHT' and WoWWMOLight.match(obj):
                        obj.hide_select = True
                        
            else:
                bpy.ops.wbs.viewport_text_display('INVOKE_DEFAULT', message="Doodadset mode disabled", font_size=24, y_offset=67)   
                for i, obj in enumerate(get_wmo_groups_list(context.scene)):
                    obj : bpy.types.Object
                    obj.lock_location = (False, False, False)
                    obj.lock_rotation = (False, False, False)
                    obj.lock_scale = (False, False, False)     
                    obj.hide_select = False           
                for obj in bpy.context.scene.objects:
                    if obj.type == 'MESH':
                        if WoWWMOPortal.match(obj):
                            obj.hide_select = False
                        elif WoWWMOFog.match(obj):
                            obj.hide_select = False
                        elif WoWWMOLiquid.match(obj):
                            obj.hide_select = False
                        elif WoWWMOCollision.match(obj):
                            obj.hide_select = False                            
                    elif obj.type == 'LIGHT' and WoWWMOLight.match(obj):
                        obj.hide_select = False         
        return {'FINISHED'}

keymap = None

def register():
    global keymap

    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.new(name='3D View', space_type='VIEW_3D', region_type='WINDOW')
    kmi = km.keymap_items.new("scene.wow_doodads_bake_color", type='B', value='PRESS', shift=True)
    keymap = km, kmi


def unregister():
    global keymap

    km, kmi = keymap
    km.keymap_items.remove(kmi)

