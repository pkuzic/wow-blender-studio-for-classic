from ....utils.callbacks import on_release, string_property_validator, string_filter_internal_dir
from .common import panel_poll
from ..enums import root_flags_enum

import bpy


class WMO_PT_collection(bpy.types.Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'collection'
    bl_label = 'World Map Object'

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.enabled = context.collection.wow_wmo.enabled
        layout.prop(context.collection.wow_wmo, "dir_path")

        col = layout.column()

        col.separator()

        col.prop(context.collection.wow_wmo, "flags")
        col.separator()

        if "2" in context.collection.wow_wmo.flags:
            col.prop(context.collection.wow_wmo, "ambient_color")

        col.separator()

        col.prop(context.collection.wow_wmo, "skybox_path")
        col.prop(context.collection.wow_wmo, "wmo_id")

    def draw_header(self, context):
        layout = self.layout
        row = layout.row()
        row.prop(context.collection.wow_wmo, 'enabled', text='')

    @classmethod
    def poll(cls, context):
        return panel_poll(cls, context) and context.collection.name in context.scene.collection.children

@on_release()
def update_flags(self, context):
    properties = bpy.data.node_groups.get('MO_Properties')
    if properties:
        properties.nodes['IsRenderPathUnified'].outputs[0].default_value = int('2' in self.flags)
        properties.nodes['DoNotFixColorVertexAlpha'].outputs[0].default_value = int('1' in self.flags)


@on_release()
def update_ambient_color(self, context):
    properties = bpy.data.node_groups.get('MO_Properties')
    if properties:
        properties.nodes['IntAmbientColor'].outputs[0].default_value = self.ambient_color


class WoWWMOCollectionPropertyGroup(bpy.types.PropertyGroup):

    enabled: bpy.props.BoolProperty(
        name='Enabled'
        , description='Enable this collection as a WMO object.'
        , default=False
    )

    dir_path: bpy.props.StringProperty(
        name='Directory path'
        , description='Full path of the WMO in WoW filesystem.'
        , options={'TEXTEDIT_UPDATE'}
        , update=lambda self, ctx: string_property_validator(self, ctx
                                                             , name='dir_path'
                                                             , str_filter=string_filter_internal_dir
                                                             , lockable=True)
    )

    flags:  bpy.props.EnumProperty(
        name="Root flags",
        description="WoW WMO root flags",
        items=root_flags_enum,
        options={"ENUM_FLAG"},
        update=update_flags
        )
    
    ambient_color:  bpy.props.FloatVectorProperty(
        name="Ambient Color",
        subtype='COLOR',
        default=(1, 1, 1, 1),
        size=4,
        min=0.0,
        max=1.0,
        update=update_ambient_color
        )

    skybox_path:  bpy.props.StringProperty(
        name="Skybox Path",
        description="Skybox for WMO (.MDX)",
        default='',
        )

    wmo_id:  bpy.props.IntProperty(
        name="DBC ID",
        description="Used in WMOAreaTable (optional)",
        default=0,
        )   

def register():
    bpy.types.Collection.wow_wmo = bpy.props.PointerProperty(type=WoWWMOCollectionPropertyGroup)


def unregister():
    del bpy.types.Collection.wow_wmo
