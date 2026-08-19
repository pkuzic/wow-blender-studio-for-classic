import bpy
from ..enums import *


class M2_PT_bone_panel(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "bone"
    bl_label = "M2 Bone"

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(context.edit_bone.wow_m2_bone, "key_bone_id")
        col.separator()
        col.prop(context.edit_bone.wow_m2_bone, "flags")
        col.separator()
        col.prop(context.edit_bone.wow_m2_bone, "sort_index")
        col.separator()
        col.prop(context.edit_bone.wow_m2_bone, "submesh_id")
        col.separator()
        col.prop(context.edit_bone.wow_m2_bone, "bone_name_crc")

    @classmethod
    def poll(cls, context):
        return (context.scene is not None
                and context.scene.wow_scene.type == 'M2'
                and context.edit_bone is not None)


class WowM2BonePropertyGroup(bpy.types.PropertyGroup):
    key_bone_id:  bpy.props.EnumProperty(
        name="Keybone",
        description="WoW bone keybone ID",
        items=get_keybone_ids
    )

    flags:  bpy.props.EnumProperty(
        name="Bone flags",
        description="WoW bone flags",
        items=BONE_FLAGS,
        options={"ENUM_FLAG"}
    )

    sort_index:  bpy.props.IntProperty(
        name='Sort Index',
        description="Used to sort bones when exporting M2 files. All bones must have this >= 0 or this setting is ignored",
        default=-1
    )

    submesh_id:  bpy.props.IntProperty(
        name='Unknown value #1',
        description="Unused (submesh_id)",
        min=0,
        max=65535,
        default=0
    )

    bone_name_crc:  bpy.props.IntProperty(
        name='Unknown value #2 (bone_name_crc)',
        description="Unused (bone_name_crc) (stored as int32, most readers read it as a uint32)",
        default=0
    )


def register():
    bpy.types.EditBone.wow_m2_bone =  bpy.props.PointerProperty(type=WowM2BonePropertyGroup)


def unregister():
    del bpy.types.EditBone.wow_m2_bone

