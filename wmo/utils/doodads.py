import io
import os
import traceback

import bpy

from ...utils.misc import load_game_data
from ..utils.materials import load_texture
from ...utils.node_builder import NodeTreeBuilder
from ...pywowlib.io_utils.types import *
from ...ui.preferences import get_project_preferences


# This file is implementing basic M2 geometry parsing in prodedural style for the sake of performance.
class Submesh:
    __slots__ = (
        "start_vertex",
        "n_vertices",
        "start_triangle",
        "n_triangles",
        "texture_id",
        "blend_mode"
    )

    def __init__(self, f):
        skip(f, 4)
        self.start_vertex = uint16.read(f)
        self.n_vertices = uint16.read(f)
        self.start_triangle = uint16.read(f)
        self.n_triangles = uint16.read(f)
        self.texture_id = None
        self.blend_mode = 0

        skip(f, 36)


def skip(f, n_bytes):
    f.seek(f.tell() + n_bytes)


def import_doodad_model(asset_dir: str, filepath: str, placeholder: bool) -> bpy.types.Object:
    """Import World of Warcraft M2 model to scene."""

    game_data = load_game_data()

    # Everwood Classic fork: 1.12 / TBC doodads (M2 < v264) keep their skin profile INSIDE the .m2 and use
    # different header offsets - the WotLK-only parser below would fail on every one of them.
    if placeholder and not game_data.has_file('Spells\\Errorcube.m2')[0]:
        return _simple_placeholder(filepath)
    classic = None if placeholder else _read_classic_doodad(game_data, filepath)
    if classic is not None:
        m2_name, vertices, normals, uv_coords, texture_paths, texture_lookup_table, indices, triangles, submeshes = classic
        n_triangles = len(triangles)
    else:

        if placeholder:
            m2_path = os.path.splitext('Spells\\Errorcube.m2')[0] + ".m2"
            skin_path = os.path.splitext('Spells\\Errorcube.m2')[0] + "00.skin"
            real_m2_path = os.path.splitext(filepath)[0] + ".m2"
            m2_name = os.path.basename(os.path.splitext(real_m2_path)[0])
        else:
            m2_path = os.path.splitext(filepath)[0] + ".m2"
            skin_path = os.path.splitext(filepath)[0] + "00.skin"
            m2_name = os.path.basename(os.path.splitext(m2_path)[0])

        try:
            file, _ = game_data.read_file(m2_path)
            m2_file = io.BytesIO(file)
        except KeyError:
            raise FileNotFoundError("\nModel <<{}>> not found in WoW file system.".format(filepath))

        try:
            file, _ = game_data.read_file(skin_path)
            skin_file = io.BytesIO(file)
        except KeyError:
            raise FileNotFoundError("\nSkin file for model <<{}>> not found in WoW file system.".format(filepath))

        ###### M2 file parsing ######

        f = m2_file
        magic = f.read(4).decode("utf-8")
        while magic not in ('MD20', 'MD21'):
            skip(f, uint32.read(f))
            magic = f.read(4).decode("utf-8")

        # read flags
        f.seek(16)
        global_flags = uint32.read(f)

        # read vertex positions
        f.seek(60)
        n_vertices = uint32.read(f)
        f.seek(uint32.read(f))

        vertices = [(0.0, 0.0, 0.0)] * n_vertices
        normals = [(0.0, 0.0, 0.0)] * n_vertices
        uv_coords = [(0.0, 0.0)] * n_vertices

        # if n_vertices == 0:
        #     addon_dir = os.path.dirname(__file__)
        #     placeholder_blend_path = os.path.join(addon_dir, "utils", "placeholders", "placeholder.blend")
        #     directory = placeholder_blend_path + "\\Object\\"
        #     bpy.ops.wm.append(filename='placeholder', directory=directory)
        #     return import_doodad_model(asset_dir, filepath, True)

        for i in range(n_vertices):
            vertices[i] = float32.read(f, 3)
            skip(f, 8)
            normals[i] = float32.read(f, 3)
            uv_coords[i] = float32.read(f, 2)
            skip(f, 8)

        # read render flags and blending modes
        f.seek(112)
        n_render_flags = uint32.read(f)
        f.seek(uint32.read(f))

        blend_modes = []  # skip render flags for now
        for _ in range(n_render_flags):
            skip(f, 2)
            blend_modes.append(uint16.read(f))

        # read texture lookup
        f.seek(128)
        n_tex_lookups = uint32.read(f)
        f.seek(uint32.read(f))
        texture_lookup_table = [uint16.read(f) for _ in range(n_tex_lookups)]

        # read texture names
        f.seek(80)
        n_textures = uint32.read(f)
        f.seek(uint32.read(f))

        texture_paths = []
        for _ in range(n_textures):
            skip(f, 8)
            len_tex = uint32.read(f)
            ofs_tex = uint32.read(f)

            if not len_tex:
                texture_paths.append(None)
                continue

            pos = f.tell()
            f.seek(ofs_tex)
            texture_paths.append(f.read(len_tex).decode('utf-8').rstrip('\0'))
            f.seek(pos)

        # read blend mode overrides
        if global_flags & 0x08:
            f.seek(304)
            n_blendmode_overrides = uint32.read(f)
            f.seek(uint32.read(f))

            blend_mode_overrides = []
            for _ in range(n_blendmode_overrides):
                blend_mode_overrides.append(uint16.read(f))

        ###### Skin ######

        f = skin_file
        padding = 0

        # indices
        try:
            magic = f.read(4).decode("utf-8")
        except UnicodeDecodeError:
            padding = 4
            f.seek(0)

        n_indices = uint32.read(f)
        f.seek(uint32.read(f))
        indices = unpack('{}H'.format(n_indices), f.read(2 * n_indices))

        # triangles
        f.seek(12 - padding)
        n_triangles = uint32.read(f) // 3
        f.seek(uint32.read(f))
        triangles = [(0, 0, 0)] * n_triangles
        for i in range(n_triangles):
            triangles[i] = unpack('HHH', f.read(6))

        # submeshes
        f.seek(28 - padding)
        n_submeshes = uint32.read(f)
        f.seek(uint32.read(f))
        submeshes = [Submesh(f) for _ in range(n_submeshes)]

        # texture units
        f.seek(36 - padding)
        n_tex_units = uint32.read(f)
        f.seek(uint32.read(f))
        for _ in range(n_tex_units):
            skip(f, 2)
            shader_id = uint16.read(f)
            submesh_id = uint16.read(f)

            if submeshes[submesh_id].texture_id is not None:
                skip(f, 18)
                continue

            skip(f, 4)
            render_flag_index = uint16.read(f)
            skip(f, 4)
            submeshes[submesh_id].texture_id = uint16.read(f)
            skip(f, 6)

            submeshes[submesh_id].blend_mode = blend_modes[render_flag_index]

            '''
            # determine blending mode
            if global_flags & 0x08 and shader_id < len(blend_mode_overrides):
                submeshes[submesh_id].blend_mode = blend_mode_overrides[shader_id]
            else:
                submeshes[submesh_id].blend_mode = blend_modes[render_flag_index]
            '''

    ###### Build blender object ######
    faces = [[0, 0, 0]] * n_triangles

    for i, tri in enumerate(triangles):
        face = []
        for index in tri:
            face.append(indices[index])

        faces[i] = face

    # create mesh
    mesh = bpy.data.meshes.new(m2_name)
    mesh.from_pydata(vertices, [], faces)

    for poly in mesh.polygons:
        poly.use_smooth = True

    # set normals
    custom_normals = [(0.0, 0.0, 0.0)] * len(mesh.loops)
    mesh.use_auto_smooth = True
    for i, loop in enumerate(mesh.loops):
        custom_normals[i] = normals[loop.vertex_index]

    mesh.normals_split_custom_set(custom_normals)

    # set uv
    uv_layer1 = mesh.uv_layers.new(name="UVMap")
    for i in range(len(uv_layer1.data)):
        uv = uv_coords[mesh.loops[i].vertex_index]
        uv_layer1.data[i].uv = (uv[0], 1 - uv[1])

    # unpack and convert textures
    game_data.extract_textures_as_png(asset_dir, texture_paths)

    def import_placeholder(addon_relative_path, placeholder_object_name):
        current_dir = os.path.dirname(__file__)
        base_dir = os.path.dirname(os.path.dirname(current_dir))
        blend_path = os.path.join(base_dir, addon_relative_path)

        directory = os.path.join(blend_path, "Object\\")

        try:
            bpy.ops.wm.append(filename=placeholder_object_name, directory=directory)

            #obj = bpy.ops.wm.append(filename=placeholder_object_name, directory=directory)
            if placeholder_object_name in bpy.data.objects:
                placeholder = bpy.data.objects.get(placeholder_object_name)
                nplaceholder = bpy.data.objects.new(m2_name, placeholder.data.copy())
                #placeholder_object_name.delete()
                #placeholder_duplicate = placeholder.copy()
                #placeholder_duplicate.data = placeholder.data.copy()
                bpy.data.objects.remove(placeholder, do_unlink=True)

            return nplaceholder
                
        except Exception as e:
            print(f"Failed to import placeholder: {e}")
            return None

    # create object
    if len(mesh.vertices) == 0 or placeholder:
        placeholder_object_name = 'Placeholder'
        addon_relative_path = 'utils\\placeholder\\placeholder.blend'
        nobj = import_placeholder(addon_relative_path, placeholder_object_name)
        nobj.wow_wmo_doodad.path = filepath
        nobj.wow_wmo_doodad.enabled = True
        image_name = "Placeholder"

        img = bpy.data.images.get('Placeholder_Texture')
        if not img:
            img = bpy.data.images.new(name=image_name, width=512, height=512, alpha=True, float_buffer=False)
            img.generated_type = 'UV_GRID'
        #img = bpy.data.images['Placeholder_Texture']
        
        mat = bpy.data.materials.get('Placeholder')
        if mat:
            nobj.data.materials.append(mat)

            for block in bpy.data.meshes:
                if block.users == 0:
                    bpy.data.meshes.remove(block)

            for block in bpy.data.materials:
                if block.users == 0:
                    bpy.data.materials.remove(block)

            for block in bpy.data.textures:
                if block.users == 0:
                    bpy.data.textures.remove(block)

            for block in bpy.data.images:
                if block.users == 0:
                    bpy.data.images.remove(block)

            return nobj
        else:
            mat = bpy.data.materials.new(name="Placeholder")

            mat.use_nodes = True

            node_tree = mat.node_tree
            tree_builder = NodeTreeBuilder(node_tree)

            tex_image = tree_builder.add_node('ShaderNodeTexImage', "Texture", 0, 0)
            tex_image.image = img

            doodad_color= tree_builder.add_node('ShaderNodeAttribute', "DoodadColor", 0, 2)

            mix_rgb = tree_builder.add_node('ShaderNodeMixRGB', "ApplyColor", 1, 1)
            mix_rgb.inputs['Fac'].default_value = 1.0
            mix_rgb.blend_type = 'MULTIPLY'

            transparent_bsdf = tree_builder.add_node('ShaderNodeBsdfTransparent', "Transparent", 2, 0)
            bsdf = tree_builder.add_node('ShaderNodeBsdfDiffuse', "Diffuse", 2, 2)

            mix_shader = tree_builder.add_node('ShaderNodeMixShader', "MixShader", 3, 0)
            mix_shader.inputs['Fac'].default_value = 1.0

            output = tree_builder.add_node('ShaderNodeOutputMaterial', "Output", 4, 1)

            mat.node_tree.links.new(tex_image.outputs['Color'], mix_rgb.inputs['Color1'])

            mat.node_tree.links.new(doodad_color.outputs['Color'], mix_rgb.inputs['Color2'])
            mat.node_tree.links.new(mix_rgb.outputs['Color'], bsdf.inputs['Color'])
            mat.node_tree.links.new(bsdf.outputs['BSDF'], mix_shader.inputs[2])
            mat.node_tree.links.new(transparent_bsdf.outputs['BSDF'], mix_shader.inputs[1])
            mat.node_tree.links.new(mix_shader.outputs['Shader'], output.inputs['Surface'])
            mat.blend_method = 'OPAQUE'

            nobj.data.materials.append(mat)

        return nobj
    
    else:
        nobj = bpy.data.objects.new(m2_name, mesh)
    
    nobj.wow_wmo_doodad.path = filepath
    nobj.wow_wmo_doodad.enabled = True

    # set textures
    texture_dir = get_project_preferences().cache_dir_path
    textures = {}
    for i, submesh in enumerate(submeshes):
        # tex_path = os.path.splitext(texture_paths[texture_lookup_table[submesh.texture_id]])[0] + '.png'
        tex_path = texture_paths[texture_lookup_table[submesh.texture_id]]

        # add support for unix filesystems
        if os.name != 'nt':
            tex_path = tex_path.replace('\\', '/')

        img = None

        # try:
        #     img = bpy.data.images.load(os.path.join(asset_dir, tex_path), check_existing=True)
        # except RuntimeError:
        #     traceback.print_exc()
        #     print("\nFailed to load texture: <<{}>>. File is missing or corrupted.".format(tex_path))

        try:
            img = load_texture(textures, tex_path, texture_dir)
        except:
            print("\nFailed to load texture: <<{}>>. File is missing or corrupted.".format(tex_path))
            pass

        if img:
            for j in range(submesh.start_triangle // 3, (submesh.start_triangle + submesh.n_triangles) // 3):
                mesh.polygons[j].material_index = i

        mat = bpy.data.materials.new(name="{}_{}".format(m2_name, i))

        mat.use_nodes = True

        node_tree = mat.node_tree
        tree_builder = NodeTreeBuilder(node_tree)

        tex_image = tree_builder.add_node('ShaderNodeTexImage', "Texture", 0, 0)
        tex_image.image = img

        # doodad_color = tree_builder.add_node('ShaderNodeRGB', "DoodadColor", 0, 2)

        doodad_color= tree_builder.add_node('ShaderNodeAttribute', "DoodadColor", 0, 2)

        mix_rgb = tree_builder.add_node('ShaderNodeMixRGB', "ApplyColor", 1, 1)
        mix_rgb.inputs['Fac'].default_value = 1.0
        mix_rgb.blend_type = 'MULTIPLY'

        transparent_bsdf = tree_builder.add_node('ShaderNodeBsdfTransparent', "Transparent", 2, 0)
        bsdf = tree_builder.add_node('ShaderNodeBsdfDiffuse', "Diffuse", 2, 2)

        mix_shader = tree_builder.add_node('ShaderNodeMixShader', "MixShader", 3, 0)
        mix_shader.inputs['Fac'].default_value = 1.0

        output = tree_builder.add_node('ShaderNodeOutputMaterial', "Output", 4, 1)

        mat.node_tree.links.new(tex_image.outputs['Color'], mix_rgb.inputs['Color1'])

        if submesh.blend_mode not in (0, 3):
            mat.node_tree.links.new(tex_image.outputs['Alpha'], mix_shader.inputs['Fac'])

        mat.node_tree.links.new(doodad_color.outputs['Color'], mix_rgb.inputs['Color2'])
        mat.node_tree.links.new(mix_rgb.outputs['Color'], bsdf.inputs['Color'])
        mat.node_tree.links.new(bsdf.outputs['BSDF'], mix_shader.inputs[2])
        mat.node_tree.links.new(transparent_bsdf.outputs['BSDF'], mix_shader.inputs[1])
        mat.node_tree.links.new(mix_shader.outputs['Shader'], output.inputs['Surface'])


        # configure blending
        if submesh.blend_mode == 0:
            mat.blend_method = 'OPAQUE'
        elif submesh.blend_mode == 1:
            mat.blend_method = 'CLIP'
            mat.alpha_threshold = 0.9
        else:
            mat.blend_method = 'BLEND'

        mesh.materials.append(mat)

    return nobj


def import_doodad(m2_path: str, cache_path: str) -> bpy.types.Object:

    try:
        obj = import_doodad_model(cache_path, m2_path, False)
    except:
        obj = import_doodad_model(cache_path, m2_path, True)
        traceback.print_exc()
        print("\nFailed to import model: <<{}>>. Placeholder is imported instead.".format(m2_path))

    obj.name = os.path.splitext(m2_path.split('\\')[-1])[0]

    return obj


# ------------------------------------------------------------------ Everwood Classic fork: 1.12 doodads

class _ClassicSubmesh:
    __slots__ = ("start_vertex", "n_vertices", "start_triangle", "n_triangles", "texture_id", "blend_mode")

    def __init__(self, start_triangle, n_triangles):
        self.start_vertex = self.n_vertices = 0
        self.start_triangle, self.n_triangles = start_triangle, n_triangles
        self.texture_id, self.blend_mode = None, 0


def _read_classic_doodad(game_data, filepath):
    """Geometry of a <= v263 M2 with its embedded skin profile 0, in the same shape the WotLK parser produces.
    Returns None for v264+ models (the original parser handles those)."""
    import struct as _st
    m2_path = os.path.splitext(filepath)[0] + ".m2"
    try:
        data, _ = game_data.read_file(m2_path)
    except KeyError:
        return None
    if not data or data[:4] != b'MD20' or _st.unpack_from('<I', data, 4)[0] >= 264:
        return None
    vanilla = _st.unpack_from('<I', data, 4)[0] <= 256
    arr = lambda off: _st.unpack_from('<II', data, off)

    n_v, o_v = arr(0x44)
    vertices, normals, uv_coords = [], [], []
    for i in range(n_v):
        b = o_v + 48 * i
        vertices.append(_st.unpack_from('<3f', data, b))
        normals.append(_st.unpack_from('<3f', data, b + 20))
        uv_coords.append(_st.unpack_from('<2f', data, b + 32))

    n_rf, o_rf = arr(0x84)
    blend_modes = [_st.unpack_from('<HH', data, o_rf + 4 * i)[1] for i in range(n_rf)]
    n_tl, o_tl = arr(0x94)
    texture_lookup_table = list(_st.unpack_from('<%dH' % n_tl, data, o_tl)) if n_tl else []
    n_tex, o_tex = arr(0x5C)
    texture_paths = []
    for i in range(n_tex):
        _t, _f, ln, of = _st.unpack_from('<IIII', data, o_tex + 16 * i)
        texture_paths.append(data[of:of + ln].split(b'\0', 1)[0].decode('latin-1') if ln else None)

    n_views, o_view = arr(0x4C)
    if not n_views:
        return None
    n_idx, o_idx = arr(o_view)
    n_tri, o_tri = arr(o_view + 8)
    n_sub, o_sub = arr(o_view + 24)
    n_bat, o_bat = arr(o_view + 32)
    indices = _st.unpack_from('<%dH' % n_idx, data, o_idx) if n_idx else ()
    flat = _st.unpack_from('<%dH' % n_tri, data, o_tri) if n_tri else ()
    triangles = [flat[i:i + 3] for i in range(0, len(flat) - len(flat) % 3, 3)]
    sub_size = 32 if vanilla else 48
    submeshes = []
    for i in range(n_sub):
        _geo, level, _vs, _vc, istart, icount = _st.unpack_from('<HHHHHH', data, o_sub + sub_size * i)
        submeshes.append(_ClassicSubmesh(istart + (level << 16), icount))
    for i in range(n_bat):
        _fl, _pr, _sh, sub, _geo, _col, mat_idx, _lay, _cnt, combo = _st.unpack_from('<BbHHHhHHHH', data, o_bat + 24 * i)
        if sub < len(submeshes) and submeshes[sub].texture_id is None:
            submeshes[sub].texture_id = combo
            submeshes[sub].blend_mode = blend_modes[mat_idx] if mat_idx < len(blend_modes) else 0
    for sm in submeshes:                       # a submesh without a batch still needs a valid texture slot
        if sm.texture_id is None:
            sm.texture_id = 0
    if not texture_lookup_table:
        texture_lookup_table = [0]
    if not texture_paths or all(t is None for t in texture_paths):
        texture_paths = texture_paths or [None]
    m2_name = os.path.basename(os.path.splitext(m2_path)[0])
    return m2_name, vertices, normals, uv_coords, texture_paths, texture_lookup_table, indices, triangles, submeshes


def _simple_placeholder(filepath):
    """1.12 has no Spells\\Errorcube.m2: a plain 1 m cube stands in for a doodad that cannot be read."""
    import bmesh
    name = os.path.basename(os.path.splitext(filepath)[0])
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.wow_wmo_doodad.path = filepath
    obj.wow_wmo_doodad.enabled = True
    return obj
