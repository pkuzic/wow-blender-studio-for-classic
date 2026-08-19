import bpy

def can_apply_scale(fcurves,keyframe_count):
    for i in range(keyframe_count):
        x = fcurves[0].keyframe_points[i].co[1] if 0 in fcurves else 1
        y = fcurves[1].keyframe_points[i].co[1] if 1 in fcurves else 1
        z = fcurves[2].keyframe_points[i].co[1] if 2 in fcurves else 1
        if abs(x-y)>0.0001 or abs(x-z)>0.0001:
            return False
    return True

def make_fcurve_compound(fcurves, accept = lambda path: True):
    compound = {}
    for fcurve in fcurves:
        if not accept(fcurve.data_path):
            # print("not accepting data path :")
            # print(fcurve.data_path)
            continue
        if not fcurve.data_path in compound:
            compound[fcurve.data_path] = {}
        compound[fcurve.data_path][fcurve.array_index] = fcurve
    
    # print(compound)
    return compound

def get_bone_groups(obj, vertex, bone_names):
    groups = [el for el in vertex.groups if obj.vertex_groups[el.group].name in bone_names]
    groups.sort(key=lambda x: -x.weight)
    return groups

def _find_final_alias(self, n_global_sequences, alias_next):
    for i, anim_index in enumerate(self.animations):
        anim = bpy.context.scene.wow_m2_animations[alias_next + n_global_sequences]
        if '64' in anim.flags:
            alias_next = anim.alias_next
        else:
            return alias_next + n_global_sequences