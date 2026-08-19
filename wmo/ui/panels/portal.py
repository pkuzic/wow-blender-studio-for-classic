from ..enums import *
from ..custom_objects import WoWWMOPortal
from ....ui.panels import WBS_PT_object_properties_common
from ....ui.enums import WoWSceneTypes
from ....wmo.ui.custom_objects import WoWWMOGroup
from ....wmo.ui.collections import get_wmo_groups_list
from ...ui.enums import SpecialCollections
from ...ui.collections import get_wmo_collection

import bpy


class WMO_PT_portal(WBS_PT_object_properties_common, bpy.types.Panel):
    bl_label = "WMO Portal"
    bl_context = "object"

    __wbs_custom_object_type__ = WoWWMOPortal
    __wbs_scene_type__ = WoWSceneTypes.WMO

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        column = layout.column()
        column.prop(context.object.wow_wmo_portal, "first")
        column.prop(context.object.wow_wmo_portal, "second")

        col = layout.column()

        col.separator()
        col.prop(context.object.wow_wmo_portal, "detail", expand=True)

        col.separator()
        col.prop(context.object.wow_wmo_portal, "algorithm", expand=True)


def portal_validator(self, context):
    if self.second and not WoWWMOGroup.match(self.second):
        self.second = None

    if self.first and not WoWWMOGroup.match(self.first):
        self.first = None

def build_first_group_list(self, context):
    obj_list = []
    # print(bpy.data.collections.get('Outdoor').objects)
    scn = bpy.context.scene
    for outdoor_obj in list(get_wmo_collection(scn, SpecialCollections.Outdoor).objects):
        # print(outdoor_obj)
        if self.second != outdoor_obj and outdoor_obj.name:
            obj_list.append(outdoor_obj)
    
    for indoor_obj in list(get_wmo_collection(scn, SpecialCollections.Indoor).objects):
        print(indoor_obj)
        if self.second != indoor_obj and indoor_obj.name:
            obj_list.append(indoor_obj)
    
    return obj_list


class WowPortalPlanePropertyGroup(bpy.types.PropertyGroup):

    first:  bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="First group",
        poll=lambda self, obj: WoWWMOGroup.match(obj) and self.second != obj and obj.name in bpy.context.scene.objects,

        update=portal_validator
    )

    second:  bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Second group",
        # doesn't work
        # poll=lambda self, obj: WoWWMOGroup.match(obj) and self.first != obj and obj.name 
        #     in get_wmo_groups_list(bpy.context.scene),
        poll=lambda self, obj: WoWWMOGroup.match(obj) and self.first != obj and obj.name in bpy.context.scene.objects,
        update=portal_validator
    )

    detail: bpy.props.EnumProperty(
        items=portal_detail_enum,
        name="Detail",
        description="Disable this group will only work as a target for the portal. "
                    "See Stormwind cathedral for reference.",
        default="0"
    )

    portal_id:  bpy.props.IntProperty(
        name="Portal's ID",
        description="Portal ID"
    )

    algorithm:  bpy.props.EnumProperty(
        items=portal_dir_alg_enum,
        name="Algorithm",
        default="0"
    )


def register():
    bpy.types.Object.wow_wmo_portal = bpy.props.PointerProperty(type=WowPortalPlanePropertyGroup)


def unregister():
    del bpy.types.Object.wow_wmo_portal

