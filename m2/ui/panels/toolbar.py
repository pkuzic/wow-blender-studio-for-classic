import bpy
from ....ui.preferences import get_project_preferences
from ..enums import *


def update_wow_visibility(self, context):
    values = self.m2_visibility

    for obj in self.objects:

        if 'wow_hide' not in obj:
            obj['wow_hide'] = obj.hide_get()

        if obj['wow_hide'] != obj.hide_get():
            continue

        if obj.type == "MESH": # only geoset and collision ?
            if  obj.wow_m2_geoset:
                if obj.wow_m2_geoset.collision_mesh:
                    obj.hide_set('6' not in values)
                if obj.wow_m2_geoset.enabled and obj.wow_m2_geoset.collision_mesh == False:
                    obj.hide_set('0' not in values)

        elif obj.wow_m2_attachment.enabled:
            obj.hide_set('1' not in values)
        elif obj.wow_m2_event.enabled:
            obj.hide_set('2' not in values)
        elif obj.wow_m2_particle.enabled:
            obj.hide_set('4' not in values)
        elif obj.type == "LIGHT" and obj.wow_m2_light.enabled:
            obj.hide_set('3' not in values)
        elif obj.type == "CAMERA" and obj.wow_m2_camera.enabled:
            obj.hide_set('5' not in values)
        elif obj.type == "ARMATURE": # and obj.data.edit_bones[0].wow_m2_bone: # wow_m2_bone. check if first armature's bone is m2 bone
            obj.hide_set('7' not in values)
        else:
            print("unknown type")
            print(obj.name)
            print(obj.type)
        
        obj['wow_hide'] = obj.hide_get()


class M2_PT_tools_object_mode_display(bpy.types.Panel):
    bl_label = 'M2 Display'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = 'objectmode'
    bl_category = 'M2'

    def draw(self, context):
        layout = self.layout.split()
        col = layout.column(align=True)
        col_row = col.row()
        col_row.column(align=True).prop(context.scene, "m2_visibility")
        col_col = col_row.column(align=True)
        col_col.operator("scene.wow_m2_select_entity", text='', icon='VIEWZOOM').entity = 'wow_m2_geoset'
        col_col.operator("scene.wow_m2_select_entity", text='', icon='VIEWZOOM').entity = 'wow_m2_attachment'
        col_col.operator("scene.wow_m2_select_entity", text='', icon='VIEWZOOM').entity = 'wow_m2_event'
        col_col.operator("scene.wow_m2_select_entity", text='', icon='VIEWZOOM').entity = 'wow_m2_particle'
        col_col.operator("scene.wow_m2_select_entity", text='', icon='VIEWZOOM').entity = 'wow_m2_camera'
        col_col.operator("scene.wow_m2_select_entity", text='', icon='VIEWZOOM').entity = 'wow_m2_light'
        col_col.operator("scene.wow_m2_select_entity", text='', icon='VIEWZOOM').entity = 'Collision'
        col_col.operator("scene.wow_m2_select_entity", text='', icon='VIEWZOOM').entity = 'Skeleton'


    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.wow_scene.type == 'M2'


class M2_PT_tools_panel_object_mode_add_to_scene(bpy.types.Panel):
    bl_label = 'Add to scene'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = 'objectmode'
    bl_category = 'M2'

    def draw(self, context):
        layout = self.layout.split()

        game_data_loaded = hasattr(bpy, "wow_game_data") and bpy.wow_game_data.files

        col = layout.column(align=True)

        col.separator()
        col1_col = col.column(align=True)
        col1_row1 = col1_col.row(align=True)  
        
        col1_row2 = col1_col.row(align=True)  

        
        col1_row1.operator("scene.wow_import_last_m2_from_wmv", text='M2',
            icon_value=ui_icons['WOW_STUDIO_DOODADS_ADD']) 
        
        
        if proj_prefs := get_project_preferences():
            col1_row1.prop(proj_prefs, 'import_method', text='')

        col1_row2.operator("scene.m2_add_attachment", text='Attachment', icon='POSE_HLT')
        col1_row2.operator("scene.m2_add_event", text='Event', icon='POSE_HLT')

        col1_row3 = col1_col.row(align=True)

        col1_row3.operator("scene.wow_m2_texture_import", text='Texture', icon='IMAGE_DATA')

        col1_row4 = col1_col.row(align=True)
        col.separator()

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.wow_scene.type == 'M2'


class M2_PT_tools_object_mode_actions(bpy.types.Panel):
    bl_label = 'Actions'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = 'objectmode'
    bl_category = 'M2'

    def draw(self, context):
        layout = self.layout.split()
        col = layout.column(align=True)
        col.separator()
        box_col = col.column(align=True)

        col1_row1 = box_col.row(align=True)  
    
        col1_row1.operator("scene.m2_ot_enable_drivers", text='Drivers ON', icon='RADIOBUT_ON')
        col1_row1.operator("scene.m2_ot_disable_drivers", text='Drivers OFF', icon='RADIOBUT_OFF')

        box_col.operator("scene.wow_creature_editor_toggle", text='Creature Editor', icon_value=ui_icons['WOW_STUDIO_SCALE_ADD'])

        if bpy.context.selected_objects:
            box_col.operator("scene.m2_fill_textures", text='Fill Paths', icon='SEQ_SPLITVIEW')
            
        if context.object and context.object.type == 'ARMATURE':
            box_col.operator("object.m2_bone_renamer", text='Rename', icon='CONSOLE')

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.wow_scene.type == 'M2'


class M2_MT_mesh_wow_components_add(bpy.types.Menu):
    bl_label = "WoW"
    bl_options = {'REGISTER'}

    def draw(self, context):
        layout = self.layout
        col = layout.column()

        if hasattr(bpy, "wow_game_data") and bpy.wow_game_data.files:
            col.operator("scene.wow_import_last_m2_from_wmv", text='M2',
                icon_value=ui_icons['WOW_STUDIO_DOODADS_ADD'])          

        col.operator("scene.m2_add_attachment", text='Attachment', icon='POSE_HLT')
        col.operator("scene.m2_add_event", text='Event', icon='POSE_HLT')
        # col.operator("scene.wow_add_fog", text='Fog', icon_value=ui_icons['WOW_STUDIO_FOG_ADD'])
        # col.operator("scene.wow_add_liquid", text='Liquid', icon_value=ui_icons['WOW_STUDIO_LIQUID_ADD'])
        # col.operator("scene.wow_add_scale_reference", text='Scale', icon_value=ui_icons['WOW_STUDIO_SCALE_ADD'])
        # col.operator("scene.wow_add_light", text='Light', icon='LIGHT')
# 
        #if hasattr(bpy, "wow_game_data") and bpy.wow_game_data.files:
        #     col.operator("scene.wow_wmo_import_doodad_from_wmv", text='M2',
        #                  icon_value=ui_icons['WOW_STUDIO_DOODADS_ADD'])
        #     col.operator("scene.wow_import_last_wmo_from_wmv", text='WMO', icon_value=ui_icons['WOW_STUDIO_WMO_ADD'])

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.wow_scene.type == 'M2'

def wow_components_add_menu_item(self, context):
    self.layout.menu("M2_MT_mesh_wow_components_add", icon_value=ui_icons['WOW_STUDIO_WOW'])


def render_viewport_toggles_right(self, context):
    if hasattr(context.scene, 'wow_scene') \
    and hasattr(context.scene.wow_scene, 'type') \
    and context.scene.wow_scene.type == 'M2':
        layout = self.layout
        row = layout.row(align=True)
        row.popover(  panel="M2_PT_tools_object_mode_display"
                    , text=''
                    , icon='HIDE_OFF'
                   )


def register():
    bpy.types.Scene.m2_visibility = bpy.props.EnumProperty(
        items=[
            ('0', "Geosets", "Display geosets", 'FILE_3D', 0x1),
            ('1', "Attachments", "Display attachments", 'POSE_HLT', 0x2),
            ('2', "Events", "Display events", 'PLUGIN', 0x4),
            ('3', "Lights", "Display lights", 'LIGHT', 0x8),
            ('4', "Particles emitters", "Display particle emitters", 'MOD_PARTICLES', 0x10),
            ('5', "Cameras", "Display cameras", 'CAMERA_DATA', 0x20),
            ('6', "Collision", "Display collision", 'CON_SIZELIMIT', 0x40),
            ('7', "Skeleton", "Display bones", 'BONE_DATA', 0x80)],
        options={'ENUM_FLAG'},
        default={'0', '1', '2', '3', '4', '5', '6', '7'},
        update=update_wow_visibility
    )


    bpy.types.VIEW3D_MT_add.prepend(wow_components_add_menu_item)
    bpy.types.VIEW3D_HT_header.append(render_viewport_toggles_right)


def unregister():
    del bpy.types.Scene.m2_visibility

    bpy.types.VIEW3D_MT_add.remove(wow_components_add_menu_item)
    bpy.types.VIEW3D_MT_add.remove(render_viewport_toggles_right)
