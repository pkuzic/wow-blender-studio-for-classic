import bpy

from ..custom_objects import WoWWMOGroup
from .common import panel_poll


class WMO_PT_vertex_info(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"
    bl_label = "WMO Vertex Info"

    def draw(self, context):
        self.layout.use_property_split = True
        self.layout.prop_search(context.object.wow_wmo_vertex_info, "vertex_group",
                                context.object, "vertex_groups", text="Collision vertex group"
                                )

        self.layout.prop(context.object.wow_wmo_vertex_info, "node_size", slider=True)

    @classmethod
    def poll(cls, context):
        obj = context.object
        return (panel_poll(cls, context)
                and obj is not None
                and WoWWMOGroup.match(obj)
                )


class WowVertexInfoPropertyGroup(bpy.types.PropertyGroup):

    vertex_group:  bpy.props.StringProperty()

    node_size:  bpy.props.IntProperty(
        name="Node max size",
        description="Max count of faces for a node in bsp tree on export. 0 = Dynamic based on face count",
        default=0, min=0,
        soft_max=1000
        )


def register():
    bpy.types.Object.wow_wmo_vertex_info = bpy.props.PointerProperty(type=WowVertexInfoPropertyGroup)


def unregister():
    del bpy.types.Object.wow_wmo_vertex_info
