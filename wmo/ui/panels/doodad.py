from ....ui.locks import DepsgraphLock
from ....ui.panels import WBS_PT_object_properties_common
from ....ui.enums import WoWSceneTypes
from ..custom_objects import WoWWMODoodad

import bpy


class WMO_PT_doodad(WBS_PT_object_properties_common, bpy.types.Panel):
    bl_label = "WMO Doodad"
    bl_context = "object"

    __wbs_custom_object_type__ = WoWWMODoodad
    __wbs_scene_type__ = WoWSceneTypes.WMO

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(context.object.wow_wmo_doodad, "path")
        layout.prop(context.object.wow_wmo_doodad, "color")

        col = layout.column()
        col.prop(context.object.wow_wmo_doodad, "flags")


def update_doodad_color(self, context):
    mesh = self.id_data.data
    # print(mesh) # <bpy_struct, Object("BOOTSLEATHERBROWN01.011") at 0x0000017A1A837208>
    # print(type(mesh)) # <class 'bpy_types.Object'>
    with DepsgraphLock():
        for mat in mesh.materials: # TODO : this broke somehow
            # mat.node_tree.nodes['DoodadColor'].outputs[0].default_value = self.color
            mat.node_tree.nodes['DoodadColor'].attribute_type = 'OBJECT'
            mat.node_tree.nodes['DoodadColor'].attribute_name = 'wow_wmo_doodad.color'


class WoWDoodadPropertyGroup(bpy.types.PropertyGroup):

    enabled:  bpy.props.BoolProperty()
    """ Set by operators. To make an object a doodad. """

    path:  bpy.props.StringProperty(name="Path", description='Path of doodad in WoW filesystem.')

    color:  bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        size=4,
        default=(1, 1, 1, 1),
        min=0.0,
        max=1.0,
        update=update_doodad_color
    )

    flags:  bpy.props.EnumProperty(
        name="Settings",
        description="WoW doodad instance settings",
        items=[("1", "Accept Projected Tex.", ""),
               ("2", "Adjust lighting", ""),
               ("4", "Unknown", ""),
               ("8", "Unknown", "")],
        options={"ENUM_FLAG"}
    )


def register():
    bpy.types.Object.wow_wmo_doodad = bpy.props.PointerProperty(type=WoWDoodadPropertyGroup)


def unregister():
    bpy.types.Object.wow_wmo_doodad = None
