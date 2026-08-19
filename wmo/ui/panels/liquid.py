from ..custom_objects import WoWWMOLiquid
from ....ui.panels import WBS_PT_object_properties_common
from ....ui.enums import WoWSceneTypes

import bpy

class WMO_PT_liquid(WBS_PT_object_properties_common, bpy.types.Panel):
    bl_label = "WMO Liquid"
    bl_context = "object"

    __wbs_custom_object_type__ = WoWWMOLiquid
    __wbs_scene_type__ = WoWSceneTypes.WMO

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        layout.prop(context.object.wow_wmo_liquid, "color")


class WowLiquidPropertyGroup(bpy.types.PropertyGroup):

    enabled:  bpy.props.BoolProperty()

    color:  bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        default=(0.08, 0.08, 0.08, 1.0),
        size=4,
        min=0.0,
        max=1.0
        )


def register():
    bpy.types.Object.wow_wmo_liquid = bpy.props.PointerProperty(type=WowLiquidPropertyGroup)


def unregister():
    del bpy.types.Object.wow_wmo_liquid
