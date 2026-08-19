import bpy
import re
from mathutils import Matrix, Vector, Quaternion
from ..util import can_apply_scale,make_fcurve_compound,get_bone_groups

def convert_m2_bones():
    def fix_scale(matrix,curves,keyframe_count):
        if not can_apply_scale(curves,keyframe_count):
            return (True,'Non-uniform scaling')

        for i in range(keyframe_count):
            def co(j): return fcurves[j].keyframe_points[i].co
            # read vector defining the old rotation
            vec = Vector((co(0)[1], co(1)[1], co(2)[1]))

            # TODO: CHANGE VECTOR USING 'matrix' HERE SOMEHOW

            # write vector back
            co(0)[1] = vec.x
            co(1)[1] = vec.y
            co(2)[1] = vec.z

        return (False,'')

    def fix_rotation(matrix,fcurves,keyframe_count):
        def quat_dist(q1,q2):
            # takes polarity into account on purpose.
            # we just want to do _mostly_ correct rotations,
            # but there might be a better formula to use here.
            return (
                pow(q1.w-q2.w,2) +
                pow(q1.x-q2.x,2) +
                pow(q1.y-q2.y,2) +
                pow(q1.z-q2.z,2))

        last_quat = None
        for i in range(keyframe_count):
            def co(j): return fcurves[j].keyframe_points[i].co

            q_in = Quaternion((co(0)[1], co(1)[1], co(2)[1], co(3)[1]))
            axis,angle = q_in.to_axis_angle()
            axis.rotate(matrix)

            rot_q = Quaternion(axis,angle)
            if last_quat is None:
                last_quat = rot_q
            else:
                rot_q_neg = Quaternion(-rot_q)
                dist = quat_dist(rot_q,last_quat)
                neg_dist = quat_dist(rot_q_neg,last_quat)
                last_quat = rot_q if dist <= neg_dist else rot_q_neg

            co(0)[1] = last_quat.w
            co(2)[1] = last_quat.x
            co(1)[1] = -last_quat.y
            co(3)[1] = last_quat.z
        return (False,'')

    def fix_location(matrix, fcurves,keyframe_count):
        for i in range(keyframe_count):
            def co(j): return fcurves[j].keyframe_points[i].co
            vec = Vector((co(0)[1],co(1)[1], co(2)[1]))
            vec.rotate(matrix)

            co(1)[1] = vec.x
            co(0)[1] = -vec.y
            co(2)[1] = vec.z
        return (False,'')

    def fix_curves(name, matrix, fcurves, track_count, callback):
        for i in range(track_count):
            if not i in fcurves:
                raise ValueError(f'Track index {i} missing in {name} fcurves')

        keyframe_count = len(fcurves[0].keyframe_points)
        for i,fcurve in fcurves.items():
            cur_count = len(fcurve.keyframe_points)
            if cur_count != keyframe_count:
                raise ValueError(f'Track index {i} keyframe count ({cur_count}) is different from index 0 {keyframe_count}')

        for i in range(keyframe_count):
            time = fcurves[0].keyframe_points[i].co[0]
            for j in range(track_count):
                cur_time = fcurves[j].keyframe_points[i].co[0]
                if cur_time != time:
                    raise ValueError(f'Track index {j} frame {j} has a different time value ({cur_time}) from index 0 ({time})')

        return callback(matrix,fcurves,keyframe_count)

    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')

    fixed_vertices = 0
    for obj in bpy.data.objects:
        if obj.type != 'MESH' or obj.parent is None or obj.parent.type != 'ARMATURE':
            continue
        
        bone_names = [bone.name for bone in obj.parent.data.bones]
        for vertex in obj.data.vertices:
            groups = get_bone_groups(obj, vertex, bone_names)
            for el in groups[4:]:
                obj.vertex_groups[el.group].remove([vertex.index])
            if len(groups) > 4:
                fixed_vertices += 1
    print(f'Removed overflowing groups for {fixed_vertices} vertices')

    for action in bpy.data.actions:
        removed_fcurves = []
        for curve in action.fcurves:
            if curve.data_path in ["location","rotation_euler","scale"]:
                removed_fcurves.append(curve)
                print(f'Removed fcurve "{curve.data_path}[{curve.array_index}]" from action {action.name}')
        for curve in removed_fcurves:
            action.fcurves.remove(curve)

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=False)
    bpy.ops.object.select_all(action='DESELECT')

    changed_bones = {}
    changed_objects = []

    for obj in bpy.data.objects:
        if obj.type != 'ARMATURE': continue

        try:
            obj.select_set(True)
        except RuntimeError as e:
            print(f"Unable to select armature {obj.name}, not converting it")
            continue

        changed_objects.append(obj)
        
        #this was enabled in 3.0 and worked better i think
        bpy.ops.object.mode_set(mode='EDIT')

        for bone in obj.data.edit_bones:
            if bone.use_connect:
                bone.use_connect = False

        for bone in obj.data.edit_bones:
            bone.use_connect = False
            bone.roll = 0
            bone.tail = bone.head + Vector((1,0,0))
            changed_bones[bone.name] = Matrix(obj.data.bones[bone.name].matrix_local)
        bpy.ops.object.mode_set(mode='OBJECT')

    for action in bpy.data.actions:
        fcurve_compounds = make_fcurve_compound(action.fcurves,
            lambda path: path.startswith('pose.bones')
        )
        for key,fcurves in fcurve_compounds.items():
            bone = re.search('"(.+?)"',key).group(1)
            if not bone in changed_bones:
                continue
            matrix = changed_bones[bone]
            curve_type = re.search('([a-zA-Z_]+)$',key).group(0)

            remove_reason = None
            should_remove = False
            if curve_type == 'scale':
                (should_remove,remove_reason) = fix_curves(key,matrix,fcurves,3,fix_scale)

            if curve_type == 'location':
                (should_remove,remove_reason) = fix_curves(key,matrix,fcurves,3,fix_location)

            if curve_type == 'rotation_quaternion':
                (should_remove,remove_reason) = fix_curves(key,matrix,fcurves,4,fix_rotation)

            if should_remove:
                print(f"Deleting incompatible fcurves {fcurve.data_path}: {remove_reason}")
                for fcurve in fcurves.values():
                    action.fcurves.remove(fcurve)
                    for obj in changed_objects:
                        bpy.ops.object.mode_set(mode='OBJECT')
                        bpy.ops.object.select_all(action='DESELECT')
                        obj.select_set(True)
                        bpy.ops.object.mode_set(mode='POSE')
                        # clear other curves if needed
                        bpy.ops.pose.scale_clear()
                        bpy.ops.object.mode_set(mode='OBJECT')
                        bpy.ops.object.select_all(action='DESELECT')
            else:
                for fcurve in fcurves.values():
                    fcurve.update()