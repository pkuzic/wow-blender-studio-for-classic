import bpy
from ..custom_objects import *

class WMO_OT_pie_menu_manager(bpy.types.Operator):
    bl_idname = 'wm.wmo_pie_menu_manager'
    bl_label = 'Pie Menu Manager'
    bl_options = {'INTERNAL', 'UNDO'}

    def invoke(self, context, event):

        if not context.object:
            return {'FINISHED'}

        if context.object.type == 'MESH':
            if WoWWMOGroup.match(context.object):
                if context.object.mode == 'EDIT':
                    bpy.ops.wm.call_menu_pie(name='VIEW3D_MT_wmo_select_texture')
                elif context.object.mode == 'OBJECT':
                    bpy.ops.wm.call_menu_pie(name='VIEW3D_MT_wmo_group_actions')
            elif WoWWMODoodad.match(context.object):
                bpy.ops.wm.call_menu_pie(name='VIEW3D_MT_wmo_doodad_actions')
            elif WoWWMOPortal.match(context.object):
                bpy.ops.wm.call_menu_pie(name='VIEW3D_MT_wmo_portal_actions')

        return {'FINISHED'}


keymap = None


def register():
    global keymap

    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.new(name='3D View', space_type='VIEW_3D', region_type='WINDOW')
    kmi = km.keymap_items.new("wm.wmo_pie_menu_manager", type='Q', value='PRESS', shift=True)
    keymap = km, kmi


def unregister():
    global keymap

    km, kmi = keymap
    km.keymap_items.remove(kmi)

