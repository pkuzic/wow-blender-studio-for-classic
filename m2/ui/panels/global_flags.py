import bpy
from ..enums import *

class M2_PT_global_flags_panel(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
    bl_label = "M2 Global Flags"

    def draw_header(self, context):
        self.layout.prop(context.object.wow_m2_globalflags, "enabled", text="")

    def draw(self, context):
        layout = self.layout
        layout.enabled = context.object.wow_m2_globalflags.enabled
        col = layout.column()
        globalflags = context.object.wow_m2_globalflags
        col.label(text='Flags')
        if context.scene.wow_scene.version == '2':
            col.prop(globalflags, 'flagsLK', text='Flags')
        if context.scene.wow_scene.version == '6':
            col.prop(globalflags, 'flagsLK', text='Flags')
            col.prop(globalflags, 'flagsLegion', text='Flags')

    @classmethod
    def poll(cls, context):
        return (context.object is not None and
                context.object.type == 'ARMATURE' and
                context.scene is not None and
                context.scene.wow_scene.type == 'M2')    

class WowM2globalflagsPropertyGroup(bpy.types.PropertyGroup):
    enabled:  bpy.props.BoolProperty(
        name='Enabled',
        description='Enable this armature to have M2 globalflags',
        default=False
    )

    flagsLK:  bpy.props.EnumProperty(
        name="Global flags",
        description="",
        items=GLOBAL_FLAGS[:5],
        options={"ENUM_FLAG"}
    )

    flagsLegion:  bpy.props.EnumProperty(
        name="Global flags",
        description="",
        items=GLOBAL_FLAGS[5:],
        options={"ENUM_FLAG"}
    )

def register():
    bpy.types.Object.wow_m2_globalflags = bpy.props.PointerProperty(type=WowM2globalflagsPropertyGroup)


def unregister():
    del bpy.Object.wow_m2_globalflags

