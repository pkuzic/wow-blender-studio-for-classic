import bpy
from ..ui.preferences import get_project_preferences
from .. import ui_icons
from ..utils.callbacks import on_release
from ..utils.custom_object import CustomObject
from .enums import WoWSceneTypes

from typing import Type


class WBS_PT_object_properties_common:
    """ Common base for all bpy.types.Object property panels. """
    bl_region_type = 'WINDOW'
    bl_space_type = 'PROPERTIES'

    __wbs_custom_object_type__: Type[CustomObject]
    """ Type of custom object associated with the panel. """

    __wbs_scene_type__: WoWSceneTypes
    """ Type of WoW scene. """

    _required = {'bl_context', 'bl_label', '__wbs_custom_object_type__', '__wbs_scene_type__'}
    """ Required fields to override in derived classes. """

    def __init_subclass__(cls, **kwargs):
        for requirement in cls._required:
            if not hasattr(cls, requirement):
                raise NotImplementedError(f'"{cls.__name__}" must override "{requirement}".')

        super().__init_subclass__(**kwargs)

    @classmethod
    def poll(cls, context: bpy.types.Context):
        """
        Used to identify if the panel should be rendered in a given context.
        :param context: Current context.
        :return: True if should be rendered, else False.
        """
        return (context.scene is not None
                and context.scene.wow_scene.type == cls.__wbs_scene_type__.name
                and context.object
                and cls.__wbs_custom_object_type__.match(context.object)
                )


class WBS_PT_wow_scene(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_label = "WoW Scene"

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(context.scene.wow_scene, 'version')
        col.prop(context.scene.wow_scene, 'type')
        col.prop(context.scene.wow_scene, 'game_path')
        col.prop(context.scene, 'wow_screen_3d', text='Main workspace')

    @classmethod
    def poll(cls, context):
        return context.scene is not None


class WowScenePropertyGroup(bpy.types.PropertyGroup):

    version:  bpy.props.EnumProperty(
        name='Client version',
        items=[('0', 'Classic', "Vanilla 1.12 / Turtle (M2 v256)", ui_icons['WOTLK'], 2),
               ('2', 'WotLK', "", ui_icons['WOTLK'], 0),
               ('6', 'Legion', "", ui_icons['LEGION'], 1)],
        default='0'
    )

    type:  bpy.props.EnumProperty(
        name='Scene type',
        description='Sets up the UI to work with a specific WoW game format',
        items=[
            ('M2', 'M2', 'M2 model', 'FILE_VOLUME', 0),
            ('WMO', 'WMO', 'World Map Object (WMO)', 'FILE_3D', 1)],
            default='WMO'
    )

    doodadset_mode: bpy.props.BoolProperty(
        name='Doodadset Mode',
        description='Enters doodadset editing mode',
        default=False
    )

    game_path:  bpy.props.StringProperty(
        name='Game path',
        description='A path to the model in WoW filesystem.'
    )


class WOW_PT_render_settings(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_label = "WoW Render Settings"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        col = layout.column()

        col.label(text='Lighting:')

        col.prop(context.scene.wow_render_settings, "ext_ambient_color")
        col.prop(context.scene.wow_render_settings, "ext_dir_color")
        col.prop(context.scene.wow_render_settings, "sidn_scalar")

        col.label(text='Fog:')
        col.prop(context.scene.wow_render_settings, "fog_color")
        col.prop(context.scene.wow_render_settings, "fog_start")
        col.prop(context.scene.wow_render_settings, "fog_end")

        col.label(text='Sun Direction:')
        col.prop(context.scene.wow_render_settings, "sun_direction", text='')


    @classmethod
    def poll(cls, context):
        return context.scene is not None


@on_release()
def update_ext_ambient_color(self, context):
    properties = bpy.data.node_groups.get('MO_Properties')
    if properties:
        properties.nodes['extLightAmbientColor'].outputs[0].default_value = self.ext_ambient_color


@on_release()
def update_ext_dir_color(self, context):
    properties = bpy.data.node_groups.get('MO_Properties')
    if properties:
        properties.nodes['extLightDirColor'].outputs[0].default_value = self.ext_dir_color


@on_release()
def update_sidn_scalar(self, context):
    properties = bpy.data.node_groups.get('MO_Properties')
    if properties:
        properties.nodes['SIDNScalar'].outputs[0].default_value = self.sidn_scalar


@on_release()
def update_sun_direction(self, context):
    properties = bpy.data.node_groups.get('MO_Properties')
    if properties:
        properties.nodes['SunDirection'].inputs[1].default_value = self.sun_direction


class WoWRenderSettingsPropertyGroup(bpy.types.PropertyGroup):

    ext_ambient_color: bpy.props.FloatVectorProperty(
        name="Ext. Ambient Color",
        subtype='COLOR',
        default=(1, 1, 1, 1),
        size=4,
        min=0.0,
        max=1.0,
        update=update_ext_ambient_color
    )

    ext_dir_color: bpy.props.FloatVectorProperty(
        name="Ext. Dir Color",
        subtype='COLOR',
        default=(0.991, 0.246, 0, 1),
        size=4,
        min=0.0,
        max=1.0,
        update=update_ext_dir_color
    )

    sidn_scalar: bpy.props.FloatProperty(
        name='SIDN intensity',
        description='Controls intensity of night glow in materials',
        min=0.0,
        max=1.0,
        update=update_sidn_scalar
    )

    sun_direction: bpy.props.FloatVectorProperty(
        name='Sun Direction',
        description='Defines the direction of the sun',
        default=(0.2, 0.7, 0.6),
        size=3,
        subtype='DIRECTION',
        update=update_sun_direction
    )

    fog_color: bpy.props.FloatVectorProperty(
        name='Fog Color',
        subtype='COLOR',
        default=(0.5, 0.5, 0.5),
        size=3,
        min=0.0,
        max=1.0
    )

    fog_start: bpy.props.FloatProperty(
        name='Fog Start',
        min=0.1,
        default=30.0
    )

    fog_end: bpy.props.FloatProperty(
        name='Fog End',
        min=0.1,
        default=1000.0
    )


def update_screen_3d(self, context):

    if not self.wow_screen_3d:
        return

    viewport = None

    for area in bpy.context.scene.wow_screen_3d.areas:
        if area.type == 'VIEW_3D':
            rv3d = area.spaces[0].region_3d
            if rv3d is not None:
                viewport = rv3d
                break

    bpy.app.driver_namespace["wow_viewport"] = viewport


def register_wow_scene_properties():
    bpy.types.Scene.wow_scene = bpy.props.PointerProperty(type=WowScenePropertyGroup)
    bpy.types.Scene.wow_screen_3d = bpy.props.PointerProperty(type=bpy.types.Screen, update=update_screen_3d)
    bpy.types.Scene.wow_render_settings = bpy.props.PointerProperty(type=WoWRenderSettingsPropertyGroup)


def unregister_wow_scene_properties():
    del bpy.types.Scene.wow_scene
    del bpy.types.Scene.wow_render_settings


def render_top_bar(self, context):
    if context.region.alignment == 'TOP':
        return

    layout = self.layout
    row = layout.row(align=True)

    doodadset_mode = context.scene.wow_scene.doodadset_mode

    if proj_prefs := get_project_preferences():
       row.prop(proj_prefs, 'export_method_enum', text='Export Folder', icon='FILE_TICK')

    if context.scene.wow_scene.type == 'WMO':
        icon = 'CHECKBOX_HLT' if doodadset_mode else 'CHECKBOX_DEHLT'
        text = "Doodadset Mode ON" if doodadset_mode else "Doodadset Mode OFF"
        row.operator("scene.doodadset_mode", text=text, icon=icon)     
        row.operator("scene.save_current_wmo_collection", text="Save current WMO", icon='FILE_TICK')
    if context.scene.wow_scene.type == 'M2':
        row.operator("scene.save_current_m2", text="Save current M2", icon='FILE_TICK')   
    row.label(text='WoW Scene:')
    row.prop(context.scene.wow_scene, 'version', text='')
    row.prop(context.scene.wow_scene, 'type', text='')
    row.operator("scene.reload_wow_filesystem", text="", icon='FILE_REFRESH')


def render_viewport_toggles_left(self, context):
    layout = self.layout
    row = layout.row(align=True)
    row.operator("wow.toggle_image_alpha", icon='NODE_TEXTURE', text='')


menu_import_wmo = lambda self, ctx: self.layout.operator("import_mesh.wmo", text="WoW WMO (.wmo)")
menu_export_wmo = lambda self, ctx: self.layout.operator("export_mesh.wmo", text="WoW WMO (.wmo)")
menu_import_m2 = lambda self, ctx: self.layout.operator("import_mesh.m2", text="WoW M2 (.m2)")
menu_export_m2 = lambda self, ctx: self.layout.operator("export_mesh.m2", text="WoW M2 (.m2)")
#menu_test_m2 = lambda self, ctx: self.layout.operator("test.m2", text="Test M2 (.m2)")
menu_convert_bones = lambda self, ctx: self.layout.operator("convert_bones.m2", text="Convert Bones To WoW")
menu_print_m2_warnings = lambda self, ctx: self.layout.operator("print_warnings.m2", text="Print M2 Warnings")

def register():
    register_wow_scene_properties()
    bpy.types.TOPBAR_HT_upper_bar.append(render_top_bar)
    bpy.types.VIEW3D_HT_header.append(render_viewport_toggles_left)
    bpy.types.TOPBAR_MT_file_import.append(menu_import_wmo)
    bpy.types.TOPBAR_MT_file_import.append(menu_import_m2)
    bpy.types.TOPBAR_MT_file_export.append(menu_export_wmo)
    bpy.types.TOPBAR_MT_file_export.append(menu_export_m2)
    #bpy.types.TOPBAR_MT_file_import.append(menu_test_m2)
    # TODO: temporary, I don't know how to enable these without a panel
    bpy.types.TOPBAR_MT_file_export.append(menu_convert_bones)
    bpy.types.TOPBAR_MT_file_export.append(menu_print_m2_warnings)


def unregister():
    unregister_wow_scene_properties()
    bpy.types.TOPBAR_MT_file_import.remove(menu_import_wmo)
    bpy.types.TOPBAR_MT_file_import.remove(menu_import_m2)
    #bpy.types.TOPBAR_MT_file_import.remove(menu_test_m2)
    bpy.types.TOPBAR_MT_file_export.remove(menu_export_wmo)
    bpy.types.TOPBAR_MT_file_export.remove(menu_export_m2)
    bpy.types.TOPBAR_HT_upper_bar.remove(render_top_bar)
    bpy.types.VIEW3D_HT_header.append(render_viewport_toggles_left)
    bpy.types.TOPBAR_MT_file_export.remove(menu_convert_bones)
    bpy.types.TOPBAR_MT_file_export.remove(menu_print_m2_warnings)