import bpy
import re
from mathutils import Vector
from ..util import can_apply_scale, make_fcurve_compound,get_bone_groups

def wrong_scene_type():
    name = "Wrong Scene Type"
    description = [
        'Issue: The scene type is set to WMO instead of M2',
        'Fix: Change the scene type to "M2" in the top-right corner of blender'
    ]
    items = []

    if not bpy.context.scene:
        items.append(f"Wrong scene: There is no scene object, please report this (i don't know how this can happen)")
    if bpy.context.scene.wow_scene.type != 'M2':
        items.append(f"Wrong scene: Type is {bpy.context.scene.wow_scene.type} but should be M2")

    return (name,description,items)

def transformed_objects():
    name = "Transformed Objects"
    description = [
        'Issue: Objects in the scene are transformed in any way (moved, rotated or scaled)',
        'Fix: Run the "Convert Bones To WoW" command and fix any issues it might cause.'
    ]
    items = []

    def vec_eq(n, q1,q2):
        for i in range(n):
            if q1[i] != q2[i]:
                return False
        return True

    def vec_str(value,names):
        str_out = ""
        for i,name in enumerate(names):
            str_out += names[i] + "=" + str(value[i]) + " "
        return str_out

    for obj in bpy.data.objects:
        if obj.type not in  ('ARMATURE', 'MESH'):
            continue

        def compare(name,names,val1,val2):
            if not vec_eq(len(names),val1,val2):
                items.append(f"Object {obj.name}s {name} is {vec_str(val1,names)}, but should be {vec_str(val2,names)}")

        vec_names = ['x','y','z']
        quat_names = ['w','x','y','z']

        compare("location",vec_names,obj.location,(0,0,0))
        compare("scale ",vec_names,obj.scale,(1,1,1))
        if obj.rotation_mode == 'QUATERNION':
            compare("quaternion rotation",quat_names,obj.rotation_quaternion,(1,0,0,0))
        elif obj.rotation_mode == 'AXIS_ANGLE':
            compare("axis angle rotation",quat_names,obj.rotation_quaternion,(1,0,0,0))
        else:
            compare("euler rotation",vec_names,obj.rotation_euler,(0,0,0))

    return (name,description,items)

def empty_textures():
    name = "Empty Textures"
    description = [
        'Issue: An M2 material has no texture set in any of its texture slots.',
        'Effect: Will usually cause the model to become invisible ingame',
        "Note: this is not *always* an error, not all materials have textures."
    ]
    items = []
    for obj in bpy.data.objects:
        if not obj.wow_m2_geoset.collision_mesh:
            for slot in obj.material_slots:
                if slot.material.wow_m2_material.texture_1 is None:
                    items.append(f'Object {obj.name} has no m2 textures, this is usually an error and will cause the model to be invisible ingame')

    return (name,description,items)

def empty_texture_paths():
    name = "Empty Texture Path"
    description = [
        'Issue: A model has an M2 material with a texture set that has no blp path',
        'Effect: Will usually cause the model to become invisible ingame',
        'Fix: Find the material with the texture and fill the Texture Path',
    ]
    items = []

    texture_maps = {}
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and not obj.wow_m2_geoset.collision_mesh and len(obj.material_slots) != 0:
            for slot in obj.material_slots:
                
                if slot.material is None:
                    continue

                if not hasattr(slot.material, 'wow_m2_material'):
                    continue 

                mat = slot.material.wow_m2_material

                for texture in [mat.texture_1,mat.texture_2]:
                    if hasattr(texture, 'wow_m2_texture'):
                        if texture is not None and len(texture.wow_m2_texture.path) == 0:
                            if texture.wow_m2_texture.texture_type == '0':
                                if not texture.name in texture_maps:
                                    texture_maps[texture.name] = []
                                
                                if not obj.name in texture_maps[texture.name]:
                                    texture_maps[texture.name].append(obj.name)
    
    for texture,obj_names in texture_maps.items():
        tex_str = f"Texture {texture} ("
        obj_name_len = len(obj_names)
        for i,obj_name in enumerate(obj_names):
            tex_str+=obj_name
            if i < obj_name_len -1:
                tex_str+=","
        tex_str += ") has no blp path set."
        items.append(tex_str)

    return (name,description,items)

def no_materials():
    name = "No Materials"
    description = [
        'Issue: A model has no materials set',
        'Effect: Will usually cause the model to be invisible ingame',
        'Fix: Add at least one material to your model',
        'Note: This is not *always* an error, not all models have materials'
    ]
    items = []
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and not obj.wow_m2_geoset.collision_mesh and len(obj.material_slots) == 0:
            items.append(f'Object {obj.name} has no m2 materials, this is usually an error and will cause the model to be invisible ingame')
    return (name,description,items)
        
def bone_constraints():
    name = "Bone Constraints"
    description = [
        "Issue: A bone has constraints applied",
        "Effect: Will almost always mess up your animations, wow does not support bone constraints",
        "Fix: Try removing bone constraints or bake your animations into keyframes"
    ]
    items = []

    for obj in bpy.data.objects:
        if obj.type != 'ARMATURE':
            continue
        for bone in obj.pose.bones:
            for constraint in bone.constraints:
                items.append(f'Bone {obj.name}.{bone.name} has constraint {constraint.name}, this is usually a mistake and will mess up your animations.')

    return (name,description,items)

def no_animation_pairs():
    name = "No Animation Pairs"
    description = [
        "Issue: Animations in the Animation Editor don't have any object pairs added",
        "Effect: No actual animation data is written for this sequence",
        "Fix: add an object pair and select an object and action"
    ]
    items = []
    for i,sequence in enumerate(bpy.context.scene.wow_m2_animations):
        if len(sequence.anim_pairs) == 0 and not "64" in sequence.flags:
            items.append(f'Sequence {sequence.name} have no pairs')
    return (name,description,items)

def missing_animation_items():
    name = "Missing Animation Items"
    description = [
        "Issue: Animation object pairs lacks an object or action set",
        "Effect: No actual animation data is written for this sequence",
        "Fix: Select an action + object for pairs missing them"
    ]
    items = []
    for i,sequence in enumerate(bpy.context.scene.wow_m2_animations):
        for j, pair in enumerate(sequence.anim_pairs):
            if pair.type == 'SCENE':
                continue
            if pair.object is None:
                items.append(f'Sequence {sequence.name} pair {j} has no object set')
            if pair.action is None:
                if pair.object.name == 'CharInfoCam' or 'CharInfoCam_Target' or 'PortraitCam' or 'PortraitCam_Target':
                    pass
                else:
                    items.append(f'Sequence {sequence.name} pair {pair.object.name} has no action set')
    return (name,description,items)

def non_primary_sequences():
    name = "Non-primary sequence"
    description = [
        "Issue: WBS currently does not support non-primary sequences",
        "Effect: The animation will break completely if not crash the game",
        "Fix: Add the 'primary sequence' flag"
    ]
    items = []
    for sequence in bpy.context.scene.wow_m2_animations:

        if not "32" in sequence.flags and not sequence.is_global_sequence:
            items.append(f'Sequence {sequence.name} does not have the primary sequence flag')

    return (name,description,items)

def too_many_bone_groups():
    name = "Too many bone groups"
    description = [
        "Issue: You have vertices with too many bone groups",
        "Effect: Bones will be dropped from vertices influence table on export, causing vertices to move differently in-game",
        "Fix: Either run 'Limit Bone Groups' to see the ingame effect in blender, or ignore this error and see results ingame.",
    ]
    items = []
    for obj in bpy.data.objects:
        if obj.type != 'MESH' or obj.parent == None or obj.parent.type != 'ARMATURE':
            continue
        bone_names = [bone.name for bone in obj.parent.data.bones]
        broken_vertices = 0
        for vertex in obj.data.vertices:
            if len(get_bone_groups(obj,vertex,bone_names)) > 4:
                broken_vertices += 1
        if broken_vertices > 0:
            items.append(f'Object {obj.name} has {broken_vertices} vertices with too many bone groups')
    return (name,description,items)

def fcurves_transforming_objects():
    name = "FCurves Transforming Objects"
    description = [
        'Issue: You have FCurves that transform blender objects themselves, this is currently unsupported',
        'Effect: Object has wrong scale/rotation/location ingame.',
        'Fix: Run "Convert Bones To WoW" and check the result.'
    ]
    items = []
    for animation in bpy.context.scene.wow_m2_animations:
        for anim_pair in animation.anim_pairs:
            action = anim_pair.action
            obj = anim_pair.object
            if action is not None:
                for curve in action.fcurves:
                    if curve.data_path in ["location", "rotation_euler", "scale"]:
                        if obj is not None and not obj.wow_m2_uv_transform.enabled:
                            items.append(f'FCurve "{curve.data_path}[{curve.array_index}]" in {action.name} transforms an object')
    return (name,description,items)

def print_warnings():
    printed_warnings = False
    def warning_section(callback):
        nonlocal printed_warnings
        (name,descriptions,items) = callback()
        if len(items) > 0:
            if not printed_warnings:
                print("\n")
                print("################################")
                print("           Warnings")
                print("################################")
                printed_warnings = True

            print(f'\n\n== {name} ==')
            for description in descriptions:
                print(f'\n{description}')
            for item in items:
                print(f'\n- {item}')
    
    warning_section(wrong_scene_type)
    warning_section(transformed_objects)
    warning_section(empty_textures)
    warning_section(empty_texture_paths)
    warning_section(no_materials)
    warning_section(bone_constraints)
    warning_section(no_animation_pairs)
    warning_section(missing_animation_items)
    warning_section(non_primary_sequences)
    warning_section(too_many_bone_groups)
    warning_section(fcurves_transforming_objects)

    if not printed_warnings:
        print("\nNo warnings found!")
        return False
    else:
        return True