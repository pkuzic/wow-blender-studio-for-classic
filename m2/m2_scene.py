import os
import re

from math import sqrt, isinf, asin, atan2, sin, cos
from functools import partial

import bpy
import sys, io
import ctypes
from mathutils import Vector
from ..ui.preferences import get_project_preferences
from ..third_party.tqdm import tqdm

from .bl_render import load_m2_shader_dependencies, update_m2_mat_node_tree
from ..render.m2.shaders import M2ShaderPermutations
from ..utils.misc import parse_bitfield, construct_bitfield, load_game_data
from ..utils.misc import resolve_texture_path, get_origin_position, get_objs_boundbox_world, get_obj_boundbox_center, \
    get_obj_radius
from .ui.enums import mesh_part_id_menu, TEXTURE_TYPES, get_texture_type_name
from .ui.panels.camera import update_follow_path_constraints
from .ui.panels.animation_editor import convert_frequency_percentage, get_frequency_percentage
from ..pywowlib.enums.m2_enums import M2SkinMeshPartID, M2AttachmentTypes, M2EventTokens, M2SequenceNames
from ..pywowlib.file_formats.wow_common_types import *
from ..pywowlib.file_formats.m2_format import *
from ..pywowlib.m2_file import M2File
from ..pywowlib.io_utils.types import vec3D
from .util import _find_final_alias, make_fcurve_compound,get_bone_groups

class BlenderM2Scene:
    """ This class is used for assembling a Blender scene from an M2 file or saving the scene back to it."""

    def __init__(self, m2: M2File, prefs):
        self.m2 = m2
        self.materials = {}
        self.loaded_textures = {}
        self.bone_ids = {}
        self.attachment_ids = {}
        self.event_ids = {}
        self.camera_ids = {}
        self.camera_target_ids = {}
        self.color_ids = {}
        self.transparency_ids = {}
        self.texture_transform_ids = {}
        self.light_ids = {}
        self.ribbon_ids = {}
        self.particle_ids = {}
        self.uv_transforms = {}
        self.geosets = []
        self.animations = []
        self.alias_animation_lookup = {}
        self.global_sequences = []
        self.old_actions = []
        self.old_selections = []
        self.old_active = None
        self.old_mode = None
        self.reset_pose_actions = []
        self.forward_axis = 'X+'
        self.axis_order = [0,1]
        self.axis_polarity = [1,1]
        self.scale = 1
        self.rig = None
        self.collision_mesh = None
        self.settings = prefs
        self.actions = {} # maps action names to actions
        self.final_textures = {}
        self.anim_data_table = M2SequenceNames()
        self.final_events = {}

        self.scene = bpy.context.scene

    def load_colors(self, timestamp_convert):

        def animate_color(anim_pair, color_track, color_index, anim_index):

            action = anim_pair.action

            try:
                frames = color_track.timestamps[anim_index]
                track = color_track.values[anim_index]
            except IndexError:
                return

            if not len(frames):
                return

            # create fcurve
            f_curves = [action.fcurves.new(data_path='wow_m2_colors[{}].color'.format(color_index),
                                           index=k, action_group='Color_{}'.format(color_index)) for k in range(3)]

            # init keyframes on the curve
            for f_curve in f_curves:
                f_curve.keyframe_points.add(len(frames))

            # set translation values for each channel
            for i, timestamp in enumerate(frames):
                if timestamp_convert == 'Convert':
                    frame = int(round( timestamp * ( bpy.context.scene.render.fps / bpy.context.scene.render.fps_base / 1000 )))
                else: 
                    frame = timestamp

                for j in range(3):
                    keyframe = f_curves[j].keyframe_points[i]
                    keyframe.co = frame, track[i][j]
                    keyframe.interpolation = 'LINEAR' if color_track.interpolation_type == 1 else 'CONSTANT'

        def animate_alpha(anim_pair, alpha_track, color_index, anim_index):

            action = anim_pair.action

            try:
                frames = alpha_track.timestamps[anim_index]
                track = alpha_track.values[anim_index]
            except IndexError:
                return

            if not len(frames):
                return

            # create fcurve
            f_curve = action.fcurves.new(data_path='wow_m2_color_alpha[{}].value'.format(color_index),
                                         index=0, action_group='Color_{}_Alpha'.format(color_index))

            # init keyframes on the curve
            f_curve.keyframe_points.add(len(frames))

            # set translation values for each channel
            for i, timestamp in enumerate(frames):
                if timestamp_convert == 'Convert':
                    frame = int(round( timestamp * ( bpy.context.scene.render.fps / bpy.context.scene.render.fps_base / 1000 )))
                else: 
                    frame = timestamp

                keyframe = f_curve.keyframe_points[i]
                keyframe.co = frame, track[i] / 0x7FFF
                keyframe.interpolation = 'LINEAR' if alpha_track.interpolation_type == 1 else 'CONSTANT'

        if not len(self.m2.root.colors):
            print("\nNo colors found to import.")
            return

        else:
            print("\nImporting colors.")

        bpy.context.scene.animation_data_create()
        bpy.context.scene.animation_data.action_blend_type = 'ADD'
        n_global_sequences = len(self.global_sequences)

        for i, m2_color in enumerate(self.m2.root.colors):
            bl_color = bpy.context.scene.wow_m2_colors.add()
            bl_color.name = 'Color_{}'.format(i)
            bl_color.color = (1.0, 1.0, 1.0)

            bl_alpha = bpy.context.scene.wow_m2_color_alpha.add()
            bl_alpha.name = 'Color_{}_Alpha'.format(i)
            bl_alpha.value = 1.0

            # load global sequences
            for j, seq_index in enumerate(self.global_sequences):
                anim = bpy.context.scene.wow_m2_animations[j]

                if anim.is_alias: # skip alias anims
                    continue
                anim_pair = None
                for pair in anim.anim_pairs:
                    if pair.type == 'SCENE':
                        anim_pair = pair
                        break
                
                if not anim_pair.action:
                    print("\nFailed to animate color #{}, no action for global seq #{}".format(i, j))
                    continue

                if m2_color.color.global_sequence == seq_index:
                    animate_color(anim_pair, m2_color.color, i, 0)

                if m2_color.alpha.global_sequence == seq_index:
                    animate_alpha(anim_pair, m2_color.alpha, i, 0)

            # load animations
            for j, anim_index in enumerate(self.animations):
                anim = bpy.context.scene.wow_m2_animations[j + n_global_sequences]

                if anim.is_alias: # skip alias anims
                    continue
                anim_pair = None
                for pair in anim.anim_pairs:
                    if pair.type == 'SCENE':
                        anim_pair = pair
                        break
                
                if not anim_pair.action:
                    print("\nFailed to animate color #{}, no action for anim #{}".format(i, (j - n_global_sequences)))
                    print(anim.name)
                    continue   

                if m2_color.color.global_sequence < 0:
                    animate_color(anim_pair, m2_color.color, i, anim_index)

                if m2_color.alpha.global_sequence < 0:
                    animate_alpha(anim_pair, m2_color.alpha, i, anim_index)

    def load_transparency(self, timestamp_convert):

        def animate_transparency(anim_pair, trans_track, trans_index, anim_index):

            action = anim_pair.action

            try:
                frames = trans_track.timestamps[anim_index]
                track = trans_track.values[anim_index]
            except IndexError:
                return

            if not len(frames):
                return

            # create fcurve
            f_curve = action.fcurves.new(data_path='wow_m2_transparency[{}].value'.format(trans_index),
                                         index=0, action_group='Transparency_{}'.format(trans_index))

            # init keyframes on the curve
            f_curve.keyframe_points.add(len(frames))

            # set translation values for each channel
            for i, timestamp in enumerate(frames):
                if timestamp_convert == 'Convert':
                    frame = int(round( timestamp * ( bpy.context.scene.render.fps / bpy.context.scene.render.fps_base / 1000 )))
                else: 
                    frame = timestamp

                keyframe = f_curve.keyframe_points[i]
                keyframe.co = frame, track[i] / 0x7FFF
                keyframe.interpolation = 'LINEAR' if trans_track.interpolation_type == 1 else 'CONSTANT'

        if not len(self.m2.root.texture_weights):
            print("\nNo transparency tracks found to import.")
            return

        else:
            print("\nImporting transparency.")

        bpy.context.scene.animation_data_create()
        bpy.context.scene.animation_data.action_blend_type = 'ADD'
        n_global_sequences = len(self.global_sequences)

        for i, m2_transparency in enumerate(self.m2.root.texture_weights):
            bl_transparency = bpy.context.scene.wow_m2_transparency.add()
            bl_transparency.name = 'Transparency_{}'.format(i)

            # load global sequences
            for j, seq_index in enumerate(self.global_sequences):
                anim = bpy.context.scene.wow_m2_animations[j]

                if anim.is_alias: # skip alias anims
                    continue
                anim_pair = None
                for pair in anim.anim_pairs:
                    if pair.type == 'SCENE':
                        anim_pair = pair
                        break
                
                if not anim_pair.action:
                    print("\nFailed to animate transparency #{}, no action for global seq #{}".format(i, j))
                    continue

                if m2_transparency.global_sequence == seq_index:
                    animate_transparency(anim_pair, m2_transparency, i, 0)

            # load animations
            for j, anim_index in enumerate(self.animations):
                anim = bpy.context.scene.wow_m2_animations[j + n_global_sequences]

                if anim.is_alias: # skip alias anims
                    continue
                anim_pair = None
                for pair in anim.anim_pairs:
                    if pair.type == 'SCENE':
                        anim_pair = pair
                        break

                if not anim_pair.action:
                    print("\nFailed to animate transparency #{}, no action for anim #{}".format(i, (j - n_global_sequences)))
                    print(anim.name)
                    continue
                if m2_transparency.global_sequence < 0:
                    animate_transparency(anim_pair, m2_transparency, i, anim_index)

    def load_texture(self,index):
        # textureid = self.m2.root.texture_lookup_table[index]
        if index in self.loaded_textures:
            return self.loaded_textures[index]


        texture = self.m2.root.textures[index]
        tex_path_png = ""


        if texture.type == 0:  # check if texture is hardcoded

            try:
                tex_path_blp = self.m2.texture_path_map[texture.fdid] \
                    if texture.fdid else self.m2.texture_path_map[texture.filename.value]

                tex_path_png = os.path.splitext(tex_path_blp)[0] + '.png'
            except KeyError:
                pass

        tex = None
        if tex_path_png:
            #print("tex path : " + tex_path_png)
            try:
                tex = bpy.data.images.load(tex_path_png)
            except RuntimeError:
                print("\nWarning: failed to load texture \"{}\".".format(tex_path_png))

        if not tex:
            if texture.type == 0: # hardcoded
                tex = bpy.data.images.new(os.path.basename(texture.filename.value), 256, 256)
            else: # DBC tetxure

                tetxname = get_texture_type_name(texture.type)
                tex = bpy.data.images.new(os.path.basename(tetxname), 256, 256)

        tex.wow_m2_texture.enabled = True
        tex.wow_m2_texture.flags = parse_bitfield(texture.flags, 0x2)
        tex.wow_m2_texture.texture_type = str(texture.type)
        tex.wow_m2_texture.path = texture.filename.value

        # titi test textures ui
        #slot = bpy.context.scene.wow_m2_root_elements.textures.add()
        #slot.pointer = tex

        self.loaded_textures[index] = tex
        return tex
        ####

    def load_materials(self):

        dbc_textures = False

        BLENDING_MODES_DICT = {
            "0": "Opaque",
            "1": "AlphaKey",
            "2": "Alpha",
            "3": "NoAlphaAdd",
            "4": "Add",
            "5": "Mod",
            "6": "Mod2X",
            "7": "BlendAdd"
        }

        if 'UV Picker' not in bpy.data.node_groups:
            load_m2_shader_dependencies(reload_shader=True)                                                  
        def create_m2_material(mat_flags, priority_plane, texture1, t1_flags, t1_bl_mode, t1_mapping, 
                               texture_count, transparency=None, color=None, texture2=None, t2_flags=None, t2_bl_mode=None, t2_mapping=None):
           
            blender_mat = bpy.data.materials.new(name='Unknown')
            
            if transparency is not None:
                blender_mat.wow_m2_material.transparency = transparency
            if color is not None:
                blender_mat.wow_m2_material.color = color
            
            blender_mat.wow_m2_material.flags = mat_flags
            blender_mat.wow_m2_material.priority_plane = priority_plane

            #Texture1
            blender_mat.wow_m2_material.texture_1 = texture1            
            blender_mat.wow_m2_material.texture_1_render_flags = t1_flags
            blender_mat.wow_m2_material.texture_1_blending_mode = t1_bl_mode
            blender_mat.wow_m2_material.texture_1_mapping = t1_mapping

            #Texture2
            if texture_count == 2:
                blender_mat.wow_m2_material.texture_2 = texture2
                blender_mat.wow_m2_material.texture_2_render_flags = t2_flags
                blender_mat.wow_m2_material.texture_2_blending_mode = t2_bl_mode
                blender_mat.wow_m2_material.texture_2_mapping = t2_mapping

                blender_mat.name = 'T1_{}_({})_T2_{}_({})'.format(
                                    texture1.name, BLENDING_MODES_DICT.get(str(t1_bl_mode), "Unknown"), texture2.name, BLENDING_MODES_DICT.get(str(t2_bl_mode), "Unknown"))
            else:
                blender_mat.name = 'T1_{}_({})'.format(
                    texture1.name, BLENDING_MODES_DICT.get(str(t1_bl_mode), "Unknown"))          

            update_m2_mat_node_tree(blender_mat)   
                   
            return blender_mat
            
        print("\nImporting materials.")

        skin = self.m2.skins[0]

        flags = parse_bitfield(self.m2.root.global_flags, 0x10)

        unique_materials = {}

        for k, tex_unit in enumerate(skin.texture_units):
            try:
                m2_mat = self.m2.root.materials[tex_unit.material_index] 
            except IndexError:
                print('\n')
                m2_mat_error_message = f"Material with index {tex_unit.material_index} not found in M2 file. This may indicate a corrupt M2 file."
                raise IndexError(m2_mat_error_message) from None

            if tex_unit.texture_count == 2 and '8' not in flags:
                try: 
                    m2_mat2 = self.m2.root.materials[tex_unit.material_index+1] 
                except IndexError as e:
                    print("\nMaterial for second texture not found, using first texture material:", e)
                    m2_mat2 = m2_mat

            t1_flags = t2_flags = ()
            tex1 = t1_bl_mode = t1_mapping = None
            tex2 = t2_bl_mode = t2_mapping = None
       
            for i in range(tex_unit.texture_count):
                try:
                    texid = self.m2.root.texture_lookup_table[tex_unit.texture_combo_index + i]
                except IndexError as e:
                    print("\nTexture not found, probably messed up m2:", e)
                tex = self.load_texture(texid)
                if i == 0:
                    tex1 = tex
                else:
                    tex2 = tex

                texture = self.m2.root.textures[texid]
                if texture.type != 0:
                    #We'll use this for loading dbc textures after finishing the import
                    dbc_textures = True

            # bind transparency to material
            if tex_unit.texture_weight_combo_index >= 0:
                real_tw_index = self.m2.root.transparency_lookup_table[tex_unit.texture_weight_combo_index]
                transparency = bpy.context.scene.wow_m2_transparency[real_tw_index]
                transparency = transparency.name

            # bind color to material
            color = None
            if tex_unit.color_index >= 0:
                try:
                    color = bpy.context.scene.wow_m2_colors[tex_unit.color_index]
                    color = color.name
                except:
                    print(f'TexUnit {k}, references a non-existing color {tex_unit.color_index}, importing without color')

            int_to_enum_mapping = {
                -1: "Env",
                0: "UVMap",
                1: "UVMap.001",
            }

            # filling material settings
            mat_flags = parse_bitfield(tex_unit.flags, 0x80)
            t1_flags = parse_bitfield(m2_mat.flags, 0x800)
            t1_bl_mode = str(m2_mat.blending_mode)           
            t1_mapping = int_to_enum_mapping.get(self.m2.root.tex_unit_lookup_table[tex_unit.texture_coord_combo_index])
            texture_count = 2 if tex_unit.texture_count == 2  else 1
                
            if texture_count == 2 and '8' in flags: #M2 is using global flag for second material override
                #print("Second material override flag is activated")
                try:
                    t2_flags = parse_bitfield(self.m2.root.texture_combiner_combos[tex_unit.shader_id], 0x800)
                    t2_bl_mode = str(self.m2.root.texture_combiner_combos[tex_unit.shader_id+1])
                    t2_mapping = int_to_enum_mapping.get(self.m2.root.tex_unit_lookup_table[tex_unit.texture_coord_combo_index+1])
                except:
                    print('Texture 2 Flags and Blending Mode not found, trying to use index 0')
                    t2_flags = parse_bitfield(self.m2.root.texture_combiner_combos[0], 0x800)
                    t2_bl_mode = str(self.m2.root.texture_combiner_combos[1])
                    try:
                        t2_mapping = int_to_enum_mapping.get(self.m2.root.tex_unit_lookup_table[tex_unit.texture_coord_combo_index+1])
                    except:
                        print('Second UVMap not found, using first one')
                        t2_mapping = int_to_enum_mapping.get(self.m2.root.tex_unit_lookup_table[tex_unit.texture_coord_combo_index])
            elif texture_count == 2 and '8' not in flags:
                    t2_flags = parse_bitfield(m2_mat2.flags, 0x800)  # render flags
                    t2_bl_mode = str(m2_mat2.blending_mode)
                    try: 
                        t2_mapping = int_to_enum_mapping.get(self.m2.root.tex_unit_lookup_table[tex_unit.texture_coord_combo_index+1])
                    except IndexError as e:
                        print("Mapping for second texture not found, using first texture mapping", e)
                        t2_mapping = int_to_enum_mapping.get(self.m2.root.tex_unit_lookup_table[tex_unit.texture_coord_combo_index])
                    
        
            priority_plane = tex_unit.priority_plane

            if not tex_unit.skin_section_index in self.materials:
                self.materials[tex_unit.skin_section_index] = []

            material_key = (
                tuple(mat_flags), priority_plane,
                tex1.name, tuple(t1_flags), t1_bl_mode, t1_mapping,
                texture_count,
                transparency, color,
                tex2.name if tex2 else None, tuple(t2_flags), t2_bl_mode, t2_mapping
            )
            
            if material_key in unique_materials:
                material = unique_materials[material_key]
            else:
                material = create_m2_material(
                    mat_flags, priority_plane,
                    tex1, t1_flags, t1_bl_mode, t1_mapping,
                    texture_count, transparency, color,
                    tex2, t2_flags, t2_bl_mode, t2_mapping
                )
                 
                unique_materials[material_key] = material
            
            self.materials[tex_unit.skin_section_index].append((material, tex_unit))
        
        return dbc_textures

    def load_armature(self):
        if not len(self.m2.root.bones):
            print("\nNo armature found to import.")
            return
        
        print("\nImporting armature")

        # Create armature
        armature = bpy.data.armatures.new('{}_Armature'.format(self.m2.root.name.value))
        rig = bpy.data.objects.new(self.m2.root.name.value, armature)
        rig.location = (0, 0, 0)
        self.rig = rig

        # Link the object to the scene
        bpy.context.collection.objects.link(rig)
        bpy.context.view_layer.objects.active = rig

        bpy.context.view_layer.update()

        bpy.ops.object.mode_set(mode='EDIT')

        bpy.context.object.data.layers[1] = True
        bpy.context.object.data.layers[2] = True
        bpy.context.object.data.layers[3] = True
        bpy.context.object.data.layers[4] = True

        for i, bone in enumerate(self.m2.root.bones):  # add bones to armature.
            bl_edit_bone = armature.edit_bones.new(bone.name)
            bl_edit_bone.head = Vector(bone.pivot)

            bl_edit_bone.tail.x = bl_edit_bone.head.x + 0.1  # TODO: mess with bones parenting even more
            bl_edit_bone.tail.y = bl_edit_bone.head.y
            bl_edit_bone.tail.z = bl_edit_bone.head.z

            bl_edit_bone.wow_m2_bone.sort_index = i
            bl_edit_bone.wow_m2_bone.flags = parse_bitfield(bone.flags)
            bl_edit_bone.wow_m2_bone.submesh_id = bone.submesh_id
            bl_edit_bone.wow_m2_bone.bone_name_crc = ctypes.c_int(bone.bone_name_crc).value

            try:
                bl_edit_bone.wow_m2_bone.key_bone_id = str(bone.key_bone_id)
            except TypeError:
                print('\nFailed to set keybone ID \"{}\". Unknown keybone ID'.format(bone.key_bone_id))          
                
            if 'AT_' in bone.name:
                bl_edit_bone.layers[0] = False
                bl_edit_bone.layers[1] = False
                bl_edit_bone.layers[2] = False
                bl_edit_bone.layers[3] = True
                bl_edit_bone.layers[4] = False
            elif 'ET' in bone.name:
                bl_edit_bone.layers[0] = False
                bl_edit_bone.layers[1] = False
                bl_edit_bone.layers[2] = False
                bl_edit_bone.layers[3] = False
                bl_edit_bone.layers[4] = True
            elif 'Bone_' in bone.name:
                bl_edit_bone.layers[0] = False
                bl_edit_bone.layers[1] = False
                bl_edit_bone.layers[2] = True
                bl_edit_bone.layers[3] = False
                bl_edit_bone.layers[4] = False
            elif bone.key_bone_id == -1:
                bl_edit_bone.layers[0] = False
                bl_edit_bone.layers[1] = True
                bl_edit_bone.layers[2] = False
                bl_edit_bone.layers[3] = False     
                bl_edit_bone.layers[4] = False         
            else:
                bl_edit_bone.layers[1] = False
                bl_edit_bone.layers[2] = False
                bl_edit_bone.layers[3] = False
                bl_edit_bone.layers[4] = False
            
            print('Bone number:', i, bone.name, bone.bone_name_crc)

        # link children to parents
        for i, bone in enumerate(self.m2.root.bones):
            if bone.parent_bone >= 0:
                bl_edit_bone = armature.edit_bones[bone.name]
                parent = armature.edit_bones[self.m2.root.bones[bone.parent_bone].name]
                bl_edit_bone.parent = parent

        bpy.context.view_layer.update()  # update scene.
        bpy.ops.object.mode_set(mode='OBJECT')  # return to object mode. 

    @staticmethod
    def _populate_bl_fcurve(f_curves, frames, track, length, callback, interp_type):

        # init keyframes on the curve
        for f_curve in f_curves:
            f_curve.keyframe_points.add(len(frames))

        # set values for each channel
            
        preferences = get_project_preferences()
        timestamp_convert = preferences.time_import_method

        if track:

            for j, timestamp in enumerate(frames):
                value = callback(value=track[j])
                if timestamp_convert == 'Convert':
                    frame = int(round( timestamp * ( bpy.context.scene.render.fps / bpy.context.scene.render.fps_base / 1000 )))
                else: 
                    frame = timestamp

                for k in range(len(value)):
                    keyframe = f_curves[k].keyframe_points[j]
                    keyframe.co = frame, value[k]
                    keyframe.interpolation = interp_type

        else:

            for j, timestamp in enumerate(frames):
                if timestamp_convert == 'Convert':
                    frame = int(round( timestamp * ( bpy.context.scene.render.fps / bpy.context.scene.render.fps_base / 1000 )))
                else: 
                    frame = timestamp
                keyframe = f_curves[0].keyframe_points[j]
                keyframe.co = frame, True
                keyframe.interpolation = interp_type

    def _bl_create_sequences(self, m2_obj, m2_track_name, prefix, bl_obj, bl_obj_name, bl_track_name, track_count, conv):
        # Create tracks (and actions, as needed) for all sequences for a specific M2Track
        track = getattr(m2_obj,m2_track_name)
        seq_name_table = M2SequenceNames()
        n_global_sequences = len(self.global_sequences)

        # M2Track uses global sequences
        if track.global_sequence >= 0:
            global_seq_str = str(track.global_sequence).zfill(3)
            # action_name = f'{prefix}_{i}_{bl_obj.name}_Global_sequence_{global_seq_str}'
            action_name = f'{prefix}_{bl_obj.name}_Global_sequence_{global_seq_str}'

            # Create new animation pair if action doesn't already exist
            if action_name in self.actions:
                action = self.actions[action_name]
            else:
                sequence = bpy.context.scene.wow_m2_animations[self.global_sequences[track.global_sequence]]
                # pair = sequence.anim_pairs.add()
                anim_pair = sequence.anim_pairs.add()
                anim_pair.object = bl_obj
                anim_pair.action = BlenderM2Scene._bl_create_action(anim_pair,action_name)
                action = self.actions[action_name] = anim_pair.action

            self._bl_create_fcurves(
                anim_pair.action,
                '',
                conv,
                track_count,
                0,
                bl_obj_name+'.'+bl_track_name,
                track
            )
        # M2Track uses normal sequences
        else:
            for j, anim_index in enumerate(self.animations):
                anim = bpy.context.scene.wow_m2_animations[j + n_global_sequences]
                sequence = self.m2.root.sequences[anim_index]
                if track.timestamps.n_elements > anim_index:
                    if not len(track.timestamps[anim_index]):
                        continue
                field_name = seq_name_table.get_sequence_name(sequence.id) 
                action_name = f'{prefix}_{bl_obj.name}_{str(j).zfill(3)}_{sequence.variation_index}'

                # Create new animation pair if action doesn't already exist
                if action_name in self.actions:
                    action = self.actions[action_name]
                else:
                    anim_pair = anim.anim_pairs.add()
                    anim_pair.type = 'OBJECT'
                    anim_pair.object = bl_obj
                    anim_pair.action = BlenderM2Scene._bl_create_action(anim_pair,action_name)
                    action = self.actions[action_name] = anim_pair.action

                self._bl_create_fcurves(
                    action,
                    '',
                    conv,
                    track_count,
                    j,
                    bl_obj_name+'.'+bl_track_name,
                    track
                )

    @staticmethod
    def _bl_create_fcurves(action, action_group, callback, length, anim_index, data_path, anim_track):

        if anim_track.timestamps.n_elements > anim_index:

            frames = anim_track.timestamps[anim_index]

            try:
                track = anim_track.values[anim_index]
            except AttributeError:
                track = None

            if frames:
                t_fcurves = [action.fcurves.new(data_path=data_path, index=k, action_group=action_group)
                             for k in range(length)]

                BlenderM2Scene._populate_bl_fcurve(t_fcurves, frames, track, length, callback,
                                                   'LINEAR' if anim_track.interpolation_type == 1 else 'CONSTANT')

    @staticmethod
    def _bl_create_action(anim_pair, name: str) -> bpy.types.Action:

        if not anim_pair.action:

            action = bpy.data.actions.new(name=name)
            action.use_fake_user = True
            anim_pair.action = action

            return action

        return anim_pair.action

    @staticmethod
    def _bl_convert_track_dummy(value=None):
        return [value]

    @staticmethod
    def _bl_convert_track_value(value=None):
        return [value]

    @staticmethod
    def _bl_convert_track_tuple(value=None):
        return value

    def _bl_add_sequence(self, name: str = "Sequence", is_global: bool = False, is_alias: bool = False):
        seq = self.scene.wow_m2_animations.add()
        seq.is_global_sequence = is_global

        # register scene in the sequence
        anim_pair_scene = seq.anim_pairs.add()
        anim_pair_scene.type = 'SCENE'
        anim_pair_scene.scene = bpy.context.scene

        # register rig in the sequence
        anim_pair = seq.anim_pairs.add()
        anim_pair.type = 'OBJECT'
        anim_pair.object = self.rig

        if not is_alias:
            action = bpy.data.actions.new(name='SC_{}'.format(name))
            action.use_fake_user = True
            anim_pair_scene.action = action

            action = bpy.data.actions.new(name=name)
            action.use_fake_user = True
            anim_pair.action = action

        return seq

    def _bl_load_sequences(self):
        #anim_data_table = M2SequenceNames()

        # import global sequence animations
        for i in range(len(self.m2.root.global_sequences)):
            self._bl_add_sequence(name='Global_Sequence_{}'.format(str(i).zfill(3)), is_global=True)
            self.global_sequences.append(len(self.scene.wow_m2_animations) - 1)

        m2_sequences = sorted(enumerate(self.m2.root.sequences),
                              key=lambda item: (item[0], item[1].id, item[1].variation_index))

        # import animation sequence
        for i, pair in enumerate(m2_sequences):
            idx, sequence = pair

            # create sequence
            field_name = self.anim_data_table.get_sequence_name(sequence.id)
            name = '{}_UnkAnim'.format(str(i).zfill(3)) \
                if not field_name else "{}_{}_({})".format(str(i).zfill(3), field_name, sequence.variation_index)

            # check if sequence is an alias
            is_alias = sequence.flags & 0x40

            # create sequence
            anim = self._bl_add_sequence(name=name, is_global=False, is_alias=is_alias)

            # find real animation index
            if is_alias:
                anim.is_alias = True

                for j, seq in m2_sequences:
                    anim.alias_next = j
                    if j == sequence.alias_next:
                        self.alias_animation_lookup[i] = j
                        break

            # add animation properties
            anim.animation_id = str(sequence.id)
            anim.flags = parse_bitfield(sequence.flags, 0x800)

            # titi set primary seq flag - WBS doesnt export .anim files 
            if not "32" in anim.flags:
                # anim.flags.add(str(32))
                anim.flags |= {str(32)}
            anim.move_speed = sequence.movespeed
            anim.frequency = get_frequency_percentage(sequence.frequency)
            anim.replay_min = sequence.replay.minimum
            anim.replay_max = sequence.replay.maximum
            anim.VariationNext = sequence.variation_next
            anim.use_preset_bounds = True
            anim.preset_bounds_min_x = sequence.bounds.extent.min[0]
            anim.preset_bounds_min_y = sequence.bounds.extent.min[1]
            anim.preset_bounds_min_z = sequence.bounds.extent.min[2]
            anim.preset_bounds_max_x = sequence.bounds.extent.max[0]
            anim.preset_bounds_max_y = sequence.bounds.extent.max[1]
            anim.preset_bounds_max_z = sequence.bounds.extent.max[2]
            anim.preset_bounds_radius = sequence.bounds.radius
            anim.use_preset_duration = False
            anim.duration = sequence.duration

            if self.m2.root.version >= M2Versions.WOD:
                anim.blend_time_in = sequence.blend_time_in
                anim.blend_time_out = sequence.blend_time_out

            else:
                anim.blend_time = sequence.blend_time

            self.animations.append(idx)

    @staticmethod
    def _bl_create_action_group(action: bpy.types.Action, name: str) -> str:
        if name not in action.groups:
            action.groups.new(name=name)

        return name

    def load_animations(self):

        # TODO: pre-wotlk

        def bl_convert_trans_track(value=None, bl_bone=None, bone=None):
            return bl_bone.bone.matrix_local.inverted() @ (Vector(bone.pivot) + Vector(value))

        def bl_convert_rot_track(value=None):
            if hasattr(value, 'to_quaternion'):
                return value.to_quaternion()
            # vanilla/TBC: uncompressed (x, y, z, w) float tuple. Apply the same
            # axis handling M2CompQuaternion.read/to_quaternion does for WotLK
            # (disk x -> y, disk y -> -x), yielding (w, -y, x, z).
            x, y, z, w = value
            return (w, -y, x, z)

        def bl_convert_scale_track(value=None):

            value = list(value)

            for i, val in enumerate(value):
                if isinf(val):
                    print("\nWarning: Fixed infinite scale value!")  #TODO: figure out infinite values there
                    value[i] = 1.0

            return tuple((value[1], value[0], value[2]))
        
        def load_alias_actions():

            scene = self.scene      
                
            n_global_sequences = len(self.m2.root.global_sequences)
            for i, anim_index in enumerate(self.animations):
                anim = scene.wow_m2_animations[i + n_global_sequences]
                scene_action = anim.anim_pairs[0].action
                action = anim.anim_pairs[1].action
                alias_next = anim.alias_next

                final_alias = _find_final_alias(self, n_global_sequences, alias_next)

                if not action and not scene_action:
                    alias_anim = scene.wow_m2_animations[final_alias]
                    alias_scene_action = alias_anim.anim_pairs[0].action
                    alias_action = alias_anim.anim_pairs[1].action
                    anim.anim_pairs[0].action = alias_scene_action
                    anim.anim_pairs[1].action = alias_action 

        if not len(self.m2.root.sequences) and not len(self.m2.root.global_sequences):
            print("\nNo animation data found to import.")
            return
        else:
            print("\nImporting animations.")

        if not self.rig:
            print("\nArmature is not present on the scene. Skipping animation import. M2 is most likely corrupted.")
            return

        # create animation data for rig and set it as an active object
        scene = self.scene
        rig = self.rig
        rig.animation_data_create()
        rig.animation_data.action_blend_type = 'ADD'
        bpy.context.view_layer.objects.active = rig

        self._bl_load_sequences()

        # import fcurves
        for bone in self.m2.root.bones:
            bl_bone = rig.pose.bones[bone.name]

            is_global_seq_trans = bone.translation.global_sequence >= 0
            is_global_seq_rot = bone.rotation.global_sequence >= 0
            is_global_seq_scale = bone.scale.global_sequence >= 0

            glob_sequences = self.global_sequences

            # write global sequence fcurves
            if is_global_seq_trans:
                action = scene.wow_m2_animations[glob_sequences[bone.translation.global_sequence]].anim_pairs[1].action
                self._bl_create_action_group(action, bone.name)
                self._bl_create_fcurves(action, bone.name, partial(bl_convert_trans_track, bl_bone=bl_bone, bone=bone),
                                        3, 0, 'pose.bones["{}"].location'.format(bl_bone.name), bone.translation)

            if is_global_seq_rot:
                action = scene.wow_m2_animations[glob_sequences[bone.rotation.global_sequence]].anim_pairs[1].action
                self._bl_create_action_group(action, bone.name)
                self._bl_create_fcurves(action, bone.name, partial(bl_convert_rot_track), 4, 0,
                                        'pose.bones["{}"].rotation_quaternion'.format(bl_bone.name), bone.rotation)

            if is_global_seq_scale:
                action = scene.wow_m2_animations[glob_sequences[bone.scale.global_sequence]].anim_pairs[1].action
                self._bl_create_action_group(action, bone.name)
                self._bl_create_fcurves(action, bone.name, partial(bl_convert_scale_track), 3, 0,
                                        'pose.bones["{}"].scale'.format(bl_bone.name), bone.scale)

            # write regular animation fcurves
            n_global_sequences = len(self.m2.root.global_sequences)
            for i, anim_index in enumerate(self.animations):
                anim = scene.wow_m2_animations[i + n_global_sequences]
                action = anim.anim_pairs[1].action

                if not action:
                    continue

                # translate bones
                if not is_global_seq_trans and bone.translation.timestamps.n_elements > anim_index:
                    self._bl_create_action_group(action, bone.name)
                    self._bl_create_fcurves(action, bone.name, partial(bl_convert_trans_track, bl_bone=bl_bone,
                                            bone=bone), 3, anim_index,
                                            'pose.bones["{}"].location'.format(bl_bone.name),
                                            bone.translation)

                # rotate bones
                if not is_global_seq_rot and bone.rotation.timestamps.n_elements > anim_index:
                    self._bl_create_action_group(action, bone.name)
                    self._bl_create_fcurves(action, bone.name, partial(bl_convert_rot_track), 4,
                                            anim_index,'pose.bones["{}"].rotation_quaternion'.format(bl_bone.name),
                                            bone.rotation)

                # scale bones
                if not is_global_seq_scale and bone.scale.timestamps.n_elements > anim_index:
                    self._bl_create_action_group(action, bone.name)
                    self._bl_create_fcurves(action, bone.name, partial(bl_convert_scale_track), 3, anim_index,
                                            'pose.bones["{}"].scale'.format(bl_bone.name),
                                            bone.scale)
        load_alias_actions()

    def load_geosets(self):

        if not len(self.m2.root.vertices):
            print("\nNo mesh geometry found to import.")
            return

        else:
            print("\nImporting geosets.")

        skin = self.m2.skins[0]

        for smesh_i, smesh in enumerate(skin.submeshes):

            vertices = [self.m2.root.vertices[skin.vertex_indices[i]].pos
                        for i in range(smesh.vertex_start, smesh.vertex_start + smesh.vertex_count)]

            normals = [self.m2.root.vertices[skin.vertex_indices[i]].normal
                       for i in range(smesh.vertex_start, smesh.vertex_start + smesh.vertex_count)]

            tex_coords = [self.m2.root.vertices[skin.vertex_indices[i]].tex_coords
                          for i in range(smesh.vertex_start, smesh.vertex_start + smesh.vertex_count)]

            tex_coords2 = [self.m2.root.vertices[skin.vertex_indices[i]].tex_coords2
                          for i in range(smesh.vertex_start, smesh.vertex_start + smesh.vertex_count)]

            triangles = [[skin.triangle_indices[i + j] - smesh.vertex_start for j in range(3)]
                         for i in range(smesh.index_start, smesh.index_start + smesh.index_count, 3)]

            # create mesh
            mesh = bpy.data.meshes.new(self.m2.root.name.value)
            mesh.from_pydata(vertices, [], triangles)

            for poly in mesh.polygons:
                poly.use_smooth = True

            # set normals
            #for index, vertex in enumerate(mesh.vertices):
                #vertex.normal = normals[index]
            
            # set normals
            #custom_normals = [(0.0, 0.0, 0.0)] * len(mesh.loops)
            #mesh.use_auto_smooth = True

            # Set custom normals
            #mesh.create_normals_split()
            #mesh.normals_split_custom_set_from_vertices(normals)

            mesh.auto_smooth_angle = 3.14159
            mesh.use_auto_smooth = True
            custom_normals = [normals[loop.vertex_index] for loop in mesh.loops]
            mesh.normals_split_custom_set(custom_normals)            

            # set uv
            mesh.uv_layers.new(name="UVMap")
            uv_layer1 = mesh.uv_layers[0]
            for i in range(len(uv_layer1.data)):
                uv = tex_coords[mesh.loops[i].vertex_index]
                uv_layer1.data[i].uv = (uv[0], 1 - uv[1])

            mesh.uv_layers.new(name="UVMap.001")
            uv_layer2 = mesh.uv_layers[1]
            for i in range(len(uv_layer2.data)):
                uv = tex_coords2[mesh.loops[i].vertex_index]
                uv_layer2.data[i].uv = (uv[0], 1 - uv[1])

            # set textures and materials
            for material, tex_unit in self.materials[smesh_i]:
                mesh.materials.append(material)

            # get object name
            name = M2SkinMeshPartID.get_mesh_part_name(smesh.skin_section_id)
            obj = bpy.data.objects.new(name if name else 'Geoset', mesh)
            bpy.context.collection.objects.link(obj)

            try:
                obj.wow_m2_geoset.mesh_part_group = name
                obj.wow_m2_geoset.mesh_part_id = str(smesh.skin_section_id)
            except TypeError:
                print('Warning: unknown mesh part ID \"{}\"'.format(smesh.skin_section_id))
            for item in mesh_part_id_menu(obj.wow_m2_geoset, None):
                if item[0] == smesh.skin_section_id:
                    obj.name = item[1]

            if self.rig:
                obj.parent = self.rig

                # bind armature to geometry
                armature_modifier = obj.modifiers.new(name="Armature", type='ARMATURE')
                armature_modifier.object = self.rig

                vgroups = {}
                for j in range(smesh.vertex_start, smesh.vertex_start + smesh.vertex_count):
                    m2_vertex = self.m2.root.vertices[skin.vertex_indices[j]]

                    for b_index, bone_index in enumerate(filter(lambda x: x >= 0, m2_vertex.bone_indices)):
                        vgroups.setdefault(self.m2.root.bones[bone_index].name, []).append(
                            (j - smesh.vertex_start, m2_vertex.bone_weights[b_index] / 255))

                for name in vgroups.keys():
                    if len(vgroups[name]) > 0:
                        grp = obj.vertex_groups.new(name=name)
                        for (v, w) in vgroups[name]:
                            grp.add([v], w, 'ADD')

            self.geosets.append(obj)
            
            #slot = bpy.context.scene.wow_m2_root_elements.geosets.add()
            #slot.pointer = obj

    def load_texture_transforms(self):

        def bl_convert_trans_track(value=None):
            return Vector((0, 0, 0)) + Vector((-value[0], value[1], value[2]))

        def bl_convert_rot_track(value=None):
            return value[3], -value[1], value[0], value[2]

        if not self.geosets:
            print('\nNo geosets found. Skipping texture transform import')
            return
        else:
            print('\nImporting texture transforms')

        skin = self.m2.skins[0]

        for smesh_pair, obj in zip(enumerate(skin.submeshes), self.geosets):
            smesh_i, smesh = smesh_pair

            for _, tex_unit in self.materials[smesh_i]:

                for i in range(2 if tex_unit.texture_count > 1 else 1):

                    combo_index = tex_unit.texture_transform_combo_index + i

                    try:
                        tex_tranform_index = self.m2.root.texture_transforms_lookup_table[combo_index]
                    except IndexError as e:
                        print(f'Texture Animation with index {combo_index} doesn\'t exist in the m2, not importing it, check it out')
                        continue
                
                    if tex_tranform_index >= 0 & self.m2.root.texture_transforms_lookup_table[combo_index] != -1:

                        c_obj = self.uv_transforms.get(tex_tranform_index)

                        try:
                            tex_transform = self.m2.root.texture_transforms[tex_tranform_index]
                        except IndexError as e:
                            print(f'Texture animation {tex_tranform_index} not found, skipping import')
                            continue
                    
                        seq_name_table = M2SequenceNames()
                        n_global_sequences = len(self.global_sequences)

                        TT_Controllers = [obj for obj in bpy.data.objects if obj.wow_m2_uv_transform.enabled]

                        if not c_obj:
                            bpy.ops.object.empty_add(type='SINGLE_ARROW', location=(0, 0, 0))
                            c_obj = bpy.context.view_layer.objects.active
                            c_obj.name = "TT_Controller_{}".format(len(TT_Controllers))
                            c_obj.wow_m2_uv_transform.enabled = True
                            c_obj = bpy.context.view_layer.objects.active
                            c_obj.rotation_mode = 'QUATERNION'
                            c_obj.empty_display_size = 0.5
                            c_obj.animation_data_create()
                            c_obj.animation_data.action_blend_type = 'ADD'

                            self.uv_transforms[tex_tranform_index] = c_obj

                            create_actions = True
                        else:
                            create_actions = False


                        if i == 0:
                            material = obj.active_material
                            obj.active_material = material.copy()
                            obj.active_material.wow_m2_material.texture_1_animation = c_obj
                        else:
                            material = obj.active_material
                            obj.active_material = material.copy()                            
                            obj.active_material.wow_m2_material.texture_2_animation = c_obj

                        bpy.context.view_layer.objects.active = obj
                        bpy.ops.object.modifier_add(type='UV_WARP')
                        uv_transform = bpy.context.object.modifiers[-1]
                        uv_transform.name = 'M2TexTransform_{}'.format(i + 1)
                        uv_transform.object_from = obj
                        uv_transform.object_to = c_obj
                        uv_transform.uv_layer = 'UVMap' if not i else 'UVMap.001'


                        setattr(obj.wow_m2_geoset, 'uv_transform_{}'.format(i + 1), c_obj)

                        if create_actions:
                                
                            # load global sequences
                            for j, seq_index in enumerate(self.global_sequences):
                                anim = bpy.context.scene.wow_m2_animations[seq_index]

                                name = "TT_{}_{}_Global_Sequence_{}".format(tex_tranform_index, obj.name, str(j).zfill(3))

                                cur_index = len(anim.anim_pairs)
                                anim_pair = anim.anim_pairs.add()
                                anim_pair.type = 'OBJECT'
                                anim_pair.object = c_obj

                                if tex_transform.translation.global_sequence == j \
                                and tex_transform.translation.timestamps.n_elements:
                                    action = self._bl_create_action(anim_pair, name)
                                    self._bl_create_fcurves(action, c_obj.name, bl_convert_trans_track, 3, 0, 'location',
                                                            tex_transform.translation)

                                if tex_transform.rotation.global_sequence == j \
                                and tex_transform.rotation.timestamps.n_elements:
                                    action = self._bl_create_action(anim_pair, name)
                                    self._bl_create_fcurves(action, c_obj.name, bl_convert_rot_track, 4, 0, 'rotation_quaternion',
                                                            tex_transform.rotation)

                                if tex_transform.scaling.global_sequence == j \
                                and tex_transform.scaling.timestamps.n_elements:
                                    action = self._bl_create_action(anim_pair, name)
                                    self._bl_create_fcurves(action, c_obj.name, bl_convert_trans_track, 3, 0, 'scale',
                                                            tex_transform.scaling)

                                if not anim_pair.action:
                                        anim.anim_pairs.remove(cur_index)

                        # load animations
                            for j, anim_index in enumerate(self.animations):

                                # skip alias
                                if self.alias_animation_lookup.get(j):
                                    continue

                                anim = bpy.context.scene.wow_m2_animations[j + n_global_sequences]
                                sequence = self.m2.root.sequences[anim_index]

                                field_name = seq_name_table.get_sequence_name(sequence.id)
                                name = 'TT_{}_{}_{}_UnkAnim'.format(tex_tranform_index, obj.name, str(j).zfill(3)) \
                                    if not field_name else "TT_{}_{}_{}_{}_({})".format(tex_tranform_index,
                                                                                        obj.name,
                                                                                        str(j).zfill(3),
                                                                                        field_name,
                                                                                        sequence.variation_index)

                                cur_index = len(anim.anim_pairs)
                                anim_pair = anim.anim_pairs.add()
                                anim_pair.type = 'OBJECT'
                                anim_pair.object = c_obj

                                if tex_transform.translation.global_sequence < 0 \
                                and tex_transform.translation.timestamps.n_elements > j:
                                    action = self._bl_create_action(anim_pair, name)
                                    self._bl_create_fcurves(action, obj.name, bl_convert_trans_track, 3, j, 'location',
                                                            tex_transform.translation)

                                if tex_transform.rotation.global_sequence < 0 \
                                        and tex_transform.rotation.timestamps.n_elements > j:
                                    action = self._bl_create_action(anim_pair, name)
                                    self._bl_create_fcurves(action, obj.name, bl_convert_rot_track, 4, j, 'rotation_quaternion',
                                                            tex_transform.rotation)

                                if tex_transform.scaling.global_sequence < 0 \
                                        and tex_transform.scaling.timestamps.n_elements > j:
                                    action = self._bl_create_action(anim_pair, name)
                                    self._bl_create_fcurves(action, obj.name, bl_convert_trans_track, 3, j,
                                                            'scale', tex_transform.scaling)

                                if not anim_pair.action:
                                    anim.anim_pairs.remove(cur_index)

    def load_attachments(self):
        # TODO: unknown field
        print("\nImporting attachments.")

        for i, attachment in enumerate(self.m2.root.attachments):
            bpy.ops.object.empty_add(type='SPHERE', location=(0, 0, 0))
            obj = bpy.context.view_layer.objects.active
            obj.empty_display_size = 0.07
            bpy.ops.object.constraint_add(type='CHILD_OF')
            constraint = obj.constraints[-1]
            constraint.target = self.rig
            obj.parent = self.rig
            bone = self.m2.root.bones[attachment.bone]
            constraint.subtarget = bone.name

            bl_edit_bone = self.rig.data.bones[bone.name]
            obj.location = attachment.position

            obj.name = M2AttachmentTypes.get_attachment_name(attachment.id, i)
            obj.wow_m2_attachment.enabled = True
            obj.wow_m2_attachment.type = str(attachment.id)

            # animate attachment
            obj.animation_data_create()
            obj.animation_data.action_blend_type = 'ADD'
            seq_name_table = M2SequenceNames()
            n_global_sequences = len(self.global_sequences)

            # titi test
            #slot = bpy.context.scene.wow_m2_root_elements.attachments.add()
            #slot.pointer = obj

            # load global sequence
            if attachment.animate_attached.global_sequence >= 0:
                anim = bpy.context.scene.wow_m2_animations[attachment.animate_attached.global_sequence]

                if not attachment.animate_attached.timestamps.n_elements \
                or not attachment.animate_attached.timestamps[0]:
                    return

                name = "AT_{}_{}_Global_Sequence_{}".format(i, obj.name,
                                                            str(attachment.animate_attached.global_sequence).zfill(3))

                anim_pair = anim.anim_pairs.add()
                anim_pair.type = 'OBJECT'
                anim_pair.object = obj
                anim_pair.action = self._bl_create_action(anim_pair, name)

                self._bl_create_fcurves(anim_pair.action, "", self._bl_convert_track_dummy, 1, 0,
                                        'wow_m2_attachment.animate', attachment.animate_attached)

                return

            # load animations
            for j, anim_index in enumerate(self.animations):
                anim = bpy.context.scene.wow_m2_animations[j + n_global_sequences]
                sequence = self.m2.root.sequences[anim_index]

                if attachment.animate_attached.timestamps.n_elements > anim_index:
                    if not len(attachment.animate_attached.timestamps[anim_index]):
                        continue

                    field_name = seq_name_table.get_sequence_name(sequence.id)
                    name = 'AT_{}_{}_UnkAnim'.format(i, obj.name, str(j).zfill(3)) \
                         if not field_name else "AT_{}_{}_{}_({})".format(i, obj.name, str(j).zfill(3), field_name,
                                                                          sequence.variation_index)

                    anim_pair = anim.anim_pairs.add()
                    anim_pair.type = 'OBJECT'
                    anim_pair.object = obj
                    self._bl_create_action(anim_pair, name)

                    self._bl_create_fcurves(anim_pair.action, "", self._bl_convert_track_dummy, 1, j,
                                            'wow_m2_attachment.animate', attachment.animate_attached)

    def load_lights(self):

        def animate_property(anim_pair, m2_light, prop_name, length, action_name, anim_index):

            prop_track = getattr(m2_light, prop_name)

            try:
                frames = prop_track.timestamps[anim_index]
            except IndexError:
                return

            if not len(frames):
                return

            self._bl_create_action(anim_pair, action_name)
            action_group = self._bl_create_action_group(anim_pair.action, 'Color_{}'.format(prop_name))

            self._bl_create_fcurves(anim_pair.action, action_group, self._bl_convert_track_value if length == 1 else self._bl_convert_track_tuple, length, anim_index,
                                    'data.wow_m2_light.{}'.format(prop_name), prop_track)

        for i, light in enumerate(self.m2.root.lights):
            #bpy.ops.object.lamp_add(type='POINT' if light.type else 'SPOT', location=(0, 0, 0))
            bpy.ops.object.light_add(type='POINT' if light.type else 'SPOT', location=(0, 0, 0))
            obj = bpy.context.view_layer.objects.active
            obj.data.wow_m2_light.type = str(light.type)
            obj.data.wow_m2_light.enabled = True

            if self.rig:
                obj.parent = self.rig

            if light.bone >= 0:
                bpy.ops.object.constraint_add(type='CHILD_OF')
                constraint = obj.constraints[-1]
                constraint.target = self.rig
                bone = self.m2.root.bones[light.bone]
                constraint.subtarget = bone.name

                bl_edit_bone = self.rig.data.bones[bone.name]
                obj.location = light.position

            # animate light
            obj.animation_data_create()
            obj.animation_data.action_blend_type = 'ADD'
            seq_name_table = M2SequenceNames()
            n_global_sequences = len(self.global_sequences)

            channels = [('ambient_color', 3), ('ambient_intensity', 1), ('diffuse_color', 3),
                        ('diffuse_intensity', 1), ('attenuation_start', 1), ('attenuation_end', 1), ('visibility', 1)]
            
            # titi test
            #slot = bpy.context.scene.wow_m2_root_elements.lights.add()
            #slot.pointer = obj

            # load global sequences
            for j, seq_index in enumerate(self.global_sequences):
                anim = bpy.context.scene.wow_m2_animations[seq_index]
                action_name = "LT_{}_{}_Global_Sequence_{}".format(i, obj.name, str(j).zfill(3))

                anim_pair = anim.anim_pairs.add()
                anim_pair.type = 'OBJECT'
                anim_pair.object = obj

                for channel, array_length in channels:
                    if getattr(light, channel).global_sequence == seq_index:
                        animate_property(anim_pair, light, channel, array_length, action_name, 0)

                if not anim_pair.action:
                    anim.anim_pairs.remove(-1)

            # load animations
            for j, anim_index in enumerate(self.animations):
                anim = bpy.context.scene.wow_m2_animations[j + n_global_sequences]
                sequence = self.m2.root.sequences[anim_index]

                field_name = seq_name_table.get_sequence_name(sequence.id)
                action_name = 'LT_{}_UnkAnim'.format(i, str(j).zfill(3)) if not field_name \
                    else "LT_{}_{}_({})".format(i, str(j).zfill(3), field_name, sequence.variation_index)

                anim_pair = anim.anim_pairs.add()
                anim_pair.type = 'OBJECT'
                anim_pair.object = obj

                for channel, array_length in channels:
                    if getattr(light, channel).global_sequence < 0:
                        animate_property(anim_pair, light, channel, array_length, action_name, anim_index)

                if not anim_pair.action:
                    anim.anim_pairs.remove(-1)

    def load_events(self):

        if not len(self.m2.root.events):
            print("\nNo events found to import.")
            return
        else:
            print("\nImport events.")

        for event in self.m2.root.events:
            bpy.ops.object.empty_add(type='CUBE', location=(0, 0, 0))
            obj = bpy.context.view_layer.objects.active
            obj.scale = (0.019463, 0.019463, 0.019463)
            bpy.ops.object.constraint_add(type='CHILD_OF')
            constraint = obj.constraints[-1]
            constraint.target = self.rig
            obj.parent = self.rig
            bone = self.m2.root.bones[event.bone]
            constraint.subtarget = bone.name

            bl_edit_bone = self.rig.data.bones[bone.name]
            obj.location = event.position
            token = M2EventTokens.get_event_name(event.identifier)
            obj.name = "Event_{}_{}".format(token, event.identifier)
            obj.wow_m2_event.enabled = True

            try:
                obj.wow_m2_event.token = event.identifier
            except TypeError:
                print('Warning: unknown event token \"{}\".'.format(event.identifier))

            if token in ('PlayEmoteSound',
                         'DoodadSoundUnknown',
                         'DoodadSoundOneShot',
                         'GOPlaySoundKitCustom',
                         'GOAddShake'):
                obj.wow_m2_event.data = event.data

            # animate event firing
            obj.animation_data_create()
            obj.animation_data.action_blend_type = 'ADD'
            seq_name_table = M2SequenceNames()
            n_global_sequences = len(self.global_sequences)
            
            #titi test
            #slot = bpy.context.scene.wow_m2_root_elements.events.add()
            #slot.pointer = obj

            # load global sequences
            if event.enabled.global_sequence >= 0:
                anim = bpy.context.scene.wow_m2_animations[event.enabled.global_sequence]
                if not event.enabled.timestamps.n_elements \
                or not event.enabled.timestamps[0]:
                    return

                anim_pair = anim.anim_pairs.add()
                anim_pair.type = 'OBJECT'
                anim_pair.object = obj

                name = 'ET_{}_{}_UnkAnim'.format(token, str(event.enabled.global_sequence).zfill(3))

                self._bl_create_action(anim_pair, name)
                self._bl_create_fcurves(anim_pair.action, "", self._bl_convert_track_dummy, 1, 0, 'wow_m2_event.fire',
                                        event.enabled)

                return
                        
            # load animations
            for j, anim_index in enumerate(self.animations):
                anim = bpy.context.scene.wow_m2_animations[j + n_global_sequences]
                sequence = self.m2.root.sequences[anim_index]

                if event.enabled.timestamps.n_elements > anim_index:
                    if not event.enabled.timestamps[anim_index]:
                        continue
                    
                    if '64' in anim.flags:
                        alias_next = anim.alias_next

                        final_alias = _find_final_alias(self, n_global_sequences, alias_next)

                        alias_anim = bpy.context.scene.wow_m2_animations[final_alias]              

                        for anim_pair_alias in alias_anim.anim_pairs:
                            if anim_pair_alias.type == 'OBJECT':
                                if anim_pair_alias.object == obj:
                                    anim_pair = anim.anim_pairs.add()
                                    anim_pair.type = 'OBJECT'
                                    anim_pair.object = obj       
                                    anim_pair.action = anim_pair_alias.action
                    else:
                        anim_pair = anim.anim_pairs.add()
                        anim_pair.type = 'OBJECT'
                        anim_pair.object = obj

                        field_name = seq_name_table.get_sequence_name(sequence.id)
                        name = 'ET_{}_{}_UnkAnim'.format(token, str(anim_index).zfill(3)) if not field_name \
                            else "ET_{}_{}_{}_({})".format(token, str(anim_index).zfill(3), field_name,
                                                            sequence.variation_index)

                        self._bl_create_action(anim_pair, name)
                        self._bl_create_fcurves(anim_pair.action, "", self._bl_convert_track_dummy, 1, anim_index,
                                                        'wow_m2_event.fire', event.enabled)
                    
    def load_cameras(self, timestamp_convert):

        def animate_camera_loc(anim_pair, name, cam_track, anim_index):

            try:
                frames = cam_track.timestamps[anim_index]
                track = cam_track.values[anim_index]
            except IndexError:
                return

            if not len(frames) > 1:
                return

            # create a parent for curve segments
            p_obj = bpy.data.objects.new(name, None)
            bpy.context.collection.objects.link(p_obj)

            curves = []
            for i in range(1, len(frames)):
                if timestamp_convert == 'Convert':
                    frame1 = int(round(frames[i - 1] * (bpy.context.scene.render.fps / bpy.context.scene.render.fps_base / 1000)))
                    frame2 = int(round(frames[i]  * (bpy.context.scene.render.fps / bpy.context.scene.render.fps_base / 1000)))
                else: 
                    frame1 = frames[i - 1]    
                    frame2 = frames[i]       

                curve_name = '{}_Path'.format(anim_pair.object.name)
                curve = bpy.data.curves.new(name=curve_name, type='CURVE')
                curve_obj = bpy.data.objects.new(name=curve_name, object_data=curve)
                curve_obj.parent = p_obj
                bpy.context.collection.objects.link(curve_obj)

                curve.dimensions = '3D'
                curve.resolution_u = 64

                spline = curve.splines.new('BEZIER')
                spline.resolution_u = 64
                spline.bezier_points.add(count=1)

                for j, k in enumerate((i - 1, i)):
                    spline_point = spline.bezier_points[j]
                    spline_point.co = Vector(track[k].value) + anim_pair.object.location
                    spline_point.handle_left_type = 'FREE'
                    spline_point.handle_left = Vector(track[k].in_tan) + anim_pair.object.location
                    spline_point.handle_right_type = 'FREE'
                    spline_point.handle_right = Vector(track[k].out_tan) + anim_pair.object.location

                curve_slot = anim_pair.object.wow_m2_camera.animation_curves.add()
                curve_slot.object = curve_obj
                curve_slot.duration = frame2 - frame1

                curves.append(curve_obj)

            # zero in tan of frist point and out tan of last point
            first_point = curves[0].data.splines[0].bezier_points[0]
            first_point.handle_left = first_point.co
            last_point = curves[-1].data.splines[0].bezier_points[-1]
            last_point.handle_right = last_point.co

            # create contraints and set appropriate drivers for each curve
            anim_pair.object.location = (0, 0, 0)

            # active object is required for constraints / drivers to install properly
            bpy.context.view_layer.objects.active = anim_pair.object
            update_follow_path_constraints(None, bpy.context)

        def animate_camera_roll(anim_pair, name, cam_track, anim_index):

            action = anim_pair.action

            try:
                frames = cam_track.timestamps[anim_index]
                track = cam_track.values[anim_index]
            except IndexError:
                return

            if not len(frames):
                return

            if not action:
                action = anim_pair.action = bpy.data.actions.new(name=name)

            # create fcurve
            f_curve = action.fcurves.new(data_path='rotation_axis_angle', index=0, action_group='Roll')

            # init keyframes on the curve
            f_curve.keyframe_points.add(len(frames))

            # set translation values for each channel
            for i, timestamp in enumerate(frames):
                if timestamp_convert == 'Convert':
                    frame = int(round( timestamp * ( bpy.context.scene.render.fps / bpy.context.scene.render.fps_base / 1000 )))
                else: 
                    frame = timestamp

                keyframe = f_curve.keyframe_points[i]
                keyframe.co = frame, track[i].value
                keyframe.handle_left = frame, track[i].in_tan
                keyframe.handle_left_type = 'ALIGNED'
                keyframe.handle_right = frame, track[i].out_tan
                keyframe.handle_right_type = 'ALIGNED'
                keyframe.interpolation = 'BEZIER'  # TODO: hermite

        if not len(self.m2.root.cameras):
            print("\nNo cameras found to import.")
            return
        else:
            print("\nImporting cameras.")

        camera_names = {
            0: "PortraitCam",
            1: "CharInfoCam",
            -1: "MiscCam"
        }

        for camera in self.m2.root.cameras:

            # create camera object
            cam = bpy.data.cameras.new(camera_names[camera.type])
            obj = bpy.data.objects.new(camera_names[camera.type], cam)
            bpy.context.collection.objects.link(obj)

            obj.location = camera.position_base
            obj.wow_m2_camera.type = str(camera.type)
            obj.data.clip_start = camera.near_clip
            obj.data.clip_end = camera.far_clip
            obj.data.lens_unit = 'FOV'
            obj.data.angle = camera.fov

            obj.animation_data_create()
            obj.animation_data.action_blend_type = 'ADD'

            # create camera target object
            t_obj = bpy.data.objects.new("{}_Target".format(obj.name), None)
            bpy.context.collection.objects.link(t_obj)

            t_obj.location = camera.target_position_base
            t_obj.wow_m2_camera.enabled = True
            t_obj.empty_display_size = 0.07
            t_obj.empty_display_type = 'CONE'
            t_obj.rotation_mode = 'AXIS_ANGLE'
            t_obj.rotation_axis_angle = (0, 1, 0, 0)
            t_obj.lock_rotation = (True, True, True)

            t_obj.animation_data_create()
            t_obj.animation_data.action_blend_type = 'ADD'

            # animate camera

            # load global sequences
            n_global_sequences = len(self.global_sequences)
            for j, seq_index in enumerate(self.global_sequences):
                anim = bpy.context.scene.wow_m2_animations[j]

                c_anim_pair = anim.anim_pairs.add()
                c_anim_pair.type = 'OBJECT'
                c_anim_pair.object = obj

                t_anim_pair = anim.anim_pairs.add()
                t_anim_pair.type = 'OBJECT'
                t_anim_pair.object = t_obj

                name = '{}_UnkAnim'.format(str(j).zfill(3))
                c_name = "CM{}".format(name)
                t_name = "CT{}".format(name)

                if camera.positions.global_sequence == seq_index:
                    animate_camera_loc(c_anim_pair, c_name, camera.positions, 0)

                if camera.target_position.global_sequence == seq_index:
                    animate_camera_loc(t_anim_pair, t_name, camera.target_position, 0)

                if camera.roll.global_sequence == seq_index:
                    animate_camera_roll(t_anim_pair, t_name, camera.roll, 0)

            # load animations
            anim_data_table = M2SequenceNames()
            for j, anim_index in enumerate(self.animations):
                anim = bpy.context.scene.wow_m2_animations[j + n_global_sequences]
                sequence = self.m2.root.sequences[anim_index]

                if '64' in anim.flags:
                    alias_next = anim.alias_next

                    final_alias = _find_final_alias(self, n_global_sequences, alias_next)

                    alias_anim = bpy.context.scene.wow_m2_animations[final_alias]              

                    for anim_pair_alias in alias_anim.anim_pairs:
                        if anim_pair_alias.type == 'OBJECT':
                            if anim_pair_alias.object == obj:
                                anim_pair = anim.anim_pairs.add()
                                anim_pair.type = 'OBJECT'
                                anim_pair.object = obj       
                                anim_pair.action = anim_pair_alias.action
                            elif anim_pair_alias.object == t_obj:
                                anim_pair = anim.anim_pairs.add()
                                anim_pair.type = 'OBJECT'
                                anim_pair.object = t_obj       
                                anim_pair.action = anim_pair_alias.action
                else:

                    c_anim_pair = anim.anim_pairs.add()
                    c_anim_pair.type = 'OBJECT'
                    c_anim_pair.object = obj

                    t_anim_pair = anim.anim_pairs.add()
                    t_anim_pair.type = 'OBJECT'
                    t_anim_pair.object = t_obj

                    field_name = anim_data_table.get_sequence_name(sequence.id)
                    name = '_{}_UnkAnim'.format(str(anim_index).zfill(3)) if not field_name \
                        else "_{}_{}_({})".format(str(anim_index).zfill(3), field_name, sequence.variation_index)

                    c_name = "CM{}".format(name)
                    t_name = "CT{}".format(name)

                    if camera.positions.global_sequence < 0:
                        animate_camera_loc(c_anim_pair, c_name, camera.positions, anim_index)

                    if camera.target_position.global_sequence < 0:
                        animate_camera_loc(t_anim_pair, t_name, camera.target_position, anim_index)

                    if camera.roll.global_sequence < 0:
                        animate_camera_roll(t_anim_pair, t_name, camera.roll, anim_index)

            # set target for camera
            bpy.context.view_layer.objects.active = obj  # active object is required for constraints to install properly
            obj.wow_m2_camera.target = t_obj

    def load_ribbons(self):
        if not len(self.m2.root.ribbon_emitters):
            print("\nNo ribbons found to import.")
            return
        else:
            print("\nImport ribbons.")

        loaded_mats = {}
        for i,ribbon in enumerate(self.m2.root.ribbon_emitters):
            bpy.ops.object.empty_add(type='SPHERE', location=(0, 0, 0))
            obj = bpy.context.view_layer.objects.active
            obj.empty_display_size = 0.07
            bpy.ops.object.constraint_add(type='CHILD_OF')
            constraint = obj.constraints[-1]
            constraint.target = self.rig
            obj.parent = self.rig
            bone = self.m2.root.bones[ribbon.bone_index]
            constraint.subtarget = bone.name

            bl_edit_bone = self.rig.data.bones[bone.name]
            obj.location = ribbon.position

            obj.name = f'Ribbon {i}'
            obj.wow_m2_ribbon.enabled = True

            obj.wow_m2_ribbon.edges_per_second = ribbon.edges_per_second
            obj.wow_m2_ribbon.edge_lifetime = ribbon.edge_lifetime
            obj.wow_m2_ribbon.gravity = ribbon.gravity
            obj.wow_m2_ribbon.texture_rows = ribbon.texture_rows
            obj.wow_m2_ribbon.texture_cols = ribbon.texture_cols

            obj.animation_data_create()
            obj.animation_data.action_blend_type = 'ADD'

            for tex_id in ribbon.texture_indices:
                tex = self.load_texture(tex_id)
                slot = obj.wow_m2_ribbon.textures.add()
                slot.pointer = tex

            for mat_id in ribbon.material_indices:
                mat = None
                if mat_id in loaded_mats:
                    mat = loaded_mats[mat_id]
                else:
                    material = self.m2.root.materials[mat_id]
                    mat = bpy.data.materials.new(name=f'Ribbon Material #{mat_id}')
                    mat.wow_m2_material.enabled = True
                    mat.wow_m2_material.texture_1_render_flags = parse_bitfield(material.flags, 0x800)
                    mat.wow_m2_material.texture_1 = tex
                    mat.wow_m2_material.texture_1_blending_mode = str(material.blending_mode)
                    loaded_mats[mat_id] = mat

            slot = obj.wow_m2_ribbon.materials.add()
            slot.pointer = mat

            self._bl_create_sequences(ribbon,'color_track',
                f'RB_{i}',obj,'wow_m2_ribbon','color',3,self._bl_convert_track_tuple)

            self._bl_create_sequences(ribbon,'alpha_track',
                f'RB_{i}',obj,'wow_m2_ribbon','alpha',1,lambda value: [value/0x7fff])

            self._bl_create_sequences(ribbon,'height_above_track',
                f'RB_{i}',obj,'wow_m2_ribbon','height_above',1,self._bl_convert_track_value)

            self._bl_create_sequences(ribbon,'height_below_track',
                f'RB_{i}',obj,'wow_m2_ribbon','height_below',1,self._bl_convert_track_value)

            self._bl_create_sequences(ribbon,'tex_slot_track',
                f'RB_{i}',obj,'wow_m2_ribbon','texture_slot',1,self._bl_convert_track_value)

            self._bl_create_sequences(ribbon,'visibility_track',
                f'RB_{i}',obj,'wow_m2_ribbon','visibility',1,self._bl_convert_track_value)

    def load_particles(self, timestamp_convert):
        if not len(self.m2.root.particle_emitters):
            print("\nNo particles found to import.")
            return
        else:
            print("\nImport particles.")

        for i,m2_particle in enumerate(self.m2.root.particle_emitters):
            bpy.ops.object.empty_add(type='SPHERE', location=(0,0,0))
            obj = bpy.context.view_layer.objects.active
            obj.empty_display_size = 0.07
            bpy.ops.object.constraint_add(type='CHILD_OF')
            constraint = obj.constraints[-1]
            constraint.target = self.rig
            obj.parent = self.rig
            bone = self.m2.root.bones[m2_particle.bone]
            constraint.subtarget = bone.name
            obj.location = m2_particle.position
            obj.name = f'Particle {i}'
            obj.wow_m2_particle.enabled = True
            obj.animation_data_create()
            bl_particle = obj.wow_m2_particle

            # static fields
            bl_particle.enabled = True
            bl_particle.flags = parse_bitfield(m2_particle.flags, 0x80000)
            bl_particle.texture = self.load_texture(m2_particle.texture)
            bl_particle.geometry_model_filename = m2_particle.geometry_model_filename.value
            bl_particle.recursion_model_filename = m2_particle.recursion_model_filename.value
            bl_particle.blending_type = str(m2_particle.blending_type)
            bl_particle.emitter_type = str(m2_particle.emitter_type)
            bl_particle.particle_color_index = m2_particle.particle_color_index
            try: 
                bl_particle.particle_type = str(m2_particle.particle_type)
            except TypeError:
                bl_particle.particle_type = '0'
            try:
                bl_particle.side = str(m2_particle.head_or_tail)
            except TypeError:
                bl_particle.side = '0'
            bl_particle.texture_tile_rotation = m2_particle.texture_tile_rotation
            bl_particle.texture_dimensions_rows = m2_particle.texture_dimensions_rows
            bl_particle.texture_dimensions_cols = m2_particle.texture_dimension_columns
            bl_particle.lifespan_vary = m2_particle.life_span_vary
            bl_particle.emission_rate_vary = m2_particle.emission_rate_vary
            bl_particle.scale_vary = m2_particle.scale_vary
            bl_particle.tail_length = m2_particle.tail_length
            bl_particle.twinkle_speed = m2_particle.twinkle_speed
            bl_particle.twinkle_percent = m2_particle.twinkle_percent
            bl_particle.twinkle_scale = (m2_particle.twinkle_scale.min,m2_particle.twinkle_scale.max)
            bl_particle.burst_multiplier = m2_particle.burst_multiplier
            bl_particle.drag = m2_particle.drag
            bl_particle.basespin = m2_particle.basespin
            bl_particle.base_spin_vary = m2_particle.base_spin_vary
            bl_particle.spin = m2_particle.spin
            bl_particle.spin_vary = m2_particle.spin_vary
            bl_particle.tumble_min = m2_particle.tumble.model_rotation_speed_min
            bl_particle.tumble_max = m2_particle.tumble.model_rotation_speed_max
            bl_particle.wind = m2_particle.wind_vector
            bl_particle.wind_time = m2_particle.wind_time
            bl_particle.follow_speed_1 = m2_particle.follow_speed1
            bl_particle.follow_scale_1 = m2_particle.follow_scale1
            bl_particle.follow_speed_2 = m2_particle.follow_speed2
            bl_particle.follow_scale_2 = m2_particle.follow_scale2

            # animations
            self._bl_create_sequences(m2_particle,'emission_speed',
                f'PT_{i}',obj,'wow_m2_particle','emission_speed',1,self._bl_convert_track_value)

            self._bl_create_sequences(m2_particle,'speed_variation',
                f'PT_{i}',obj,'wow_m2_particle','speed_variation',1,self._bl_convert_track_value)

            self._bl_create_sequences(m2_particle,'vertical_range',
                f'PT_{i}',obj,'wow_m2_particle','vertical_range',1,self._bl_convert_track_value)

            self._bl_create_sequences(m2_particle,'horizontal_range',
                f'PT_{i}',obj,'wow_m2_particle','horizontal_range',1,self._bl_convert_track_value)

            self._bl_create_sequences(m2_particle,'gravity',
                f'PT_{i}',obj,'wow_m2_particle','gravity',1,self._bl_convert_track_value)

            self._bl_create_sequences(m2_particle,'lifespan',
                f'PT_{i}',obj,'wow_m2_particle','lifespan',1,self._bl_convert_track_value)

            self._bl_create_sequences(m2_particle,'emission_rate',
                f'PT_{i}',obj,'wow_m2_particle','emission_rate',1,self._bl_convert_track_value)

            self._bl_create_sequences(m2_particle,'emission_area_length',
                f'PT_{i}',obj,'wow_m2_particle','emission_area_length',1,self._bl_convert_track_value)

            self._bl_create_sequences(m2_particle,'emission_area_width',
                f'PT_{i}',obj,'wow_m2_particle','emission_area_width',1,self._bl_convert_track_value)

            self._bl_create_sequences(m2_particle,'z_source',
                f'PT_{i}',obj,'wow_m2_particle','z_source',1,self._bl_convert_track_value)

            self._bl_create_sequences(m2_particle,'enabled_in',
                f'PT_{i}',obj,'wow_m2_particle','active',1,self._bl_convert_track_value)

            def create_fcurve_track(action, m2_track,bl_track_name, group_name, track_count, conv = lambda x: x):
                fcurves = [action.fcurves.new(data_path="wow_m2_particle."+bl_track_name, index=k, action_group=group_name)
                    for k in range(track_count)
                ]

                frame_count = len(m2_track.timestamps)

                for fcurve in fcurves:
                    fcurve.keyframe_points.add(frame_count)

                for k in range(frame_count):
                    if timestamp_convert == 'Convert':
                        time = int(round( m2_track.timestamps[k] * (bpy.context.scene.render.fps / bpy.context.scene.render.fps_base / 1000)))
                    else: 
                        time = m2_track.timestamps[k]
                    value = conv(m2_track.keys[k])
                    for j,fcurve in enumerate(fcurves):
                        keyframe = fcurve.keyframe_points[k]
                        keyframe.co = (time, value if track_count == 1 else value[j])
                        keyframe.interpolation = 'LINEAR'

            obj.animation_data_create()
            obj.animation_data.action_blend_type = 'ADD'
            particle_action = bpy.data.actions.new(name=f'PT_{obj.name}_particle_tracks')
            particle_action.use_fake_user = True
            obj.wow_m2_particle.action = particle_action
            create_fcurve_track(particle_action, m2_particle.color_track,'color','Color',3, lambda x: (x[0]/255,x[1]/255,x[2]/255))
            create_fcurve_track(particle_action, m2_particle.alpha_track,'alpha','',1,lambda x: x/0x7fff)
            create_fcurve_track(particle_action, m2_particle.scale_track,'scale','Scale',2)
            create_fcurve_track(particle_action, m2_particle.head_cell_track,'head_cell','',1)
            create_fcurve_track(particle_action, m2_particle.tail_cell_track,'tail_cell','',1)

            spline_action = bpy.data.actions.new(name=f'PT_{obj.name}_particle_spline')
            spline_action.use_fake_user = True
            obj.wow_m2_particle.spline_action = spline_action
            fake_spline_fcurve = FBlock(vec3D)
            fake_spline_fcurve.interpolation_type = 1
            for i,spline in enumerate(m2_particle.spline_points):
                if timestamp_convert == 'Convert':
                    fake_spline_fcurve.timestamps.append(int(round(i / (bpy.context.scene.render.fps / bpy.context.scene.render.fps_base / 1000))))
                else: 
                    fake_spline_fcurve.timestamps.append(i)
                fake_spline_fcurve.keys.append(spline)
            create_fcurve_track(spline_action, fake_spline_fcurve, 'spline_point','Spline', 3)

    def load_collision(self):

        if not len(self.m2.root.collision_vertices):
            print("\nNo collision mesh found to import.")
            return
        else:
            print("\nImporting collision mesh.")

        vertices = [vertex for vertex in self.m2.root.collision_vertices]
        triangles = [self.m2.root.collision_triangles[i:i+3]
                     for i in range(0, len(self.m2.root.collision_triangles), 3)]

        # create mesh
        mesh = bpy.data.meshes.new(self.m2.root.name.value)
        mesh.from_pydata(vertices, [], triangles)

        for poly in mesh.polygons:
            poly.use_smooth = True

        # create object
        obj = bpy.data.objects.new('Collision', mesh)
        bpy.context.collection.objects.link(obj)
        obj.wow_m2_geoset.collision_mesh = True
        obj.hide_set(True)
        bl_mat = bpy.data.materials.new(name="Collision")
        bl_mat.blend_method = 'BLEND'
        bl_mat.use_nodes = True
        node_tree = bl_mat.node_tree
        for node in node_tree.nodes:
            node_tree.nodes.remove(node)
        transparent_bsdf = node_tree.nodes.new(type='ShaderNodeBsdfTransparent')
        output_node = node_tree.nodes.new(type='ShaderNodeOutputMaterial')
        node_tree.links.new(transparent_bsdf.outputs["BSDF"], output_node.inputs["Surface"])
        bsdf = bl_mat.node_tree.nodes["Transparent BSDF"]
        bsdf.inputs['Color'].default_value = (0.381325, 0.887923, 0.371238, 1)
        obj.data.materials.append(bl_mat)


    def load_globalflags(self):
        print("\nImporting global flags.")
        armature = next((obj for obj in bpy.data.objects if obj.type == 'ARMATURE'), None)
        armature.wow_m2_globalflags.enabled = True
        bl_globalflags = armature.wow_m2_globalflags

        bl_globalflags.enabled = True
        if self.m2.root.version >= M2Versions.LEGION:
            bl_globalflags.flagsLegion = parse_bitfield(self.m2.root.global_flags, 0x200000)
        else:
            # Vanilla/TBC/WotLK only use the low global flags (0x1..0x10).
            bl_globalflags.flagsLK = parse_bitfield(self.m2.root.global_flags, 0x10)

    def prepare_export_axis(self, forward_axis, scale):
        self.scale = scale
        self.forward_axis = forward_axis

        armatures = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
        # check for > 1 is later
        if len(armatures) > 0:
            armature = armatures[0]
            scale = armature.scale
            if abs(scale[0]-scale[1])>0.0001 or abs(scale[0]-scale[2])>0.0001:
                raise ValueError(f'Non-uniform object scaling in armature {armature.name}, WBS doesn\'t know how to do this yet :(')
            self.scale *= scale[0]

        if forward_axis == 'X+':
            self.axis_order = [0,1]
            self.axis_polarity = [1,1]
        elif forward_axis == 'X-':
            self.axis_order = [0,1]
            self.axis_polarity = [-1,-1]
        elif forward_axis == 'Y+':
            self.axis_order = [1,0]
            self.axis_polarity = [1,-1]
        elif forward_axis == 'Y-':
            self.axis_order = [1,0]
            self.axis_polarity = [-1,1]
        else:
            raise ValueError(f'Invalid forward axis: {forward_axis}')

    def _convert_vec(self,vec):
        return (
            vec[self.axis_order[0]] * self.axis_polarity[0] * self.scale,
            vec[self.axis_order[1]] * self.axis_polarity[1] * self.scale,
            vec[2] * self.scale
        )

    def prepare_pose(self, selected_only):

        if bpy.context.object:
            self.old_mode = bpy.context.object.mode
        else:
            armatures = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
            armature = armatures[0]
            bpy.data.objects[armature.name].select_set(True)
            bpy.context.view_layer.objects.active = bpy.data.objects[armature.name]
            self.old_mode = bpy.context.object.mode 
        
        

        self.old_selections = [obj for obj in bpy.context.selected_objects]
        self.old_active = bpy.context.active_object

        objects = bpy.context.selected_objects if selected_only else bpy.context.scene.objects

        # TODO: this is a temporary fix to reset pose, because wbs uses the wrong data
        #       when reading bone and vertex positions.
        for obj in objects:
            if obj.type != 'ARMATURE' or not obj.animation_data:
                continue
            if obj.animation_data and obj.animation_data.action:
                self.old_actions.append((obj,obj.animation_data.action))

            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            action = bpy.data.actions.new(name=obj.name+"__RESET_POSE")
            self.reset_pose_actions.append(action)
            for bone in obj.data.bones:
                def make_curve(data_path,index, value):
                    curve = action.fcurves.new(data_path = data_path, index = index)
                    curve.keyframe_points.add(1)
                    curve.keyframe_points[0].co[0] = 0
                    curve.keyframe_points[0].co[1] = value

                make_curve(f"pose.bones[\"{bone.name}\"].rotation_quaternion", 0, 1)
                for i in range(3):
                    make_curve(f"pose.bones[\"{bone.name}\"].location", i, 0)
                    make_curve(f"pose.bones[\"{bone.name}\"].scale", i, 1)
                    make_curve(f"pose.bones[\"{bone.name}\"].rotation_quaternion", i+1, 0)
            obj.animation_data.action = action

    def restore_pose(self):
        for (obj,action) in self.old_actions:
            obj.animation_data.action = action

        for action in self.reset_pose_actions:
            bpy.data.actions.remove(action)

        bpy.ops.object.select_all(action='DESELECT')
        for obj in self.old_selections:
            obj.select_set(True)
        if self.old_active:
            bpy.context.view_layer.objects.active = self.old_active
        if self.old_mode:
            bpy.ops.object.mode_set( mode = self.old_mode )

    def save_properties(self, filepath, selected_only):
        self.m2.root.name.value = os.path.basename(os.path.splitext(filepath)[0])
        objects = bpy.context.selected_objects if selected_only else bpy.context.scene.objects

        b_min, b_max = get_objs_boundbox_world(filter(lambda ob: not ob.wow_m2_geoset.collision_mesh
                                                                and ob.type == 'MESH'
                                                                and not ob.hide_get(), objects))
        b_min = self._convert_vec(b_min)
        b_max = self._convert_vec(b_max)

        self.m2.root.bounding_box.min = b_min
        self.m2.root.bounding_box.max = b_max
        self.m2.root.bounding_sphere_radius = sqrt(((b_max[self.axis_order[0]]-b_min[self.axis_order[0]]) * self.axis_polarity[0] * self.scale) ** 2
                                                + ((b_max[self.axis_order[1]]-b_min[self.axis_order[1]]) * self.axis_polarity[1] * self.scale) ** 2
                                                + ((b_max[2]-b_min[2])) ** 2) / 2

        # TODO: flags, collision bounding box

    def save_bones(self, selected_only):

        def add_bone(bl_bone):
            key_bone_id = int(bl_bone.wow_m2_bone.key_bone_id)
            flags = construct_bitfield(bl_bone.wow_m2_bone.flags)
            parent_bone = self.bone_ids[bl_bone.parent.name] if bl_bone.parent else -1
            pivot = self._convert_vec(bl_bone.head)

            m2_bone = self.bone_ids[bl_bone.name] = self.m2.add_bone(
                pivot,
                key_bone_id,
                flags,
                parent_bone,
                bl_bone.wow_m2_bone.submesh_id,
                ctypes.c_uint(bl_bone.wow_m2_bone.bone_name_crc).value
            )

        rigs = list(filter(lambda ob: ob.type == 'ARMATURE' and not ob.hide_get(), bpy.context.scene.objects))

        if len(rigs) > 1:
            raise Exception('Error: M2 exporter does not support more than one armature. Hide or remove the extra one.')

        for rig in rigs:
            self.rig = rig
            bpy.context.view_layer.objects.active = rig
            bpy.ops.object.mode_set(mode='EDIT')

            armature = rig.data

            has_unsorted_bones = False
            for bone in armature.edit_bones:
                if bone.wow_m2_bone.sort_index < 0:
                    has_unsorted_bones = True
                    break

            if has_unsorted_bones:
                # find root bone, check if we only have one root bone
                root_bone = None
                global_bones = []
                for bone in armature.edit_bones:
                    if root_bone is not None and bone.parent is None and bone.children:
                        raise Exception('Error: M2 exporter does not support more than one global root bone.')

                    if bone.parent is None:
                        if bone.children:
                            root_bone = bone
                            add_bone(root_bone)
                        else:
                            global_bones.append(bone)

                # add global bones
                for bone in global_bones:
                    add_bone(bone)

                # find root keybone, write additional bones
                root_keybone = None

                if root_bone:
                    for bone in root_bone.children:

                        if bone.wow_m2_bone.key_bone_id == '26':
                            root_keybone = bone
                            continue

                        add_bone(bone)
                        for child_bone in bone.children_recursive:
                            add_bone(child_bone)

                # write root keybone and its children
                if root_keybone:
                    add_bone(root_keybone)
                    for bone in root_keybone.children_recursive:
                        add_bone(bone)
            else:
                all_bones = [bone for bone in armature.edit_bones]
                all_bones.sort(key=lambda x:x.wow_m2_bone.sort_index)
                for bone in all_bones: add_bone(bone)

            bpy.ops.object.mode_set(mode='OBJECT')

            break

        else:
            # Add an empty bone, if the model is not animated
            if selected_only:
                bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')
                origin = self._convert_vec(get_origin_position())
            else:
                origin = self._convert_vec(get_origin_position())

        # TODO: should we always do this?
        if len(self.m2.root.key_bone_lookup) == 0:
            self.m2.root.key_bone_lookup.append(-1)

    def save_cameras(self):
        cameras = [cam for cam in bpy.data.objects if cam.type == 'CAMERA']
        cameras.sort(key=lambda cam: int(cam.wow_m2_camera.type) if int(cam.wow_m2_camera.type) >= 0 else 3)
        for i, blender_cam in tqdm(enumerate(cameras), desc='Exporting Cameras', ascii=True):
            self.camera_ids[blender_cam.name] = i
            m2_cam = M2Camera()
            m2_cam.position_base = self._convert_vec(blender_cam.location)
            m2_cam.type = int(blender_cam.wow_m2_camera.type)
            m2_cam.near_clip = blender_cam.data.clip_start
            m2_cam.far_clip = blender_cam.data.clip_end
            m2_cam.fov = blender_cam.data.angle

            if blender_cam.wow_m2_camera.target:
                m2_cam.target_position_base = self._convert_vec(blender_cam.wow_m2_camera.target.location)
                self.camera_target_ids[blender_cam.wow_m2_camera.target.name] = i

            self.m2.root.cameras.append(m2_cam)
            if m2_cam.type >= 0:
                while len(self.m2.root.camera_lookup_table) <= m2_cam.type:
                    self.m2.root.camera_lookup_table.append(-1)
                self.m2.root.camera_lookup_table.set_index(m2_cam.type, i)

    def save_attachments(self):
        attachments = [obj for obj in bpy.data.objects if obj.type == 'EMPTY' and obj.wow_m2_attachment.enabled]

        if not attachments:
            return

        attachments.sort(key=lambda att: int(att.wow_m2_attachment.type) if int(att.wow_m2_attachment.type) >= 0 else float('inf'))

        for i, bl_att in tqdm(enumerate(attachments), desc='Exporting Attachments', ascii=True):
            self.attachment_ids[bl_att.name] = i
            att = M2Attachment()
            self.m2.root.attachments.append(att)
            att.id = int(bl_att.wow_m2_attachment.type)
            if len(bl_att.constraints) > 0:
                # TODO: properly find constraint
                att.bone = self.bone_ids[bl_att.constraints[0].subtarget]
                att.position = self._convert_vec(bl_att.location)
            while len(self.m2.root.attachment_lookup_table) <= att.id:
                self.m2.root.attachment_lookup_table.append(0xffff)
            self.m2.root.attachment_lookup_table.set_index(att.id,i)

    def save_events(self):
        events = [obj for obj in bpy.data.objects if obj.type == 'EMPTY' and obj.wow_m2_event.enabled]

        if not events:
            return

        for i, bl_evt in tqdm(enumerate(events), desc='Exporting Events', ascii=True):
            self.event_ids[bl_evt.name] = i
            evt = M2Event()
            self.m2.root.events.append(evt)
            evt.identifier = bl_evt.wow_m2_event.token
            token = M2EventTokens.get_event_name(evt.identifier)
            if len(bl_evt.constraints) > 0:
                # TODO: properly find constraint
                evt.bone = self.bone_ids[bl_evt.constraints[0].subtarget]
                evt.position = self._convert_vec(bl_evt.location)
            if token in ('PlayEmoteSound',
                'DoodadSoundUnknown',
                'DoodadSoundOneShot',
                'GOPlaySoundKitCustom',
                'GOAddShake'):
                evt.data = bl_evt.wow_m2_event.data
            self.final_events[bl_evt.name] = evt

    def save_lights(self):
        lights = [light for light in bpy.data.objects if light.type == 'LIGHT' and light.data.wow_m2_light.enabled]

        if not lights:
            return        

        for i, bl_light in tqdm(enumerate(lights), desc='Exporting Lights', ascii=True):
            self.light_ids[bl_light.name] = i
            light = M2Light()
            self.m2.root.lights.append(light)
            light.type = int(bl_light.data.wow_m2_light.type)
            if len(bl_light.constraints) > 0:
                # TODO: properly find constraint
                light.bone = self.bone_ids[bl_light.constraints[0].subtarget]
            light.position = self._convert_vec(bl_light.location)

    def save_ribbons(self):
        ribbons = [obj for obj in bpy.data.objects if obj.type == 'EMPTY' and obj.wow_m2_ribbon.enabled]

        if not ribbons:
            return

        ribbon_textures = {}
        ribbon_materials = {}

        for i, bl_ribbon in tqdm(enumerate(ribbons), desc='Exporting Ribbons', ascii=True):
            self.ribbon_ids[bl_ribbon.name] = i
            m2_ribbon = M2Ribbon()
            self.m2.root.ribbon_emitters.append(m2_ribbon)
            if len(bl_ribbon.constraints) > 0:
                m2_ribbon.bone_index = self.bone_ids[bl_ribbon.constraints[0].subtarget]
            m2_ribbon.position = self._convert_vec(bl_ribbon.location)
            m2_ribbon.edges_per_second = bl_ribbon.wow_m2_ribbon.edges_per_second
            m2_ribbon.edge_lifetime = bl_ribbon.wow_m2_ribbon.edge_lifetime
            m2_ribbon.gravity = bl_ribbon.wow_m2_ribbon.gravity
            m2_ribbon.texture_rows = bl_ribbon.wow_m2_ribbon.texture_rows
            m2_ribbon.texture_cols = bl_ribbon.wow_m2_ribbon.texture_cols

            for tex_slot in bl_ribbon.wow_m2_ribbon.textures:
                bl_texture = tex_slot.pointer
                if bl_texture in ribbon_textures:
                    tex_id = ribbon_textures[bl_texture]
                else:
                    tex_id = self.m2.add_texture(
                        bl_texture.wow_m2_texture.path,
                        construct_bitfield(bl_texture.wow_m2_texture.flags),
                        int(bl_texture.wow_m2_texture.texture_type)
                    )
                    ribbon_textures[bl_texture] = tex_id
                m2_ribbon.texture_indices.append(tex_id)
                wow_path = bl_texture.wow_m2_texture.path
                self.final_textures[wow_path] = tex_id

            for mat_slot in bl_ribbon.wow_m2_ribbon.materials:
                bl_mat = mat_slot.pointer
                if bl_mat in ribbon_materials:
                    mat_id = ribbon_materials[bl_mat]
                else:
                    m2_mat = M2Material()
                    mat_id = self.m2.root.materials.add(m2_mat)
                    m2_mat.flags = construct_bitfield(bl_mat.wow_m2_material.texture_1_render_flags)
                    m2_mat.blending_mode = int(bl_mat.wow_m2_material.texture_1_blending_mode)
                    ribbon_materials[bl_mat] = mat_id
                m2_ribbon.material_indices.append(mat_id)

    def save_particles(self, timestamp_convert):
        particles = [obj for obj in bpy.data.objects if obj.type == 'EMPTY' and obj.wow_m2_particle.enabled]

        if not particles:
            return

        particle_textures = {}

        for i, bl_obj in tqdm(enumerate(particles), desc='Saving Particles', ascii=True):
            self.particle_ids[bl_obj.name] = i
            m2_particle = M2Particle()
            self.m2.root.particle_emitters.append(m2_particle)
            bl_particle = bl_obj.wow_m2_particle

            m2_particle.particle_id = 4294967295
            m2_particle.position = bl_obj.location

            if len(bl_obj.constraints) > 0:
                m2_particle.bone = self.bone_ids[bl_obj.constraints[0].subtarget]

            bl_texture = bl_particle.texture
            if bl_texture:
                if bl_texture in particle_textures:
                    m2_particle.texture = particle_textures[bl_texture]
                else:
                    m2_particle.texture = self.m2.add_texture(
                        bl_texture.wow_m2_texture.path,
                        construct_bitfield(bl_texture.wow_m2_texture.flags),
                        int(bl_texture.wow_m2_texture.texture_type)
                    )
                wow_path = bl_texture.wow_m2_texture.path
                self.final_textures[wow_path] = m2_particle.texture
            else:
                m2_particle.texture = 0

            m2_particle.flags = construct_bitfield(bl_particle.flags)
            m2_particle.geometry_model_filename.value = bl_particle.geometry_model_filename
            m2_particle.recursion_model_filename.value = bl_particle.recursion_model_filename
            m2_particle.blending_type = int(bl_particle.blending_type)
            m2_particle.emitter_type = int(bl_particle.emitter_type)
            m2_particle.particle_color_index = bl_particle.particle_color_index
            m2_particle.particle_type = int(bl_particle.particle_type)
            m2_particle.head_or_tail = int(bl_particle.side)
            m2_particle.texture_tile_rotation = bl_particle.texture_tile_rotation
            m2_particle.texture_dimensions_rows = bl_particle.texture_dimensions_rows
            m2_particle.texture_dimension_columns = bl_particle.texture_dimensions_cols
            m2_particle.life_span_vary = bl_particle.lifespan_vary
            m2_particle.emission_rate_vary = bl_particle.emission_rate_vary
            m2_particle.scale_vary = tuple(bl_particle.scale_vary)
            m2_particle.tail_length = bl_particle.tail_length
            m2_particle.twinkle_speed = bl_particle.twinkle_speed
            m2_particle.twinkle_percent = bl_particle.twinkle_percent
            m2_particle.twinkle_scale.min = bl_particle.twinkle_scale[0]
            m2_particle.twinkle_scale.max = bl_particle.twinkle_scale[1]
            m2_particle.burst_multiplier = bl_particle.burst_multiplier
            m2_particle.drag = bl_particle.drag
            m2_particle.basespin = bl_particle.basespin
            m2_particle.base_spin_vary = bl_particle.basespin_vary
            m2_particle.spin = bl_particle.spin
            m2_particle.spin_vary = bl_particle.spin_vary
            m2_particle.tumble.model_rotation_speed_min = tuple(bl_particle.tumble_min)
            m2_particle.tumble.model_rotation_speed_max = tuple(bl_particle.tumble_max)
            m2_particle.wind_vector = tuple(bl_particle.wind)
            m2_particle.wind_time = bl_particle.wind_time
            m2_particle.follow_speed1 = bl_particle.follow_speed_1
            m2_particle.follow_scale1 = bl_particle.follow_scale_1
            m2_particle.follow_speed2 = bl_particle.follow_speed_2
            m2_particle.follow_scale2 = bl_particle.follow_scale_2

            def export_fcurve(m2_track,action,data_path,has_time,conv = lambda x: x):
                fcurves = [fcurve for fcurve in action.fcurves if fcurve.data_path == 'wow_m2_particle.'+data_path]
                if len(fcurves) == 0:
                    # TODO: warning?
                    return

                keyframe_count = len(fcurves[0].keyframe_points)
                for i,fcurve in enumerate(fcurves):
                    cur_count = len(fcurve.keyframe_points)
                    if cur_count != keyframe_count:
                        raise ValueError(f'Track index {i} keyframe count ({cur_count}) is different from index 0 {keyframe_count} in {action}, {data_path}')

                for i in range(keyframe_count):
                    values = []
                    for fcurve in fcurves:
                        values.append(fcurve.keyframe_points[i].co[1])
                    values = conv(tuple(values) if len(values)>1 else values[0])
                    if has_time:
                        if timestamp_convert == 'Convert':
                            time = int(round(fcurves[0].keyframe_points[i].co[0] / (bpy.context.scene.render.fps / bpy.context.scene.render.fps_base / 1000)))
                        else: 
                            time = int(fcurves[0].keyframe_points[i].co[0])                   
                        m2_track.timestamps.append(time)
                        m2_track.keys.append(values)
                    else:
                        m2_track.append(values)

            if bl_particle.action:
                export_fcurve(m2_particle.color_track, bl_particle.action, 'color', True, lambda x: (x[0]*255,x[1]*255,x[2]*255))
                export_fcurve(m2_particle.alpha_track, bl_particle.action, 'alpha', True, lambda x: int(x*0x7fff))
                export_fcurve(m2_particle.scale_track, bl_particle.action, 'scale', True)
                export_fcurve(m2_particle.head_cell_track, bl_particle.action, 'head_cell', True, lambda x: int(x))
                export_fcurve(m2_particle.tail_cell_track, bl_particle.action, 'tail_cell', True, lambda x: int(x))

            if bl_particle.spline_action:
                export_fcurve(m2_particle.spline_points, bl_particle.spline_action, 'spline_point', False)

    def save_animations(self, timestamp_convert):
        def bl_to_m2_time(bl):
            if timestamp_convert == 'Convert':
                return int(round( bl / (bpy.context.scene.render.fps / bpy.context.scene.render.fps_base / 1000)))
            else: 
                return int(bl)                    

        #def bl_to_m2_quat(n):
            #n = max(min(n,1),-1) * 32767
            #return int(n + 32767 if n <= 0 else n-32768)
        
        def bl_to_m2_quat(n, threshold=1e-7):
            n = max(min(n, 1), -1) * 32767
            if abs(n) < threshold:
                n = 0
            return int(n + 32767 if n <= 0 else n - 32768)

        def bl_to_m2_interpolation(interpolation):
            if interpolation == 'CONSTANT': return 0
            if interpolation == 'LINEAR': return 1
            if interpolation == 'BEZIER': return 2
            if interpolation == 'CUBIC': return 3
            raise AssertionError('Invalid interpolation type ' + interpolation)

        def bl_find_interpolation(fcurve):
            last_interp = None
            for point in fcurve.keyframe_points:
                if last_interp is None:
                    last_interp = point.interpolation
                else:
                    # wow does not support changing interpolation type
                    assert last_interp == point.interpolation
            return last_interp

        def func_animations_count():
            global_seq_count = 0
            for wow_seq in bpy.context.scene.wow_m2_animations:
                if wow_seq.is_global_sequence:
                    global_seq_count += 1
                    
            return len(bpy.context.scene.wow_m2_animations) - global_seq_count
        
        # Used to measure the highest duration for any keyframe of a given sequence index
        global_seq_durations = {}
        seq_durations = {}

        # Used to ensure consistent data between tracks
        track_global_sequences = {}
        track_interpolations = {}

        class ObjectTracks:
            def __init__(self,seq_id,global_seq_id,pair,callback):
                self.seq_id = seq_id
                self.global_seq_id = global_seq_id
                self.compounds = make_fcurve_compound(pair.action.fcurves)
                self.pair = pair
                self.n_animations = func_animations_count()
                callback(self,pair)

            def get_paths(self):
                return self.compounds.keys()

            def get_curves(self, path):
                return self.compounds[path]

            def ensure_track_length(self, track, seq_id, anim_count, value_type=None, fill_tracks=False):

                while len(track.timestamps) <= seq_id:
                    track.timestamps.add(M2Array(uint32))

                if seq_id > 0 or fill_tracks:
                    while len(track.timestamps) < anim_count:
                        track.timestamps.add(M2Array(uint32))

                if value_type is not None:
                    while len(track.values) <= seq_id:
                        track.values.add(M2Array(value_type))

                    if seq_id > 0 or fill_tracks:
                        while len(track.values) < anim_count:
                            track.values.add(M2Array(value_type))

            def write_track(self,path,track_count,m2_track,value_type,converter = lambda x: x, fill_tracks = False):
                # Exit on empty tracks
                if not path in self.compounds and not fill_tracks:
                        #print("M2 track path not found : " + path)                                                              
                        return

                anim_count = self.n_animations

                if fill_tracks and path not in self.compounds:
                    self.ensure_track_length(m2_track, self.seq_id, anim_count, value_type, fill_tracks)                 
                    return
                
                fcurves = self.get_curves(path)
                if not fcurves:
                    return

                mismatch_detected = False
                
                # Find interpolation in current action
                for i, fcurve in enumerate(fcurves.values()):
                    interpolation = None
                    
                    for point in fcurve.keyframe_points:
                        if interpolation is None:
                            interpolation = point.interpolation
                        else:
                            if interpolation != point.interpolation and not mismatch_detected:
                                print(f"\nThere's an interpolation discrepancy in {path}, found {point.interpolation}, but last type for this object was {interpolation}, WoW only supports one interpolation setting.")
                                print(f'Exportation will continue using the original interpolation, but make sure to check the action: {self.pair.action.name}')
                                mismatch_detected = True
                                break
                
                # Compare interpolation from (let's say a bone.translation) with other animations, to see discrepancies
                if m2_track in track_interpolations:
                    if track_interpolations[m2_track] != interpolation:
                        print(f'\nPath {path} in action {self.pair.action.name} has {interpolation} interpolation while in other sequences uses {track_interpolations[m2_track]}, WoW only supports one.')
                        print(f'Exportation will continue using the original interpolation, but make sure to check the action: {self.pair.action.name}')
                else:
                    m2_track.interpolation_type = bl_to_m2_interpolation(interpolation)
                    track_interpolations[m2_track] = interpolation

                # Find global sequence id discrepancies
                if not m2_track in track_global_sequences:
                    track_global_sequences[m2_track] = self.global_seq_id
                    m2_track.global_sequence = self.global_seq_id
                else:
                    if track_global_sequences[m2_track] != self.global_seq_id:
                        if self.global_seq_id != -1:
                            raise ValueError(f'\n\nPath {path} in action {self.pair.action.name} was assigned to Global Sequence: {track_global_sequences[m2_track]} and has been found using Global Sequence:  {self.global_seq_id}, WoW only supports one\nExample: If a bone.translation is animated in a Global Sequence it cannot be animated in a different Global Sequence')
                        else:
                            raise ValueError(f'\n\nPath {path} in action {self.pair.action.name} was assigned to Global Sequence: {track_global_sequences[m2_track]} and has been found in a regular animation\nExample: If a bone.translation is animated in a Global Sequence it cannot be animated in a regular animation')
                
                # Find missing tracks (For example, missing Green from RGB Color)
                for i in range(track_count):
                    if not i in fcurves:
                        raise ValueError(f'\n\nTrack index {i} from {path} missing in {self.pair.action.name} fcurves')

                # Find keyframe count discrepancies
                keyframe_count = len(fcurves[0].keyframe_points)
                for i,fcurve in fcurves.items():
                    cur_count = len(fcurve.keyframe_points)
                    if cur_count != keyframe_count:
                        raise ValueError(f'\n\nTrack index {i} keyframe count ({cur_count}) is different from index 0: {keyframe_count} in bone: {path} from action: {self.pair.action.name}')
                
                # Find timestamp discrepancies
                for i in range(keyframe_count):
                    time = fcurves[0].keyframe_points[i].co[0]
                    for j in range(track_count):
                        cur_time = fcurves[j].keyframe_points[i].co[0]
                        if cur_time != time:
                            raise ValueError(f'\n\nTrack index {j} frame {j} has a different time value ({cur_time}) from index 0 ({time}) in bone: {path} from action: {self.pair.action.name}')
                
                self.ensure_track_length(m2_track, self.seq_id, anim_count, value_type, fill_tracks)

                m2_times = m2_track.timestamps[self.seq_id]
                m2_values = m2_track.values[self.seq_id] if value_type is not None else None

                for i in range(keyframe_count):
                    time = bl_to_m2_time(fcurves[0].keyframe_points[i].co[0])
                    if m2_values is not None:
                        values = [fcurves[j].keyframe_points[i].co[1] for j in range(track_count)]
                        m2_values.add(converter(tuple(values) if len(values) > 1 else values[0]))
                    m2_times.append(time)

                # Increase the highest duration
                if self.global_seq_id >= 0:
                    if not self.global_seq_id in global_seq_durations or time > global_seq_durations[self.global_seq_id]:
                        global_seq_durations[self.global_seq_id] = time
                else:
                    # if path.startswith('pose'):
                    #     if not self.seq_id in seq_durations or time > seq_durations[self.seq_id]:
                    #         seq_durations[self.seq_id] = max(33, time)
                    if not self.seq_id in seq_durations or time > seq_durations[self.seq_id]:
                        seq_durations[self.seq_id] = max(33, time)

        def write_light(cpd, pair):
            m2_light = self.m2.root.lights.values[self.light_ids[pair.object.name]]
            cpd.write_track('data.wow_m2_light.ambient_color',
                3, m2_light.ambient_color,vec3D)

            cpd.write_track('data.wow_m2_light.diffuse_color',
                3, m2_light.diffuse_color,vec3D)

            cpd.write_track('data.wow_m2_light.ambient_intensity',
                1, m2_light.ambient_intensity,float32)

            cpd.write_track('data.wow_m2_light.diffuse_intensity',
                1, m2_light.diffuse_intensity,float32)

            cpd.write_track('data.wow_m2_light.attenuation_start',
                1, m2_light.attenuation_start,float32)

            cpd.write_track('data.wow_m2_light.attenuation_end',
                1, m2_light.attenuation_end,float32)

            cpd.write_track('data.wow_m2_light.visibility',
                1, m2_light.visibility,uint8, lambda x: int(x)
            )

        def write_attachment(cpd, pair):
            m2_attachment = self.m2.root.attachments.values[self.attachment_ids[pair.object.name]]
            cpd.write_track('wow_m2_attachment.animate',
                1, m2_attachment.animate_attached,boolean,lambda x: bool(x), fill_tracks=True)

        def write_bone(cpd, pair):
            for path in cpd.get_paths():
                bone_str = re.search('"(.+?)"',path)
                if not bone_str:
                    print(f"Warning: FCurve {path} doesn't reference a bone")
                    continue
                bone = bone_str.group(1)

                curve_type_str = re.search('([a-zA-Z_]+)$',path)
                if not curve_type_str:
                    print(f"Warning: FCurve {path} doesn't have a proper type")
                    continue
                curve_type = curve_type_str.group(0)

                #if not bone in self.bone_ids:
                    #print(f"Warning: FCurve {path} references non-existing bone {bone}")
                    #continue

                m2_bone = self.m2.root.bones.values[self.bone_ids[bone]]
                m2_bone.flags = m2_bone.flags | 512

                if curve_type == 'rotation_quaternion':
                    if self.m2.version < M2Versions.WOTLK:
                        # vanilla/TBC: uncompressed (x,y,z,w) floats. Inverse of the
                        # import transform bl_convert_rot_track applies for classic
                        # ((x,y,z,w) disk -> (w,-y,x,z) blender), so blender (w,x,y,z)
                        # -> disk (y, -x, z, w).
                        cpd.write_track(path, 4, m2_bone.rotation, quat,
                            lambda x: (x[2], -x[1], x[3], x[0]), fill_tracks=False)
                    else:
                        cpd.write_track(path,4,m2_bone.rotation,M2CompQuaternion,
                            lambda x: M2CompQuaternion((
                                bl_to_m2_quat(x[0]),
                                bl_to_m2_quat(x[self.axis_order[0] + 1] * self.axis_polarity[0]),
                                bl_to_m2_quat(x[self.axis_order[1] + 1] * self.axis_polarity[1]),
                                bl_to_m2_quat(x[3])
                            )), fill_tracks = False
                        )

                elif curve_type == 'scale':
                    def convert_scale(scale):                  
                        if self.forward_axis == 'X+' or self.forward_axis == 'X-':
                            scale = (scale[1],scale[0],scale[2])
                        elif self.forward_axis == 'Y+' or self.forward_axis == 'Y-':
                            scale = (scale[0],scale[1],scale[2])
                        return scale
                    cpd.write_track(path,3,m2_bone.scale,vec3D,convert_scale, fill_tracks = False)

                # TODO: this probably doesn't work if bone is not at 0,0,0
                elif curve_type == 'location':
                    cpd.write_track(path,3,m2_bone.translation,vec3D,
                        lambda x: self._convert_vec((x[1],-x[0],x[2])), fill_tracks = False)

        def write_scene(cpd, pair):
            def extract_scene_data(path):
                index = re.search('\\[(.+?)\\]', path).group(1)
                data_path = re.search('\\]\.(.+)', path).group(1)
                return (int(index),data_path)

            for path in cpd.get_paths():
                if path.startswith("wow_m2_colors"):
                    (index,data_path) = extract_scene_data(path)
                    while len(self.m2.root.colors) <= index:
                        self.m2.root.colors.append(M2Color())
                    
                    col = self.m2.root.colors[index]
                    if index < len(bpy.context.scene.wow_m2_colors):
                        col_name = bpy.context.scene.wow_m2_colors[index].name
                    else:
                        print(f'Error: Color: wow_m2_color[{index}] is animated but doesn\'t actually exist in the scene, create it or consider removing it from the animation')
                        col_name = None               
                        #raise Exception(f'\n\nError: Color: {path} is animated but doesn\'t actually exist in the scene, create it or remove it from the animation if it\'s unused')
                                        
                    if col_name is not None and col_name in self.color_ids:
                        old_index = self.color_ids[col_name]
                        assert old_index == index,f'Color {col_name} has multiple ids: {index},{old_index}'
                    else:
                        self.color_ids[col_name] = index

                    if data_path == 'color':
                        cpd.write_track(path,3,col.color,vec3D)
                
                if path.startswith("wow_m2_color_alpha"):
                    (index,data_path) = extract_scene_data(path)

                    while len(self.m2.root.colors) <= index:
                        self.m2.root.colors.append(M2Color())

                    col = self.m2.root.colors[index]
                    if index < len(bpy.context.scene.wow_m2_color_alpha):
                        col_name = bpy.context.scene.wow_m2_color_alpha[index].name
                    else:
                        col_name = None
                        print(f'Error: Color Alpha: wow_m2_color_alpha[{index}] is animated but doesn\'t actually exist in the scene, create it or consider removing it from the animation')
                        #raise Exception(f'\n\nError: Color Alpha: {path} is animated but doesn\'t actually exist in the scene, create it or remove it from the animation if it\'s unused')
                    
                    if col_name is not None and data_path == 'value':
                        cpd.write_track(path,1,col.alpha,fixed16,lambda x: int(x * 0x7fff))

                if path.startswith("wow_m2_transparency"):
                    (index,_) = extract_scene_data(path)
                    while len(self.m2.root.texture_weights) <= index:
                        self.m2.root.texture_weights.append(M2Track(fixed16,M2Header))

                    # (3.3.5a)
                    # The transparency lookup table is seemingly worthless,
                    # it always just contains 0,1,2,3,4... in blizzard m2s
                    lt = self.m2.root.transparency_lookup_table
                    while len(lt) <= index:
                        lt.append(len(lt))

                    weight = self.m2.root.texture_weights.values[index]

                    if index < len(bpy.context.scene.wow_m2_transparency):
                        weight_name = bpy.context.scene.wow_m2_transparency[index].name
                    else:
                        print(f'Error: Transparency: wow_m2_transparency[{index}] is animated but doesn\'t actually exist in the scene, create it or consider removing it from the animation')
                        weight_name = None
                        #raise Exception(f'\n\nError: Transparency: {path} is animated but doesn\'t actually exist in the scene, create it or remove it from the animation if it\'s unused')
                    if weight_name is not None:
                        if weight_name in self.transparency_ids:
                            old_index = self.transparency_ids[weight_name]
                            assert old_index == index,f'Transparency {weight_name} has multiple ids: {index},{old_index}'
                        else:
                            self.transparency_ids[weight_name] = index

                        cpd.write_track(path,1,weight,fixed16, lambda x: int(x*0x7fff))

        def write_event(cpd, pair):
            m2_event = self.m2.root.events[self.event_ids[pair.object.name]]

            cpd.write_track("wow_m2_event.fire",1,m2_event.enabled,None, fill_tracks = True)

            events_to_remove = []
            for event in self.final_events:
                if pair.object.name == event:
                    events_to_remove.append(event)
            for event in events_to_remove:
                del self.final_events[event]

        def write_empty_events():
            global_seq_count = 0
            for wow_seq in bpy.context.scene.wow_m2_animations:
                if wow_seq.is_global_sequence:
                    global_seq_count += 1
            animations_count = len(bpy.context.scene.wow_m2_animations) - global_seq_count

            for key, identifier in self.final_events.items():
                m2_track = identifier.enabled
                while len(m2_track.timestamps) < animations_count:
                    m2_track.timestamps.add(M2Array(0))
                    
        def write_texture_transform(cpd, pair):
            if pair.object.name in self.texture_transform_ids:
                return
            
            self.texture_transform_ids[pair.object.name] = len(self.m2.root.texture_transforms)
            trans = M2TextureTransform()
            self.m2.root.texture_transforms.append(trans)

            cpd.write_track("location",3,trans.translation,vec3D, 
                            lambda x: (
                                -x[0],
                                x[1],
                                x[2]
                            )
            )

            cpd.write_track("scale",3,trans.scaling,vec3D)

            # TODO: fix this with axis order!
            cpd.write_track("rotation_quaternion",4,trans.rotation,quat,
                lambda x: (
                     x[2],
                    -x[1],
                     x[3],
                     x[0]
                )
            )

        def write_ribbon(cpd, pair):
            m2_ribbon = self.m2.root.ribbon_emitters[self.ribbon_ids[pair.object.name]]
            cpd.write_track("wow_m2_ribbon.color",3,m2_ribbon.color_track,vec3D)
            cpd.write_track("wow_m2_ribbon.alpha",1,m2_ribbon.alpha_track,float32,
                lambda x: int(x*0x7fff)
            )
            cpd.write_track("wow_m2_ribbon.height_above",1,m2_ribbon.height_above_track,float32)
            cpd.write_track("wow_m2_ribbon.height_below",1,m2_ribbon.height_below_track,float32)
            cpd.write_track("wow_m2_ribbon.texture_slot",1,m2_ribbon.tex_slot_track,uint16,
                lambda x: int(x)
            )
            cpd.write_track("wow_m2_ribbon.visibility",1,m2_ribbon.visibility_track,uint8,
                lambda x: int(x)
            )

        def write_particle(cpd, pair):
            m2_particle = self.m2.root.particle_emitters[self.particle_ids[pair.object.name]]
            cpd.write_track("wow_m2_particle.emission_speed",1,m2_particle.emission_speed,float32)
            cpd.write_track("wow_m2_particle.speed_variation",1,m2_particle.speed_variation,float32)
            cpd.write_track("wow_m2_particle.vertical_range",1,m2_particle.vertical_range,float32)
            cpd.write_track("wow_m2_particle.horizontal_range",1,m2_particle.horizontal_range,float32)
            cpd.write_track("wow_m2_particle.gravity",1,m2_particle.gravity,float32)
            cpd.write_track("wow_m2_particle.lifespan",1,m2_particle.lifespan,float32)
            cpd.write_track("wow_m2_particle.emission_rate",1,m2_particle.emission_rate,float32)
            cpd.write_track("wow_m2_particle.emission_area_length",1,m2_particle.emission_area_length,float32)
            cpd.write_track("wow_m2_particle.emission_area_width",1,m2_particle.emission_area_width,float32)
            cpd.write_track("wow_m2_particle.z_source",1,m2_particle.z_source,float32)
            cpd.write_track("wow_m2_particle.color_track",3,m2_particle.color_track,vec3D)
            cpd.write_track("wow_m2_particle.alpha",1,m2_particle.alpha_track,float32)
            cpd.write_track("wow_m2_particle.scale",2,m2_particle.scale_track,vec2D)
            #cpd.write_track("wow_m2_particle.head_cell_track",1,m2_particle.head_cell_track,uint16,
                #lambda x: int(x))
            #cpd.write_track("wow_m2_particle.tail_cell_track",1,m2_particle.tail_cell_track,uint16,
                #lambda x: int(x))
            cpd.write_track("wow_m2_particle.active",1,m2_particle.enabled_in,uint8,
                lambda x: int(x), fill_tracks = True)

        def write_camera(cpd, pair):
            m2_camera = self.m2.root.cameras[self.camera_ids[pair.object.name]]
            def convert_spline(x):
                key = M2SplineKey(vec3D)
                key.value = x
                return key
            cpd.write_track("rotation_axis_angle",m2_camera.positions,vec3D,convert_spline)                                                         

        def write_camera_target(cpd, pair):
            m2_camera = self.m2.root.cameras[self.camera_target_ids[pair.object.name]]
            def convert_spline(x):
                key = M2SplineKey(float32)
                key.value = x
                return key
            # TODO: can't write this because the track thinks the m2array type is generic for some reason
            #cpd.write_track("rotation_axis_angle",m2_camera.roll,float32,convert_spline)

        self.m2.root.transparency_lookup_table.add(len(self.m2.root.texture_weights))

        global_seq_count = 0
        for wow_seq in self.scene.wow_m2_animations:
            if wow_seq.is_global_sequence:
                global_seq_count += 1

        for wow_seq in tqdm(self.scene.wow_m2_animations, desc='Exporting Animations', ascii=True):
            seq_id = 0
            global_seq_id = -1
            if wow_seq.is_global_sequence:
                global_seq_id = len(self.m2.root.global_sequences)
                self.m2.root.global_sequences.append(0)
            else:
                is_alias = "64" in wow_seq.flags

                # TODO using root boundings when not using preset, better than nothing
                if wow_seq.use_preset_bounds:
                    box_min = self._convert_vec((wow_seq.preset_bounds_min_x, wow_seq.preset_bounds_min_y, wow_seq.preset_bounds_min_z))
                    box_max = self._convert_vec((wow_seq.preset_bounds_max_x, wow_seq.preset_bounds_max_y, wow_seq.preset_bounds_max_z))
                    
                    bounding = ((box_min, box_max), wow_seq.preset_bounds_radius)     
                else: 
                    bounding = ((self.m2.root.bounding_box.min,self.m2.root.bounding_box.max),
                        self.m2.root.bounding_sphere_radius)
                    
                seq_id = self.m2.add_anim(
                    int(wow_seq.animation_id),
                    wow_seq.chain_index, # titi, to test
                    (0,0), # set it later
                    wow_seq.move_speed * self.scale,
                    construct_bitfield(wow_seq.flags),
                    convert_frequency_percentage(wow_seq.frequency),
                    (wow_seq.replay_min, wow_seq.replay_max),
                    wow_seq.blend_time,  # TODO: multiversioning
                    bounding,
                    wow_seq.VariationNext,
                    wow_seq.alias_next
                )
            
            for pair in wow_seq.anim_pairs:
                if (pair.type != 'SCENE' and pair.object is None) or pair.action is None:
                    continue

                if pair.type == 'SCENE':
                    ObjectTracks(seq_id, global_seq_id, pair, write_scene)
                elif pair.object.type == 'ARMATURE':
                    ObjectTracks(seq_id, global_seq_id, pair, write_bone)
                elif pair.object.type == 'LIGHT':
                    ObjectTracks(seq_id, global_seq_id, pair, write_light)
                elif pair.object.type == 'CAMERA':
                    ObjectTracks(seq_id, global_seq_id, pair, write_camera)
                elif pair.object.type == 'CAMERA_TARGET':
                    ObjectTracks(seq_id, global_seq_id, pair, write_camera_target)
                elif pair.object.type == 'EMPTY':
                    if pair.object.wow_m2_attachment.enabled:
                        ObjectTracks(seq_id, global_seq_id, pair, write_attachment)
                    elif pair.object.wow_m2_event.enabled:
                        ObjectTracks(seq_id, global_seq_id, pair, write_event)
                    elif pair.object.wow_m2_camera.enabled:
                        ObjectTracks(seq_id, global_seq_id, pair, write_camera_target)
                    elif pair.object.wow_m2_uv_transform.enabled:
                        ObjectTracks(seq_id, global_seq_id, pair, write_texture_transform)
                    elif pair.object.wow_m2_ribbon.enabled:
                        ObjectTracks(seq_id, global_seq_id, pair, write_ribbon)
                    elif pair.object.wow_m2_particle.enabled:
                        ObjectTracks(seq_id, global_seq_id, pair, write_particle)

            for global_seq_id,duration in global_seq_durations.items():
                assert global_seq_id < len(self.m2.root.global_sequences)
                self.m2.root.global_sequences.set_index(global_seq_id,duration)

            if wow_seq.use_preset_duration == True:
                self.m2.root.sequences[seq_id].duration = wow_seq.duration
            else:
                for seq_id,duration in seq_durations.items():
                    assert seq_id < len(self.m2.root.sequences)
                    self.m2.root.sequences[seq_id].duration = duration

        # Add dummy texture weight/transparency
        if len(self.m2.root.texture_weights) == 0:
            texture_weight = self.m2.root.texture_weights.new()
            if self.m2.root.version >= M2Versions.WOTLK:
                texture_weight.timestamps.new().add(0)
                texture_weight.values.new().add(32767)

        # Write alias durations
        for i,wow_seq in enumerate(self.m2.root.sequences.values):
            if not 64 & wow_seq.flags: continue
            cur_seq = wow_seq
            visited = [i]
            while 64 & cur_seq.flags:
                assert cur_seq.alias_next != -1,"alias action without alias_next set"
                assert not (cur_seq.alias_next in visited),f"Circular alias_next: {cur_seq.alias_next} ({visited})"
                assert cur_seq.alias_next < len(self.m2.root.sequences.values)
                visited.append(cur_seq.alias_next)
                cur_seq = self.m2.root.sequences.values[cur_seq.alias_next]
            wow_seq.duration = cur_seq.duration

        if len(self.m2.root.sequences) == 0:
            self.m2.add_dummy_anim_set((0,0,0))

        while len(self.m2.root.sequence_lookup) < 5: # don't crash creatures
            self.m2.root.sequence_lookup.append(0xffff)
        if self.m2.root.sequence_lookup[4] == -1:
            self.m2.root.sequence_lookup[4] = 0
        
        write_empty_events()

    def save_globalflags(self, need_combiner_flag):   
        global_flags_armature = next((obj for obj in bpy.data.objects if obj.type == 'ARMATURE'), None)
        if global_flags_armature is None:
            pass
        else:
            globalflagsLK = list(global_flags_armature.wow_m2_globalflags.flagsLK)  # Convert set to list

            if need_combiner_flag:
                if '8' not in globalflagsLK:
                    print("Adding Texture Combiner Global Flag")
                    globalflagsLK.append('8')
                    global_flags_armature.wow_m2_globalflags.flagsLK = set(globalflagsLK)
            else:
                if '8' in globalflagsLK:
                    print("Removing Texture Combiner Global Flag")
                    globalflagsLK.remove('8')
                    global_flags_armature.wow_m2_globalflags.flagsLK = set(globalflagsLK)
            
            self.m2.root.global_flags = construct_bitfield(globalflagsLK)
            globalflagsLegion = list(global_flags_armature.wow_m2_globalflags.flagsLegion)  # Convert set to list
            for item in globalflagsLegion:
                self.m2.root.global_flags = construct_bitfield(globalflagsLK+globalflagsLegion)

    def save_geosets(self, selected_only, fill_textures, merge_vertices):
        objects = bpy.context.selected_objects if selected_only else bpy.context.scene.objects
        if not objects:
            raise Exception('Error: no mesh found on the scene or selected.')

        # deselect all objects before saving geosets
        bpy.ops.object.select_all(action='DESELECT')

        proxy_objects = []
        tex_anim_lookup_table = [] 
        tex_combiner_materials = []
        tt_controller_combinations = []
        rearranged_transforms = []  
        anim_lookup_executed = False
        need_combiner_flag = False

        def mapping(mapping_method):
            if mapping_method == "UVMap":
                return 0
            elif mapping_method == "UVMap.001":
                return 1
            elif mapping_method == "Env":
                return -1      

        for wow_seq in self.scene.wow_m2_animations:                
            for pair in wow_seq.anim_pairs:
                if pair.object is None or (pair.type != 'SCENE' and pair.action is None):
                    continue
                if pair.object.type == 'EMPTY':
                    if pair.object.wow_m2_uv_transform.enabled:
                        if pair.object.name not in rearranged_transforms:
                            rearranged_transforms.append(pair.object.name)

        tt_controller_id_map = {name: idx for idx, name in enumerate(rearranged_transforms)}   
        
        for obj in tqdm(filter(lambda ob: not ob.wow_m2_geoset.collision_mesh and ob.type == 'MESH' and not ob.hide_get(), objects), desc='Exporting Geosets', ascii=True):

            new_obj = obj.copy()
            new_obj.data = obj.data.copy()
            proxy_objects.append(new_obj)

            bpy.context.collection.objects.link(new_obj)

            bpy.context.view_layer.objects.active = new_obj
            mesh = new_obj.data

            # security checks

            if not mesh.uv_layers.active:
                raise Exception("Mesh <<{}>> has no UV Map.".format(obj.name))
            
            ntexanim = 0
            tt_controller_id_uv1 = None
            tt_controller_id_uv2 = None    

            # apply all modifiers
            if len(obj.modifiers):
                for modifier in obj.modifiers:
                    if 'M2TexTransform' not in modifier.name:
                        bpy.ops.object.modifier_apply(modifier=modifier.name)
            
            #Temporal console to hide Blender's removing vertices messages
            temporal_console_output = io.StringIO()
            sys.stdout = temporal_console_output

            # triangulate mesh, delete loose geometry
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.reveal()
            bpy.ops.mesh.quads_convert_to_tris()
            bpy.ops.mesh.delete_loose()
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.object.mode_set(mode='OBJECT')

            # prepare scene
            ###################################

            # add custom split normals if there're none
            bpy.ops.object.use_auto_smooth  = True 
            bpy.ops.mesh.customdata_custom_splitnormals_add()
              
            if merge_vertices: # TODO find a better method           

                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.mesh.remove_doubles(threshold = 0.0001, use_sharp_edge_from_normals = True)
                bpy.ops.uv.select_all(action='SELECT')
                bpy.ops.uv.seams_from_islands(mark_seams=False, mark_sharp=True)
                bpy.ops.mesh.select_all(action='DESELECT')
                bpy.ops.object.mode_set(mode='OBJECT')
                for e in new_obj.data.edges:
                    if e.use_edge_sharp:
                        e.select = True
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.edge_split()
                bpy.ops.mesh.select_all(action='DESELECT')
                bpy.ops.object.mode_set(mode='OBJECT')

                bpy.ops.object.modifier_add(type='DATA_TRANSFER')
                bpy.context.object.modifiers["DataTransfer"].use_loop_data = True
                bpy.context.object.modifiers["DataTransfer"].data_types_loops = {'CUSTOM_NORMAL'}
                bpy.context.object.modifiers["DataTransfer"].object = obj
                bpy.ops.object.datalayout_transfer(modifier="DataTransfer")
                bpy.ops.object.modifier_apply(modifier="DataTransfer")

            sys.stdout = sys.__stdout__
            captured_output = temporal_console_output.getvalue()
            temporal_console_output.close()
            #print(captured_output) #Print Blender's removed vertices info
           
            # smooth edges
            # bpy.ops.object.mode_set(mode='EDIT')
            # bpy.ops.mesh.select_all(action='SELECT')
            # bpy.ops.mesh.mark_sharp(clear=True)
            # bpy.ops.mesh.select_all(action='DESELECT')
            # bpy.ops.object.mode_set(mode='OBJECT')
            
            # export vertices
            mesh.calc_loop_triangles()
            mesh.calc_normals_split()

            vertices = [self._convert_vec(new_obj.matrix_world @ vertex.co) for vertex in mesh.vertices]
            #normals = [self._convert_vec(vertex.normal) for vertex in mesh.vertices] # Original normals

            normals = [(0.0, 0.0, 0.0)] * len(vertices)
            tex_coords = [(0.0, 0.0)] * len(vertices)
            tex_coords2 = [(0.0, 0.0)] * len(vertices)

            for loop in mesh.loops:

                normals[loop.vertex_index] = (mesh.loops[loop.index].normal) # custom split normals
                tex_coords[loop.vertex_index] = (mesh.uv_layers[0].data[loop.index].uv[0],
                                                 1 - mesh.uv_layers[0].data[loop.index].uv[1])
                if len(mesh.uv_layers) >= 2:
                    tex_coords2[loop.vertex_index] = (mesh.uv_layers[1].data[loop.index].uv[0],
                                                      1 - mesh.uv_layers[1].data[loop.index].uv[1])
                else:
                    tex_coords2[loop.vertex_index] = (mesh.uv_layers[0].data[loop.index].uv[0],
                                                      1 - mesh.uv_layers[0].data[loop.index].uv[1])                    

            tris = [poly.vertices for poly in mesh.polygons]

            # old system
            # bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')
            # origin = new_obj.location

            vertx = 0.0
            verty = 0.0
            vertz = 0.0
            vertcount = len(vertices)
            
            for vert in vertices:
                vertx += vert[0]
                verty += vert[1]
                vertz += vert[2]
            
            origin = ( vertx / vertcount, verty / vertcount, vertz / vertcount )
            
            sort_pos = get_obj_boundbox_center(new_obj)
            sort_radius = get_obj_radius(new_obj, sort_pos)

            if self.rig:

                bone_indices = []
                bone_weights = []

                bone_names = [bone.name for bone in self.rig.data.bones]

                unique_bones = set()

                for vertex in mesh.vertices:
                    v_bone_indices = [0, 0, 0, 0]
                    v_bone_weights = [0, 0, 0, 0]

                    bone_groups = get_bone_groups(new_obj,vertex,bone_names)[:4]

                    for i, group_info in enumerate(bone_groups):
                        bone_id = self.bone_ids.get(new_obj.vertex_groups[group_info.group].name)
                        weight = group_info.weight

                        if bone_id is None:
                            bone_id = 0
                            weight = 0

                        v_bone_indices[i] = bone_id
                        v_bone_weights[i] = int(weight * 255)

                        unique_bones.add(bone_id)
                    
                    weight_sum = sum(v_bone_weights)

                    if weight_sum != 255:
                        if weight_sum > 0:
                            scale = 255 / weight_sum
                            v_bone_weights = [int(w * scale) for w in v_bone_weights]

                        weight_sum = sum(v_bone_weights)
                        if weight_sum != 255:
                            diff = 255 - weight_sum
                            max_weight_index = v_bone_weights.index(max(v_bone_weights))
                            v_bone_weights[max_weight_index] += diff    

                    bone_indices.append(v_bone_indices)
                    bone_weights.append(v_bone_weights)
                
                num_bones = len(unique_bones)

                if num_bones > 64:
                    bpy.data.objects.remove(new_obj, do_unlink=True)  
                    raise Exception(f"\n\nWarning: The number of bones affecting the mesh: {obj.name} is {num_bones}, which exceeds the limit of 64! Separate it into more objects, and try again")

            else:
                bone_indices = [[0, 0, 0, 0] for _ in mesh.vertices]
                bone_weights = [[255, 0, 0, 0] for _ in mesh.vertices]

            # add geoset
            g_index = self.m2.add_geoset(vertices, normals, tex_coords, tex_coords2, tris, bone_indices, bone_weights,
                                         origin, sort_pos, sort_radius, int(new_obj.wow_m2_geoset.mesh_part_id))
            
            for i, material in enumerate(mesh.materials):

                textures = [material.wow_m2_material.texture_1, material.wow_m2_material.texture_2]

                texture_count = 0

                for bl_texture in textures:
                    if bl_texture:
                        texture_count += 1
                        wow_path = bl_texture.wow_m2_texture.path
                        tex_type = bl_texture.wow_m2_texture.texture_type
                        if texture_count == 1:
                            if tex_type == '0':
                                first_path = wow_path
                            else:
                                first_path = tex_type

                        if bl_texture.wow_m2_texture.texture_type == 0 and fill_textures and not wow_path:                        
                            wow_path = resolve_texture_path(bl_texture.filepath)
                        
                        self.m2.add_texture(wow_path,
                                            construct_bitfield(bl_texture.wow_m2_texture.flags),
                                            int(tex_type),
                                            )
                        
                    if tex_type == '0':
                        if (wow_path) in self.final_textures:
                            tex2_id = self.final_textures[wow_path]
                        else:
                            tex2_id = len(self.final_textures)
                            self.final_textures[wow_path] = tex2_id

                        tex1_id = tex2_id

                        if first_path in self.final_textures:
                            tex1_id = self.final_textures[first_path]
                    else:
                        if (tex_type) in self.final_textures:
                            tex2_id = self.final_textures[tex_type]
                        else:
                            tex2_id = len(self.final_textures)
                            self.final_textures[tex_type] = tex2_id

                        tex1_id = tex2_id

                        if first_path in self.final_textures:
                            tex1_id = self.final_textures[first_path]
                
                # TODO lyswh, combiners need lookups to be in pairs, so we're exporting everything in pairs for now, in the future
                # it'd be nice to export first all pairs, and after all individual lookups, but this works
                tex_lookup_id = self.m2.add_tex_lookup(tex1_id, tex2_id)  
                           
                render_flags = construct_bitfield(material.wow_m2_material.texture_1_render_flags)
                flags = construct_bitfield(material.wow_m2_material.flags)
                priority_plane = int(material.wow_m2_material.priority_plane)
                bl_mode = int(material.wow_m2_material.texture_1_blending_mode)
                shader_id = 0
                mat_layer = i

                if material.wow_m2_material.color in bpy.context.scene.wow_m2_colors and material.wow_m2_material.color in self.color_ids or material.wow_m2_material.color == "":
                    color_id = self.color_ids[material.wow_m2_material.color] if material.wow_m2_material.color != "" else -1
                else:
                    print(f'{material.wow_m2_material.color} from {material.name} in object: {obj.name} doesn\'t exist in the scene or is not animated, create it and/or add a keyframe for it and try again.')
                    raise Exception(f'\n\n{material.wow_m2_material.color} from {material.name} in object: {obj.name} doesn\'t exist in the scene or is not animated, create it and/or add a keyframe for it and try again.')                    
                
                if material.wow_m2_material.transparency in bpy.context.scene.wow_m2_transparency and material.wow_m2_material.transparency in self.transparency_ids or material.wow_m2_material.transparency == "":
                    transparency_id = self.transparency_ids[material.wow_m2_material.transparency] if material.wow_m2_material.transparency != "" else 0
                else:
                    print(f'{material.wow_m2_material.transparency} from {material.name} in object: {obj.name} doesn\'t exist in the scene or is not animated, create it and/or add a keyframe for it and try again.')
                    raise Exception(f'\n\n{material.wow_m2_material.transparency} from {material.name} in object: {obj.name} doesn\'t exist in the scene or is not animated, create it and/or add a keyframe for it and try again.')

                tex_1_mapping = mapping(material.wow_m2_material.texture_1_mapping)
                tex_2_mapping = 1

                if texture_count == 2:

                    need_combiner_flag = True
                    tex_2_mapping = mapping(material.wow_m2_material.texture_2_mapping)
                    texture_2_render_flags = construct_bitfield(material.wow_m2_material.texture_2_render_flags)
                    texture_2_blending_mode = int(material.wow_m2_material.texture_2_blending_mode)
                    tex_combiner_data = (texture_2_render_flags, texture_2_blending_mode)
                  
                    if tex_combiner_data not in tex_combiner_materials:
                        tex_combiner_materials.append(tex_combiner_data)
                        self.m2.root.texture_combiner_combos.append(tex_combiner_data[0])
                        self.m2.root.texture_combiner_combos.append(tex_combiner_data[1])
                    
                    #print("tex_combiners_materials", tex_combiner_materials)

                    if tex_combiner_data in tex_combiner_materials:
                        shader_id = next(i for i, value in enumerate(tex_combiner_materials) if value == tex_combiner_data) * 2
                    else:
                        shader_id = 0  

                if material.wow_m2_material.texture_1_animation is not None:
                    tt_controller_name = material.wow_m2_material.texture_1_animation.name
                    tt_controller_id_uv1 = tt_controller_id_map.get(tt_controller_name, -1)
                    ntexanim += 1
                if material.wow_m2_material.texture_2_animation is not None:
                    tt_controller_name_001 = material.wow_m2_material.texture_2_animation.name
                    tt_controller_id_uv2 = tt_controller_id_map.get(tt_controller_name_001, -1)
                    ntexanim += 1   

                def add_combination(combination):
                    if combination not in tt_controller_combinations:
                        tt_controller_combinations.append(combination)                                  

                if ntexanim == 0:
                    add_combination((-1, -1))
                elif ntexanim == 1:
                    if tt_controller_id_uv1 is not None:
                        add_combination((tt_controller_id_uv1, -1))
                    else:
                        add_combination((-1, tt_controller_id_uv2))
                elif ntexanim == 2:
                    add_combination((tt_controller_id_uv1, tt_controller_id_uv2))
                
                if not anim_lookup_executed:
                    tex_anim_lookup_table.append((-1, -1))       
                    self.m2.root.texture_transforms_lookup_table.extend([-1,-1])     
                    anim_lookup_executed = True
                else:
                    transform_id = 0
                if ntexanim != 0:
                    for tt_combination in tt_controller_combinations:
                        if (tt_combination) not in tex_anim_lookup_table:
                            tex_anim_lookup_table.append(tt_combination)
                            self.m2.root.texture_transforms_lookup_table.extend([tt_combination[0],tt_combination[1]])
                
                if tt_controller_id_uv1 is None:
                    tt_controller_id_uv1 = -1        
                if tt_controller_id_uv2 is None:
                    tt_controller_id_uv2 = -1

                if ((tt_controller_id_uv1, tt_controller_id_uv2)) in tex_anim_lookup_table:
                    transform_id = tex_anim_lookup_table.index((tt_controller_id_uv1, tt_controller_id_uv2)) * 2
                    #print("Animations: ", (tt_controller_id_uv1, tt_controller_id_uv2),"Tex anim lookup table: ", tex_anim_lookup_table, "Lookup ID: ", (tex_anim_lookup_table.index((tt_controller_id_uv1, tt_controller_id_uv2)) * 2))

                #print("tt_combination", tt_controller_combinations)
                #print("tex_anim_lookup_table", tex_anim_lookup_table)       

                self.m2.add_material_to_geoset(g_index, render_flags, bl_mode, flags, shader_id, tex_lookup_id,
                                                tex_1_mapping, tex_2_mapping, priority_plane, mat_layer, texture_count, color_id, transparency_id, transform_id)

           
            bpy.data.objects.remove(new_obj, do_unlink=True)  
        
        self.save_globalflags(need_combiner_flag)

        # remove temporary objects
        # for obj in proxy_objects:
        #     bpy.data.objects.remove(obj, do_unlink=True)

    def save_collision(self, selected_only):
        objects = bpy.context.selected_objects if selected_only else bpy.context.scene.objects
        objects = list(filter(lambda ob: ob.wow_m2_geoset.collision_mesh and ob.type == 'MESH', objects))

        proxy_objects = []

        for obj in tqdm(objects, desc='Exporting Collision', ascii=True):
            new_obj = obj.copy()
            new_obj.data = obj.data.copy()
            proxy_objects.append(new_obj)

            bpy.context.collection.objects.link(new_obj)

            bpy.context.view_layer.objects.active = new_obj
            mesh = new_obj.data

            # apply all modifiers
            if len(obj.modifiers):
                for modifier in obj.modifiers:
                    bpy.ops.object.modifier_apply(modifier=modifier.name)

            temporal_console_output = io.StringIO()
            sys.stdout = temporal_console_output
             
            # triangulate mesh, delete loose geometry
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.reveal()
            bpy.ops.mesh.quads_convert_to_tris()
            bpy.ops.mesh.delete_loose()
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.object.mode_set(mode='OBJECT')

            sys.stdout = sys.__stdout__
            captured_output = temporal_console_output.getvalue()
            temporal_console_output.close()

            # collect geometry data
            vertices = [self._convert_vec(tuple(new_obj.matrix_world @ vertex.co)) for vertex in mesh.vertices]
            faces = [tuple([vertex for vertex in poly.vertices]) for poly in mesh.polygons]
            normals = [self._convert_vec(tuple(poly.normal)) for poly in mesh.polygons]

            self.m2.add_collision_mesh(vertices, faces, normals)
            bpy.data.objects.remove(new_obj, do_unlink=True)

        # remove temporary objects
        #for obj in proxy_objects:
        #    bpy.data.objects.remove(obj, do_unlink=True)

        # calculate collision bounding box
        b_min, b_max = get_objs_boundbox_world(objects)
        b_min = self._convert_vec(b_min)
        b_max = self._convert_vec(b_max)
        self.m2.root.collision_box.min = b_min
        self.m2.root.collision_box.max = b_max
        self.m2.root.collision_sphere_radius = sqrt(((b_max[self.axis_order[0]] - b_min[self.axis_order[0]]) * self.axis_polarity[0] * self.scale) ** 2
                                                    + ((b_max[self.axis_order[1]] - b_min[self.axis_order[1]]) * self.axis_polarity[1] * self.scale) ** 2
                                                    + ((b_max[2] - b_min[2])) ** 2) / 2

        #for key, identifier in self.final_events.items():
        #    print(key, identifier)