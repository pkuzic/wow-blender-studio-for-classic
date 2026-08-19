from ensurepip import version
import bpy
from ....pywowlib.enums.m2_enums import M2EventTokens, M2SequenceNames

def update_event_type(self, context):
    # self.attachment_type.items.append
    pass

def set_event_types_enum(self, context):

    enum = []
    events = [obj.wow_m2_event.token for obj in bpy.data.objects if obj.type == 'EMPTY' and obj.wow_m2_event.enabled]

    for field in M2EventTokens:

        # TODO : versions
        # if version == lichking and field.value > 52 (?): return

        enum.append((str(field.value), field.name, ""))

    return enum

class M2_OT_add_Event(bpy.types.Operator):
    bl_idname = 'scene.m2_add_event'
    bl_label = 'Add event'
    bl_description = 'Add a M2 event object to the scene'
    bl_options = {'REGISTER', 'UNDO'}

    event_type: bpy.props.EnumProperty(
        name="Event type",
        description="Select M2 component entity objects",
        items=set_event_types_enum,

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


        event_type = self.event_type

        # obj.location = attachment.position
        obj.location = scn.cursor.location

        events = [obj for obj in bpy.data.objects if obj.type == 'EMPTY' and obj.wow_m2_event.enabled]

        bpy.context.view_layer.objects.active = obj

        # name based on selected attach type
        obj.name = ('Event_' + M2EventTokens.get_event_name(event_type))
        obj.wow_m2_event.enabled = True
        obj.wow_m2_event.token = str(event_type)

        # animate attachment
        obj.animation_data_create()
        obj.animation_data.action_blend_type = 'ADD'

        self.report({'INFO'}, "Successfully created M2 event: " + obj.name + "\nYou might want to edit the bone parent in object's constraint properties.")

        return {'FINISHED'}
