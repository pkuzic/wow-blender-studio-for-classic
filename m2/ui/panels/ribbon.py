import bpy
from ..enums import *

from .utils import draw_object_list

class RibbonMaterialPointerPropertyGroup(bpy.types.PropertyGroup):
    pointer:  bpy.props.PointerProperty(
        name='Material',
        type=bpy.types.Material,
    )

class RibbonTexturePointerPropertyGroup(bpy.types.PropertyGroup):
    pointer:  bpy.props.PointerProperty(
        name='Texture',
        type=bpy.types.Image,
    )

class M2_PT_ribbon_panel(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
    bl_label = "M2 Ribbon"

    def draw_header(self, context):
        self.layout.prop(context.object.wow_m2_ribbon, "enabled", text="")

    def draw(self, context):
        layout = self.layout
    
        layout.enabled = context.object.wow_m2_ribbon.enabled
        col = layout.column()

        draw_object_list(
            context.object.wow_m2_ribbon,col,
            'Textures',
            'M2_UL_root_elements_textures_list',
            'wow_m2_ribbon',
            'textures',
            'cur_texture'
        )

        draw_object_list(
            context.object.wow_m2_ribbon,col,
            'Materials',
            'M2_UL_root_elements_materials_list',
            'wow_m2_ribbon',
            'materials',
            'cur_material'
        )
        col.prop(context.object.wow_m2_ribbon, 'color', text="Color")
        col.prop(context.object.wow_m2_ribbon, 'alpha', text="Alpha")
        col.prop(context.object.wow_m2_ribbon, 'height_above', text="Height Above")
        col.prop(context.object.wow_m2_ribbon, 'height_below', text="Height Below")
        col.prop(context.object.wow_m2_ribbon, 'texture_slot', text="Texture Slot")
        col.prop(context.object.wow_m2_ribbon, 'edges_per_second', text="Edges Per Second")
        col.prop(context.object.wow_m2_ribbon, 'edge_lifetime', text="Edges Lifetime")
        col.prop(context.object.wow_m2_ribbon, 'gravity', text="Gravity")
        col.prop(context.object.wow_m2_ribbon, 'texture_rows', text="Texture Rows")
        col.prop(context.object.wow_m2_ribbon, 'texture_cols', text="Texture Cols")
        col.prop(context.object.wow_m2_ribbon, 'priority_plane', text="Priority Plane")

    @classmethod
    def poll(cls, context):
        return (context.scene is not None
                and context.scene.wow_scene.type == 'M2'
                and context.object is not None
                and context.object.type == 'EMPTY'
                and not (context.object.wow_m2_event.enabled
                         or context.object.wow_m2_uv_transform.enabled
                         or context.object.wow_m2_camera.enabled
                         or context.object.wow_m2_attachment.enabled
                         or context.object.wow_m2_particle.enabled
                         )
        )

class WowM2RibbonPropertyGroup(bpy.types.PropertyGroup):
    enabled:  bpy.props.BoolProperty(
        name='Enabled',
        description='Enabled this object to be a WoW M2 Ribbon',
        default=False
    )

    textures: bpy.props.CollectionProperty(type=RibbonTexturePointerPropertyGroup)
    cur_texture: bpy.props.IntProperty()

    materials: bpy.props.CollectionProperty(type=RibbonMaterialPointerPropertyGroup)
    cur_material: bpy.props.IntProperty()

    color: bpy.props.FloatVectorProperty(
        name = "Color",
        description="",
        subtype='COLOR',
        size=3,
        default=(1.0,1.0,1.0),
        min=0.0,
        max=1.0
    )

    alpha: bpy.props.FloatProperty(
        name = "Alpha",
        description="",
        default=0,
        min=0,
        max=1
    )

    height_above: bpy.props.FloatProperty(
        name = "Height Above",
        description="",
        default=0
    )

    height_below: bpy.props.FloatProperty(
        name = "Height Below",
        description="",
        default=0
    )

    texture_slot: bpy.props.IntProperty(
        name = "Texture Slot",
        description = "",
        default = 0
    )

    visibility: bpy.props.IntProperty(
        name = "Visibility",
        description = "",
        default = 0
    )

    edges_per_second: bpy.props.FloatProperty(
        name = "Edges Per Second",
        description = "",
        default = 0
    )

    edge_lifetime: bpy.props.FloatProperty(
        name = "Edges Lifetime",
        description = "",
        default = 0
    )

    gravity: bpy.props.FloatProperty(
        name = "Gravity",
        description = "",
        default = 0
    )

    texture_rows: bpy.props.IntProperty(
        name = "Texture Rows",
        description = "",
        default = 0
    )

    texture_cols: bpy.props.IntProperty(
        name = "Texture Cols",
        description = "",
        default = 0
    )


    priority_plane: bpy.props.IntProperty(
        name = "Priority Plane",
        description = "",
        default = 0
    )

def register():
    bpy.types.Object.wow_m2_ribbon =  bpy.props.PointerProperty(type=WowM2RibbonPropertyGroup)

def unregister():
    del bpy.types.Object.wow_m2_ribbon