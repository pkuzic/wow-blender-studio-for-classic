import bpy

from .common import panel_poll


class WMO_PT_texture(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "image"
    bl_label = "WMO Texture"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        col = layout.column()
        col.prop(context.edit_image.wow_wmo_texture, "path")

    @classmethod
    def poll(cls, context):
        return panel_poll(cls, context) and context.image is not None


class WowWMOTexturePropertyGroup(bpy.types.PropertyGroup):

    path:  bpy.props.StringProperty(
        name="Path",
        description="Warning: texture path is applied on a per-texture (per-image), not on per-material basis."
        )


def register():
    bpy.types.Image.wow_wmo_texture = bpy.props.PointerProperty(type=WowWMOTexturePropertyGroup)


def unregister():
    del bpy.types.Image.wow_wmo_texture
