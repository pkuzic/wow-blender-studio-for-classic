from .liquid import WMO_PT_liquid
from ..enums import *
from ..custom_objects import WoWWMOGroup
from ....ui.panels import WBS_PT_object_properties_common
from ....ui.enums import WoWSceneTypes
from ..custom_objects import *
from ..collections import get_wmo_collection, SpecialCollections

from collections import namedtuple
import bpy


class WMO_PT_wmo_group(WBS_PT_object_properties_common, bpy.types.Panel):
    bl_label = "WMO Group"
    bl_context = "object"

    __wbs_custom_object_type__ = WoWWMOGroup
    __wbs_scene_type__ = WoWSceneTypes.WMO

    def draw(self, context):
        self.layout.use_property_split = True

        col = self.layout.column()
        col.prop(context.object.wow_wmo_group, "export_order")

        col.separator()

        col.prop(context.object.wow_wmo_group, "description")

        col.separator()
        col.prop(context.object.wow_wmo_group, "flags")

        col.separator()
        box = col.box()
        box.prop(context.object.wow_wmo_group, "fog1")
        box.prop(context.object.wow_wmo_group, "fog2")
        box.prop(context.object.wow_wmo_group, "fog3")
        box.prop(context.object.wow_wmo_group, "fog4")

        col.separator()
        col.prop(context.object.wow_wmo_group, "group_dbc_id")
        col.prop(context.object.wow_wmo_group, "liquid_type")

        box = col.box()
        box.prop(context.object.wow_wmo_group, "liquid_mesh")

        if context.object.wow_wmo_group.liquid_mesh:
            ctx_override = namedtuple('ctx_override', ('layout', 'object'))
            ctx = ctx_override(box, context.object.wow_wmo_group.liquid_mesh)
            WMO_PT_liquid.draw(ctx, ctx)

        box.prop(context.object.wow_wmo_group, "collision_mesh")


def fog_validator(self, context):
    scn = bpy.context.scene
    if self.fog1 and (not WoWWMOFog.match(self.fog1) or self.fog1.name not in get_wmo_collection(scn, SpecialCollections.Fogs).objects):
        self.fog1 = None

    if self.fog2 and (not WoWWMOFog.match(self.fog2) or self.fog2.name not in get_wmo_collection(scn, SpecialCollections.Fogs).objects):
        self.fog2 = None

    if self.fog3 and (not WoWWMOFog.match(self.fog3) or self.fog3.name not in get_wmo_collection(scn, SpecialCollections.Fogs).objects):
        self.fog3 = None

    if self.fog4 and (not WoWWMOFog.match(self.fog4) or self.fog4.name not in get_wmo_collection(scn, SpecialCollections.Fogs).objects):
        self.fog4 = None


def update_flags(self, context):

    obj = context.object

    if not obj:
        obj = context.view_layer.objects.active

    if not obj:
        return

    if '0' in self.flags:
        obj.pass_index |= 0x20  # BlenderWMOObjectRenderFlags.HasVertexColor
        mesh = obj.data
        if 'Col' not in mesh.color_attributes:
            vertex_color_layer = mesh.color_attributes.new(name="Col", type='BYTE_COLOR', domain='POINT')
    else:
        obj.pass_index &= ~0x20

    if '1' in self.flags:
        obj.pass_index |= 0x4  # BlenderWMOObjectRenderFlags.NoLocalLight
    else:
        obj.pass_index &= ~0x4


class WowWMOGroupPropertyGroup(bpy.types.PropertyGroup):

    description:  bpy.props.StringProperty(
        name="Description",
        description='Saved in the WMO file.'
    )

    export_order: bpy.props.IntProperty(
        name="Export Order",
        min=0,
        max=999
    )

    flags:  bpy.props.EnumProperty(
        items=group_flag_enum,
        options={'ENUM_FLAG'},
        update=update_flags
        )

    group_dbc_id:  bpy.props.IntProperty(
        name="DBC Group ID",
        description="WMO Group ID in DBC file"
        )

    liquid_type:  bpy.props.EnumProperty(
        items=liquid_type_enum,
        name="LiquidType",
        description="Fill this WMO group with selected liquid."
        )

    fog1:  bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Fog #1",
        poll=lambda self, obj: WoWWMOFog.match(obj) and obj.name in get_wmo_collection(bpy.context.scene, SpecialCollections.Fogs).objects,
        update=fog_validator
    )

    fog2:  bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Fog #2",
        poll=lambda self, obj: WoWWMOFog.match(obj) and obj.name in get_wmo_collection(bpy.context.scene, SpecialCollections.Fogs).objects,
        update=fog_validator
    )

    fog3:  bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Fog #3",
        poll=lambda self, obj: WoWWMOFog.match(obj) and obj.name in get_wmo_collection(bpy.context.scene, SpecialCollections.Fogs).objects,
        update=fog_validator
    )

    fog4:  bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Fog #4",
        poll=lambda self, obj: WoWWMOFog.match(obj) and obj.name in get_wmo_collection(bpy.context.scene, SpecialCollections.Fogs).objects,
        update=fog_validator
    )

    collision_mesh:  bpy.props.PointerProperty(
        type=bpy.types.Object,
        name='Collision',
        description='Invisible collision geometry of this group',
        poll=lambda self, obj: obj.type == 'MESH' and obj.name in get_wmo_collection(bpy.context.scene, SpecialCollections.Collision).objects
    )

    liquid_mesh: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name='Liquid',
        description='Liquid plane linked to this group',
        poll=lambda self, obj: obj.type == 'MESH' and WoWWMOLiquid.match(obj)
    )


def register():
    bpy.types.Object.wow_wmo_group = bpy.props.PointerProperty(type=WowWMOGroupPropertyGroup)


def unregister():
    del bpy.types.Object.wow_wmo_group
