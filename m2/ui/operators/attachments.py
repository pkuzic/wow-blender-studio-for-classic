from ensurepip import version
import bpy
from ....pywowlib.enums.m2_enums import M2AttachmentTypes, M2SequenceNames
# from ...ui.enums import get_attachment_types

def update_attachment_type(self, context):
    # self.attachment_type.items.append
    pass

def set_attachment_types_enum(self, context):

    enum = []
    attachments = [obj.wow_m2_attachment.type for obj in bpy.data.objects if obj.type == 'EMPTY' and obj.wow_m2_attachment.enabled]

    for i, field in enumerate(M2AttachmentTypes):
        if i not in attachments:
            if context.scene.wow_scene.version == '2' and i <= 46:
                enum.append((str(field.value), field.name, ""))
            elif context.scene.wow_scene.version == '6':
                enum.append((str(field.value), field.name, ""))
    return enum

class M2_OT_add_attachment(bpy.types.Operator):
    bl_idname = 'scene.m2_add_attachment'
    bl_label = 'Add attachment'
    bl_description = 'Add a M2 attachment object to the scene'
    bl_options = {'REGISTER', 'UNDO'}

    attachment_type: bpy.props.EnumProperty(
        name="Attachment type",
        description="Select M2 component entity objects",
        # items=get_attachment_types,
        items=set_attachment_types_enum,
        # default='19'
        # update=update_attachment_type
    )

    def execute(self, context):

        scn = bpy.context.scene

        bpy.ops.object.empty_add(type='SPHERE', location=(0, 0, 0))

        obj = bpy.context.view_layer.objects.active

        obj.empty_display_size = 0.07
        bpy.ops.object.constraint_add(type='CHILD_OF')
        constraint = obj.constraints[-1]

        rig = list(filter(lambda ob: ob.type == 'ARMATURE' and not ob.hide_get(), bpy.context.scene.objects))[0]

        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='EDIT')

        armature = rig.data

        constraint.target = rig
        obj.parent = rig
        # TODO : find or create matching animation bone ?
        if len(armature.edit_bones) > 0:
            bone = armature.edit_bones[0]
            constraint.subtarget = bone.name

        bpy.ops.object.mode_set(mode='OBJECT')


        attachment_id = self.attachment_type

        # obj.location = attachment.position
        obj.location = scn.cursor.location

        attachments = [obj for obj in bpy.data.objects if obj.type == 'EMPTY' and obj.wow_m2_attachment.enabled]

        bpy.context.view_layer.objects.active = obj

        # name based on selected attach type
        obj.name = M2AttachmentTypes.get_attachment_name(int(attachment_id), len(attachments))
        obj.wow_m2_attachment.enabled = True
        obj.wow_m2_attachment.type = str(attachment_id)

        # animate attachment
        obj.animation_data_create()
        obj.animation_data.action_blend_type = 'ADD'

        bpy.ops.wbs.viewport_text_display('INVOKE_DEFAULT', message="Info: Successfully created attachment: " + obj.name + "!", font_size=24, y_offset=67)
        bpy.ops.wbs.viewport_text_display('INVOKE_DEFAULT', message="You might want to edit the bone parent in object's constraint properties.", font_size=24, y_offset=100)
        self.report({'INFO'}, "Successfully created M2 attachment: " + obj.name + "\nYou might want to edit the bone parent in object's constraint properties.")

        # for attachment in attachments:
        #     if attachment.wow_m2_attachment.type == attachment_id:
        #         self.report({'WARNING'}, 'An attachment of this type already exists in the model.')

        return {'FINISHED'}
