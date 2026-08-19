from collections import namedtuple
import bpy
from ..enums import *


class M2_PT_geoset_panel(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
    bl_label = "M2 Geoset"

    def draw(self, context):
        self.layout.prop(context.object.wow_m2_geoset, "collision_mesh")

        if not context.object.wow_m2_geoset.collision_mesh:
            self.layout.prop(context.object.wow_m2_geoset, "mesh_part_group")
            self.layout.prop(context.object.wow_m2_geoset, "mesh_part_id")

    @classmethod
    def poll(cls, context):
        return (context.scene is not None
                and context.scene.wow_scene.type == 'M2'
                and context.object is not None
                and context.object.data is not None
                and isinstance(context.object.data, bpy.types.Mesh))


class WowM2GeosetPropertyGroup(bpy.types.PropertyGroup):
    
    enabled:  bpy.props.BoolProperty()
    
    collision_mesh:  bpy.props.BoolProperty(
        name='Collision mesh',
        default=False
    )

    mesh_part_group:  bpy.props.EnumProperty(
        name="Geoset group",
        description="Group of this geoset",
        items=MESH_PART_TYPES
    )

    mesh_part_id:  bpy.props.EnumProperty(
        name="Geoset ID",
        description="Mesh part ID of this geoset",
        items=mesh_part_id_menu
    )

#############

def register():
    bpy.types.Object.wow_m2_geoset = bpy.props.PointerProperty(type=WowM2GeosetPropertyGroup)


def unregister():
    del bpy.types.Object.wow_m2_geoset

