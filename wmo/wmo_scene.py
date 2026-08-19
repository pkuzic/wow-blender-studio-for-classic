import hashlib
import math
import bpy
import bmesh
import typing

from mathutils import Vector, Matrix
from bmesh.types import BMVert

from math import sqrt, atan2, pi
from typing import Dict, List


from .bl_render import update_wmo_mat_node_tree, load_wmo_shader_dependencies, BlenderWMOMaterialRenderFlags
from .utils.fogs import create_fog_object
from .utils.materials import add_ghost_material, load_texture
from .utils.doodads import import_doodad
from .wmo_scene_group import BlenderWMOSceneGroup
from ..ui.preferences import get_project_preferences
from ..utils.misc import find_nearest_object
from ..wbs_kernel.wmo_utils import CWMOGeometryBatcher, WMOGeometryBatcherMeshParams
from .ui.collections import get_wmo_collection, SpecialCollections, get_wmo_groups_list
from ..utils.collections import get_current_wow_model_collection

from ..pywowlib.file_formats.wmo_format_root import GroupInfo, PortalInfo, PortalRelation, Fog
from ..pywowlib.wmo_file import WMOFile
from ..pywowlib import WoWVersions

from ..third_party.tqdm import tqdm


class BlenderWMOScene:
    """ This class is used for assembling a Blender scene from a WNO file or saving the scene back to it."""

    def __init__(self, wmo: WMOFile, prefs):
        self.wmo: WMOFile = wmo
        self.settings = prefs

        self.bl_materials: Dict[int, bpy.types.Material] = {}
        self.bl_groups: List[BlenderWMOSceneGroup] = []
        self.bl_portals: List[bpy.types.Object] = []
        self.bl_fogs: List[bpy.types.Object] = []
        self.bl_lights: List[bpy.types.Object] = []
        self.bl_liquids: List[bpy.types.Object] = []
        self.bl_doodad_sets: Dict[str, bpy.types.Object] = {}
        # used for export:
        self.groups_eval: List[bpy.types.Mesh] = []
        self.group_batch_params: List[WMOGeometryBatcherMeshParams] = []
        self.portals_relations: Dict[bpy.types.Object, List[bpy.types.Object]] = {}
        self.lights_relations: Dict[bpy.types.Object, List[int]] = {}
        self.doodads_relations: Dict[bpy.types.Object, List[int]] = {}
        self.export_group_ids: Dict[bpy.types.Object, List[int]] = {}

    def load_materials(self, texture_dir=None):
        """ Load materials from WoW WMO root file """

        project_preferences = get_project_preferences()

        if texture_dir is None:
            texture_dir = project_preferences.cache_dir_path

        self.bl_materials = {0xFF : add_ghost_material()}

        if 'MO_WMOShader' not in bpy.data.node_groups:
            load_wmo_shader_dependencies(reload_shader=True)

        textures = {}

        for index, wmo_material in tqdm(list(enumerate(self.wmo.momt.materials)), desc='Importing materials', ascii=True):
            texture1 = self.wmo.motx.get_string(wmo_material.texture1_ofs)
            texture2 = self.wmo.motx.get_string(wmo_material.texture2_ofs)

            mat = bpy.data.materials.new(texture1.split('\\')[-1][:-4] + '.png')
            self.bl_materials[index] = mat

            try:
                mat.wow_wmo_material.shader = str(wmo_material.shader)
            except TypeError:
                print("Incorrect shader id \"{}\". Most likely badly retro-ported WMO.".format(str(wmo_material.shader)))
                mat.wow_wmo_material.shader = "0"

            mat.wow_wmo_material.blending_mode = str(wmo_material.blend_mode)
            mat.wow_wmo_material.emissive_color = [x / 255 for x in wmo_material.emissive_color]
            mat.wow_wmo_material.diff_color = (wmo_material.diff_color[2] / 255,
                                               wmo_material.diff_color[1] / 255,
                                               wmo_material.diff_color[0] / 255,
                                               wmo_material.diff_color[3] / 255
                                              )


            try:
                mat.wow_wmo_material.terrain_type = str(wmo_material.terrain_type)
            except TypeError as e:
                print('Terrain type not found for ', mat, e)
                mat.wow_wmo_material.terrain_type = '0'

            mat_flags = set()
            bit = 1
            while bit <= 0x80:
                if wmo_material.flags & bit:
                    mat_flags.add(str(bit))
                bit <<= 1
            mat.wow_wmo_material.flags = mat_flags

            # create texture slots and load textures

            if texture1:
                try:
                    tex = load_texture(textures, texture1, texture_dir)
                    mat.wow_wmo_material.diff_texture_1 = tex
                except:
                    pass

            if texture2:

                try:
                    tex = load_texture(textures, texture2, texture_dir)
                    mat.wow_wmo_material.diff_texture_2 = tex
                except:
                    pass

            update_wmo_mat_node_tree(mat)

            # set render flags
            pass_index = 0

            if wmo_material.flags & 0x1:
                pass_index |= BlenderWMOMaterialRenderFlags.Unlit

            if wmo_material.flags & 0x10:
                pass_index |= BlenderWMOMaterialRenderFlags.SIDN

            if wmo_material.shader in (3, 5, 6, 7, 8, 9, 11, 12, 13, 15):
                pass_index |= BlenderWMOMaterialRenderFlags.IsTwoLayered

            if wmo_material.blend_mode in (0, 8, 9):
                pass_index |= BlenderWMOMaterialRenderFlags.IsOpaque

            # configure blending
            if wmo_material.blend_mode in (0, 8, 9):
                mat.blend_method = 'OPAQUE'
            elif wmo_material.blend_mode == 1:
                mat.blend_method = 'CLIP'
                mat.alpha_threshold = 0.9
            # TODO : those blending modes don't exist anymore in 2.9+
            # elif wmo_material.blend_mode in (3, 7, 10):
            #     mat.blend_method = 'ADD'
            # elif wmo_material.blend_mode in (4, 5):
            #     mat.blend_method = 'MULTIPLY'
            else:
                mat.blend_method = 'BLEND'

            mat.pass_index = pass_index


    def load_lights(self):
        """ Load WoW WMO MOLT lights """

        bl_light_types = ['POINT', 'SPOT', 'SUN', 'POINT']
        
        scn = bpy.context.scene
        light_collection = get_wmo_collection(scn, SpecialCollections.Lights) 

        for i, wmo_light in tqdm(list(enumerate(self.wmo.molt.lights)), desc='Importing lights', ascii=True):

            try:
                l_type = bl_light_types[wmo_light.light_type]
            except IndexError:
                raise Exception("Light type unknown : {} (light nbr : {})".format(str(wmo_light.LightType), str(i)))

            light_name = "{}_Light_{}".format(self.wmo.display_name, str(i).zfill(2))

            light = bpy.data.lights.new(light_name, l_type)
            obj = bpy.data.objects.new(light_name, light)
            obj.location = self.wmo.molt.lights[i].position

            if wmo_light.type in {0, 2, 3}:
                light.type = 'POINT'
            elif wmo_light.type == 1:
                light.type = 'SPOT'

            # TODO set rotation for spot lights. currently wmo_light.unknown1
            

            light.color = (wmo_light.color[2] / 255, wmo_light.color[1] / 255, wmo_light.color[0] / 255)
            light.energy = wmo_light.intensity

            if wmo_light.light_type in {0, 1}:
                light.falloff_type = 'INVERSE_LINEAR'
                light.distance = wmo_light.unknown4 / 2

            obj.wow_wmo_light.enabled = True
            obj.wow_wmo_light.light_type = str(wmo_light.light_type)
            obj.wow_wmo_light.type = bool(wmo_light.type)
            obj.wow_wmo_light.use_attenuation = bool(wmo_light.use_attenuation)
            obj.wow_wmo_light.padding = bool(wmo_light.padding)
            obj.wow_wmo_light.type = bool(wmo_light.type)
            obj.wow_wmo_light.color = light.color
            obj.wow_wmo_light.color_alpha = wmo_light.color[3] / 255
            obj.wow_wmo_light.intensity = wmo_light.intensity
            obj.wow_wmo_light.attenuation_start = wmo_light.attenuation_start
            obj.wow_wmo_light.attenuation_end = wmo_light.attenuation_end

            self.bl_lights.append(light)

            # move lights to collection
            light_collection.objects.link(obj)

    def load_fogs(self):
        """ Load fogs from WMO Root File"""

        fog_collection = get_wmo_collection(bpy.context.scene, SpecialCollections.Fogs)

        for i, wmo_fog in tqdm(list(enumerate(self.wmo.mfog.fogs)), desc='Importing fogs', ascii=True):

            fog_obj = create_fog_object(  name="{}_Fog_{}".format(self.wmo.display_name, str(i).zfill(2))
                                        , location=wmo_fog.position
                                        #, radius=wmo_fog.big_radius
                                        , color=(wmo_fog.color1[2] / 255,
                                                 wmo_fog.color1[1] / 255,
                                                 wmo_fog.color1[0] / 255,
                                                 0.0
                                                )
                                        )

            fog_obj.scale = (wmo_fog.big_radius,wmo_fog.big_radius,wmo_fog.big_radius)

            # applying object properties
            fog_obj.wow_wmo_fog.enabled = True
            fog_obj.wow_wmo_fog.ignore_radius = wmo_fog.flags & 0x01
            try:
                fog_obj.wow_wmo_fog.unknown = wmo_fog.flags & 0x10
            except:
                fog_obj.wow_wmo_fog.unknown = False

            if wmo_fog.small_radius != 0:
                fog_obj.wow_wmo_fog.inner_radius = wmo_fog.small_radius / wmo_fog.big_radius * 100
            else:
                fog_obj.wow_wmo_fog.inner_radius = 0

            fog_obj.wow_wmo_fog.end_dist = wmo_fog.end_dist
            fog_obj.wow_wmo_fog.start_factor = wmo_fog.start_factor
            fog_obj.wow_wmo_fog.color1 = (wmo_fog.color1[2] / 255, wmo_fog.color1[1] / 255, wmo_fog.color1[0] / 255)
            fog_obj.wow_wmo_fog.end_dist2 = wmo_fog.end_dist2
            fog_obj.wow_wmo_fog.start_factor2 = wmo_fog.start_factor2
            fog_obj.wow_wmo_fog.color2 = (wmo_fog.color2[2] / 255, wmo_fog.color2[1] / 255, wmo_fog.color2[0] / 255)

            self.bl_fogs.append(fog_obj)

            # move fogs to collection
            fog_collection.objects.link(fog_obj)            

    def load_doodads(self):

        cache_path = self.settings.cache_dir_path
        doodad_prototypes = {}

        scene = bpy.context.scene
        doodad_collection = get_wmo_collection(scene, SpecialCollections.Doodads)

        with tqdm(self.wmo.modd.definitions, desc='Importing doodads', ascii=True) as progress:
            for doodad_set in self.wmo.mods.sets:
                # replace anchor object by collections
                doodadset_coll = bpy.data.collections.get(doodad_set.name)
                if not doodadset_coll:
                    doodadset_coll = bpy.data.collections.new(doodad_set.name)
                    doodad_collection.children.link(doodadset_coll)

                doodadset_coll.color_tag = 'COLOR_04'

                for i in range(doodad_set.start_doodad, doodad_set.start_doodad + doodad_set.n_doodads):
                    doodad = self.wmo.modd.definitions[i]

                    doodad_path = self.wmo.modn.get_string(doodad.name_ofs)
                    path_hash = str(hashlib.md5(doodad_path.encode('utf-8')).hexdigest())

                    proto_obj = doodad_prototypes.get(path_hash)

                    if not proto_obj:
                        nobj = import_doodad(doodad_path, cache_path)
                        doodad_prototypes[path_hash] = nobj
                    else:
                        nobj = proto_obj.copy()
                        # nobj.data = nobj.data.copy()

                        # for j, mat in enumerate(nobj.data.materials):
                        #     nobj.data.materials[j] = mat.copy()

                    # also link to base collection ?
                    doodadset_coll.objects.link(nobj)

                    bpy.context.view_layer.objects.active = nobj

                    nobj.wow_wmo_doodad.color = (doodad.color[2] / 255,
                                                 doodad.color[1] / 255,
                                                 doodad.color[0] / 255,
                                                 doodad.color[3] / 255
                                                )

                    flags = []
                    bit = 1
                    while bit <= 0x8:
                        if doodad.flags & bit:
                            flags.append(str(bit))
                        bit <<= 1

                    nobj.wow_wmo_doodad.flags = set(flags)

                    # place the object correctly on the scene
                    nobj.location = doodad.position
                    nobj.scale = (doodad.scale, doodad.scale, doodad.scale)

                    nobj.rotation_mode = 'QUATERNION'
                    nobj.rotation_quaternion = (doodad.rotation[3],
                                                doodad.rotation[0],
                                                doodad.rotation[1],
                                                doodad.rotation[2])
                    nobj.hide_set(True)

                    # doodad_collection.objects.link(nobj)

                    progress.update(1)

    def load_portals(self):
        """ Load WoW WMO portal planes """
        portal_collection = get_wmo_collection(bpy.context.scene, SpecialCollections.Portals)

        vert_count = 0
        for index, portal in tqdm(list(enumerate(self.wmo.mopt.infos)), desc='Importing portals', ascii=True):
            portal_name = "{}_Portal_{}".format(self.wmo.display_name, str(index).zfill(3))

            verts = []
            face = []
            faces = []

            for j in range(portal.n_vertices):
                if len(face) < 4:
                    verts.append(self.wmo.mopv.portal_vertices[vert_count])
                    face.append(j)
                vert_count += 1

            faces.append(face)

            mesh = bpy.data.meshes.new(portal_name)

            obj = bpy.data.objects.new(portal_name, mesh)


            mesh.from_pydata(verts, [], faces)

            self.bl_portals.append(obj)

            # assign portal material
            portal_mat = bpy.data.materials.get("WowMaterial_ghost_Portal")
            if portal_mat is None:
                portal_mat = bpy.data.materials.new("WowMaterial_ghost_Portal")
                portal_mat.blend_method = 'BLEND'
                portal_mat.use_nodes = True
                portal_mat.node_tree.nodes.remove(portal_mat.node_tree.nodes.get('Principled BSDF'))
                material_output = portal_mat.node_tree.nodes.get('Material Output')
                transparent = portal_mat.node_tree.nodes.new('ShaderNodeBsdfTransparent')
                portal_mat.node_tree.links.new(material_output.inputs[0], transparent.outputs[0])
                portal_mat.node_tree.nodes["Transparent BSDF"].inputs[0].default_value = (1, 0, 0, 1)

            obj.data.materials.append(portal_mat)

            # move portals to collection
            portal_collection.objects.link(obj)

    def load_portal_relations(self):
        """
            Load portal relations from MOPR data.
            Note that portals do not have to have a pair of relations. They may be linked to just one group.
            In that the portal works in a one-sided way. Example is floating cathedral exterior in Stormwind.
        """

        portal_relations = {}

        for index, group in tqdm(list(enumerate(self.bl_groups)), desc='Importing portal relations', ascii=True):
            portal_start = group.wmo_group.mogp.portal_start
            portal_count = group.wmo_group.mogp.portal_count

            if not portal_count:
                continue

            for i in range(portal_count):
                relation = self.wmo.mopr.relations[portal_start + i]

                # group from
                this_portal_rels = portal_relations.setdefault(relation.portal_index, (set(), set()))
                this_portal_rels[0].add(group.bl_object)
                this_portal_rels[1].add(group.bl_object)

                other_group = self.bl_groups[relation.group_index]
                this_portal_rels[0].add(other_group.bl_object)

        for portal_index, linked_groups in portal_relations.items():
            assert(len(linked_groups) == 2 and f"Portal links {len(linked_groups)} groups. Expected 2.")
            portal = self.bl_portals[portal_index]

            l_linked_groups = list(linked_groups[0])
            portal.wow_wmo_portal.first = l_linked_groups[0]
            portal.wow_wmo_portal.second = l_linked_groups[1]

            if portal.wow_wmo_portal.first not in linked_groups[1]:
                portal.wow_wmo_portal.detail = "1"
            elif portal.wow_wmo_portal.second not in linked_groups[1]:
                portal.wow_wmo_portal.detail = "2"

    def load_properties(self):
        """ Load global WoW WMO properties """

        wow_model_collection = get_current_wow_model_collection(bpy.context.scene, 'wow_wmo')
        
        properties = wow_model_collection.wow_wmo
        properties.ambient_color = (self.wmo.mohd.ambient_color[0] / 255,
                                    self.wmo.mohd.ambient_color[1] / 255,
                                    self.wmo.mohd.ambient_color[2] / 255,
                                    self.wmo.mohd.ambient_color[3] / 255)

        flags = set()
        if self.wmo.mohd.flags & 0x1:
            flags.add("0")
        if self.wmo.mohd.flags & 0x2:
            flags.add("2")
        if self.wmo.mohd.flags & 0x8:
            flags.add("1")
        # if self.wmo.mohd.flags & 0x4:
        #     flags.add("3")

        properties.flags = flags
        properties.skybox_path = self.wmo.mosb.skybox
        properties.wmo_id = self.wmo.mohd.id

    def load_groups(self):

        for i, group in tqdm(enumerate(self.wmo.groups), desc='Importing groups', ascii=True):
            bl_group = BlenderWMOSceneGroup(self, group)
            self.bl_groups.append(bl_group)

            if not bl_group.name == 'antiportal':
                bl_group.load_object(i)

    def build_references(self, export_selected, export_method):
        """ Build WMO references in Blender scene """

        group_objects = []
        scn = bpy.context.scene

        material_id = 0

        sorted_objects = sorted(get_wmo_groups_list(scn), key=lambda obj: obj.wow_wmo_group.export_order)

        for i, group_object in tqdm(enumerate(sorted_objects), desc='Building group references', ascii=True):
            if (export_selected and not group_object.select_get()) or group_object.hide_get():
                continue

            group_object : bpy.types.Object

            bpy.ops.object.select_all(action='DESELECT')
            group_object.select_set(True)
            bpy.context.view_layer.objects.active = group_object  

            self.export_group_ids[group_object.name] = i

            # self.groups_relations[group_object.name, relations]
            self.portals_relations[group_object] = []
            self.lights_relations[group_object] = []
            self.doodads_relations[group_object] = []

            group = self.wmo.add_group()
            self.bl_groups.append(BlenderWMOSceneGroup(self, group, obj=group_object))
            group_objects.append(group_object)

            # only iterate materials in the wmo groups.
            for material in group_object.data.materials:
                # don't create duplicates
                if material not in self.bl_materials.values():
                    self.bl_materials[material_id] = material
                    material_id += 1

            group.export = not (export_method == 'PARTIAL' and not group_object.export)


        # process portals
        for i, portal_object in tqdm(enumerate(get_wmo_collection(scn, SpecialCollections.Portals).objects), desc='Building portal references', ascii=True):
            self.bl_portals.append(portal_object)
            portal_object.wow_wmo_portal.portal_id = i

            # new system
            if portal_object.wow_wmo_portal.first:
                # self.groups_relations[portal_object.wow_wmo_portal.first.name].portals.append(portal_object.name)
                self.portals_relations[portal_object.wow_wmo_portal.first].append(portal_object)
            
            if portal_object.wow_wmo_portal.second:
                # self.groups_relations[portal_object.wow_wmo_portal.second.name].portals.append(portal_object.name)
                self.portals_relations[portal_object.wow_wmo_portal.second].append(portal_object)

        # process fogs
        for i, fog_object in tqdm(enumerate(get_wmo_collection(scn, SpecialCollections.Fogs).objects), desc='Building fog references', ascii=True):
            self.bl_fogs.append(fog_object)
            fog_object.wow_wmo_fog.fog_id = i

        # process lights
        for i, light_object in tqdm(enumerate(get_wmo_collection(scn, SpecialCollections.Lights).objects), desc='Building light references', ascii=True):
            group = find_nearest_object(light_object, group_objects)
            self.lights_relations[group].append(i)
            self.bl_lights.append(light_object)

        # process doodads
        doodad_counter = 0
        for i, doodad_set_collection in tqdm(enumerate(get_wmo_collection(scn, SpecialCollections.Doodads).children), desc='Building doodad references', ascii=True):

            doodads = []

            for doodad in doodad_set_collection.objects:
                group = find_nearest_object(doodad, group_objects)
                if group not in self.doodads_relations:
                    print("ERROR doodad group ref, nearest_object: " + group.name)
                self.doodads_relations[group].append(doodad_counter)

                doodad_counter += 1

                doodads.append(doodad)

            self.bl_doodad_sets[doodad_set_collection.name] = doodads

    def save_materials(self):
        """ Add material if not already added, then return index in root file """

        for i, mat in tqdm(enumerate(self.bl_materials.values())
                                , desc='Saving materials'
                                , ascii=True
                                ):

            if not mat.wow_wmo_material.diff_texture_1:
                raise ReferenceError('\nError:  Material \"{}\" must have a diffuse texture.'.format(mat.name))

            diff_texture_1 = mat.wow_wmo_material.diff_texture_1.wow_wmo_texture.path
            diff_texture_1 = diff_texture_1.replace('/', '\\')
            diff_texture_1 = diff_texture_1.lower()

            diff_texture_2 = mat.wow_wmo_material.diff_texture_2.wow_wmo_texture.path \
                if mat.wow_wmo_material.diff_texture_2 else ""
            diff_texture_2 = diff_texture_2.replace('/', '\\')
            diff_texture_2 = diff_texture_2.lower()

            flags = 0

            for flag in mat.wow_wmo_material.flags:
                flags |= int(flag)

            self.wmo.add_material(diff_texture_1
                                  , diff_texture_2
                                  , int(mat.wow_wmo_material.shader)
                                  , int(mat.wow_wmo_material.blending_mode)
                                  , int(mat.wow_wmo_material.terrain_type)
                                  , flags
                                  , ( int(mat.wow_wmo_material.emissive_color[0] * 255),
                                      int(mat.wow_wmo_material.emissive_color[1] * 255),
                                      int(mat.wow_wmo_material.emissive_color[2] * 255),
                                      int(mat.wow_wmo_material.emissive_color[3] * 255)
                                    )
                                  , ( int(mat.wow_wmo_material.diff_color[2] * 255),
                                      int(mat.wow_wmo_material.diff_color[1] * 255),
                                      int(mat.wow_wmo_material.diff_color[0] * 255),
                                      int(mat.wow_wmo_material.diff_color[3] * 255)
                                    )
                                 )

    def add_group_info(self, flags, bounding_box, name, desc):
        """ Add group info, then return offset of name and desc in a tuple """
        group_info = GroupInfo()

        group_info.flags = flags  # 8
        group_info.bounding_box_corner1 = [_ for _ in bounding_box[0]]
        group_info.bounding_box_corner2 = [_ for _ in bounding_box[1]]
        group_info.name_ofs = self.wmo.mogn.add_string(name)  # 0xFFFFFFFF

        if desc:
            desc_ofs = self.wmo.mogn.add_string(desc)
        else:
            desc_ofs = 0

        self.wmo.mogi.infos.append(group_info)

        return group_info.name_ofs, desc_ofs

    def save_doodad_sets(self):
        """ Save doodads data from Blender scene to WMO root """

        def normalize_quaternion(quat):
            w, x, y, z = quat
            norm = math.sqrt(w ** 2 + x ** 2 + y ** 2 + z ** 2)
            return (w / norm, x / norm, y / norm, z / norm)  

        has_global = False
        set_counter = 1

        if len(self.bl_doodad_sets):

            for set_name, doodads in tqdm(self.bl_doodad_sets.items(), desc='Saving doodad sets', ascii=True):
                
                if set_name.startswith("Set_$DefaultGlobal"):
                    if not has_global:
                        set_name = "Set_$DefaultGlobal"
                        has_global = True
                    else:
                        set_name = f"Set_{set_counter:03}"
                        set_counter += 1

                self.wmo.add_doodad_set(set_name, len(doodads))

                for doodad in doodads:

                    path = doodad.wow_wmo_doodad.path.replace('/', '\\')

                    position = (doodad.matrix_world @ Vector((0, 0, 0))).to_tuple()

                    doodad.rotation_mode = 'QUATERNION'

                    doodad.rotation_quaternion = normalize_quaternion(doodad.rotation_quaternion)  

                    rotation = (doodad.rotation_quaternion[1],
                                doodad.rotation_quaternion[2],
                                doodad.rotation_quaternion[3],
                                doodad.rotation_quaternion[0])

                    scale = doodad.scale[0]

                    doodad_color = [int(channel * 255) for channel in doodad.wow_wmo_doodad.color]
                    doodad_color = (doodad_color[2], doodad_color[1], doodad_color[0], doodad_color[3])

                    flags = 0
                    for flag in doodad.wow_wmo_doodad.flags:
                        flags |= int(flag)

                    self.wmo.add_doodad(path, position, rotation, scale, doodad_color, flags)

        if not has_global:
            self.wmo.add_doodad_set("Set_$DefaultGlobal", 0)

    def save_lights(self):

        for obj in tqdm(self.bl_lights, desc='Saving lights', ascii=True):

            light_type = int(obj.wow_wmo_light.light_type)

            unk1 = obj.data.distance * 2

            unk2 = obj.wow_wmo_light.type
            use_attenuation = obj.wow_wmo_light.use_attenuation
            padding = obj.wow_wmo_light.padding

            color = (int(obj.wow_wmo_light.color[2] * 255),
                     int(obj.wow_wmo_light.color[1] * 255),
                     int(obj.wow_wmo_light.color[0] * 255),
                     int(obj.wow_wmo_light.color_alpha * 255))

            position = obj.location.to_tuple()
            intensity = obj.wow_wmo_light.intensity
            attenuation_start = obj.wow_wmo_light.attenuation_start
            attenuation_end = obj.wow_wmo_light.attenuation_end

            self.wmo.add_light(light_type, unk1, unk2, use_attenuation, padding, color,
                               position, intensity, attenuation_start, attenuation_end)

    @staticmethod
    def get_angle(vec_a: Vector, vec_b: Vector, vec_n: Vector) -> float:
        return atan2(
            -(vec_a.x * vec_b.y * vec_n.z + vec_b.x * vec_n.y * vec_a.z + vec_n.x * vec_a.y * vec_b.z
              - vec_a.z * vec_b.y * vec_n.x - vec_b.z * vec_n.y * vec_a.x - vec_n.z * vec_a.y * vec_b.x),
            -(vec_a.x * vec_b.x + vec_a.y * vec_b.y + vec_a.z * vec_b.z)) + pi

    @staticmethod
    def traverse(cur_vtx: BMVert
                 , nodes_to_hit: List
                 , nodes_hit: List
                 , origin: BMVert) -> List:

        for edge in cur_vtx.link_edges:

            other = edge.other_vert(cur_vtx)

            if other == origin:
                if not nodes_to_hit:
                    return nodes_hit
                else:
                    continue

            if other in nodes_hit:
                continue

            nodes_to_hit_new = nodes_to_hit.copy()
            nodes_to_hit_new.remove(other)

            nodes_hit_new = nodes_hit.copy()
            nodes_hit_new.append(other)

            result = BlenderWMOScene.traverse(other, nodes_to_hit_new, nodes_hit_new, origin)

            if result:
                return result

        return []

    @staticmethod
    def sort_portal_vertices(vertices: List[BMVert], normal: Vector) -> List[BMVert]:

        pos_n = Vector((0, 0, 0))
        origin = None

        for vtx in vertices:
            if len(vtx.link_edges) == 2 and origin is None:
                origin = vtx
            pos_n += (vtx.co)

        pos_n /= len(vertices)
        vtx_a = origin.link_edges[0].other_vert(origin)
        vtx_b = origin.link_edges[1].other_vert(origin)
        vector_o = (origin.co) - pos_n
        next_vtx = vtx_b if BlenderWMOScene.get_angle((vtx_a.co) - pos_n, vector_o, normal) \
                            < BlenderWMOScene.get_angle((vtx_b.co) - pos_n, vector_o, normal) else vtx_a

        # traversing mesh
        nodes_to_hit = list(vertices).copy()
        nodes_to_hit.remove(origin)
        nodes_to_hit.remove(next_vtx)

        nodes_hit = [origin, next_vtx]
        result = BlenderWMOScene.traverse(next_vtx, nodes_to_hit, nodes_hit, origin)

        return result

    def save_portals(self):

        saved_portals_ids = []

        depsgraph = bpy.context.evaluated_depsgraph_get()
        self.wmo.mopt.infos = len(self.bl_portals) * [PortalInfo()]

        for bl_group, group_mesh_eval in tqdm(zip(self.bl_groups, self.groups_eval), desc='Saving portals', ascii=True):

            group_obj = bl_group.bl_object
            portal_relations = self.portals_relations[group_obj]
            bl_group.wmo_group.mogp.portal_start = len(self.wmo.mopr.relations)

            for portal_obj in portal_relations:
                portal_index = portal_obj.original.wow_wmo_portal.portal_id
                portal_mesh = portal_obj.data

                if portal_index not in saved_portals_ids:

                    portal_info = PortalInfo()
                    portal_info.start_vertex = len(self.wmo.mopv.portal_vertices)
                    v = []

                    bm = bmesh.new()
                    bm.from_mesh(portal_mesh)
                    bm.verts.ensure_lookup_table()

                    portal_matrix_normal = portal_obj.matrix_world.to_3x3().transposed().inverted()
                    portal_normal = (portal_matrix_normal @ portal_mesh.polygons[0].normal).normalized()

                    portal_verts = self.sort_portal_vertices(bm.verts, portal_mesh.polygons[0].normal)

                    for vertex in portal_verts:
                        vertex_pos = portal_obj.matrix_world @ vertex.co
                        self.wmo.mopv.portal_vertices.append(vertex_pos.to_tuple())
                        v.append(vertex_pos)

                    bm.free()

                    v_A = v[0][1] * v[1][2] - v[1][1] * v[0][2] - v[0][1] * v[2][2] + v[2][1] * v[0][2] + v[1][1] * \
                          v[2][2] - \
                          v[2][1] * v[1][2]
                    v_B = -v[0][0] * v[1][2] + v[2][0] * v[1][2] + v[1][0] * v[0][2] - v[2][0] * v[0][2] - v[1][0] * \
                          v[2][2] + \
                          v[0][0] * v[2][2]
                    v_C = v[2][0] * v[0][1] - v[1][0] * v[0][1] - v[0][0] * v[2][1] + v[1][0] * v[2][1] - v[2][0] * \
                          v[1][1] + \
                          v[0][0] * v[1][1]
                    v_D = -v[0][0] * v[1][1] * v[2][2] + v[0][0] * v[2][1] * v[1][2] + v[1][0] * v[0][1] * v[2][2] - \
                          v[1][0] * \
                          v[2][1] * v[0][2] - v[2][0] * v[0][1] * v[1][2] + v[2][0] * v[1][1] * v[0][2]

                    portal_info.unknown = v_D / sqrt(v_A * v_A + v_B * v_B + v_C * v_C)
                    portal_info.n_vertices = len(self.wmo.mopv.portal_vertices) - portal_info.start_vertex
                    portal_info.normal = portal_normal.to_tuple()

                    self.wmo.mopt.infos[portal_index] = portal_info
                    saved_portals_ids.append(portal_index)

                first = portal_obj.original.wow_wmo_portal.first
                second = portal_obj.original.wow_wmo_portal.second

                # skip detail groups (see e.g. Stormwind cathedral)
                if portal_obj.original.wow_wmo_portal.detail != '0':
                    if first.name == group_obj.original.name:
                        if portal_obj.original.wow_wmo_portal.detail == '1':
                            continue
                    else:
                        if portal_obj.original.wow_wmo_portal.detail == '2':
                            continue

                # calculating portal relation
                relation = PortalRelation()
                relation.portal_index = portal_index

                relation.group_index = self.export_group_ids[second.name] if first.name == group_obj.original.name \
                    else self.export_group_ids[first.name]

                relation.side = bl_group.get_portal_direction(portal_obj, group_obj.evaluated_get(depsgraph))

                self.wmo.mopr.relations.append(relation)

            bl_group.wmo_group.mogp.portal_count = len(self.wmo.mopr.relations) - bl_group.wmo_group.mogp.portal_start

    def prepare_groups(self):
        for bl_group in tqdm(self.bl_groups, desc='Preparing groups', ascii=True):
            if bl_group.wmo_group.export:
                bl_group.doodads_relations = self.doodads_relations[bl_group.bl_object]
                bl_group.lights_relations = self.lights_relations[bl_group.bl_object]

                mesh, params = bl_group.create_batching_parameters()
                self.groups_eval.append(mesh)
                self.group_batch_params.append(params)

    def save_groups(self):
        for _ in tqdm(range(1), desc='Processing group geometry', ascii=True):
            batcher = CWMOGeometryBatcher(self.group_batch_params)

        for i, bl_group in enumerate(tqdm(self.bl_groups, desc='Saving groups', ascii=True)):

            if bl_group.wmo_group.export:
                bl_group.save(batcher, i)

    def save_fogs(self):

        for fog_obj in tqdm(self.bl_fogs, desc='Saving fogs', ascii=True):

            big_radius = fog_obj.dimensions[2] / 2
            # small radius % calculation is done by pywowlib

            color1 = (int(fog_obj.wow_wmo_fog.color1[2] * 255),
                          int(fog_obj.wow_wmo_fog.color1[1] * 255),
                          int(fog_obj.wow_wmo_fog.color1[0] * 255),
                          0xFF)

            color2 = (int(fog_obj.wow_wmo_fog.color2[2] * 255),
                          int(fog_obj.wow_wmo_fog.color2[1] * 255),
                          int(fog_obj.wow_wmo_fog.color2[0] * 255),
                          0xFF)

            end_dist = fog_obj.wow_wmo_fog.end_dist
            end_dist2 = fog_obj.wow_wmo_fog.end_dist2
            position = fog_obj.location.to_tuple()
            start_factor = fog_obj.wow_wmo_fog.start_factor
            start_factor2 = fog_obj.wow_wmo_fog.start_factor2

            flags = 0
            if fog_obj.wow_wmo_fog.ignore_radius:
                flags |= 0x01
            if fog_obj.wow_wmo_fog.unknown:
                flags |= 0x10

            self.wmo.add_fog(big_radius, fog_obj.wow_wmo_fog.inner_radius, color1, color2, end_dist, end_dist2, position,
                             start_factor, start_factor2, flags)

    def save_root_header(self):

        wow_model_collection = get_current_wow_model_collection(bpy.context.scene, 'wow_wmo')

        properties = wow_model_collection.wow_wmo

        scene = bpy.context.scene

        self.wmo.mver.version = 17

        # setting up default fog with default blizzlike values.
        if not len(self.wmo.mfog.fogs):
            empty_fog = Fog()
            empty_fog.color1 = (0xFF, 0xFF, 0xFF, 0xFF)
            empty_fog.color2 = (0x00, 0x00, 0x00, 0xFF)
            empty_fog.end_dist = 444.4445
            empty_fog.end_dist2 = 222.2222
            empty_fog.start_factor = 0.25
            empty_fog.start_factor2 = -0.5
            self.wmo.mfog.fogs.append(empty_fog)

        bb = self.wmo.get_global_bounding_box()
        self.wmo.mohd.bounding_box_corner1 = bb[0]
        self.wmo.mohd.bounding_box_corner2 = bb[1]

        # DBC foreign keys
        self.wmo.mohd.id = properties.wmo_id
        self.wmo.mosb.skybox = properties.skybox_path

        self.wmo.mohd.ambient_color = [int(properties.ambient_color[0] * 255),
                                       int(properties.ambient_color[1] * 255),
                                       int(properties.ambient_color[2] * 255),
                                       int(properties.ambient_color[3] * 255)]

        self.wmo.mohd.n_materials = len(self.wmo.momt.materials)
        self.wmo.mohd.n_groups = len(self.wmo.mogi.infos)
        self.wmo.mohd.n_portals = len(self.wmo.mopt.infos)
        self.wmo.mohd.n_models = self.wmo.modn.string_table.decode("ascii").count('.MDX')
        self.wmo.mohd.n_lights = len(self.wmo.molt.lights)
        self.wmo.mohd.n_doodads = len(self.wmo.modd.definitions)
        self.wmo.mohd.n_sets = len(self.wmo.mods.sets)

        flags = properties.flags
        if "0" in flags:
            self.wmo.mohd.flags |= 0x01
        if "2" in flags:
            self.wmo.mohd.flags |= 0x02
        if "1" in flags:
            self.wmo.mohd.flags |= 0x08
        # if "3" in flags:
        #     self.wmo.mohd.flags |= 0x4
        version = int(scene.wow_scene.version)
        if version >= WoWVersions.WOTLK:
            self.wmo.mohd.flags |= 0x4






