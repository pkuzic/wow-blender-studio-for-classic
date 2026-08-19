import bpy
from ....ui.preferences import get_project_preferences
from ..enums import *

from .common import panel_poll
from ..custom_objects import *
from ...ui.enums import SpecialCollections
from ...ui.collections import get_current_wow_model_collection, get_or_create_collection, get_wmo_groups_list


def update_wow_visibility(self, context):
    values = self.wow_visibility

    for obj in self.objects:
        if 'wow_hide' not in obj:
            obj['wow_hide'] = obj.hide_get()

        if obj['wow_hide'] != obj.hide_get():
            continue

        if obj.type == "MESH":
            if WoWWMOGroup.match(obj):
                if WoWWMOGroup.is_outdoor(obj):
                    obj.hide_set('0' not in values)
                elif WoWWMOGroup.is_indoor(obj):
                    obj.hide_set('1' not in values)

                if obj.wow_wmo_group.collision_mesh:
                    col = obj.wow_wmo_group.collision_mesh

                    if 'wow_hide' not in col:
                        col['wow_hide'] = col.hide_get()

                    if col['wow_hide'] != col.hide_get():
                        continue

                    col.hide_set('6' not in values)
                    col['wow_hide'] = col.hide_get()

            elif WoWWMOPortal.match(obj):
                obj.hide_set('2' not in values)
            elif WoWWMOFog.match(obj):
                obj.hide_set('3' not in values)
            elif WoWWMOLiquid.match(obj):
                obj.hide_set('4' not in values)
        elif obj.type == "LIGHT" and WoWWMOLight.match(obj):
            obj.hide_set('5' not in values)

        obj['wow_hide'] = obj.hide_get()


def update_wow_wmo_culling(self, context):
    values = self.wow_enable_culling

    for group_object in get_wmo_groups_list(bpy.context.scene):
        for material in group_object.data.materials:
            if not "4" in material.wow_wmo_material.flags: # two-sided flag
                material.use_backface_culling = ('culling' in values)


def get_doodad_sets(self, context):
    has_global = False
    global_col = None
    doodad_set_collections = set()
    doodad_sets = []

    wmo_model_collection = get_current_wow_model_collection(bpy.context.scene, 'wow_wmo')
    if wmo_model_collection:
        for set_collection in get_or_create_collection(wmo_model_collection, SpecialCollections.Doodads.name).children:

            if "Set_$DefaultGlobal" not in set_collection.name:
                doodad_set_collections.add(set_collection)
            else:
                has_global = True
                global_col = set_collection

    for index, set_collection in enumerate(sorted(doodad_set_collections, key=lambda x: x.name), 1 + has_global):
        doodad_sets.append((set_collection.name, set_collection.name, "", 'SCENE_DATA', index))

    doodad_sets.insert(0, ("None", "No set", "", 'X', 0))
    if has_global:
        doodad_sets.insert(1, (global_col.name, "Set_$DefaultGlobal", "", 'WORLD', 1))

    return doodad_sets


def switch_doodad_set(self, context):
    set = self.wow_doodad_visibility

    wmo_model_collection = get_current_wow_model_collection(bpy.context.scene, 'wow_wmo')
    if wmo_model_collection:
        for set_collection in get_or_create_collection(wmo_model_collection, SpecialCollections.Doodads.name).children:

            name = set_collection.name
            for obj in set_collection.objects:
                obj.hide_set(set == "None" or name != set and name != "Set_$DefaultGlobal")


class WMO_PT_tools_object_mode_display(bpy.types.Panel):
    bl_label = 'Display'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = 'objectmode'
    bl_category = 'WMO'

    def draw(self, context):
        layout = self.layout.split()
        col = layout.column(align=True)
        col_row = col.row()
        col_row.column(align=True).prop(context.scene, "wow_visibility")
        col_col = col_row.column(align=True)
        col_col.operator("scene.wow_wmo_select_entity", text='', icon='VIEWZOOM').entity = 'Outdoor'
        col_col.operator("scene.wow_wmo_select_entity", text='', icon='VIEWZOOM').entity = 'Indoor'
        col_col.operator("scene.wow_wmo_select_entity", text='', icon='VIEWZOOM').entity = 'wow_wmo_portal'
        col_col.operator("scene.wow_wmo_select_entity", text='', icon='VIEWZOOM').entity = 'wow_wmo_fog'
        col_col.operator("scene.wow_wmo_select_entity", text='', icon='VIEWZOOM').entity = 'wow_wmo_liquid'
        col_col.operator("scene.wow_wmo_select_entity", text='', icon='VIEWZOOM').entity = 'wow_wmo_light'
        col_col.operator("scene.wow_wmo_select_entity", text='', icon='VIEWZOOM').entity = 'Collision'

        box2_row2 = col.row()
        box2_row2.prop(context.scene, "wow_doodad_visibility", expand=False)
        box2_row2.operator("scene.wow_wmo_select_entity", text='', icon='VIEWZOOM').entity = 'wow_wmo_doodad'

        box2_row3 = col.row()
        box2_row3.prop(context.scene, "wow_enable_culling")
    @classmethod
    def poll(cls, context):
        return panel_poll(cls, context)


class WMO_PT_tools_panel_object_mode_add_to_scene(bpy.types.Panel):
    
    bl_label = 'Add to scene'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = 'objectmode'
    bl_category = 'WMO'

    def draw(self, context):

        layout = self.layout.split()

        wow_model_collection = get_current_wow_model_collection(bpy.context.scene, 'wow_wmo')

        col = layout.column(align=True)

        if wow_model_collection:
            col.label(text=f'WMO: {wow_model_collection.name}')
            col.separator()


        if bpy.context.scene.wow_scene.doodadset_mode == False:
            col.separator()
            col1_col = col.column(align=True)
            col1_row0 = col1_col.row(align=True)
            col1_row1 = col1_col.row(align=True)
            col1_row2 = col1_col.row(align=True)

            col1_row3 = col1_col.row(align=True)
            col1_row4 = col1_col.row(align=True)
            col1_row4 = col1_col.row(align=True)
            col1_row5 = col1_col.row(align=True)
            col.separator()

            if proj_prefs := get_project_preferences():
                col1_row0.prop(proj_prefs, 'import_method', text='')                  
                if proj_prefs.import_method == 'DirectPath':
                    box = col1_row1.box()
                    box.prop(proj_prefs, "direct_path")  
            col1_row2.operator("scene.wow_wmo_import_doodad_from_wmv", text='M2',
                            icon_value=ui_icons['WOW_STUDIO_DOODADS_ADD'])        
            col1_row2.operator("scene.wow_import_last_wmo_from_wmv", text='WMO',
                            icon_value=ui_icons['WOW_STUDIO_WMO_ADD'])                      
            col1_row3.operator("scene.wow_add_fog", text='Fog', icon_value=ui_icons['WOW_STUDIO_FOG_ADD'])
            col1_row3.operator("scene.wow_add_liquid", text='Liquid', icon_value=ui_icons['WOW_STUDIO_LIQUID_ADD'])                    

            col1_row4.operator("scene.wow_add_light", text='Light', icon='LIGHT')      
            col1_row4.operator("scene.wow_add_scale_reference", text='Scale',
                            icon_value=ui_icons['WOW_STUDIO_SCALE_ADD'])
            col1_row5.operator("scene.wow_wmo_texture_import", text='Texture', icon='IMAGE_DATA')
        else:
            col.separator()
            col1_col = col.column(align=True)
            col1_row0 = col1_col.row(align=True)
            col1_row1 = col1_col.row(align=True)
            col1_row2 = col1_col.row(align=True)
            col1_row3 = col1_col.row(align=True)
            col1_row4 = col1_col.row(align=True)
            col.separator()


            if proj_prefs := get_project_preferences():
                col1_row0.prop(proj_prefs, 'import_method', text='')                  

            col1_row2.operator("scene.wow_wmo_import_doodad_from_wmv", text='M2',
                            icon_value=ui_icons['WOW_STUDIO_DOODADS_ADD']) 

    @classmethod
    def poll(cls, context):
        return panel_poll(cls, context)


class WMO_PT_tools_object_mode_actions(bpy.types.Panel):
    bl_label = 'Actions'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = 'objectmode'
    bl_category = 'WMO'

    def draw(self, context):
        layout = self.layout.split()
        col = layout.column(align=True)
        col.separator()
        box_col = col.column(align=True)
        box_col.operator("scene.wow_wmo_generate_minimaps", text='Generate minimaps', icon='SHADING_RENDERED')

        if bpy.context.selected_objects:
            box_col.operator("scene.wow_wmo_generate_materials", text='Generate materials', icon='MATERIAL')
            box_col.operator("scene.wow_fill_textures", text='Fill texture paths', icon='SEQ_SPLITVIEW')
            box_col.operator("scene.wow_quick_collision", text='Quick collision', icon='MOD_TRIANGULATE')
            box_col.operator("scene.wow_set_portal_dir_alg", text='Set portal direction', icon='ORIENTATION_NORMAL')
            box_col.operator("scene.wow_bake_portal_relations", text='Bake portal relations', icon='FULLSCREEN_EXIT')
            col.separator()

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.wow_scene.type == 'WMO' and bpy.context.scene.wow_scene.doodadset_mode == False


class WMO_PT_tools_object_mode_doodads(bpy.types.Panel):
    bl_label = 'Doodads'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = 'objectmode'
    bl_category = 'WMO'

    @classmethod
    def poll(cls, context):
        return panel_poll(cls, context) and bpy.context.selected_objects

    def draw(self, context):
        layout = self.layout.split()
        col = layout.column(align=True)

        col.separator()
        box_col2 = col.column(align=True)

        box_col2.operator("scene.wow_doodads_bake_color", text='Bake color', icon='SHADING_RENDERED')
        box_col2.operator("scene.wow_doodad_set_color", text='Set color', icon='SHADING_SOLID')
        box_col2.operator("scene.wow_doodad_set_template_action", text='Template action', icon='STICKY_UVS_LOC')
        col.separator()

class WMO_MT_mesh_wow_components_add(bpy.types.Menu):
    bl_label = "WoW"
    bl_options = {'REGISTER'}

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.operator("scene.wow_add_fog", text='Fog', icon_value=ui_icons['WOW_STUDIO_FOG_ADD'])
        col.operator("scene.wow_add_liquid", text='Liquid', icon_value=ui_icons['WOW_STUDIO_LIQUID_ADD'])
        col.operator("scene.wow_add_scale_reference", text='Scale', icon_value=ui_icons['WOW_STUDIO_SCALE_ADD'])
        col.operator("scene.wow_add_light", text='Light', icon='LIGHT')

        if hasattr(bpy, "wow_game_data") and bpy.wow_game_data.files:
            col.operator("scene.wow_wmo_import_doodad_from_wmv", text='M2',
                         icon_value=ui_icons['WOW_STUDIO_DOODADS_ADD'])
            col.operator("scene.wow_import_last_wmo_from_wmv", text='WMO', icon_value=ui_icons['WOW_STUDIO_WMO_ADD'])

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.wow_scene.type == 'WMO'


def wow_components_add_menu_item(self, context):
    self.layout.menu("WMO_MT_mesh_wow_components_add", icon_value=ui_icons['WOW_STUDIO_WOW'])


def render_viewport_toggles_right(self, context):
    if hasattr(context.scene, 'wow_scene') \
    and hasattr(context.scene.wow_scene, 'type') \
    and context.scene.wow_scene.type == 'WMO':
        layout = self.layout
        row = layout.row(align=True)
        row.popover(  panel="WMO_PT_tools_object_mode_display"
                    , text=''
                    , icon='HIDE_OFF'
                   )


def register():
    bpy.types.Scene.wow_visibility = bpy.props.EnumProperty(
        items=[
            ('0', "Outdoor", "Display outdoor groups", 'SELECT_SET', 0x1),
            ('1', "Indoor", "Display indoor groups", 'OBJECT_HIDDEN', 0x2),
            ('2', "Portals", "Display portals", 'FULLSCREEN_ENTER', 0x4),
            ('3', "Fogs", "Display fogs", 'MOD_FLUID', 0x8),
            ('4', "Liquids", "Display liquids", 'MOD_OCEAN', 0x10),
            ('5', "Lights", "Display lights", 'LIGHT', 0x20),
            ('6', "Collision", "Display collision", 'CON_SIZELIMIT', 0x40)],
        options={'ENUM_FLAG'},
        default={'0', '1', '2', '3', '4', '5'},
        update=update_wow_visibility
    )


    bpy.types.Scene.wow_enable_culling = bpy.props.EnumProperty(
        items=[
            ('culling', "Backface Culling",
             "Enable materials backface culling unless that material has the two-sided flag for a realistic WoW rendering",
              'XRAY', 0x1)],
        options={'ENUM_FLAG'},
        # default={},
        update=update_wow_wmo_culling
    )


    bpy.types.Scene.wow_doodad_visibility = bpy.props.EnumProperty(
        name="",
        description="Switch doodad sets",
        items=get_doodad_sets,
        update=switch_doodad_set
    )

    bpy.types.VIEW3D_MT_add.prepend(wow_components_add_menu_item)
    bpy.types.VIEW3D_HT_header.append(render_viewport_toggles_right)


def unregister():
    del bpy.types.Scene.wow_visibility
    del bpy.types.Scene.wow_doodad_visibility
    del bpy.types.Scene.wow_enable_culling

    bpy.types.VIEW3D_MT_add.remove(wow_components_add_menu_item)
    bpy.types.VIEW3D_MT_add.remove(render_viewport_toggles_right)
