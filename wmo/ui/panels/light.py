import bpy

from ..enums import *
from ..custom_objects import WoWWMOLight
from ....ui.panels import WBS_PT_object_properties_common
from ....ui.enums import WoWSceneTypes


class WMO_PT_light(WBS_PT_object_properties_common, bpy.types.Panel):
    bl_label = "WMO Light"
    bl_context = "data"

    __wbs_custom_object_type__ = WoWWMOLight
    __wbs_scene_type__ = WoWSceneTypes.WMO

    def draw(self, context):
        self.layout.use_property_split = True
        self.layout.prop(context.object.wow_wmo_light, "light_type")
        self.layout.prop(context.object.wow_wmo_light, "use_attenuation")
        self.layout.prop(context.object.wow_wmo_light, "color")
        self.layout.prop(context.object.wow_wmo_light, "intensity")
        self.layout.prop(context.object.wow_wmo_light, "attenuation_start")
        self.layout.prop(context.object.wow_wmo_light, "attenuation_end")


class WowLightPropertyGroup(bpy.types.PropertyGroup):

    enabled: bpy.props.BoolProperty()

    light_type:  bpy.props.EnumProperty(
        items=light_type_enum,
        name="Type",
        description="Type of the lamp"
        )

    type:  bpy.props.BoolProperty(
        name="Type",
        description="Unknown"
        )

    use_attenuation:  bpy.props.BoolProperty(
        name="Use attenuation",
        description="True if lamp uses attenuation"
        )

    padding:  bpy.props.BoolProperty(
        name="Padding",
        description="True if lamp uses padding"
        )

    color:  bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        default=(1, 1, 1),
        min=0.0,
        max=1.0
        )

    intensity:  bpy.props.FloatProperty(
        name="Intensity",
        description="Intensity of the lamp"
        )

    color_alpha:  bpy.props.FloatProperty(
        name="ColorAlpha",
        description="Color alpha",
        default=1,
        min=0.0,
        max=1.0
        )

    attenuation_start:  bpy.props.FloatProperty(
        name="Attenuation start",
        description="Distance at which light intensity starts to decrease"
        )

    attenuation_end:  bpy.props.FloatProperty(
        name="Attenuation end",
        description="Distance at which light intensity reach 0"
        )


def register():
    bpy.types.Object.wow_wmo_light = bpy.props.PointerProperty(type=WowLightPropertyGroup)


def unregister():
    del bpy.types.Object.wow_wmo_light


