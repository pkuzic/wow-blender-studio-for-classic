import bpy
from ..enums import *

class SetDefaultTexture(bpy.types.Operator):
    """Sets the texture to the default value 'textures\\ShaneCube.blp'"""
    bl_idname = "wow_m2_texture.set_default_texture"
    bl_label = "Set Default Texture"

    img_name:  bpy.props.StringProperty(options={'HIDDEN'})

    def execute(self, context):
        edit_image = bpy.data.images[self.img_name]
        edit_image.wow_m2_texture.path = "textures\\ShaneCube.blp"
        return {'FINISHED'}

class M2_PT_texture_panel(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "image"
    bl_label = "M2 Texture"

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(context.edit_image.wow_m2_texture, "flags")
        col.separator()
        col.prop(context.edit_image.wow_m2_texture, "texture_type")
        col.separator()
        # only show path setting if texture type is hardcoded
        if context.edit_image.wow_m2_texture.texture_type == "0":
            col.prop(context.edit_image.wow_m2_texture, "path", text='Path')
            if(len(context.edit_image.wow_m2_texture.path) == 0):
                op = col.operator(SetDefaultTexture.bl_idname, text="Set Default Texture", icon="CONSOLE")
                # todo: not a great method, but it should work reliably since this updates every frame
                op.img_name = context.edit_image.name

    @classmethod
    def poll(cls, context):
        return (context.scene is not None
                and context.scene.wow_scene.type == 'M2'
                and context.image is not None)


class WowM2TexturePropertyGroup(bpy.types.PropertyGroup):
    
    enabled:  bpy.props.BoolProperty()

    flags:  bpy.props.EnumProperty(
        name="Texture flags",
        description="WoW  M2 texture flags",
        items=TEXTURE_FLAGS,
        options={"ENUM_FLAG"},
        default={'1', '2'}
        )

    texture_type:  bpy.props.EnumProperty(
        name="Texture type",
        description="WoW  M2 texture type",
        items=TEXTURE_TYPES
        )

    path:  bpy.props.StringProperty(
        name='Path',
        description='Path to .blp file in wow file system.'
    )

    # self_pointer: bpy.props.PointerProperty(type=bpy.types.Image)

def register():
    bpy.types.Image.wow_m2_texture = bpy.props.PointerProperty(type=WowM2TexturePropertyGroup)


def unregister():
    del bpy.types.Image.wow_m2_texture
