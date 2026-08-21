import bpy
import mathutils
import bmesh

from typing import Tuple, Dict, List

from ..pywowlib.file_formats.wmo_format_root import MOHDFlags, PortalRelation
from ..pywowlib.file_formats.wmo_format_group import MOGPFlags, LiquidVertex, BSPPlaneType
from ..pywowlib.wmo_file import WMOGroupFile
from .bl_render import BlenderWMOObjectRenderFlags
from ..pywowlib import WoWVersions, WoWVersionManager
from .classic_lint import ClassicLint
from ..wbs_kernel.wmo_utils import CWMOGeometryBatcher, WMOGeometryBatcherMeshParams, LiquidExportParams
from ..utils.colors import srgb_to_linear as linear
from .ui.custom_objects import WoWWMOGroup
from .ui.collections import get_wmo_collection, SpecialCollections

class BlenderWMOSceneGroup:
    def __init__(self, wmo_scene, wmo_group, obj=None):
        self.wmo_group: WMOGroupFile = wmo_group
        self.wmo_scene: 'BlenderWMOScene' = wmo_scene
        self.bl_object: bpy.types.Object = obj
        self.name = wmo_scene.wmo.mogn.get_string(wmo_group.mogp.group_name_ofs)
        self.has_blending: bool = False
        self.bounding_box_base: bpy.types.Object = None

        self.lights_relations: List[int] = []
        self.doodads_relations:  List[int] = []

    @staticmethod
    def get_material_viewport_image(material):
        """ Get viewport image assigned to a material """

        if material.wow_wmo_material.diff_texture_1:
            return material.wow_wmo_material.diff_texture_1

    def from_wmo_liquid_type(self, basic_liquid_type):
        """ Convert simplified WMO liquid type IDs to real LiquidType.dbc IDs """
        real_liquid_type = 0

        if basic_liquid_type < 20:
            if basic_liquid_type == 0:
                real_liquid_type = 14 if self.wmo_group.mogp.flags & MOGPFlags.IsNotOcean else 13
            elif basic_liquid_type == 1:
                real_liquid_type = 14
            elif basic_liquid_type == 2:
                real_liquid_type = 19
            elif basic_liquid_type == 15:
                real_liquid_type = 17
            elif basic_liquid_type == 3:
                real_liquid_type = 20
        else:
            real_liquid_type = basic_liquid_type + 1

        return real_liquid_type

    def get_legacy_water_type(self, liquid_type):
        # Copied 1:1 from blizzard's decompiled code...
        liquid_type += 1
        if (liquid_type - 1) <= 0x13:
            newwater = (liquid_type - 1) & 3
            if newwater == 1:
                liquid_type = 14
                return liquid_type

            if newwater >= 1:
                if newwater == 2:
                    liquid_type = 19
                elif newwater == 3:
                    liquid_type = 20

                return liquid_type

            liquid_type = 13

        return liquid_type

    # return array of vertices and array of faces in a tuple
    def load_liquids(self, group_name, pos):
        """ Load liquid plane of the WMO group. Should only be called if MLIQ is present. """

        group = self.wmo_group

        # load vertices
        vertices = []
        for y in range(0, group.mliq.y_verts):
            y_pos = group.mliq.position[1] + y * 4.1666625
            for x in range(0, group.mliq.x_verts):
                x_pos = group.mliq.position[0] + x * 4.1666625
                vertices.append((x_pos, y_pos, group.mliq.vertex_map[y * group.mliq.x_verts + x].height))

        # calculate faces
        indices = []
        for y in range(group.mliq.y_tiles):
            for x in range(group.mliq.x_tiles):
                indices.append(y * group.mliq.x_verts + x)
                indices.append(y * group.mliq.x_verts + x + 1)
                indices.append((y + 1) * group.mliq.x_verts + x)
                indices.append((y + 1) * group.mliq.x_verts + x + 1)

        faces = []

        for i in range(0, len(indices), 4):
            faces.append((indices[i], indices[i + 1], indices[i + 3], indices[i + 2]))

        # create mesh and object
        name = group_name + "_Liquid"
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)

        # create mesh from python data
        mesh.from_pydata(vertices, [], faces)
        mesh.update(calc_edges=True)
        mesh.validate()
        
        render_state_list = []
        
        # load legacy liquid type (vanilla/bc models) and render state from MLIQ tiles flags
        legacy_liquid_type = 0
        for poly in mesh.polygons:
            bit = 1
            tile_flags = 0
            while bit <= 0x8:
                tile_flag = group.mliq.tile_flags[poly.index]
                if tile_flag & bit:
                    tile_flags += bit
                bit <<= 1
            if tile_flags != 15:  # 15 = don't render/no liquid, ignore those tiles
                # and get the flags from the first non 15 tile.
                legacy_liquid_type = tile_flags
                # break
                render_state = True
            else:
                render_state = False

            render_state_list.append(render_state)

        # getting Liquid Type ID
        if self.wmo_scene.wmo.mohd.flags & 0x4:
            real_liquid_type = group.mogp.liquid_type
        else:
            real_liquid_type = self.get_legacy_water_type(legacy_liquid_type)
            # real_liquid_type = self.from_wmo_liquid_type(group.mogp.liquid_type)

        # create uv map if liquid is lava or slime
        if real_liquid_type in {3, 4, 7, 8, 11, 12, 15, 19, 20, 21, 121, 141}:
            uv_map = {}

            for vertex in mesh.vertices:
                uv_map[vertex.index] = (group.mliq.vertex_map[vertex.index].u,
                                        group.mliq.vertex_map[vertex.index].v)

            mesh.uv_layers.new(name="UVMap")
            uv_layer1 = mesh.uv_layers[0]

            for poly in mesh.polygons:
                for loop_index in poly.loop_indices:
                    uv_layer1.data[loop_index].uv = (uv_map.get(mesh.loops[loop_index].vertex_index)[0] / 255,
                                                     - uv_map.get(mesh.loops[loop_index].vertex_index)[1] / 255)

        # setting flags in a hacky way using vertex colors
        bit = 1
        counter = 0
        while bit <= 0x80:
            # if bit == 0x8: # hackfix to make layer 4 the vertex layer used by the WMO shader
            #     vc_layer = mesh.vertex_colors.new(name="Col")
            # else:
            #     vc_layer = mesh.vertex_colors.new(name="flag_" + str(counter))
            vc_layer = mesh.vertex_colors.new(name="flag_" + str(counter))
            counter += 1

            if bit <= 0x8:
                bit <<= 1
                continue # ignore legacy liquid type flags
            for poly in mesh.polygons:
                tile_flag = group.mliq.tile_flags[poly.index]
                for loop in poly.loop_indices:
                    if tile_flag & bit:
                        vc_layer.data[loop].color = (0, 0, 255, 255)
                    else:
                        vc_layer.data[loop].color = (255, 255, 255, 255)
            bit <<= 1

        # legacy liquid flags, if "no render", set all 4, else set none.
        # Cleanup blizzlike data to make flag 4 the "no render flag" used by the liquid flag editor.
        for i, poly in enumerate(mesh.polygons):
            render_state = render_state_list[i]

            bit = 1
            counter = 0
            while bit <= 0x8:
                vc_layer = mesh.vertex_colors["flag_{}".format(counter)]
                for loop in poly.loop_indices:
                    if not render_state:
                        vc_layer.data[loop].color = (0, 0, 255, 255)
                    else:
                        vc_layer.data[loop].color = (255, 255, 255, 255)
                bit <<= 1
                counter += 1

        # assign WMO liquid material
        liquid_material = self.wmo_scene.bl_materials[group.mliq.material_id]   
        mesh.materials.append(liquid_material)

        # assign ghost material to unrendered tiles
        mat_ghost = bpy.data.materials.get("WowMaterial_ghost_Liquid")
        if mat_ghost is None:
            mat_ghost = bpy.data.materials.new("WowMaterial_ghost_Liquid")
            mat_ghost.blend_method = 'BLEND'
            mat_ghost.use_nodes = True
            mat_ghost.node_tree.nodes.remove(mat_ghost.node_tree.nodes.get('Principled BSDF'))
            material_output = mat_ghost.node_tree.nodes.get('Material Output')
            transparent = mat_ghost.node_tree.nodes.new('ShaderNodeBsdfTransparent')
            mat_ghost.node_tree.links.new(material_output.inputs[0], transparent.outputs[0])
            mat_ghost.node_tree.nodes["Transparent BSDF"].inputs[0].default_value = (1, 1, 1, 1)
        mesh.materials.append(mat_ghost)

        # create a material for blender rendering
        liquid_render_mat = bpy.data.materials.new("WowMaterial_" + name)
        liquid_render_mat.blend_method = 'BLEND'
        liquid_render_mat.use_nodes = True
        liquid_render_mat.node_tree.nodes.remove(liquid_render_mat.node_tree.nodes.get('Principled BSDF'))
        material_output = liquid_render_mat.node_tree.nodes.get('Material Output')
        # transparent = liquid_render_mat.node_tree.nodes.new('ShaderNodeBsdfTransparent')
        transparent = liquid_render_mat.node_tree.nodes.new('ShaderNodeBsdfDiffuse') # diffuse looks better ?
        liquid_render_mat.node_tree.links.new(material_output.inputs[0], transparent.outputs[0])

        if real_liquid_type in {3, 7, 11, 15, 19, 121, 141}:# lava
            material_color = (1, 0.1, 0.0, 1.0) # orange
        elif real_liquid_type in {4, 8, 12, 20, 21}: # slime
            material_color = (0.06274, 0.77647, 0.0, 1.0) # green
        else:
            material_color = self.wmo_scene.bl_materials[group.mliq.material_id].wow_wmo_material.diff_color

        # liquid_render_mat.node_tree.nodes["Transparent BSDF"].inputs[0].default_value = material_color
        liquid_render_mat.node_tree.nodes["Diffuse BSDF"].inputs[0].default_value = material_color
        mesh.materials.append(liquid_render_mat)

        for poly in mesh.polygons:
            tile_flag = group.mliq.tile_flags[poly.index]
            if tile_flag & 0x1 and tile_flag & 0x2 and tile_flag & 0x4 and tile_flag & 0x8:
                poly.material_index = 1 # assign ghost_material to non rendered tiles
            else:
                # if group.mogp.liquid_type in {3, 4, 7, 8, 11, 12, 15, 19, 20, 21, 121, 141}:
                #     poly.material_index = 0
                # else:
                #     poly.material_index = 2
                poly.material_index = 2

        # set mesh location
        obj.location = pos

        liquid_collection = get_wmo_collection(bpy.context.scene, SpecialCollections.Liquids)
        liquid_collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=True)
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')

        obj.lock_scale = [True, True, True]
        obj.lock_rotation[2] = True

        obj.wow_wmo_liquid.enabled = True

        obj.wow_wmo_liquid.color = self.wmo_scene.bl_materials[group.mliq.material_id].wow_wmo_material.diff_color

        wmo_group_obj = bpy.context.scene.objects[group_name]
        wmo_group_obj.wow_wmo_group.liquid_type = str(real_liquid_type)
        wmo_group_obj.wow_wmo_group.liquid_mesh = obj

    # Return faces indices
    def get_bsp_node_indices(self, i_node, nodes, faces, indices):
        """ Get indices of a WMO BSP tree nodes """
        # last node in branch
        node_indices = []
        try:
            if nodes[i_node].plane_type & BSPPlaneType.Leaf:
                for i in range(nodes[i_node].first_face, nodes[i_node].first_face + nodes[i_node].num_faces):
                    node_indices.append(faces[i])
        except:
            pass 
        try:
            if nodes[i_node].children[0] != -1:
                node_indices.extend(self.get_bsp_node_indices(nodes[i_node].children[0], nodes, faces, indices))
        except:
            pass   
        try:
            if nodes[i_node].children[1] != -1:
                node_indices.extend(self.get_bsp_node_indices(nodes[i_node].children[1], nodes, faces, indices))
        except:
            pass
        return node_indices

    def get_collision_indices(self):
        """ Get indices of a WMO BSP tree nodes that have collision """

        group = self.wmo_group
        node_indices = self.get_bsp_node_indices(0, group.mobn.nodes, group.mobr.faces, group.movi.indices)
        indices = []
        for i in node_indices:
            try:
                if not group.mopy.triangle_materials[i].flags & 0x04:
                    indices.append(group.movi.indices[i * 3])
                    indices.append(group.movi.indices[i * 3 + 1])
                    indices.append(group.movi.indices[i * 3 + 2])
            except:
                pass

        return indices
    

    def create_bb_base_object(self):
        if "BBBase" in bpy.data.objects:
            return bpy.data.objects["BBBase"]

        mesh =  bpy.data.meshes.get("SharedBBMesh")
        if mesh is None:
            verts = [
                (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
                (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
            ]

        edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
        ]
            
        faces = [
            # (0, 1, 2, 3), (4, 5, 6, 7),
            # (0, 1, 5, 4), (2, 3, 7, 6),
            # (1, 2, 6, 5), (0, 3, 7, 4),
        ]
        mesh = bpy.data.meshes.new("SharedBBMesh")
        mesh.from_pydata(verts, edges, faces)
        mesh.update()

        # if "TransparentBoxMaterial" not in bpy.data.materials:
        #     mat = bpy.data.materials.new(name="TransparentBoxMaterial")
        #     mat.use_nodes = True
        #     mat.blend_method = 'BLEND'
        #     mat.shadow_method = 'NONE'
        #     nodes = mat.node_tree.nodes
        #     links = mat.node_tree.links
        #     nodes.clear()
        #     output = nodes.new("ShaderNodeOutputMaterial")
        #     transparent = nodes.new("ShaderNodeBsdfTransparent")
        #     diffuse = nodes.new("ShaderNodeBsdfDiffuse")
        #     mix = nodes.new("ShaderNodeMixShader")
        #     mix.inputs['Fac'].default_value = 0.7
        #     links.new(diffuse.outputs['BSDF'], mix.inputs[1])
        #     links.new(transparent.outputs['BSDF'], mix.inputs[2])
        #     links.new(mix.outputs['Shader'], output.inputs['Surface'])
        # mat = bpy.data.materials["TransparentBoxMaterial"]

        # wireframe mat
        if "BBSharedMaterial" not in bpy.data.materials:
            mat = bpy.data.materials.new(name="BBSharedMaterial")
            mat.use_nodes = True
            mat.blend_method = 'BLEND'
            mat.shadow_method = 'NONE'

            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            nodes.clear()

            output = nodes.new(type='ShaderNodeOutputMaterial')
            # wireframe_shader = nodes.new(type='ShaderNodeWireframe')
            diffuse_shader = nodes.new(type='ShaderNodeBsdfDiffuse')

            # Set wireframe color to yellow
            # wireframe_shader.inputs['Color'].default_value = (1, 1, 0, 1)

            # links.new(wireframe_shader.outputs['BSDF'], diffuse_shader.inputs['Color'])
            links.new(diffuse_shader.outputs['BSDF'], output.inputs['Surface'])
        mat = bpy.data.materials.get("BBSharedMaterial")

        mesh.materials.clear()
        mesh.materials.append(mat)

        base_obj = bpy.data.objects.new("BBBase", mesh)

        coll_name = "BSP tree boxes"
        if coll_name not in bpy.data.collections:
            collection = bpy.data.collections.new(coll_name)
            bpy.context.collection.children.link(collection)
        else:
            collection = bpy.data.collections[coll_name]

        collection.objects.link(base_obj)

        base_obj.hide_set(True)
        base_obj.hide_render = True
        base_obj.hide_viewport = True
        base_obj.hide_select = True

        return base_obj

    def create_bb_instance_from_base(self, min_corner, max_corner, name="BBInstance"):
        base_obj = self.bounding_box_base

        if (base_obj is None):
            base_obj = self.create_bb_base_object()

        new_obj = base_obj.copy()
        new_obj.data = base_obj.data
        new_obj.name = name
        new_obj.hide_set(False)
        new_obj.hide_render = False
        new_obj.hide_viewport = False
        new_obj.hide_select = False

        size = (
            max_corner[0] - min_corner[0],
            max_corner[1] - min_corner[1],
            max_corner[2] - min_corner[2],
        )
        center = (
            (min_corner[0] + max_corner[0]) / 2,
            (min_corner[1] + max_corner[1]) / 2,
            (min_corner[2] + max_corner[2]) / 2,
        )

        # new_obj.scale = scale
        new_obj.scale = size  # (size[0] / 2, size[1] / 2, size[2] / 2)
        new_obj.location = min_corner # center

        # wireframe_modifier = new_obj.modifiers.new(name="Wireframe", type='WIREFRAME')
        # wireframe_modifier.thickness = 0.01

        new_obj.display_type = 'SOLID'
        new_obj.show_wire = True

        bpy.data.collections["BSP tree boxes"].objects.link(new_obj)
        # bpy.context.collection.objects.link(new_obj)
        # return new_obj

    def create_BSP_render(self, i_node, bounding_box_min, bounding_box_max, depth):

        bsp_node = self.wmo_group.mobn.nodes[i_node]

        # print(f"group {self.name} node {i_node} type {bsp_node.plane_type}")

        if bsp_node.plane_type & BSPPlaneType.Leaf:
            # final leaf, create BB
            self.create_bb_instance_from_base(bounding_box_min, bounding_box_max, f"{self.name}BSP Depth {depth}")
            # print(f"draw bb for node {i_node}")
            return

        negative_min, negative_max = None, None
        positive_min, positive_max = None, None

        # set plane intersection
        if bsp_node.plane_type == BSPPlaneType.YZ_plane:
            # divide_pos = (center_x + bsp_node.dist, center_y, center_z)
            divide_pos = (bsp_node.dist, 0, 0)

            # preview plane
            # TODO, gotta use instancing
            # bpy.ops.mesh.primitive_plane_add(location=divide_pos, rotation=(0, -math.pi/2, 0))  # Rotate -90° around Y-axis
            # obj = bpy.context.view_layer.objects.active
            # obj.name = f"{self.name}typeX"
            # obj.hide_set(False)

            # intersect the bounding box
            negative_min = bounding_box_min
            negative_max = (min(bounding_box_max[0], bsp_node.dist), bounding_box_max[1], bounding_box_max[2])
            positive_min = (max(bounding_box_min[0], bsp_node.dist), bounding_box_min[1], bounding_box_min[2])
            positive_max = bounding_box_max

        elif bsp_node.plane_type == BSPPlaneType.XZ_plane:
            negative_min = bounding_box_min
            negative_max = (bounding_box_max[0], min(bounding_box_max[1], bsp_node.dist), bounding_box_max[2])

            positive_min = (bounding_box_min[0], max(bounding_box_min[1], bsp_node.dist), bounding_box_min[2])
            positive_max = bounding_box_max
            

        elif bsp_node.plane_type == BSPPlaneType.XY_plane:
            negative_min = bounding_box_min
            negative_max = (bounding_box_max[0], bounding_box_max[1], min(bounding_box_max[2], bsp_node.dist))
            positive_min = (bounding_box_min[0], bounding_box_min[1], max(bounding_box_min[2], bsp_node.dist))
            positive_max = bounding_box_max
        
        else:
            print(f"error node {i_node} has type {bsp_node.plane_type}")
            return

        # recurse
        #  child on negative side of dividing plane
        if bsp_node.children[0] != -1:
            self.create_BSP_render(bsp_node.children[0], negative_min, negative_max, depth+1)
 
        # on positive side
        if bsp_node.children[1] != -1:
            self.create_BSP_render(bsp_node.children[1], positive_min, positive_max, depth+1)


    def load_object(self, export_order):
        """ Load WoW WMO group as an object to the Blender scene """

        group = self.wmo_group

        vertices = group.movt.vertices
        normals = group.monr.normals
        tex_coords = group.motv.tex_coords
        faces = [group.movi.indices[i:i + 3] for i in range(0, len(group.movi.indices), 3)]

        # create mesh
        mesh = bpy.data.meshes.new(self.name)
        mesh.from_pydata(vertices, [], faces)

        # create object
        scn = bpy.context.scene

        nobj = bpy.data.objects.new(self.name, mesh)

        collision_face_ids = []
        for i, poly in enumerate(mesh.polygons):
            poly.use_smooth = True

            try: 
                if group.mopy.triangle_materials[i].material_id == 0xFF:
                    collision_face_ids.append(i)
            except:
                pass

        # set normals
        custom_normals = [(0.0, 0.0, 0.0)] * len(mesh.loops)
        mesh.use_auto_smooth = True
        for i, loop in enumerate(mesh.loops):
            custom_normals[i] = normals[loop.vertex_index]

        mesh.normals_split_custom_set(custom_normals)

        pass_index = 0

        # set vertex color
        vertex_color_layer = None
        if group.mogp.flags & MOGPFlags.HasVertexColor:
            flag_set = nobj.wow_wmo_group.flags
            flag_set.add('0')
            nobj.wow_wmo_group.flags = flag_set
            vertex_color_layer = mesh.color_attributes.new(name="Col", type='BYTE_COLOR', domain='POINT')
            mesh.color_attributes.new(name="Lightmap", type='BYTE_COLOR', domain='POINT')

            pass_index |= BlenderWMOObjectRenderFlags.HasVertexColor
            pass_index |= BlenderWMOObjectRenderFlags.HasLightmap

        blendmap = None
        if group.mogp.flags & MOGPFlags.HasTwoMOCV:
            blendmap = mesh.color_attributes.new(name="Blendmap", type='BYTE_COLOR', domain='POINT')

            pass_index |= BlenderWMOObjectRenderFlags.HasBlendmap

        # set uv
        mesh.uv_layers.new(name="UVMap")
        uv_layer1 = mesh.uv_layers[0]

        for i, uv_loop in enumerate(uv_layer1.data):
            uv = tex_coords[mesh.loops[i].vertex_index]
            uv_layer1.data[i].uv = (uv[0], 1 - uv[1])

        if group.mogp.flags & MOGPFlags.HasTwoMOTV:
            uv2 = mesh.uv_layers.new(name="UVMap.001")
            nobj.wow_wmo_vertex_info.second_uv = uv2.name
            uv_layer2 = mesh.uv_layers[1]

            for i, uv_loop in enumerate(uv_layer2.data):
                uv = group.motv2.tex_coords[mesh.loops[i].vertex_index]
                uv_loop.uv = (uv[0], 1 - uv[1])

        # map wmo material ID to index in mesh materials
        material_indices = {}
        material_viewport_textures = {}

        # create batch vertex groups

        batch_map_a = None
        batch_map_b = None

        if group.mogp.n_batches_a != 0:
            batch_map_a = mesh.color_attributes.new(name="BatchmapTrans", type='BYTE_COLOR', domain='POINT')
            pass_index |= BlenderWMOObjectRenderFlags.HasBatchA

        if group.mogp.n_batches_b != 0:
            batch_map_b = mesh.color_attributes.new(name="BatchmapInt", type='BYTE_COLOR', domain='POINT')
            pass_index |= BlenderWMOObjectRenderFlags.HasBatchB

        # nobj.wow_wmo_vertex_info.batch_map = batch_map.name

        batch_material_map = {}

        batch_a_range = range(0, group.moba.batches[group.mogp.n_batches_a - 1].last_vertex + 1
        if group.mogp.n_batches_a else 0)

        batch_b_range = range(len(batch_a_range) - 1,
                              group.moba.batches[group.mogp.n_batches_a + group.mogp.n_batches_b - 1].last_vertex + 1
                              if group.mogp.n_batches_b else len(batch_a_range) - 1)

        # add materials
        for i, batch in enumerate(group.moba.batches):

            material = self.wmo_scene.bl_materials[group.moba.batches[i].material_id]

            mat_index_local = material_indices.get(batch.material_id)

            if mat_index_local is None:
                mat_id = len(mesh.materials)
                material_indices[batch.material_id] = mat_id

                image = self.get_material_viewport_image(material)
                material_viewport_textures[mat_id] = image
                mesh.materials.append(material)
                mat_index_local = mat_id

            for poly in mesh.polygons[batch.start_triangle // 3: (batch.start_triangle + batch.n_triangles) // 3]:

                poly.material_index = mat_index_local

            batch_material_map[(batch.start_triangle // 3,
                                (batch.start_triangle + group.moba.batches[i].n_triangles) // 3)] = batch.material_id

        # set layer data
        for vertex_index, vertex in enumerate(mesh.vertices):

            if vertex_color_layer is not None:

                mesh.color_attributes['Col'].data[vertex_index].color = (
                    linear(group.mocv.vert_colors[vertex_index][2] / 255),
                    linear(group.mocv.vert_colors[vertex_index][1] / 255),
                    linear(group.mocv.vert_colors[vertex_index][0] / 255),
                    1.0
                )

                mesh.color_attributes['Lightmap'].data[vertex_index].color = (
                    linear(group.mocv.vert_colors[vertex_index][3] / 255),
                    linear(group.mocv.vert_colors[vertex_index][3] / 255),
                    linear(group.mocv.vert_colors[vertex_index][3] / 255),
                    1.0
                )

            if blendmap is not None:
                mocv_layer = group.mocv2 if group.mogp.flags & MOGPFlags.HasVertexColor else group.mocv
                mesh.color_attributes['Blendmap'].data[vertex_index].color = (
                    linear(mocv_layer.vert_colors[vertex_index][3] / 255),
                    linear(mocv_layer.vert_colors[vertex_index][3] / 255),
                    linear(mocv_layer.vert_colors[vertex_index][3] / 255),
                    1.0
                )

            if batch_map_a:
                mesh.color_attributes['BatchmapTrans'].data[vertex_index].color = (
                    (1, 1, 1, 1) if vertex_index in batch_a_range else (0, 0, 0, 0)
                )

            if batch_map_b:
                mesh.color_attributes['BatchmapInt'].data[vertex_index].color = (
                    (1, 1, 1, 1) if vertex_index in batch_b_range else (0, 0, 0, 0)
                )
        '''
        # set faces material
        for i in range(len(mesh.polygons)):
            mat_id = group.mopy.triangle_materials[i].material_id
 
            mesh.polygons[i].material_index = material_indices[mat_id]
 
            # set texture displayed in viewport
            img = material_viewport_textures[material_indices[mat_id]]
            if img is not None:
                uv1.data[i].image = img
 
        '''

        # add collision vertex group
        collision_indices = self.get_collision_indices()

        if collision_indices:
            collision_vg = nobj.vertex_groups.new(name="Collision")
            collision_vg.add(collision_indices, 1.0, 'ADD')
            nobj.wow_wmo_vertex_info.vertex_group = collision_vg.name

        #render BSP bounding boxes for debugging only
        render_BSP_nodes = False
        if render_BSP_nodes:
            self.create_BSP_render(0, group.mogp.bounding_box_corner1, group.mogp.bounding_box_corner2, 0) # group BB

        # add WMO group properties
        nobj.wow_wmo_group.export_order = export_order
        nobj.wow_wmo_group.description = self.wmo_scene.wmo.mogn.get_string(group.mogp.desc_group_name_ofs)
        nobj.wow_wmo_group.group_dbc_id = int(group.mogp.group_id)

        nobj.wow_wmo_group.fog1 = self.wmo_scene.bl_fogs[group.mogp.fog_indices[0]]
        nobj.wow_wmo_group.fog2 = self.wmo_scene.bl_fogs[group.mogp.fog_indices[1]]
        nobj.wow_wmo_group.fog3 = self.wmo_scene.bl_fogs[group.mogp.fog_indices[2]]
        nobj.wow_wmo_group.fog4 = self.wmo_scene.bl_fogs[group.mogp.fog_indices[3]]

        if group.mogp.flags & MOGPFlags.Indoor:
            pass_index |= BlenderWMOObjectRenderFlags.IsIndoor
        else:
            pass_index |= BlenderWMOObjectRenderFlags.IsOutdoor

        flag_set = nobj.wow_wmo_group.flags

        if group.mogp.flags & MOGPFlags.DoNotUseLocalLighting:
            flag_set.add('1')
            pass_index |= BlenderWMOObjectRenderFlags.NoLocalLight

        if group.mogp.flags & MOGPFlags.AlwaysDraw:
            flag_set.add('2')

        if group.mogp.flags & MOGPFlags.IsMountAllowed:
            flag_set.add('3')

        if group.mogp.flags & MOGPFlags.HasSkybox:
            flag_set.add('4')
        
        if group.mogp.flags & MOGPFlags.UseExteriorSky:
            flag_set.add('5')

        nobj.wow_wmo_group.flags = flag_set
        nobj.pass_index = pass_index

        # move objects to collection

        wmo_outdoor_collection = get_wmo_collection(scn, SpecialCollections.Outdoor)
        wmo_indoor_collection = get_wmo_collection(scn, SpecialCollections.Indoor)

        if group.mogp.flags & MOGPFlags.Outdoor:
            wmo_outdoor_collection.objects.link(nobj)

        else:
            wmo_indoor_collection.objects.link(nobj)
            if not group.mogp.flags & MOGPFlags.Indoor:
                print('\nWARNING: Group ' + self.name + 'does not have an interior or exterior flag. Most likely an older alpha/beta model, importing as indoor.')


        self.bl_object = nobj

        # remove collision faces from mesh
        if collision_face_ids:

            bm_col = bmesh.new()

            bm = bmesh.new()
            bm.from_mesh(mesh)

            bm.faces.ensure_lookup_table()
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm_collision_faces = [bm.faces[i] for i in collision_face_ids]

            # create collision mesh
            vert_map = {}
            for face in bm_collision_faces:
                face_verts = [None, None, None]
                for j, vert in enumerate(face.verts):

                    n_vert = vert_map.get(vert.index)
                    if not n_vert:
                        n_vert = bm_col.verts.new(vert.co)
                        vert_map[vert.index] = n_vert

                    face_verts[j] = n_vert

                try:
                    bm_col.faces.new(face_verts)
                except ValueError:
                    pass
                    # print('\nWARNING: Duplicated face was removed from collision geometry.')

            c_mesh = bpy.data.meshes.new(name=self.name + '_Collision')
            bm_col.to_mesh(c_mesh)
            bm_col.free()

            # remove collision faces from original mesh
            bmesh.ops.delete(bm, geom=bm_collision_faces, context='FACES')
            bm.to_mesh(mesh)
            mesh.update()
            bpy.context.view_layer.update()
            bm.free()

            c_obj = bpy.data.objects.new(c_mesh.name, c_mesh)
            nobj.wow_wmo_group.collision_mesh = c_obj

            collision_collection = get_wmo_collection(scn, SpecialCollections.Collision)
            collision_collection.objects.link(c_obj)

        # assign ghost material for visual only
        if nobj.wow_wmo_group.collision_mesh:
            mat = bpy.data.materials.get("WowMaterial_ghost")
            nobj.wow_wmo_group.collision_mesh.data.materials.append(mat)

        # handle liquids
        if group.mogp.flags & MOGPFlags.HasWater:
            self.load_liquids(nobj.name, nobj.location)

        else:
            # getting Liquid Type ID

            if self.wmo_scene.wmo.mohd.flags & MOHDFlags.UseLiquidTypeDBCId:
                real_liquid_type = group.mogp.liquid_type
            else:
                real_liquid_type = self.from_wmo_liquid_type(group.mogp.liquid_type)
                real_liquid_type = 0 if real_liquid_type == 17 else real_liquid_type

            nobj.wow_wmo_group.liquid_type = str(real_liquid_type)

    @staticmethod
    def try_calculate_direction(portal_obj: bpy.types.Object
                                , group_obj: bpy.types.Object
                                , bound_relation: PortalRelation
                                , triangulated: bool = False) -> int:

        portal_mesh = portal_obj.data
        portal_polygons = portal_mesh.polygons
        mesh = group_obj.data
        ray_cast_bias = 0.001  # sys.float_info.epsilon does not work here, ray cast origin returns itself.

        if triangulated:
            portal_mesh.calc_loop_triangles()
            portal_polygons = portal_mesh.loop_triangles

        group_matrix_inv = group_obj.matrix_world.inverted()
        portal_matrix_normal = portal_obj.matrix_world.to_3x3().transposed().inverted()
        group_matrix_normal_inv = portal_obj.matrix_world.to_3x3().transposed()

        for portal_poly in portal_polygons:

            portal_normal = (portal_matrix_normal @ portal_poly.normal).normalized()
            portal_center = portal_obj.matrix_world @ mathutils.Vector(portal_poly.center)

            portal_normal_gs = (group_matrix_normal_inv @ portal_normal).normalized()
            portal_center_gs = group_matrix_inv @ portal_center

            # cast a ray into object space to see if any face was hit
            # using this hack we will avoid expensive calculations for many indoor-indoor relations.
            # note: this whole approach does not cover the situations of convoluted cases where the geometry of the
            # group intersects the portal plane from both sides (e.g. Ironforge big hallway portals.
            # For now the users will have to resolve the direction of such portals manually through GUI. TODO: fix?

            # first we cast alongside the normal vector

            ray_cast_direction = portal_normal_gs
            ray_cast_origin = portal_center_gs + ray_cast_direction * ray_cast_bias
            result, _, normal, index = group_obj.ray_cast(ray_cast_origin, ray_cast_direction)

            if result and normal.dot(ray_cast_direction) < 0:
                if bound_relation and bound_relation.side == 0:
                    bound_relation.side = -1

                return 1

            # next we cast in the oppositve direction
            ray_cast_direction = portal_normal_gs.copy()
            ray_cast_direction.negate()
            ray_cast_origin = portal_center_gs - ray_cast_direction * ray_cast_bias
            result, _, normal, index = group_obj.ray_cast(ray_cast_origin, ray_cast_direction)

            if result and normal.dot(ray_cast_direction) < 0:
                if bound_relation and bound_relation.side == 0:
                    bound_relation.side = 1

                return -1

            ray_cast_origin = portal_center_gs

            for mesh_poly in mesh.polygons:
                is_in_portal_direction = portal_normal.dot((group_obj.matrix_world
                                                            @ mesh_poly.center) - portal_center) > 0.0
                mesh_poly_normal = mathutils.Vector(mesh_poly.normal)
                ray_cast_direction = mesh_poly.center - ray_cast_origin
                ray_cast_direction.normalize()

                # skip back faces
                if mesh_poly_normal.dot(ray_cast_direction) >= 0.0:
                    continue

                result, _, _, index = group_obj.ray_cast(ray_cast_origin, ray_cast_direction)

                if result and mesh_poly.index == index:

                    # here we need to do a slower-space ray cast to determine if view is not obstructed by another
                    # group. We expect to hit the same group in this pass. If not, view is considered obstructed.
                    # It is okay though to hit collision, doodad or liquid of the same group. TODO: doodads

                    depsgraph = bpy.context.evaluated_depsgraph_get()
                    scene_ray_cast_origin = (portal_center + portal_normal * ray_cast_bias) \
                        if is_in_portal_direction else (portal_center - portal_normal * ray_cast_bias)

                    result, _, _, _, obj, _ = bpy.context.scene.ray_cast(depsgraph, scene_ray_cast_origin,
                          (group_obj.matrix_world @ mesh_poly.center) - scene_ray_cast_origin)

                    allowed_names = [
                        group_obj.original.name
                        , group_obj.original.wow_wmo_group.collision_mesh.name
                        if group_obj.original.wow_wmo_group.collision_mesh else None
                        , group_obj.original.wow_wmo_group.liquid_mesh.name
                        if group_obj.original.wow_wmo_group.liquid_mesh else None
                     ]

                    if not result or obj.name not in allowed_names:
                        # if obj: print(f"Ray casted from {portal_obj.name} to {group_obj.name}, but got {obj.name}")
                        continue

                    portal_dir = 1 if is_in_portal_direction else -1

                    # fill in the other relation if it is a second attempt from the other side
                    if bound_relation and bound_relation.side == 0:
                        bound_relation.side = -portal_dir

                    return portal_dir

        return 0

    def get_portal_direction(self
                             , portal_obj: bpy.types.Object
                             , group_obj: bpy.types.Object) -> int:
        """ Get the direction of MOPR portal relation given a portal object and a target group """

        # check if this portal was already processed
        bound_relation_side = None
        bound_relation = None
        for relation in self.wmo_scene.wmo.mopr.relations:
            if relation.portal_index == portal_obj.original.wow_wmo_portal.portal_id:
                bound_relation_side = relation.side
                bound_relation = relation

        if bound_relation_side:
            return -bound_relation_side

        if portal_obj.original.wow_wmo_portal.algorithm != '0':
            return 1 if portal_obj.original.wow_wmo_portal.algorithm == '1' else -1

        result = BlenderWMOSceneGroup.try_calculate_direction(portal_obj, group_obj, bound_relation)

        if result:
            return result

        # if the previous attempt failed, we try to calculate the direction on a triangulated portal
        # for that we use the loop tris to avoid overhead
        result = BlenderWMOSceneGroup.try_calculate_direction(portal_obj, group_obj, bound_relation, True)

        if result:
            return result

        if bound_relation_side is not None:
            print("\nFailed to calculate direction from the both sides for portal \"{}\" "
                  "You may consider setting up the direction manually.".format(portal_obj.name))

        return 0

    def save_liquid(self, obj: bpy.types.Object) -> LiquidExportParams:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        group = self.wmo_group
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.data

        params = LiquidExportParams()
        params.liquid_mesh_pointer = mesh.as_pointer()
        params.liquid_mesh_matrix_world = obj_eval.matrix_world
        params.x_tiles = round(obj_eval.dimensions[0] / 4.1666625)
        params.y_tiles = round(obj_eval.dimensions[1] / 4.1666625)

        group.mogp.flags |= MOGPFlags.HasWater

        types_1 = {3, 7, 11, 15, 19, 121, 141}  # lava
        types_2 = {4, 8, 12, 20, 21}  # slime

        diff_color = (int(obj.wow_wmo_liquid.color[2] * 255),
                      int(obj.wow_wmo_liquid.color[1] * 255),
                      int(obj.wow_wmo_liquid.color[0] * 255),
                      int(obj.wow_wmo_liquid.color[3] * 255)
                      )

        def create_default_liquid_mat():
            texture1 = "DUNGEONS\\TEXTURES\\STORMWIND\\GRAY12.BLP"

            if group.mogp.liquid_type in types_1:
                texture1 = "DUNGEONS\\TEXTURES\\METAL\\BM_BRSPIRE_CATWALK01.BLP"

            elif group.mogp.liquid_type in types_2:
                texture1 = "DUNGEONS\\TEXTURES\\FLOOR\\JLO_UNDEADZIGG_SLIMEFLOOR.BLP"

            material_id = self.wmo_scene.wmo.add_material(texture1, diff_color=diff_color)

            return material_id

        if len(mesh.materials) > 0:
            # if mesh.materials[0].wow_wmo_material.enabled:
            #     # material_id = bpy.context.scene.wow_wmo_root_elements.materials.find(
            #     #     mesh.materials[0].name)
            # else:
            #     material_id = create_default_liquid_mat()
            # TODO
            mat_found = False
            # for id, material in self.bl_materials.items():
            #     if material.name == mesh.materials[0].name:
            #         material_id = id
            #         mat_found = True
            #         break
            # if not mat_found:
            material_id = create_default_liquid_mat()
        else:
            material_id = create_default_liquid_mat()

        params.mat_id = material_id
        params.is_water = not (group.mogp.liquid_type in types_1 or group.mogp.liquid_type in types_2)

        return params

    def create_batching_parameters(self) -> Tuple[bpy.types.Mesh, WMOGeometryBatcherMeshParams]:
        """ Prepare the WoW WMO group proxy mesh for export.
            Mesh is returned in order to keep its lifetime beyond the function scope.
        """

        obj = self.bl_object
        depsgraph = bpy.context.evaluated_depsgraph_get()

        obj_eval = obj.evaluated_get(depsgraph)

        group = self.wmo_group
        scene = bpy.context.scene

        mesh = obj_eval.data

        # extremely important for accessing correct data in C++
        mesh.calc_loop_triangles()
        mesh.calc_normals()

        if mesh.has_custom_normals:
            mesh.calc_normals_split()

        # handle separate collision
        col_obj_eval = None
        col_mesh_eval = None
        if obj.wow_wmo_group.collision_mesh:
            col_obj_eval = obj.wow_wmo_group.collision_mesh.evaluated_get(depsgraph)
            col_mesh_eval = col_obj_eval.data

            # extremely important for accessing correct data in C++
            col_mesh_eval.calc_loop_triangles()
            col_mesh_eval.calc_normals()

            if col_mesh_eval.has_custom_normals:
                mesh.calc_normals_split()

        if 'UVMap' not in mesh.uv_layers:
            raise Exception('\nThe group \"{}\" must have a UV map layer named UVMap.'.format(obj.name))

        self.has_blending = 'UVMap.001' in mesh.uv_layers and 'Blendmap' in mesh.color_attributes
        if self.has_blending:
            group.add_blendmap_chunks()

        use_vertex_color = '0' in obj.wow_wmo_group.flags \
                            or (WoWWMOGroup.is_indoor(obj) and '1' not in obj.wow_wmo_group.flags) # 7 = indoor, 1 = nolocallightning

        vg_collision_index = -1

        if obj.wow_wmo_vertex_info.vertex_group:
            obj_collision_vg = obj.vertex_groups.get(obj.wow_wmo_vertex_info.vertex_group)

            if obj_collision_vg:
                vg_collision_index = obj_collision_vg.index

        material_mapping = []

        for material in mesh.materials:
            # mat_id = scene.wow_wmo_root_elements.materials.find(material.name)

            mat_id = -1
            for id, bl_mat in self.wmo_scene.bl_materials.items():
                if material.name == bl_mat.name:
                    mat_id = id
                    break

            if mat_id < 0:
                raise Exception('Error: Assigned material \"{}\" is not registered as WoW Material.'.format(
                    material.name))

            material_mapping.append(mat_id)

        self.wmo_group.mogp.liquid_type = int(obj.wow_wmo_group.liquid_type)
        liquid_params = self.save_liquid(obj.wow_wmo_group.liquid_mesh) if obj.wow_wmo_group.liquid_mesh else None

        return mesh, WMOGeometryBatcherMeshParams(mesh.as_pointer()
                                                  , obj_eval.matrix_world
                                                  , col_mesh_eval.as_pointer() if col_mesh_eval else 0
                                                  , col_obj_eval.matrix_world if col_obj_eval else None
                                                  , False  # TODO: use large material ID
                                                  , use_vertex_color
                                                  , mesh.has_custom_normals
                                                  , vg_collision_index
                                                  , obj.wow_wmo_vertex_info.node_size
                                                  , material_mapping
                                                  , liquid_params)

    def save(self, batcher: CWMOGeometryBatcher, group_index: int):
        """ Save WoW WMO group data for future export """
        obj = self.bl_object

        self.wmo_group.mver.version = 17
        self.wmo_group.movt.from_bytes(batcher.vertices(group_index))
        self.wmo_group.monr.from_bytes(batcher.normals(group_index))
        self.wmo_group.moba.from_bytes(batcher.batches(group_index))
        self.wmo_group.movi.from_bytes(batcher.triangle_indices(group_index))
        self.wmo_group.mopy.from_bytes(batcher.triangle_materials(group_index))
        self.wmo_group.motv.from_bytes(batcher.tex_coords(group_index))
        self.wmo_group.mocv.from_bytes(batcher.vertex_colors(group_index))
        self.wmo_group.mobn.from_bytes(batcher.bsp_nodes(group_index))
        self.wmo_group.mobr.from_bytes(batcher.bsp_faces(group_index))

        if self.has_blending:
            self.wmo_group.motv2.from_bytes(batcher.tex_coords2(group_index))
            self.wmo_group.mocv2.from_bytes(batcher.vertex_colors2(group_index))

        # save liquid
        if obj.wow_wmo_group.liquid_mesh:
            self.wmo_group.mliq.from_bytes(batcher.liquid(group_index))
        else:
            self.wmo_group.mliq = None
            # self.wmo_group.mogp.flags |= MOGPFlags.IsNotOcean  # TODO: check if this is necessary
            wow_version = int(bpy.context.scene.wow_scene.version)
            if wow_version >= WoWVersions.WOTLK:
                # this flag causes wmo groups to fill with liquid if liquid type is not 0.
                self.wmo_group.root.mohd.flags |= MOHDFlags.UseLiquidTypeDBCId
            else:
                # Classic / vanilla (1.12): there is no UseLiquidTypeDBCId (MOHD 0x4) flag, so the
                # client reads mogp.liquid_type directly and treats 0 as REAL water -- a group with
                # no liquid would flood and make the player swim (even in a desert). 15 is Blizzard's
                # "no liquid" sentinel; every stock dry WMO (GuardTower / GuildHouse / Player's House)
                # uses 15 on its groups. Force it so no-liquid Classic groups never spawn water.
                self.wmo_group.mogp.liquid_type = 15

        # bsp = BSPTree()
        # bsp.generate_bsp(self.wmo_group.movt.vertices, self.wmo_group.movi.indices, obj.wow_wmo_vertex_info.node_size)

        # write header
        bb = batcher.bounding_box(group_index)
        self.wmo_group.mogp.bounding_box_corner1 = bb.min
        self.wmo_group.mogp.bounding_box_corner2 = bb.max

        '''
        if len(group.movt.vertices) > 65535:
            raise Exception('\nThe group \"{}\" has too many vertices : {} (max allowed = 65535)'.format(
                obj.name, str(len(group.movt.vertices))))
                
        '''

        batch_count_info = batcher.batch_count_info(group_index)
        self.wmo_group.mogp.n_batches_a = batch_count_info.n_batches_trans
        self.wmo_group.mogp.n_batches_b = batch_count_info.n_batches_int
        self.wmo_group.mogp.n_batches_c = batch_count_info.n_batches_ext

        self.wmo_group.mogp.flags |= MOGPFlags.HasCollision  # /!\ MUST HAVE 0x1 FLAG ELSE THE GAME CRASH !
        if '0' in obj.wow_wmo_group.flags:
            self.wmo_group.mogp.flags |= MOGPFlags.HasVertexColor
        if '4' in obj.wow_wmo_group.flags:
            self.wmo_group.mogp.flags |= MOGPFlags.HasSkybox
        if '1' in obj.wow_wmo_group.flags:
            self.wmo_group.mogp.flags |= MOGPFlags.DoNotUseLocalLighting
        if '2' in obj.wow_wmo_group.flags:
            self.wmo_group.mogp.flags |= MOGPFlags.AlwaysDraw
        if '3' in obj.wow_wmo_group.flags:
            self.wmo_group.mogp.flags |= MOGPFlags.IsMountAllowed
        if '5' in obj.wow_wmo_group.flags:
            self.wmo_group.mogp.flags |= MOGPFlags.UseExteriorSky

        if WoWWMOGroup.is_outdoor(obj):
            self.wmo_group.mogp.flags |= MOGPFlags.Outdoor
        elif WoWWMOGroup.is_indoor(obj):
            self.wmo_group.mogp.flags |= MOGPFlags.Indoor
        else:
            raise Exception('\nThe group \"{}\" is not in a valid outdoor or indoor collection'.format(obj.name))

        # Classic (1.12): the client's portal flood EARLY-OUTS on ALWAYSDRAW (0x10000)
        # groups — an interior with this flag stays sealed even WITH portals, and it
        # never seeds/propagates visibility. Verified by disassembly of the 5875 client.
        # Strip it on Classic exports (it is a legitimate flag on later clients).
        if WoWVersionManager().client_version < WoWVersions.WOTLK \
                and (self.wmo_group.mogp.flags & MOGPFlags.AlwaysDraw):
            self.wmo_group.mogp.flags &= ~MOGPFlags.AlwaysDraw
            ClassicLint.warn("[1.12] Group '%s': 'Always draw' flag stripped — on 1.12 it disables "
                            "portal traversal for the group (seals interiors even with portals)."
                            % obj.name)

        if self.has_blending:
            self.wmo_group.mogp.flags |= MOGPFlags.HasTwoMOCV
            self.wmo_group.mogp.flags |= MOGPFlags.HasTwoMOTV

        has_lights = False

        fogs = (obj.wow_wmo_group.fog1,
                obj.wow_wmo_group.fog2,
                obj.wow_wmo_group.fog3,
                obj.wow_wmo_group.fog4)

        # set fog references
        self.wmo_group.mogp.fog_indices = (fogs[0].wow_wmo_fog.fog_id if fogs[0] else 0,
                                  fogs[1].wow_wmo_fog.fog_id if fogs[1] else 0,
                                  fogs[2].wow_wmo_fog.fog_id if fogs[2] else 0,
                                  fogs[3].wow_wmo_fog.fog_id if fogs[3] else 0)
        # save lamps
        lamps = self.lights_relations
        if lamps:
            has_lights = True
            for lamp_id in lamps:
                self.wmo_group.molr.light_refs.append(lamp_id)

        self.wmo_group.mogp.group_id = int(obj.wow_wmo_group.group_dbc_id)
        group_info = self.wmo_scene.add_group_info(self.wmo_group.mogp.flags,
                                                      [self.wmo_group.mogp.bounding_box_corner1
                                                      , self.wmo_group.mogp.bounding_box_corner2],
                                                  obj.name,
                                                  obj.wow_wmo_group.description)

        self.wmo_group.mogp.group_name_ofs = group_info[0]
        self.wmo_group.mogp.desc_group_name_ofs = group_info[1]

        if self.doodads_relations:
            for doodad in self.doodads_relations:
                self.wmo_group.modr.doodad_refs.append(doodad)
            self.wmo_group.mogp.flags |= MOGPFlags.HasDoodads
        else:
            self.wmo_group.modr = None

        if '0' not in obj.wow_wmo_group.flags: # HasVertexColor
            
            if WoWWMOGroup.is_indoor(obj): # Indoor # TODO : get from collection type
                if '1' in obj.wow_wmo_group.flags \
                        and not len(obj.data.vertex_colors): # DoNotUseLocalLighting
                    self.wmo_group.mocv = None
                else:
                    self.wmo_group.mogp.flags |= MOGPFlags.HasVertexColor
            else:
                self.wmo_group.mocv = None

        if not has_lights:
            self.wmo_group.molr = None
        else:
            self.wmo_group.mogp.flags |= MOGPFlags.HasLight

        # write second MOTV and MOCV
        if not self.has_blending:
            self.wmo_group.motv2 = None
            self.wmo_group.mocv2 = None



